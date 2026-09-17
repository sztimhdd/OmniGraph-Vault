"""Deterministic, offline import of read-only legacy articles into VitaX candidates.

Scope (VX-012A): turn records from a *read-only* export of the legacy article
store into the candidate representation described in
``docs/work-items/vitax-refactor/VX-012A-legacy-first-record.md``.

The entry point is deliberately narrow:

* the legacy source is opened read-only through the existing
  :mod:`kb.data.article_query` contract; no runtime configuration, credential
  file, or network socket is required or touched;
* original title/body and translated title/body are kept as separate assets and
  a missing translation stays ``unknown`` instead of being regenerated;
* migration outcome, quality verdict, and publication permission are recorded
  independently, so a review downgrade never erases imported material;
* re-importing identical inputs is a no-op and never overwrites human edits;
* ``dry_run`` previews without creating the candidate directory.

There is no model client, HTTP client, or host configuration in this module.
``llm_requests``/``network_requests`` are reported as literal zeros, and the
entry point never accepts a model callable, so a caller cannot enable one by
configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

try:  # POSIX candidates; the lock falls back to an explicit lock file elsewhere.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platform
    fcntl = None  # type: ignore[assignment]

from kb.data.article_query import (
    ArticleRecord,
    _normalize_rss_update_time,
    _normalize_update_time,
    _row_get,
)
from vitax.knowledge import KnowledgeError, build


class LegacyImportError(ValueError):
    """The legacy export, the requested scope, or the candidate output is invalid."""


SCHEMA_VERSION = 1
MIGRATION_VERSION = 1
QUALITY_RULES_VERSION = 1
DEFAULT_BATCH_LIMIT = 20
MAX_BATCH_LIMIT = 50

#: A search returns a bounded, deterministically ordered page of the private
#: candidate. The cap stops one call from streaming the whole store; it is a
#: read bound only, never a publication decision.
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100

_SOURCES = {"wechat": "articles", "rss": "rss_articles"}
_RECORDS_NAME = "import-records.jsonl"
_MANIFEST_NAME = "import-manifest.json"
_FAILURES_NAME = "import-failures.jsonl"
_LOCK_NAME = ".import.lock"
_PUBLIC_DATABASE_NAME = "public-candidate.sqlite"
_PUBLIC_SCHEMA_VERSION = 1

#: A committed candidate is a ``generations/<id>/`` directory beside one
#: ``current`` pointer. The pointer is the single atomic commit marker: a reader
#: accepts a generation only when the pointer names it and its manifest matches,
#: so files from two different batches are never mixed.
_GENERATIONS_DIRNAME = "generations"
_CURRENT_NAME = "current"

#: POSIX permission bits are enforced only where they exist. On other platforms
#: nothing is fabricated: the directory is still created, but no mode is claimed.
_POSIX = os.name == "posix"
_OWNER_ONLY_DIRECTORY_MODE = 0o700
_OWNER_ONLY_FILE_MODE = 0o600
_GROUP_OR_OTHER_WRITE = 0o022
_GROUP_OR_OTHER_ANY = 0o077
_MAX_FAILURE_REASON = 300

#: Quality verdicts. ``passed`` means the asset is structurally usable; it is
#: not a statement about professional value, factual accuracy, or translation
#: faithfulness, which deterministic rules cannot certify.
QUALITY_STATUSES = ("passed", "needs-review", "excluded")
PUBLISHED_ONLY_SUBSET = (
    "publication.status=public and publication.safety_qualification.status=qualified "
    "and quality.status=passed and quality.deterministic_status=passed "
    "and translation.completeness=full"
)

_MOJIBAKE_MARKERS = ("\ufffd", "Ã©", "â€", "ï»¿")
_TRUNCATION_MARKERS = (
    "reading length limit",
    "paste the link",
    "全文请",
    "点击阅读全文",
    "内容已折叠",
)
_LOGIN_WALL_MARKERS = (
    "扫码登录",
    "登录后查看",
    "请先登录",
    "sign in to continue",
    "log in to continue",
)
_LINK_PATTERN = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HTML_TAG_PATTERN = re.compile(r"<[^>]{0,200}>")
_CODE_FENCE_PATTERN = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_URL_PATTERN = re.compile(r"https?://\S+")
_MARKUP_PATTERN = re.compile(r"[`*_>#|~\[\]()]")
_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
_WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]*")
_REQUIRED_COLUMNS = {"id", "title", "url", "body"}
_INGESTION_COLUMNS = {"source", "article_id", "status"}
#: ``ArticleRecord`` attributes that come only from optional legacy columns. The
#: ``kb.data.article_query`` ``_row_to_record_*`` helpers are versioned: a real
#: 2026-09 remote read ran against an older copy that ignored these columns and
#: whose row keys lacked ``translated_lang``, so translated rows were recorded as
#: ``none``. This module never calls those helpers; the selected row is the only
#: source for optional fields.
_OPTIONAL_RECORD_COLUMNS = (
    "content_hash",
    "lang",
    "title_translated",
    "body_translated",
    "translated_lang",
    "body_cleaned",
    "body_repositioned",
    "body_rewritten",
)
_OPTIONAL_COLUMNS = (
    *_OPTIONAL_RECORD_COLUMNS,
    "published_at",
    "fetched_at",
    "update_time",
    "image_count",
)
#: Guard against column-name drift: the overlay may only set fields that
#: ``ArticleRecord`` really declares.
_ARTICLE_RECORD_FIELDS = frozenset(field.name for field in fields(ArticleRecord))

#: Deterministic safety rule that must hold before a record may enter the public
#: projection. It is evaluated from preserved source text only, so an explicit
#: quality override can never widen it.
PUBLICATION_SAFETY_RULE = "full-translation+deterministic-quality"
_UNKNOWN_IMAGES_REASON = "legacy export carries no image binary or stable asset id"


@dataclass(frozen=True)
class LegacySourceRow:
    """One legacy row: the ``ArticleRecord`` contract plus adapter-available extras."""

    article: ArticleRecord
    image_count: int | None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value.strip() else None


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _split_paragraphs(text: str | None) -> list[str]:
    if not text:
        return []
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _strip_markup(value: str) -> str:
    """Drop HTML/Markdown/link scaffolding while keeping code, tables, captions."""
    text = _CODE_FENCE_PATTERN.sub(lambda match: match.group(1), value)
    text = _LINK_PATTERN.sub(lambda match: match.group(1), text)
    text = _HTML_TAG_PATTERN.sub(" ", text)
    text = _URL_PATTERN.sub(" ", text)
    return _MARKUP_PATTERN.sub(" ", text)


def _derived_text_metrics(text: str | None) -> dict[str, int]:
    derived = _strip_markup(text or "").strip()
    return {
        "effective_characters": len(derived),
        "cjk_characters": len(_CJK_PATTERN.findall(derived)),
        "latin_words": len(_WORD_PATTERN.findall(derived)),
    }


def _duplicate_paragraph_ratio(text: str | None) -> float:
    paragraphs = _split_paragraphs(text)
    if len(paragraphs) < 2:
        return 0.0
    unique = len(set(paragraphs))
    return round(1.0 - (unique / len(paragraphs)), 4)


def _marker_hit(value: str | None, markers: tuple[str, ...]) -> bool:
    lowered = (value or "").lower()
    return any(marker.lower() in lowered for marker in markers)


def assess_quality(
    original_text: str | None,
    translation_text: str | None,
    *,
    override: str | None = None,
) -> dict[str, object]:
    """Return an independent structural verdict with reason codes and metrics.

    Deterministic checks cannot certify professional value, factual accuracy, or
    translation faithfulness. Ambiguous signals therefore produce
    ``needs-review`` rather than exclusion or deletion.
    """
    if override is not None and override not in QUALITY_STATUSES:
        raise LegacyImportError(f"override must be one of {list(QUALITY_STATUSES)}")
    original_metrics = _derived_text_metrics(original_text)
    translation_metrics = _derived_text_metrics(translation_text)
    original_ratio = _duplicate_paragraph_ratio(original_text)
    translation_ratio = _duplicate_paragraph_ratio(translation_text)

    needs_review: list[str] = []
    if not _text(original_text).strip():
        needs_review.append("missing-original-body")
    elif original_metrics["effective_characters"] == 0:
        needs_review.append("empty-derived-original-text")
    if _text(translation_text).strip() and translation_metrics["effective_characters"] == 0:
        needs_review.append("empty-derived-translation-text")
    if not _text(translation_text).strip():
        needs_review.append("missing-full-translation")
    if _marker_hit(original_text, _MOJIBAKE_MARKERS):
        needs_review.append("suspected-mojibake")
    if _marker_hit(original_text, _TRUNCATION_MARKERS):
        needs_review.append("suspected-truncation")
    if _marker_hit(original_text, _LOGIN_WALL_MARKERS):
        needs_review.append("suspected-login-shell")
    if original_ratio >= 0.5:
        needs_review.append("repeated-original-paragraphs")
    if translation_ratio >= 0.5:
        needs_review.append("repeated-translation-paragraphs")

    deterministic_status = "needs-review" if needs_review else "passed"
    return {
        "schema_version": SCHEMA_VERSION,
        # ``status`` is the review-effective verdict (an explicit override may
        # downgrade it). ``deterministic_status`` never changes, so the public
        # gate can rely on it regardless of any recorded override.
        "status": override or deterministic_status,
        "deterministic_status": deterministic_status,
        "reason_codes": sorted(needs_review),
        "rules_version": QUALITY_RULES_VERSION,
        "metrics": {"original": original_metrics, "translation": translation_metrics},
    }


def _translation_completeness(record: ArticleRecord) -> str:
    has_title = bool(_text(record.title_translated).strip())
    has_body = bool(_text(record.body_translated).strip())
    if has_title and has_body:
        return "full"
    if has_title:
        return "title-only"
    if has_body:
        return "body-only"
    return "none"


def _source_identity(record: ArticleRecord) -> tuple[str, str]:
    url = record.url.strip()
    if not url:
        raise LegacyImportError(
            f"{record.source} record {record.id} has no URL; source identity is required"
        )
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LegacyImportError(
            f"{record.source} record {record.id} URL is not an http(s) source URL"
        )
    url_sha256 = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"{record.source}:{url_sha256}", url


def _language(value: object) -> str:
    text = _text(value).strip()
    return text or "unknown"


def _revision_id(identity_key: str, content_sha256: str) -> str:
    digest = hashlib.sha256(f"{identity_key}\0{content_sha256}".encode("utf-8")).hexdigest()
    return f"vx012a-{digest[:24]}"


def _source_published_at(record: ArticleRecord) -> str | None:
    """Normalize the adapter's publish time to ISO-8601 (RSS only; else unknown)."""
    if record.source == "rss":
        return _optional_text(_normalize_rss_update_time(record.publish_time, None))
    return _optional_text(record.publish_time)


def build_record(
    row: LegacySourceRow,
    *,
    public: bool,
    quality_override: str | None = None,
) -> dict[str, object]:
    """Convert one legacy row into a candidate import record."""
    record = row.article
    identity_key, url = _source_identity(record)
    original = {
        "title": _optional_text(record.title),
        "text": _text(record.body),
        "lang": _language(record.lang),
        # Adapter-available derived text is preserved as a distinct asset; the
        # rewrite is display content and is never treated as the source body.
        "variants": {
            "cleaned": _optional_text(record.body_cleaned),
            "repositioned": _optional_text(record.body_repositioned),
            "rewritten": _optional_text(record.body_rewritten),
        },
    }
    completeness = _translation_completeness(record)
    has_translation = completeness != "none"
    translation = {
        "title": _optional_text(record.title_translated),
        "text": _optional_text(record.body_translated),
        "lang": _language(record.translated_lang) if has_translation else "unknown",
        "completeness": completeness,
        "provenance": {
            "origin": "legacy-store" if has_translation else "unknown",
            "model": "unknown",
            "prompt_version": "unknown",
        },
    }
    content_sha256 = hashlib.sha256(
        _canonical_json({"original": original, "translation": translation}).encode("utf-8")
    ).hexdigest()
    quality = assess_quality(record.body, record.body_translated, override=quality_override)
    qualified = (
        completeness == "full" and quality["deterministic_status"] == "passed"
    )
    table = _SOURCES[record.source]
    return {
        "schema_version": SCHEMA_VERSION,
        "revision_id": _revision_id(identity_key, content_sha256),
        "content_sha256": content_sha256,
        "source": {
            "source": record.source,
            "source_ref": f"{table}:{record.id}",
            "url": url,
            "url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
            "identity_key": identity_key,
            "legacy_content_hash": _optional_text(record.content_hash),
            "legacy_content_hash_role": "legacy-version-signal",
        },
        "original": {**original, "provenance": {"origin": "legacy-store"}},
        "translation": translation,
        "assets": {
            "images": {
                "status": "unknown",
                "count": row.image_count,
                "reason": _UNKNOWN_IMAGES_REASON,
            },
            "provenance": {"status": "unknown"},
        },
        "migration": {
            "status": "imported",
            "migration_version": MIGRATION_VERSION,
        },
        "quality": quality,
        "publication": {
            "status": "public" if public else "private",
            "authority": "caller-declared-explicit-public-mark",
            "safety_qualification": {
                "rule": PUBLICATION_SAFETY_RULE,
                "status": "qualified" if qualified else "not-qualified",
                "translation_completeness": completeness,
            },
        },
        "source_published_at": _source_published_at(record),
        "fetched_at": _optional_text(record.update_time),
    }


def _read_existing(store: Path) -> list[dict[str, object]]:
    if not store.exists():
        return []
    records: list[dict[str, object]] = []
    for number, line in enumerate(store.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LegacyImportError(f"{_RECORDS_NAME} line {number} is not valid JSON") from exc
        if not isinstance(value, dict):
            raise LegacyImportError(f"{_RECORDS_NAME} line {number} is not an object")
        records.append(value)
    return records


def _review_update(
    previous: Mapping[str, object],
    *,
    quality_override: str | None,
    public: bool,
) -> dict[str, object] | None:
    """Apply an explicit review verdict to an existing revision, or return ``None``.

    Content is keyed by ``revision_id``; re-importing the same revision is a
    byte-identical no-op unless the caller records a new review verdict or public
    mark. Only review state changes here, so a recorded human decision is never
    erased by a later identical re-import.
    """
    quality = previous["quality"]
    publication = previous["publication"]
    changed = False
    if quality_override is not None and quality.get("status") != quality_override:
        quality = {**quality, "status": quality_override}
        changed = True
    if public and publication.get("status") != "public":
        publication = {
            **publication,
            "status": "public",
            "authority": "caller-declared-explicit-public-mark",
        }
        changed = True
    if not changed:
        return None
    migration = {
        **previous["migration"],
        "migration_version": int(previous["migration"]["migration_version"]) + 1,
    }
    if quality is not previous["quality"]:
        migration["quality_review_version"] = migration["migration_version"]
    return {**previous, "migration": migration, "quality": quality, "publication": publication}


def _is_publicly_projectable(record: Mapping[str, object]) -> bool:
    """The deterministic publication gate.

    It is computed from preserved source text and completeness only, so neither a
    caller quality override nor a stored review verdict can widen it.
    """
    publication = record.get("publication")
    quality = record.get("quality")
    translation = record.get("translation")
    if not (isinstance(publication, Mapping) and isinstance(quality, Mapping) and isinstance(translation, Mapping)):
        return False
    qualification = publication.get("safety_qualification")
    if not isinstance(qualification, Mapping):
        return False
    return (
        publication.get("status") == "public"
        and qualification.get("status") == "qualified"
        and quality.get("status") == "passed"
        and quality.get("deterministic_status") == "passed"
        and translation.get("completeness") == "full"
    )


def _table_columns(connection: sqlite3.Connection, table: str, source: str) -> set[str]:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    missing = _REQUIRED_COLUMNS - columns
    if missing:
        raise LegacyImportError(
            f"legacy table {table} for source {source} is missing columns {sorted(missing)}"
        )
    return columns


def _require_ingestions(connection: sqlite3.Connection) -> None:
    """Fail loud when the success denominator cannot be verified."""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(ingestions)")}
    if not columns:
        raise LegacyImportError(
            "legacy export has no ingestions table; the success denominator "
            "(ingestions.status='ok') cannot be verified"
        )
    missing = _INGESTION_COLUMNS - columns
    if missing:
        raise LegacyImportError(
            f"legacy ingestions table is missing columns {sorted(missing)}"
        )


def _required_columns_record(
    row: sqlite3.Row, source: str, columns: set[str]
) -> ArticleRecord:
    """Build the base record from the columns every legacy export guarantees."""
    update_time = (
        _normalize_update_time(row["update_time"])
        if source == "wechat" and "update_time" in columns
        else ""
    )
    if source == "rss":
        update_time = _normalize_rss_update_time(
            row["published_at"] if "published_at" in columns else None,
            row["fetched_at"] if "fetched_at" in columns else None,
        )
    return ArticleRecord(
        id=int(row["id"]),
        source=source,  # type: ignore[arg-type]
        title=str(_row_get(row, "title") or ""),
        url=str(_row_get(row, "url") or ""),
        body=str(_row_get(row, "body") or ""),
        content_hash=_row_get(row, "content_hash"),
        lang=_row_get(row, "lang"),
        update_time=update_time,
        publish_time=_row_get(row, "published_at"),
    )


def _with_optional_columns(
    record: ArticleRecord, row: sqlite3.Row, source: str, columns: set[str]
) -> ArticleRecord:
    """Overlay every optional column the export selected onto ``record``.

    Translation, body-variant, and RSS publish/fetch fields are read straight from
    the row, so the result does not depend on which ``kb.data.article_query``
    helper version is installed beside this module. A column the export did not
    select is never written, and only real ``ArticleRecord`` fields are set, so a
    row key such as a missing ``translated_lang`` stays absent rather than being
    invented: the record keeps its dataclass default and the language is reported
    as ``unknown``.
    """
    updates: dict[str, object] = {
        name: row[name]
        for name in _OPTIONAL_RECORD_COLUMNS
        if name in columns and name in _ARTICLE_RECORD_FIELDS
    }
    if source == "wechat" and "update_time" in columns:
        updates["update_time"] = _normalize_update_time(row["update_time"])
    if source == "rss":
        has_published = "published_at" in columns
        has_fetched = "fetched_at" in columns
        if has_published:
            updates["publish_time"] = row["published_at"]
        if has_published or has_fetched:
            updates["update_time"] = _normalize_rss_update_time(
                row["published_at"] if has_published else None,
                row["fetched_at"] if has_fetched else None,
            )
    return replace(record, **updates) if updates else record


def _record_from_row(row: sqlite3.Row, source: str, columns: set[str]) -> ArticleRecord:
    """Map one legacy row into an ``ArticleRecord`` from the selected row alone.

    The KB quality filter intentionally hides rows without a stored body; the
    migration denominator must keep them. The versioned ``_row_to_record_*``
    helpers are deliberately *not* called: a real 2026-09 remote read ran an older
    copy that dropped stored translations. Required columns come from the row, and
    every optional column the export selected is overlaid from the row as well.
    """
    return _with_optional_columns(
        _required_columns_record(row, source, columns), row, source, columns
    )


def read_legacy_records(
    connection: sqlite3.Connection, *, source: str, offset: int, limit: int
) -> list[LegacySourceRow]:
    """Read one deterministic slice of the *successful* records of a legacy source.

    The migration denominator is the distinct set of ``ingestions`` rows with
    ``status='ok'`` (``source`` + ``article_id``), not every row in the source
    table; scanned, failed, and skipped rows must never be migrated. ``offset``
    and ``limit`` therefore apply to the ordered success set. A missing or
    column-incomplete ``ingestions`` table is an explicit failure rather than a
    silent whole-table read.

    Each row keeps the mapped :class:`ArticleRecord` plus the adapter-available
    ``image_count``; the image payload itself is not part of the export and is
    therefore recorded later as an explicit unknown asset.
    """
    table = _SOURCES[source]
    columns = _table_columns(connection, table, source)
    _require_ingestions(connection)
    selected = [column for column in _OPTIONAL_COLUMNS if column in columns]
    select_list = ", ".join(
        f"t.{name} AS {name}" for name in ["id", "title", "url", "body", *selected]
    )
    rows = connection.execute(
        f"SELECT {select_list} FROM {table} AS t "
        "JOIN (SELECT DISTINCT article_id FROM ingestions WHERE source = ? AND status = 'ok') AS ok "
        "ON ok.article_id = t.id ORDER BY t.id ASC LIMIT ? OFFSET ?",
        (source, limit, offset),
    ).fetchall()
    results: list[LegacySourceRow] = []
    for row in rows:
        image_count = row["image_count"] if "image_count" in columns else None
        results.append(
            LegacySourceRow(
                article=_record_from_row(row, source, columns),
                image_count=image_count if isinstance(image_count, int) else None,
            )
        )
    return results


def _merge_records(
    existing: list[dict[str, object]],
    incoming: list[dict[str, object]],
    *,
    quality_override: str | None,
    public: bool,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Merge by content revision (``revision_id`` = source identity + content).

    A new content revision is appended beside the old one, so a historical
    revision and its recorded human review state are never overwritten. An
    identical re-import is byte-identical unless an explicit review verdict or
    public mark is recorded.
    """
    results = {"imported": 0, "revised": 0, "reviewed": 0, "skipped": 0}
    merged = list(existing)
    positions = {str(record["revision_id"]): index for index, record in enumerate(existing)}
    known_identities = {str(record["source"]["identity_key"]) for record in existing}
    for record in incoming:
        revision_id = str(record["revision_id"])
        position = positions.get(revision_id)
        if position is not None:
            updated = _review_update(
                merged[position], quality_override=quality_override, public=public
            )
            if updated is None:
                results["skipped"] += 1
            else:
                merged[position] = updated
                results["reviewed"] += 1
            continue
        merged.append(record)
        positions[revision_id] = len(merged) - 1
        identity = str(record["source"]["identity_key"])
        if identity in known_identities:
            results["revised"] += 1
        else:
            results["imported"] += 1
            known_identities.add(identity)
    return merged, results


def _public_projection(records: list[dict[str, object]], release_id: str, published_at: str) -> dict[str, object]:
    documents: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    knowledge: list[dict[str, object]] = []
    for record in records:
        if not _is_publicly_projectable(record):
            continue
        translation = record["translation"]
        # The public body is the full translation. Original text is never used as
        # a fallback, so an untranslated article cannot leak through this path.
        paragraphs = _split_paragraphs(translation["text"])
        title = translation["title"]
        if not paragraphs or not title:
            continue
        revision_id = str(record["revision_id"])
        evidence_ids = []
        for index, paragraph in enumerate(paragraphs, 1):
            evidence_id = f"{revision_id}-p{index:04d}"
            evidence_ids.append(evidence_id)
            evidence.append(
                {
                    "evidence_id": evidence_id,
                    "revision_id": revision_id,
                    "locator": f"paragraph:{index}",
                    "quote": paragraph,
                    "visibility": "public",
                }
            )
        documents.append(
            {
                "doc_id": record["source"]["source_ref"].replace(":", "-"),
                "revision_id": revision_id,
                "title": title,
                "source_url": record["source"]["url"],
                "source_published_at": record["source_published_at"],
                "fetched_at": record["fetched_at"],
                "visibility": "public",
            }
        )
        knowledge.append(
            {
                "knowledge_id": revision_id,
                "kind": "article",
                "title": title,
                "body": "\n\n".join(paragraphs),
                "evidence_ids": evidence_ids,
                "visibility": "public",
            }
        )
    return {
        "schema_version": _PUBLIC_SCHEMA_VERSION,
        "release_id": release_id,
        "published_at": published_at,
        "documents": documents,
        "evidence": evidence,
        "knowledge": knowledge,
        "entities": [],
        "relations": [],
    }


def _snapshot_id(legacy_database: Path) -> str:
    return f"sha256:{_file_sha256(legacy_database)}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _owner_only_file(descriptor: int) -> None:
    if _POSIX:
        os.fchmod(descriptor, _OWNER_ONLY_FILE_MODE)


def _staging_path(directory: Path, name: str) -> tuple[int, Path]:
    """Create an owner-only temporary file beside the name it will replace."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{name}.", suffix=".tmp", dir=directory
    )
    _owner_only_file(descriptor)
    return descriptor, Path(temporary_name)


def _prepare_private_directory(output_dir: Path) -> None:
    """Create or tighten the candidate directory so only its owner can use it.

    A directory that group or other users can *write* is rejected: it cannot be
    trusted as a private candidate store. An existing directory that merely
    carries group/other read or execute bits is tightened to ``0o700``. Where
    POSIX permission bits do not exist, nothing is fabricated.
    """
    if output_dir.is_symlink():
        raise LegacyImportError(f"candidate output must not be a symlink: {output_dir}")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise LegacyImportError(f"output path is not a directory: {output_dir}")
        if _POSIX:
            mode = stat.S_IMODE(output_dir.stat().st_mode)
            if mode & _GROUP_OR_OTHER_WRITE:
                raise LegacyImportError(
                    f"candidate output directory is group/other-writable: {output_dir}"
                )
            if mode & _GROUP_OR_OTHER_ANY:
                os.chmod(output_dir, _OWNER_ONLY_DIRECTORY_MODE)
        return
    output_dir.mkdir(mode=_OWNER_ONLY_DIRECTORY_MODE, parents=True)
    if _POSIX:
        os.chmod(output_dir, _OWNER_ONLY_DIRECTORY_MODE)


@contextmanager
def _candidate_lock(output_dir: Path):
    """Hold the exclusive lock that serialises one candidate store.

    Two batches must never read-merge-write the same candidate at once, or one
    silently overwrites the other. POSIX uses ``fcntl.flock`` on an owner-only
    lock file; elsewhere an explicit ``O_EXCL`` lock file is the fallback. A busy
    candidate is reported rather than raced.
    """
    lock_path = output_dir / _LOCK_NAME
    if fcntl is not None:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, _OWNER_ONLY_FILE_MODE)
        try:
            _owner_only_file(descriptor)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise LegacyImportError(
                    f"candidate store is locked by another import: {output_dir}"
                ) from exc
            yield
        finally:
            os.close(descriptor)
        return
    try:  # pragma: no cover - non-POSIX platform
        descriptor = os.open(
            lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, _OWNER_ONLY_FILE_MODE
        )
    except FileExistsError as exc:
        raise LegacyImportError(
            f"candidate store is locked by another import: {output_dir}"
        ) from exc
    try:  # pragma: no cover - non-POSIX platform
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _stage_public_database(projection: Mapping[str, object], directory: Path) -> Path:
    """Build the validated public read model at an owner-only staging path.

    The staging database is not swapped into place here. The caller commits it as
    one ordered batch with the records store, so a rejected projection never
    replaces the previous read model.
    """
    descriptor, staging = _staging_path(directory, _PUBLIC_DATABASE_NAME)
    os.close(descriptor)
    staging.unlink()
    try:
        build(projection, staging)
    except KnowledgeError as exc:
        raise LegacyImportError(f"public candidate projection was rejected: {exc}") from exc
    return staging


def _stage_jsonl(entries: list[dict[str, object]], directory: Path, name: str) -> Path:
    descriptor, staging = _staging_path(directory, name)
    try:
        with open(descriptor, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(_canonical_json(entry) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise LegacyImportError(f"cannot write {name}: {exc}") from exc
    return staging


def _stage_manifest(manifest: Mapping[str, object], directory: Path) -> Path:
    descriptor, staging = _staging_path(directory, _MANIFEST_NAME)
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        with open(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise LegacyImportError(f"cannot write {_MANIFEST_NAME}: {exc}") from exc
    return staging


def _generation_id(
    records: list[dict[str, object]],
    failures: list[dict[str, object]],
    *,
    source: str,
    offset: int,
    limit: int,
    public: bool,
    release_id: str,
) -> str:
    """Name a generation by its exact content, so an identical commit is a no-op.

    The scope parameters are part of the name, so two batches that happen to
    produce the same records still land in distinct generations, while re-running
    one batch is content-identical and reuses the generation already on disk.
    """
    digest = hashlib.sha256()
    scope = {
        "source": source,
        "offset": offset,
        "limit": limit,
        "public": public,
        "release_id": release_id,
    }
    for part in (_canonical_json(records), _canonical_json(failures), _canonical_json(scope)):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _read_manifest(directory: Path) -> dict[str, object]:
    path = directory / _MANIFEST_NAME
    if not path.is_file():
        raise LegacyImportError(f"generation manifest is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyImportError(f"{_MANIFEST_NAME} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LegacyImportError(f"{_MANIFEST_NAME} is not an object")
    return value


def _verify_generation(
    generation_dir: Path, generation: str
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return a generation's records and failures only if its manifest fully matches.

    A generation is accepted only when the manifest names the same generation and
    every committed file's digest and count agree. A pointer that names a
    half-written or tampered generation is an error, never a partial read.
    """
    manifest = _read_manifest(generation_dir)
    if manifest.get("generation") != generation:
        raise LegacyImportError(
            f"generation manifest does not name {generation}: {generation_dir}"
        )
    digests = manifest.get("generation_files")
    if not isinstance(digests, Mapping):
        raise LegacyImportError(f"generation manifest carries no file digests: {generation_dir}")
    for name in (_RECORDS_NAME, _FAILURES_NAME, _PUBLIC_DATABASE_NAME):
        expected = digests.get(name)
        path = generation_dir / name
        if not isinstance(expected, str) or not path.is_file():
            raise LegacyImportError(f"generation is incomplete, missing {name}: {generation_dir}")
        if _file_sha256(path) != expected:
            raise LegacyImportError(f"generation file does not match its manifest: {path}")
    records = _read_existing(generation_dir / _RECORDS_NAME)
    failures = _read_existing(generation_dir / _FAILURES_NAME)
    if manifest.get("entries") != len(records):
        raise LegacyImportError(
            f"generation record count does not match its manifest: {generation_dir}"
        )
    if manifest.get("failure_count") != len(failures):
        raise LegacyImportError(
            f"generation failure count does not match its manifest: {generation_dir}"
        )
    return records, failures


def _resolve_committed(
    output_dir: Path,
) -> tuple[Path, list[dict[str, object]], list[dict[str, object]]] | None:
    """Resolve the committed candidate store, or ``None`` when nothing is committed.

    A ``current`` pointer selects exactly one generation, and that generation's
    manifest must match. A candidate written before the generation layout (a bare
    ``import-records.jsonl`` and no pointer) is still read in place, so an existing
    private candidate keeps working. A pointer that names a missing or mismatched
    generation is an error rather than a guess.
    """
    pointer = output_dir / _CURRENT_NAME
    if pointer.is_file():
        generation = pointer.read_text(encoding="utf-8").strip()
        if not generation or generation in {".", ".."} or "/" in generation or "\\" in generation:
            raise LegacyImportError(f"{_CURRENT_NAME} pointer is malformed: {pointer}")
        generation_dir = output_dir / _GENERATIONS_DIRNAME / generation
        if not generation_dir.is_dir():
            raise LegacyImportError(
                f"{_CURRENT_NAME} pointer names a missing generation: {generation}"
            )
        records, failures = _verify_generation(generation_dir, generation)
        return generation_dir, records, failures
    if (output_dir / _RECORDS_NAME).is_file():
        return (
            output_dir,
            _read_existing(output_dir / _RECORDS_NAME),
            _read_existing(output_dir / _FAILURES_NAME),
        )
    return None


def _stage_generation(
    generation_dir: Path,
    *,
    records: list[dict[str, object]],
    failures: list[dict[str, object]],
    manifest: Mapping[str, object],
    projection: Mapping[str, object],
) -> None:
    """Write a whole generation beside its final name, then rename it into place.

    Every file is written, digested, and fsynced inside a private temporary
    directory; the directory rename is the only visible step, so a reader never
    observes a half-written generation. The ``current`` pointer is swapped
    separately, after this returns, so the visible name and the pointer never
    disagree by more than one whole generation.
    """
    root = generation_dir.parent
    _prepare_private_directory(root)
    temporary = Path(tempfile.mkdtemp(prefix=f".{generation_dir.name}.", suffix=".tmp", dir=root))
    try:
        staged_records = _stage_jsonl(records, temporary, _RECORDS_NAME)
        staged_database = _stage_public_database(projection, temporary)
        staged_failures = _stage_jsonl(failures, temporary, _FAILURES_NAME)
        digests = {
            _RECORDS_NAME: _file_sha256(staged_records),
            _FAILURES_NAME: _file_sha256(staged_failures),
            _PUBLIC_DATABASE_NAME: _file_sha256(staged_database),
        }
        os.replace(staged_records, temporary / _RECORDS_NAME)
        os.replace(staged_failures, temporary / _FAILURES_NAME)
        os.replace(staged_database, temporary / _PUBLIC_DATABASE_NAME)
        # The manifest is written last, once every digest is known, so it never
        # describes a file that was not fully written.
        staged_manifest = _stage_manifest({**manifest, "generation_files": digests}, temporary)
        os.replace(staged_manifest, temporary / _MANIFEST_NAME)
        os.replace(temporary, generation_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def _write_current_pointer(pointer: Path, generation: str) -> None:
    descriptor, staging = _staging_path(pointer.parent, _CURRENT_NAME)
    try:
        with open(descriptor, "w", encoding="utf-8") as handle:
            handle.write(generation + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, pointer)
    except OSError as exc:
        raise LegacyImportError(f"cannot write {_CURRENT_NAME} pointer: {exc}") from exc
    finally:
        if staging.exists():
            staging.unlink()


def _source_ref(source: str, record: ArticleRecord) -> str:
    return f"{_SOURCES[source]}:{record.id}"


def _failure_entry(
    source: str, article: ArticleRecord, exc: Exception, timestamp: str
) -> dict[str, object]:
    reason = " ".join(str(exc).split()) or exc.__class__.__name__
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "failed",
        "source": source,
        "source_ref": _source_ref(source, article),
        "record_id": article.id,
        "error_type": exc.__class__.__name__,
        "reason": reason[:_MAX_FAILURE_REASON],
        "attempted_at": timestamp,
    }


def _merge_failures(
    previous: list[dict[str, object]],
    scoped_refs: set[str],
    incoming: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep unresolved failures, clear repaired ones, and record this run's failures.

    A failure from an earlier batch survives a run that does not touch its range,
    so a later retry still knows what is outstanding. A success in this run clears
    the failure for the same source reference, which is what makes a rerun
    retry-only-failed instead of re-reporting or hiding the broken rows.
    """
    merged: dict[str, dict[str, object]] = {}
    for entry in previous:
        if not isinstance(entry, Mapping):
            continue
        source_ref = entry.get("source_ref")
        if isinstance(source_ref, str) and source_ref not in scoped_refs:
            merged[source_ref] = dict(entry)
    for entry in incoming:
        source_ref = entry.get("source_ref")
        if isinstance(source_ref, str):
            merged[source_ref] = dict(entry)
    return [merged[key] for key in sorted(merged)]


def _validate_scope(
    legacy_database: Path, output_dir: Path, source: str, offset: int, limit: int
) -> None:
    if source not in _SOURCES:
        raise LegacyImportError(f"source must be one of {sorted(_SOURCES)}")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise LegacyImportError("offset must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_BATCH_LIMIT:
        raise LegacyImportError(f"limit must be between 1 and {MAX_BATCH_LIMIT}")
    if not legacy_database.is_file():
        raise LegacyImportError(f"legacy export is not a file: {legacy_database}")
    if output_dir.exists() and not output_dir.is_dir():
        raise LegacyImportError(f"output path is not a directory: {output_dir}")
    if not output_dir.parent.is_dir():
        raise LegacyImportError(f"output parent directory does not exist: {output_dir.parent}")


def import_legacy_articles(
    *,
    legacy_database: str | Path,
    output_dir: str | Path,
    source: str,
    offset: int = 0,
    limit: int = DEFAULT_BATCH_LIMIT,
    public: bool = False,
    dry_run: bool = False,
    quality_override: str | None = None,
    release_id: str = "vx012a-legacy-candidate",
    now: str | None = None,
) -> dict[str, object]:
    """Import one deterministic slice of a read-only legacy export.

    Each commit writes one self-contained ``generations/<id>/`` directory holding
    the append-only ``import-records.jsonl``, the failure ledger, the manifest, and
    ``public-candidate.sqlite``, then makes it visible by swapping the single
    ``current`` pointer. The restricted projection of every eligible record
    (explicitly public, fully translated, deterministic quality passed, and
    safety-qualified) is rebuilt through :func:`vitax.knowledge.build` inside that
    generation, so a rejected projection leaves the previous generation current and
    a reader never sees files from two batches. A run with no eligible record
    leaves a valid, empty projection rather than a stale one.

    ``quality_override`` records an explicit review verdict for the imported
    range; it changes the recorded quality state only and never deletes the
    preserved original or translated assets. It cannot widen the publication
    gate, which reads ``quality.deterministic_status`` and translation
    completeness only.
    """
    legacy_database = Path(legacy_database)
    output_dir = Path(output_dir)
    _validate_scope(legacy_database, output_dir, source, offset, limit)
    if quality_override is not None and quality_override not in QUALITY_STATUSES:
        # A caller bug is loud; only per-row data problems become recorded failures.
        raise LegacyImportError(f"override must be one of {list(QUALITY_STATUSES)}")
    timestamp = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        connection = sqlite3.connect(f"file:{quote(str(legacy_database))}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise LegacyImportError(f"cannot open legacy export read-only: {exc}") from exc
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.row_factory = sqlite3.Row
        rows = read_legacy_records(connection, source=source, offset=offset, limit=limit)
    except sqlite3.Error as exc:
        raise LegacyImportError(f"legacy export is not a readable article store: {exc}") from exc
    finally:
        connection.close()

    # One unconvertible row becomes a recorded failure beside the batch; the rest of
    # the slice still imports. A failing row is never merged into the store, so
    # re-running the same scope retries exactly the rows that did not succeed.
    records: list[dict[str, object]] = []
    new_failures: list[dict[str, object]] = []
    for row in rows:
        try:
            records.append(build_record(row, public=public, quality_override=quality_override))
        except Exception as exc:  # noqa: BLE001 - per-row isolation is the contract
            new_failures.append(_failure_entry(source, row.article, exc, timestamp))
    scoped_refs = {_source_ref(source, row.article) for row in rows}

    snapshot_id = _snapshot_id(legacy_database)

    def assemble() -> tuple[list[dict[str, object]], dict[str, object]]:
        committed = _resolve_committed(output_dir)
        existing = committed[1] if committed else []
        previous_failures = committed[2] if committed else []
        merged, results = _merge_records(
            existing, records, quality_override=quality_override, public=public
        )
        outstanding = _merge_failures(previous_failures, scoped_refs, new_failures)
        # ``failed`` is this batch's own failures; ``outstanding_failed`` counts
        # every unresolved failure in the candidate, including other offsets, so a
        # run that touches only clean rows never inherits another offset's tally.
        results["failed"] = len(new_failures)
        results["outstanding_failed"] = len(outstanding)
        results["input"] = len(rows)
        projectable = [record for record in merged if _is_publicly_projectable(record)]
        summary: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "source": source,
            "offset": offset,
            "limit": limit,
            "dry_run": dry_run,
            "public_requested": public,
            "release_id": release_id,
            "snapshot_id": snapshot_id,
            "results": results,
            "failures": outstanding,
            "batch_failures": new_failures,
            "llm_requests": 0,
            "network_requests": 0,
            "public_records": len(projectable),
            "public_knowledge_ids": [record["revision_id"] for record in projectable],
            "publication_subset_rule": PUBLISHED_ONLY_SUBSET,
            "publication_safety_rule": PUBLICATION_SAFETY_RULE,
        }
        return merged, summary

    if dry_run:
        _, summary = assemble()
        summary["written"] = None
        return summary

    _prepare_private_directory(output_dir)
    with _candidate_lock(output_dir):
        merged, summary = assemble()
        generation = _generation_id(
            merged,
            summary["failures"],  # type: ignore[arg-type]
            source=source,
            offset=offset,
            limit=limit,
            public=public,
            release_id=release_id,
        )
        generation_dir = output_dir / _GENERATIONS_DIRNAME / generation
        pointer = output_dir / _CURRENT_NAME

        summary["written"] = str(output_dir)
        summary["generation"] = generation
        summary["generation_dir"] = str(generation_dir)
        summary["current_pointer"] = str(pointer)
        summary["records_path"] = str(generation_dir / _RECORDS_NAME)
        summary["failures_path"] = str(generation_dir / _FAILURES_NAME)
        summary["public_database"] = str(generation_dir / _PUBLIC_DATABASE_NAME)
        summary["manifest_path"] = str(generation_dir / _MANIFEST_NAME)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "entries": len(merged),
            "failure_count": len(summary["failures"]),  # type: ignore[arg-type]
            "batch_failure_count": len(new_failures),
            "generation": generation,
            "migration_version": MIGRATION_VERSION,
            "quality_rules_version": QUALITY_RULES_VERSION,
            "snapshot_id": snapshot_id,
            "last_run_at": timestamp,
            "dry_run": False,
            "llm_requests": 0,
            "network_requests": 0,
            "summary": summary,
        }

        if generation_dir.exists():
            # An identical commit already exists; verify it instead of rewriting,
            # then re-point the current pointer at it.
            _verify_generation(generation_dir, generation)
        else:
            _stage_generation(
                generation_dir,
                records=merged,
                failures=summary["failures"],  # type: ignore[arg-type]
                manifest=manifest,
                projection=_public_projection(merged, release_id, timestamp),
            )
        # The pointer is the single atomic commit marker. A rejected projection
        # never reaches here, so the previously committed generation stays current.
        _write_current_pointer(pointer, generation)
        return summary


def current_candidate_dir(output_dir: str | Path) -> Path | None:
    """Directory holding the committed candidate files, or ``None`` when uncommitted.

    Returns the generation named by the ``current`` pointer once its manifest
    matches, or ``output_dir`` itself for a legacy flat candidate. A pointer that
    names a missing or mismatched generation raises instead of returning a guess.
    """
    resolved = _resolve_committed(Path(output_dir))
    return None if resolved is None else resolved[0]


def load_import_records(output_dir: str | Path) -> list[dict[str, object]]:
    """Read the committed candidate store without loading runtime configuration.

    Only the generation named by the ``current`` pointer and fully matching its
    manifest is accepted, so records from two different batches are never mixed.
    """
    resolved = _resolve_committed(Path(output_dir))
    return [] if resolved is None else resolved[1]


def _record_title(record: Mapping[str, object]) -> str:
    """The article's own title, falling back to the translation title when absent."""
    original = record.get("original")
    title = _optional_text(original.get("title")) if isinstance(original, Mapping) else None
    if title:
        return title
    translation = record.get("translation")
    fallback = (
        _optional_text(translation.get("title")) if isinstance(translation, Mapping) else None
    )
    return fallback or ""


def _record_search_text(record: Mapping[str, object]) -> str:
    """Title, original text, and translation text, joined for one substring test."""
    sections: list[str] = []
    for name in ("original", "translation"):
        value = record.get(name)
        if isinstance(value, Mapping):
            sections.append(_text(value.get("title")))
            sections.append(_text(value.get("text")))
    return "\n".join(sections)


def _search_result(record: Mapping[str, object]) -> dict[str, object]:
    """The stable summary of one private record; the full record stays in the read."""
    return {
        "revision_id": record.get("revision_id"),
        "title": _record_title(record),
        "quality": record.get("quality"),
        "translation": record.get("translation"),
        "publication": record.get("publication"),
        "source": record.get("source"),
    }


def search_candidate_records(
    output_dir: str | Path, query: str, limit: int = DEFAULT_SEARCH_LIMIT
) -> list[dict[str, object]]:
    """Search the committed private candidate with a deterministic text match.

    ``query`` is matched case-insensitively as a plain substring of the record
    title, original text, or translation text. No relevance is scored, so results
    are ordered by title and then ``revision_id``: the same query against the same
    generation always returns the same page. Each entry carries ``revision_id``,
    ``title``, ``quality``, ``translation``, ``publication``, and ``source``; use
    :func:`read_candidate_record` for the full private record. An empty query, a
    non-positive ``limit``, or a ``limit`` above :data:`MAX_SEARCH_LIMIT` raises
    instead of returning an unbounded or ambiguous page.
    """
    if not isinstance(query, str) or not query.strip():
        raise LegacyImportError("search query must be a non-empty string")
    if not isinstance(limit, int) or limit <= 0:
        raise LegacyImportError(f"search limit must be a positive integer, got {limit!r}")
    if limit > MAX_SEARCH_LIMIT:
        raise LegacyImportError(f"search limit must not exceed {MAX_SEARCH_LIMIT}")
    needle = query.casefold()
    matches = [
        record
        for record in load_import_records(output_dir)
        if needle in _record_search_text(record).casefold()
    ]
    matches.sort(
        key=lambda record: (_record_title(record).casefold(), str(record.get("revision_id", "")))
    )
    return [_search_result(record) for record in matches[:limit]]


def read_candidate_record(output_dir: str | Path, revision_id: str) -> dict[str, object]:
    """Read one full private record, including its source provenance.

    The record is returned exactly as committed, so the caller sees the preserved
    original text and provenance. This never returns the public projection: a
    revision the publication gate excludes from the public candidate is still
    readable here. A missing or empty ``revision_id`` raises.
    """
    if not isinstance(revision_id, str) or not revision_id.strip():
        raise LegacyImportError("revision_id must be a non-empty string")
    for record in load_import_records(output_dir):
        if record.get("revision_id") == revision_id:
            return record
    raise LegacyImportError(f"no committed record with revision_id {revision_id!r}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m vitax.legacy_migration",
        description="Deterministic offline import of legacy articles into a VitaX candidate.",
    )
    parser.add_argument("legacy_database", help="read-only export of the legacy article store")
    parser.add_argument("output_dir", help="candidate directory (created unless --dry-run)")
    parser.add_argument("--source", required=True, choices=sorted(_SOURCES))
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=DEFAULT_BATCH_LIMIT)
    parser.add_argument("--public", action="store_true", help="mark records explicitly public")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quality-override", choices=sorted(QUALITY_STATUSES))
    parser.add_argument("--release-id", default="vx012a-legacy-candidate")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = import_legacy_articles(
            legacy_database=args.legacy_database,
            output_dir=args.output_dir,
            source=args.source,
            offset=args.offset,
            limit=args.limit,
            public=args.public,
            dry_run=args.dry_run,
            quality_override=args.quality_override,
            release_id=args.release_id,
        )
    except (LegacyImportError, KnowledgeError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

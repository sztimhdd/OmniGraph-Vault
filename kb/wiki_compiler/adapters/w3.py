"""kb.wiki_compiler.adapters.w3 — W3 ingest evidence → shared compiler.

W3 (the batch-ingest hook) keeps its production-safe evidence acquisition:
article hashes + entity-buffer JSON files + current page state. Everything
here is local DB/filesystem reads — **no network, no LLM, no Tavily, no
Databricks** (W5A constraint, design §4.6).

Public API
----------
* ``build_w3_evidence_packs(article_hashes, *, db_conn, wiki_root,
  entity_buffer_dirs, min_frequency=2) -> list[EvidencePack]`` —
  buffer discovery (canonical dir first, per-article first-hit wins),
  DB existence filtering, entity frequency threshold (distinct article
  hashes per entity), existing-page path/digest capture.
* ``build_w3_pack_for_entity(slug, hashes, wiki_root) -> EvidencePack`` —
  single-entity pack from already-validated hashes.
* ``propose_w3_patch(pack, *, wiki_root, today=None) -> WikiPatch`` —
  delegates to the pure assembler (CREATE_PAGE for new pages, scoped
  update ops for existing pages).
* ``engine_wiki_root(wiki_root) -> Path`` / ``engine_ready_patch(patch)`` —
  boundary normalization so the shared engine always receives the wiki
  directory itself and wiki-relative target paths (the assembler emits
  repo-relative ``kb/wiki/...`` paths; the engine resolves against the
  directory it is given).

Wiki-root conventions
---------------------
The engine resolves ``patch.target_path`` against the ``wiki_root`` it is
passed. The assembler hardcodes repo-relative ``kb/wiki/<kind>/<slug>.md``
paths, so callers must pass ``engine_wiki_root(wiki_root)`` (the directory
holding ``entities/``) and ``engine_ready_patch(patch)`` (wiki-relative
target path) to the engine. Both helpers are idempotent.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime, date
from pathlib import Path
from typing import Optional, Tuple

from kb.wiki_articles import (
    SUPPORTED_ARTICLE_SOURCES,
    UnsupportedArticleSource,
    load_article_index,
    resolve_article,
)
from kb.wiki_compiler.assembler import assemble_patch
from kb.wiki_compiler.models import (
    EvidencePack,
    EvidenceRef,
    WikiPatch,
    page_digest,
)

_HEX10_RE = re.compile(r"^[a-f0-9]{10}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_WIKI_PATH_PREFIX = "kb/wiki/"
COMPILER_VERSION = "v2.0-w5a"


def _slugify(name: str) -> str:
    """Lowercase ASCII slug with ``-`` runs (mirrors assembler slugify)."""
    return _SLUG_RE.sub("-", str(name).lower()).strip("-")


# ---------------------------------------------------------------------------
# Engine boundary normalization
# ---------------------------------------------------------------------------


def engine_wiki_root(wiki_root) -> Path:
    """Return the directory that holds ``entities/`` for any wiki_root form.

    Accepts the repository root (``kb/wiki`` nested beneath), ``kb/wiki``
    itself, or a bare wiki directory (tests / dev runs). Returns ``kb/wiki``
    when it exists under the input, otherwise the input unchanged.
    """
    root = Path(wiki_root)
    candidate = root / "kb" / "wiki"
    if candidate.is_dir():
        return candidate
    return root


def engine_ready_patch(patch: WikiPatch) -> WikiPatch:
    """Rewrite repo-relative ``kb/wiki/...`` target paths to wiki-relative.

    The assembler emits ``target_path="kb/wiki/entities/<slug>.md"``
    (repo-relative); the shared engine resolves targets against the wiki
    directory it is given, so the prefix must be stripped before apply.
    Idempotent: wiki-relative paths pass through unchanged.
    """
    tp = patch.target_path
    if tp.startswith(_WIKI_PATH_PREFIX):
        return replace(patch, target_path=tp[len(_WIKI_PATH_PREFIX):])
    return patch


# ---------------------------------------------------------------------------
# Evidence pack construction
# ---------------------------------------------------------------------------


def build_w3_pack_for_entity(
    slug: str,
    hashes: Tuple[str, ...],
    wiki_root,
) -> EvidencePack:
    """Build one EvidencePack for *slug* from validated article hashes.

    Captures existing-page path + base digest for optimistic concurrency
    when the target page already exists (wiki-relative path, matching the
    engine's resolution convention). Article evidence refs are the
    canonical 10-char lowercase hex identities.
    """
    wiki = Path(wiki_root)
    page = wiki / "entities" / f"{slug}.md"
    existing_path: Optional[str] = None
    existing_digest: Optional[str] = None
    if page.exists():
        existing_path = f"entities/{slug}.md"
        existing_digest = page_digest(page.read_text(encoding="utf-8"))

    hashes = tuple(sorted(set(hashes)))
    evidence = tuple(
        EvidenceRef(
            evidence_id=f"w3-{i}",
            type="article",
            ref=h,
            title=h,
            provenance="w3-entity-buffer",
            metadata={},
        )
        for i, h in enumerate(hashes)
    )
    return EvidencePack(
        pack_id=f"w3-{slug}-{'-'.join(hashes)}",
        subject_slug=slug,
        subject_title=slug.replace("-", " ").title(),
        trigger="w3_incremental",
        article_hashes=hashes,
        evidence=evidence,
        context_blocks=(
            f"Observed in {len(hashes)} newly ingested OmniGraph source "
            "articles.",
        ),
        existing_page_path=existing_path,
        existing_page_digest=existing_digest,
        created_at=datetime.now(UTC).isoformat(),
        compiler_version=COMPILER_VERSION,
    )


def _legacy_content_hash_record(db_conn, ref: str) -> dict | None:
    """Legacy wechat fallback: bare ref present in ``articles.content_hash``.

    W5-0 era fixtures (and pre-Task-2 production) keyed article existence by
    ``articles.content_hash`` only (no ``url`` column), where the value
    historically equals ``md5(url)[:10]``. Kept ONLY for bare-ref inputs that
    the Task 1 URL index cannot resolve; RSS 32-char body hashes never reach
    this path because ``resolve_article`` returns a record for canonical refs.
    """
    cols = {row[1] for row in db_conn.execute("PRAGMA table_info(articles)").fetchall()}
    if "content_hash" not in cols:
        return None
    row = db_conn.execute(
        "SELECT 1 FROM articles WHERE content_hash=?", (ref,)
    ).fetchone()
    if row is None:
        return None
    return {
        "source": "wechat",
        "article_id": None,
        "ref": ref,
        "url": None,
        "title": ref,
        "text": "",
    }


def _build_pack_from_records(
    slug: str,
    records: list[dict],
    wiki_root,
) -> EvidencePack:
    """Build one EvidencePack from already-resolved source-aware records.

    Deterministic identity: all-wechat groups keep the legacy W5A pack_id
    (``w3-<slug>-<refs>``); any RSS evidence switches to a source-aware
    sha256 form so ``(source, ref)`` collisions can never alias. Evidence
    carries the real local title + ``metadata={"source": ...}``.
    """
    wiki = Path(wiki_root)
    page = wiki / "entities" / f"{slug}.md"
    existing_path: Optional[str] = None
    existing_digest: Optional[str] = None
    if page.exists():
        existing_path = f"entities/{slug}.md"
        existing_digest = page_digest(page.read_text(encoding="utf-8"))

    records = sorted(records, key=lambda r: (r["source"], r["ref"]))
    refs = tuple(r["ref"] for r in records)
    evidence = tuple(
        EvidenceRef(
            evidence_id=f"w3-{i}",
            type="article",
            ref=r["ref"],
            title=r["title"],
            provenance="w3-entity-buffer",
            metadata={"source": r["source"]},
        )
        for i, r in enumerate(records)
    )
    if all(r["source"] in (None, "wechat") for r in records):
        pack_id = f"w3-{slug}-{'-'.join(sorted(refs))}"
    else:
        material = "|".join(
            sorted(f"{r['source']}:{r['ref']}" for r in records)
        )
        pack_id = (
            f"w3-{slug}-{hashlib.sha256(material.encode()).hexdigest()[:16]}"
        )
    return EvidencePack(
        pack_id=pack_id,
        subject_slug=slug,
        subject_title=slug.replace("-", " ").title(),
        trigger="w3_incremental",
        article_hashes=refs,
        evidence=evidence,
        context_blocks=(
            f"Observed in {len(records)} newly ingested OmniGraph source "
            "articles.",
        ),
        existing_page_path=existing_path,
        existing_page_digest=existing_digest,
        created_at=datetime.now(UTC).isoformat(),
        compiler_version=COMPILER_VERSION,
    )


def build_w3_evidence_packs(
    article_hashes,
    *,
    db_conn,
    wiki_root,
    entity_buffer_dirs,
    min_frequency: int = 2,
) -> list:
    """Discover entities from source-aware article evidence + entity buffers.

    Input items are either ``{"source": "wechat"|"rss", "ref": "<10hex>"}``
    mappings (production hook) or bare 10-char refs (legacy callers). All
    resolution goes through the Task 1 local resolver/index:

    * mappings resolve strictly inside their own source; an unsupported
      source raises ``UnsupportedArticleSource`` (explicit, never silent);
    * bare refs resolve source-less only when unambiguous (ambiguous ->
      ValueError); unresolved bare refs fall back to the legacy wechat
      ``articles.content_hash`` check and are otherwise ignored;
    * entity frequency = distinct ``(source, ref)`` pairs; packs below
      ``min_frequency`` are dropped;
    * buffer search order is canonical-first (caller-supplied dir list;
      production passes ``kb.wiki_update.DEFAULT_BUFFER_DIRS``); the first
      directory holding a matching ``<ref>_entities.json`` wins per article;
    * each pack captures the existing page path/digest when present.

    No network / LLM / Tavily / Databricks work happens here.
    """
    wiki = Path(wiki_root)
    index = load_article_index(db_conn)
    legacy: dict[tuple[str, str], dict] = {}
    entity_to_keys: dict[str, set] = {}
    for item in article_hashes:
        if isinstance(item, dict):
            source = item.get("source")
            ref = item.get("ref")
            if source not in SUPPORTED_ARTICLE_SOURCES:
                raise UnsupportedArticleSource(source)
            rec = index.get((source, ref))
            if rec is None:
                continue
            key = (rec["source"], rec["ref"])
        else:
            ref = str(item)
            rec = resolve_article(index, ref)
            if rec is None:
                rec = _legacy_content_hash_record(db_conn, ref)
                if rec is None:
                    continue
                key = (rec["source"], rec["ref"])
                legacy[key] = rec
            else:
                key = (rec["source"], rec["ref"])
        for d in entity_buffer_dirs:
            p = Path(d) / f"{key[1]}_entities.json"
            if not p.exists():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            for e in data.get("raw_entities", []):
                name = e.get("name", "") if isinstance(e, dict) else str(e)
                if (slug := _slugify(name)):
                    entity_to_keys.setdefault(slug, set()).add(key)
            break
    packs = []
    for slug, keys in entity_to_keys.items():
        if len(keys) < min_frequency:
            continue
        records = []
        for key in sorted(keys):
            rec = index.get(key)
            if rec is None:
                rec = legacy.get(key)
            records.append(rec)
        packs.append(_build_pack_from_records(slug, records, wiki))
    return packs


# ---------------------------------------------------------------------------
# Patch proposal
# ---------------------------------------------------------------------------


def propose_w3_patch(pack: EvidencePack, *, wiki_root, today: Optional[date] = None) -> WikiPatch:
    """Assemble the W3 WikiPatch for *pack* via the pure assembler.

    New page -> canonical ``CREATE_PAGE`` (policy hint ``auto_apply``);
    existing page -> scoped ``MERGE_SOURCES`` + ``UPSERT_SECTION`` +
    ``SET_METADATA`` (policy hint ``suggestion_only``). Never emits legacy
    ``^[article:...]`` output for new pages.

    ``wiki_root`` is accepted for signature stability (the assembler
    derives target paths itself); ``today`` keeps tests deterministic.
    """
    return assemble_patch(pack, "entity", today=today)

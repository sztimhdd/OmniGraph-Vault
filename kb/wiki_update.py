"""W3 wiki update hook — production path converges onto the shared compiler.

W5A Task 4 (2026-08-11): the W3 batch-ingest hook now routes through
``kb.wiki_compiler.adapters.w3`` (evidence-pack construction + patch
proposal) and the shared compiler engine (``kb.wiki_compiler.engine``).
The legacy W5-0 machinery — ``_build_page()`` placeholder generation, the
local authoritative ``_atomic_write()`` target-page bypass, timestamped
``<slug>-<timestamp>.md`` suggestion files, and the duplicate lint/apply
policy — is removed. Engine policy is strictly stronger than the old
W1-richness heuristic: ANY existing page receives scoped update operations
that classify as ``suggestion_only`` (never overwritten), while new
entities get a canonical ``CREATE_PAGE`` that auto-applies.

Required target flow (production W3 path)
------------------------------------------
``article_hashes -> w3.build_w3_evidence_packs(...) -> w3.propose_w3_patch(...)
-> engine.apply_patch(...) -> result accounting``

Backward-compatible surface (call sites unchanged)
--------------------------------------------------
* ``generate_wiki_suggestions(article_hashes, wiki_root, db_conn,
  min_frequency=2, entity_buffer_dirs=None)`` still returns a list of
  suggestion dicts. Each dict keeps the legacy informational fields
  (``type``/``entity_slug``/``page_path``/``content``/``source_articles``)
  and additionally carries an engine-ready ``WikiPatch`` under ``patch``;
  the patch is authoritative for application, the other fields are
  display/log compatibility.
* ``apply_suggestion_atomic(suggestion, db_conn, wiki_root=None)`` still
  returns ``True`` only when the shared engine reports ``applied``.
  ``db_conn`` is retained for signature compatibility — the compiler
  engine performs its own validation and does not need the DB.
* ``batch_ingest_from_spider._wiki_update_check`` needs no redesign.

Accounting mapping (W5A)
------------------------
The hook's stats dict ``{suggestions_generated, applied, dropped}`` keeps
its meaning:

* ``applied`` — engine status ``applied``: page written atomically.
* ``dropped`` — every non-applied engine outcome:
    - ``suggestion`` — a deterministic structured suggestion JSON was
      persisted at ``kb/wiki/_suggestions/<slug>-<patch-id>.json``; the
      target page is untouched. A persisted suggestion is NEVER counted
      as ``applied``.
    - ``conflict`` — the target changed since the patch was assembled
      (digest race); nothing written, nothing logged.
    - ``rejected`` — validation/policy failure; logged to the Error Book
      (``wiki_compiler:*`` lint names).
* ``suggestions_generated`` — entity packs above ``min_frequency``.
* ``run_wiki_update_pipeline`` additionally exposes
  ``suggestions_persisted`` / ``conflicted`` / ``rejected`` and per-patch
  results for callers that need the full breakdown.

Determinism
-----------
``patch_id`` derives from evidence content (``stable_patch_id``), so
re-running the same logical evidence against the same page state
converges on the same patch id and the same suggestion path — no
timestamp-spam duplicates. (``last_updated`` embeds the current date, so
a patch legitimately changes identity when the date changes; same-day
re-runs are stable.)

W5-0 compat preserved: canonical entity-buffer discovery
(``DEFAULT_BUFFER_DIRS``), ``min_frequency`` as distinct article hashes,
unknown DB hashes ignored, rich existing pages never overwritten, W3
failure never fails main ingest, 120s outer timeout unchanged, and no
network/LLM/Tavily/Databricks calls anywhere in this path.
"""
from __future__ import annotations

import os
from pathlib import Path

from kb.wiki_compiler.adapters import w3
from kb.wiki_compiler.engine import apply_patch

# W5-0 Gate I (2026-08-11): canonical entity-buffer discovery — production
# buffers live at ~/.hermes/omonigraph-vault/entity_buffer (or
# OMNIGRAPH_BASE_DIR if set). The canonical dir is tried first; local-dev
# fallbacks are kept for local runs.
_OMNIGRAPH_BASE = os.environ.get("OMNIGRAPH_BASE_DIR")
_CANONICAL_BUFFER = (
    Path(_OMNIGRAPH_BASE) / "entity_buffer"
    if _OMNIGRAPH_BASE
    else Path.home() / ".hermes" / "omonigraph-vault" / "entity_buffer"
)
DEFAULT_BUFFER_DIRS = [
    _CANONICAL_BUFFER,
    Path(".dev-runtime/entity_buffer"),
    Path("entity_buffer"),
]


def generate_wiki_suggestions(
    article_hashes: list[str],
    wiki_root: Path,
    db_conn,
    min_frequency: int = 2,
    entity_buffer_dirs: list[Path] | None = None,
) -> list[dict]:
    """Propose W3 suggestions through the shared compiler (adapter + assembler).

    Entity-buffer discovery, DB-existence filtering, and frequency
    thresholding are delegated to ``w3.build_w3_evidence_packs``; patch
    proposal to ``w3.propose_w3_patch``. Each returned dict carries the
    engine-ready ``WikiPatch`` under ``patch`` plus the legacy
    informational fields.
    """
    buf_dirs = entity_buffer_dirs or DEFAULT_BUFFER_DIRS
    packs = w3.build_w3_evidence_packs(
        article_hashes,
        db_conn=db_conn,
        wiki_root=wiki_root,
        entity_buffer_dirs=buf_dirs,
        min_frequency=min_frequency,
    )
    return [
        _suggestion_dict(pack, w3.propose_w3_patch(pack, wiki_root=wiki_root), wiki_root)
        for pack in packs
    ]


def _suggestion_dict(pack, patch, wiki_root: Path) -> dict:
    """Legacy-shaped suggestion dict + authoritative engine-ready patch."""
    page_path = Path(wiki_root) / "entities" / f"{pack.subject_slug}.md"
    content = ""
    for op in patch.operations:
        if op.op in ("CREATE_PAGE", "UPSERT_SECTION") and op.content:
            content = op.content
            break
    return {
        "type": "new" if pack.existing_page_path is None else "update",
        "entity_slug": pack.subject_slug,
        "page_path": str(page_path),
        "content": content,
        "source_articles": list(pack.article_hashes),
        "patch": w3.engine_ready_patch(patch),
    }


def _apply_suggestion_engine(suggestion: dict, wiki_root) -> dict:
    """Route one suggestion through the shared engine; return its result dict.

    Embedded patches (production path) are applied directly. Legacy dicts
    without a ``patch`` key are rebuilt through the W3 adapter pipeline
    (backward compatibility); invalid legacy evidence is rejected and
    recorded in the Error Book without any write.
    """
    patch = suggestion.get("patch")
    if patch is not None:
        root = Path(wiki_root) if wiki_root else Path(suggestion["page_path"]).parent.parent
    else:
        slug = suggestion.get("entity_slug") or Path(suggestion["page_path"]).stem
        hashes = tuple(sorted(set(suggestion.get("source_articles") or ())))
        root = Path(wiki_root) if wiki_root else Path(suggestion["page_path"]).parent.parent
        try:
            pack = w3.build_w3_pack_for_entity(slug, hashes, root)
            patch = w3.propose_w3_patch(pack, wiki_root=root)
        except Exception as exc:  # noqa: BLE001 - rejected, never raised to caller
            _log_rejected_evidence(slug, root, exc)
            return {
                "status": "rejected",
                "patch_id": None,
                "error": str(exc),
                "suggestion_path": None,
            }
    return apply_patch(w3.engine_ready_patch(patch), w3.engine_wiki_root(root))


def apply_suggestion_atomic(
    suggestion: dict, db_conn, wiki_root: Path | None = None
) -> bool:
    """Apply *suggestion* via the shared engine; True only when ``applied``.

    ``suggestion`` (structured JSON persisted), ``conflict``, and
    ``rejected`` engine outcomes all return False — a persisted structured
    suggestion is never reported as applied. ``db_conn`` is retained for
    signature compatibility and is not used by the compiler path.
    """
    return _apply_suggestion_engine(suggestion, wiki_root)["status"] == "applied"


def run_wiki_update_pipeline(
    article_hashes: list[str],
    wiki_root: Path,
    db_conn,
    min_frequency: int = 2,
    entity_buffer_dirs: list[Path] | None = None,
) -> dict:
    """W3 production flow in one call: packs -> patches -> engine -> stats.

    Stats keys: ``suggestions_generated``, ``applied``, ``dropped``,
    ``suggestions_persisted``, ``conflicted``, ``rejected``, and
    ``patches`` (per-entity ``{slug, patch_id, status, suggestion_path}``).
    """
    suggestions = generate_wiki_suggestions(
        article_hashes,
        wiki_root,
        db_conn,
        min_frequency=min_frequency,
        entity_buffer_dirs=entity_buffer_dirs,
    )
    stats = {
        "suggestions_generated": len(suggestions),
        "applied": 0,
        "dropped": 0,
        "suggestions_persisted": 0,
        "conflicted": 0,
        "rejected": 0,
        "patches": [],
    }
    for s in suggestions:
        result = _apply_suggestion_engine(s, wiki_root)
        status = result["status"]
        stats["patches"].append(
            {
                "slug": s["entity_slug"],
                "patch_id": result["patch_id"],
                "status": status,
                "suggestion_path": result.get("suggestion_path"),
            }
        )
        if status == "applied":
            stats["applied"] += 1
            continue
        stats["dropped"] += 1
        if status == "suggestion":
            stats["suggestions_persisted"] += 1
        elif status == "conflict":
            stats["conflicted"] += 1
        elif status == "rejected":
            stats["rejected"] += 1
    return stats


def _log_rejected_evidence(slug: str, root: Path, exc: Exception) -> None:
    """Record legacy-evidence rebuild failures in the Error Book (best-effort)."""
    try:
        from kb.error_book import log_lint_failure

        log_lint_failure(
            {
                "lint_name": "wiki_compiler:evidence_validation",
                "page_path": str(Path(root) / "entities" / f"{slug}.md"),
                "failures": [str(exc)],
                "suggestion_excerpt": "w3-legacy-dict-rebuild",
            }
        )
    except Exception:  # noqa: BLE001 - Error Book must never break the hook
        pass

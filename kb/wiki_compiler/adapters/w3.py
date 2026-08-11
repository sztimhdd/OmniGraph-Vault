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

import json
import re
from dataclasses import replace
from datetime import UTC, datetime, date
from pathlib import Path
from typing import Optional, Tuple

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


def build_w3_evidence_packs(
    article_hashes,
    *,
    db_conn,
    wiki_root,
    entity_buffer_dirs,
    min_frequency: int = 2,
) -> list:
    """Discover entities from article hashes + entity buffers → EvidencePacks.

    Preserves the W3 discovery contract:

    * unknown article hashes (not in ``articles.content_hash``) are ignored;
    * buffer search order is canonical-first (caller-supplied dir list;
      production passes ``kb.wiki_update.DEFAULT_BUFFER_DIRS``);
    * the first directory holding a matching ``<hash>_entities.json`` wins
      per article (legacy behavior);
    * entity frequency = distinct article hashes; packs below
      ``min_frequency`` are dropped;
    * each pack captures the existing page path/digest when present.
    """
    wiki = Path(wiki_root)
    entity_to_hashes: dict[str, set] = {}
    for h in article_hashes:
        if not db_conn.execute(
            "SELECT 1 FROM articles WHERE content_hash=?", (h,)
        ).fetchone():
            continue
        for d in entity_buffer_dirs:
            p = Path(d) / f"{h}_entities.json"
            if not p.exists():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            for e in data.get("raw_entities", []):
                name = e.get("name", "") if isinstance(e, dict) else str(e)
                if (slug := _slugify(name)):
                    entity_to_hashes.setdefault(slug, set()).add(h)
            break
    packs = []
    for slug, hset in entity_to_hashes.items():
        if len(hset) < min_frequency:
            continue
        packs.append(build_w3_pack_for_entity(slug, tuple(sorted(hset)), wiki))
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

"""kb.wiki_compiler.assembler — Pure WikiPatch assembler.

Turns an :class:`EvidencePack` into a deterministic :class:`WikiPatch`
without touching the filesystem, network, DB, or locks.

Contract
--------
* **New pages** (``existing_page_path is None``) produce a single
  ``CREATE_PAGE`` operation whose content is the canonical SCHEMA.md
  representation: typed ``sources`` frontmatter (``type``/``ref``/``title``/
  ``provenance``) and GFM ``[^N]`` footnote citations with a trailing
  ``## References`` section. Legacy ``^[article:<hex>]`` inline citations are
  never emitted for new pages.

* **Existing pages** (``existing_page_path`` set) are *not* rewritten to the
  canonical format. The assembler emits scoped operations only:
  ``MERGE_SOURCES`` (union/dedup, never subtractive), ``UPSERT_SECTION``
  (replace exactly one named H2 section; never emitted when there is no new
  content, so empty sections can never be "deleted"), and ``SET_METADATA``
  (allowlist: ``last_updated``, ``confidence_level``; ``created`` is never
  touched). Body/frontmatter rendering of existing pages is the apply
  engine's job (Task 3) — the assembler only builds the patch.

Source catalog
--------------
Sources are cataloged in first-seen evidence order, deduplicated by
``(type, ref)`` for ``article``/``web`` and by ``(type, title)`` for
``builtin`` (whose ref is null). Footnote numbers ``[^N]`` are 1-based
positions in this deduplicated catalog.

Citation mapping
----------------
* If any evidence carries ``metadata["context_blocks"]`` (list of block
  indexes), block ``i`` cites every cataloged source whose evidence lists
  ``i``, in catalog order.
* Otherwise the positional fallback applies: block ``i`` cites source ``i``
  when it exists; blocks beyond the catalog carry no citation.

Provenance defaults by type (overridable per evidence): article →
``lightrag-corpus``, web → ``tavily-web``, builtin → ``training-knowledge``.

confidence_level (SCHEMA.md §1): ``high`` = >=2 distinct source types;
``medium`` = single type with >=2 sources; ``low`` = sparse (<2 sources).

Policy hints: ``CREATE_PAGE`` -> ``auto_apply``; updates (existing page) and
any ``dry_run`` -> ``suggestion_only``. Task 3's policy engine may further
restrict.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from kb.wiki_compiler.models import (
    VALID_TARGET_KINDS,
    EvidencePack,
    EvidenceRef,
    PatchOperation,
    WikiPatch,
    stable_patch_id,
)

#: Subdirectory per target kind (SCHEMA.md §4).
SUBDIR_BY_KIND = {
    "entity": "entities",
    "concept": "concepts",
    "comparison": "comparisons",
    "query": "queries",
}

#: Default provenance when an EvidenceRef carries no explicit provenance.
TYPE_PROVENANCE = {
    "article": "lightrag-corpus",
    "web": "tavily-web",
    "builtin": "training-knowledge",
}

#: Default H2 section targeted by UPSERT_SECTION on existing pages.
DEFAULT_SECTION = "Definition / Overview"

#: Frontmatter keys that may appear in a typed source entry.
_SOURCE_ENTRY_KEYS = ("type", "ref", "title", "provenance")

_COMPILER_VERSION = "v2.0-w5a"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble_patch(
    evidence_pack: EvidencePack,
    target_kind: str,  # entity|concept|comparison|query
    today: date = None,  # defaults to date.today()
    *,
    dry_run: bool = False,
) -> WikiPatch:
    """Assemble a WikiPatch from an EvidencePack.

    Deterministic: every output field derives from *evidence_pack* and
    *today*; no wall clock, randomness, or filesystem access.

    Raises:
        ValueError: invalid ``target_kind``, or an inconsistent pack
            (``existing_page_path`` without ``existing_page_digest`` or vice
            versa).
    """
    if target_kind not in VALID_TARGET_KINDS:
        raise ValueError(
            f"target_kind must be one of {sorted(VALID_TARGET_KINDS)}, "
            f"got {target_kind!r}"
        )
    if today is None:
        today = date.today()

    _validate_pack_preconditions(evidence_pack)

    slug = _slugify(evidence_pack.subject_slug)
    target_path = f"kb/wiki/{SUBDIR_BY_KIND[target_kind]}/{slug}.md"
    sources = _catalog_sources(evidence_pack)
    confidence = _derive_confidence(sources)
    gfm_body = _build_gfm_body(evidence_pack.context_blocks, sources)

    if evidence_pack.existing_page_path is None:
        operations, policy_hint, reason = _build_create_operations(
            evidence_pack, slug, sources, gfm_body, confidence, today,
        )
        base_digest: Optional[str] = None
    else:
        operations, policy_hint, reason = _build_update_operations(
            evidence_pack, slug, gfm_body, confidence, today,
        )
        base_digest = evidence_pack.existing_page_digest

    if dry_run:
        policy_hint = "suggestion_only"
        reason = f"{reason} [dry run]"

    # Evidence catalog rides on the patch for MERGE_SOURCES / apply-time use.
    evidence = tuple(
        _evidence_for_entry(evidence_pack, s) for s in sources
    )

    return WikiPatch(
        patch_schema_version=1,
        patch_id=stable_patch_id(
            target_slug=slug,
            evidence_pack_id=evidence_pack.pack_id,
            operations=operations,
        ),
        target_slug=slug,
        target_path=target_path,
        target_kind=target_kind,
        base_digest=base_digest,
        trigger=evidence_pack.trigger,
        evidence_pack_id=evidence_pack.pack_id,
        operations=operations,
        evidence=evidence,
        policy_hint=policy_hint,
        reason=reason,
        created_at=f"{today.isoformat()}T00:00:00Z",
        compiler_version=evidence_pack.compiler_version or _COMPILER_VERSION,
    )


# ---------------------------------------------------------------------------
# Frontmatter / body / references rendering
# ---------------------------------------------------------------------------

def _build_canonical_frontmatter(
    ep: EvidencePack,
    sources: list[dict] = None,
    today: date = None,
) -> dict:
    """Build the YAML frontmatter dict in canonical typed-source format.

    ``sources`` defaults to the deduplicated catalog derived from ``ep``.
    ``today`` defaults to the date embedded in ``ep.created_at`` when it is
    ISO-formatted, otherwise ``date.today()``. Source entries carry only the
    canonical keys (``type``, ``ref``, ``title``, ``provenance``); ``ref`` is
    omitted for builtin sources.
    """
    if sources is None:
        sources = _catalog_sources(ep)
    if today is None:
        today = _date_from_iso(ep.created_at) or date.today()
    return {
        "title": ep.subject_title,
        "created": today.isoformat(),
        "last_updated": today.isoformat(),
        "sources": [
            {k: s[k] for k in _SOURCE_ENTRY_KEYS
             if k in s and s[k] is not None}
            for s in sources
        ],
        "confidence_level": _derive_confidence(sources),
    }


def _build_gfm_body(context_blocks: Tuple[str, ...], sources: list[dict]) -> str:
    """Build body text with GFM ``[^N]`` citations.

    Paragraphs are the non-empty context blocks, joined by blank lines, each
    suffixed with its citations (see module docstring for the mapping rule).
    """
    mapped_mode = any("context_blocks" in s for s in sources)
    paragraphs: List[str] = []
    for i, block in enumerate(context_blocks):
        text = block.strip()
        if not text:
            continue
        if mapped_mode:
            numbers = [
                j + 1
                for j, s in enumerate(sources)
                if i in s.get("context_blocks", ())
            ]
        else:
            numbers = [i + 1] if i < len(sources) else []
        suffix = "".join(f"[^{n}]" for n in numbers)
        if suffix:
            separator = "" if text[-1].isspace() else " "
            text = text + separator + suffix
        paragraphs.append(text)
    return "\n\n".join(paragraphs)


def _build_references_section(sources: list[dict]) -> str:
    """Build the ``## References`` section with canonical source entries."""
    lines = ["## References", ""]
    for i, s in enumerate(sources, start=1):
        label = f"**{s['title']}**"
        if s["type"] == "builtin":
            detail = f"{s['provenance']}"
        else:
            detail = f"{s['ref']} ({s['provenance']})"
        lines.append(f"[^{i}]: {label} — {detail}")
    return "\n".join(lines) + "\n"


def _slugify(text: str) -> str:
    """Slug conversion for file paths (SCHEMA.md §5: lowercase ASCII)."""
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    s = s.strip("-")
    return s or "untitled"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_pack_preconditions(ep: EvidencePack) -> None:
    if ep.existing_page_path is not None and ep.existing_page_digest is None:
        raise ValueError(
            "EvidencePack sets existing_page_path but existing_page_digest "
            "is None; update patches require the base digest for optimistic "
            "concurrency"
        )
    if ep.existing_page_path is None and ep.existing_page_digest is not None:
        raise ValueError(
            "EvidencePack sets existing_page_digest but existing_page_path "
            "is None; a digest without a target page is inconsistent"
        )


def _catalog_sources(ep: EvidencePack) -> List[Dict[str, Any]]:
    """Deduplicated source catalog in first-seen evidence order.

    Dedup key: ``(type, ref)`` for article/web, ``(type, title)`` for
    builtin. Entries carry the canonical keys plus an optional
    ``context_blocks`` index list used for body citation mapping.
    """
    catalog: List[Dict[str, Any]] = []
    seen = set()
    for ev in ep.evidence:
        key = (
            (ev.type, ev.ref)
            if ev.ref is not None
            else (ev.type, ev.title)
        )
        if key in seen:
            # Extend the existing entry's block mapping, if any.
            entry = next(
                e for e in catalog
                if (e["ref"] if e["ref"] is not None else e["title"]) == key[1]
                and e["type"] == key[0]
            )
            blocks = ev.metadata.get("context_blocks")
            if blocks is not None:
                merged = sorted(
                    set(entry.get("context_blocks", ())) | set(blocks)
                )
                if merged:
                    entry["context_blocks"] = merged
            continue
        seen.add(key)
        entry: Dict[str, Any] = {
            "type": ev.type,
            "ref": ev.ref,
            "title": ev.title,
            "provenance": ev.provenance.strip() or TYPE_PROVENANCE[ev.type],
        }
        blocks = ev.metadata.get("context_blocks")
        if blocks is not None:
            entry["context_blocks"] = sorted(set(blocks))
        catalog.append(entry)
    return catalog


def _evidence_for_entry(
    ep: EvidencePack, entry: Dict[str, Any]
) -> EvidenceRef:
    """Return the first EvidenceRef matching a catalog entry."""
    for ev in ep.evidence:
        if (
            ev.type == entry["type"]
            and (ev.ref == entry["ref"] or ev.title == entry["title"])
        ):
            return ev
    raise AssertionError(f"no evidence for catalog entry {entry!r}")


def _derive_confidence(sources: list[dict]) -> str:
    """SCHEMA.md §1 confidence derivation (deterministic)."""
    if not sources:
        return "low"
    if len(sources) >= 2 and len({s["type"] for s in sources}) >= 2:
        return "high"
    if len(sources) >= 2:
        return "medium"
    return "low"


def _date_from_iso(iso: str) -> Optional[date]:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", iso or "")
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _build_create_operations(
    ep: EvidencePack,
    slug: str,
    sources: list[dict],
    gfm_body: str,
    confidence: str,
    today: date,
) -> Tuple[Tuple[PatchOperation, ...], str, str]:
    """CREATE_PAGE operation: full canonical page content."""
    frontmatter = _build_canonical_frontmatter(ep, sources, today=today)
    content = _render_page(frontmatter, gfm_body)
    operations = (
        PatchOperation(
            op="CREATE_PAGE",
            section=None,
            content=content,
            metadata={
                "title": ep.subject_title,
                "created": today.isoformat(),
                "last_updated": today.isoformat(),
                "confidence_level": confidence,
            },
        ),
    )
    reason = (
        f"Create canonical {ep.subject_slug!r} page from evidence pack "
        f"{ep.pack_id} ({len(sources)} source(s))"
    )
    return operations, "auto_apply", reason


def _build_update_operations(
    ep: EvidencePack,
    slug: str,
    gfm_body: str,
    confidence: str,
    today: date,
) -> Tuple[Tuple[PatchOperation, ...], str, str]:
    """Scoped update operations: MERGE_SOURCES + UPSERT_SECTION +
    SET_METADATA. Never rewrites existing frontmatter/body wholesale."""
    operations: List[PatchOperation] = [
        PatchOperation(op="MERGE_SOURCES", section=None, content=None,
                       metadata=None),
    ]
    if gfm_body:
        section = DEFAULT_SECTION
        for ev in ep.evidence:
            override = ev.metadata.get("section")
            if isinstance(override, str) and override.strip():
                section = override.strip()
                break
        operations.append(
            PatchOperation(op="UPSERT_SECTION", section=section,
                           content=gfm_body, metadata=None)
        )
    operations.append(
        PatchOperation(
            op="SET_METADATA",
            section=None,
            content=None,
            metadata={
                "last_updated": today.isoformat(),
                "confidence_level": confidence,
            },
        )
    )
    reason = (
        f"Update existing page {ep.subject_slug!r}: merge sources, refresh "
        f"metadata, upsert scoped section"
    )
    return tuple(operations), "suggestion_only", reason


def _render_page(frontmatter: dict, gfm_body: str) -> str:
    """Render frontmatter dict + body into a complete canonical page."""
    parts = ["---", _render_yaml(frontmatter).rstrip("\n"), "---", "",
             f"# {frontmatter['title']}"]
    if gfm_body:
        parts += ["", gfm_body]
    parts += ["", _build_references_section(frontmatter["sources"]).rstrip("\n")]
    return "\n".join(parts) + "\n"


def _render_yaml(data: dict) -> str:
    """Minimal deterministic YAML renderer for the canonical frontmatter.

    Strings are emitted double-quoted; ``ref`` omitted when None; lists are
    indented two spaces. No external YAML dependency.
    """
    lines: List[str] = []
    for key, value in data.items():
        if key == "sources":
            lines.append("sources:")
            for entry in value:
                lines.append("  - type: " + entry["type"])
                if entry.get("ref") is not None:
                    lines.append("    ref: " + _yaml_str(entry["ref"]))
                lines.append("    title: " + _yaml_str(entry["title"]))
                lines.append("    provenance: " + _yaml_value(entry["provenance"]))
        else:
            lines.append(f"{key}: " + _yaml_str(value))
    return "\n".join(lines) + "\n"


def _yaml_value(value: Any) -> str:
    """YAML scalar: unquoted for safe tokens, quoted otherwise."""
    s = str(value)
    if re.fullmatch(r"[A-Za-z0-9_.-]+", s):
        return s
    return _yaml_str(s)


def _yaml_str(value: Any) -> str:
    """Double-quoted YAML scalar (deterministic, safe for dates/URLs/hex)."""
    s = str(value)
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'

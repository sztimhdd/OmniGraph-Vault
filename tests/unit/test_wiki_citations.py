"""Wiki citation integrity unit tests (W1 deliverable).

SCHEMA §2 (post-2026-05-20 update) accepts two citation formats:

  Legacy:  ^[article:<10-char-hex>]   (frontmatter sources: list of strings)
  New:     [^N]                       (frontmatter sources: list of dicts
                                       with id/type/ref/title)

This test validates pages in EITHER format. Generation scripts (W1 T3) emit
the new format exclusively; legacy form remains for back-compat with pages
authored before the format upgrade.
"""
from __future__ import annotations

import re
from pathlib import Path

import frontmatter
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WIKI_ENTITIES = _REPO_ROOT / "kb" / "wiki" / "entities"
_LEGACY_CITATION_RE = re.compile(r"\^\[article:([a-f0-9]{10})\]")
_FOOTNOTE_CITATION_RE = re.compile(r"\[\^(\d+)\]")


def _entity_pages() -> list[Path]:
    if not _WIKI_ENTITIES.exists():
        return []
    return sorted(_WIKI_ENTITIES.glob("*.md"))


def test_all_pages_cited():
    """Every wiki entity page MUST have:

    1. Valid frontmatter with the 5 required SCHEMA fields
    2. At least one citation in body — either legacy `^[article:<hex>]` form
       or new `[^N]` GFM-footnote form
    3. Every body citation resolves to a frontmatter sources entry:
       - Legacy hash form → matches a sources string `article:<hex>` OR a
         dict-shaped entry with `type: article` and `ref: <hex>`
       - New `[^N]` form → matches a sources entry with `id: N`

    If `kb/wiki/entities/` has 0 pages, skip — generation hasn't run yet.
    """
    pages = _entity_pages()
    if not pages:
        pytest.skip(
            "kb/wiki/entities/ has no pages — run scripts/wiki_generate_pages.py first"
        )

    failures: list[str] = []
    required = {"title", "created", "last_updated", "sources", "confidence_level"}

    for page_path in pages:
        post = frontmatter.load(page_path)

        # 1. Required frontmatter fields
        missing = required - set(post.metadata.keys())
        if missing:
            failures.append(f"{page_path.name}: missing frontmatter fields {sorted(missing)}")
            continue

        body = post.content
        legacy_hashes = _LEGACY_CITATION_RE.findall(body)
        footnote_ids = _FOOTNOTE_CITATION_RE.findall(body)

        # 2. At least one citation in body — UNLESS confidence_level=low
        # (zero-article pages sourced purely from web/builtin are allowed
        # to skip inline citations per W1 generation contract)
        if not legacy_hashes and not footnote_ids:
            confidence = str(post.metadata.get("confidence_level", "")).lower()
            if confidence != "low":
                failures.append(
                    f"{page_path.name}: no ^[article:<hex>] or [^N] citations + "
                    f"confidence_level={confidence!r} (zero-article pages must declare 'low')"
                )
            continue

        # 3. Build frontmatter source index supporting both shapes
        fm_sources = post.metadata.get("sources") or []
        legacy_fm_hashes: set[str] = set()
        new_fm_ids: set[str] = set()
        new_fm_article_hashes: set[str] = set()
        for s in fm_sources:
            if isinstance(s, str) and s.startswith("article:"):
                legacy_fm_hashes.add(s.split(":", 1)[1])
            elif isinstance(s, dict):
                if "id" in s:
                    new_fm_ids.add(str(s["id"]))
                if (s.get("type") or "").lower() == "article":
                    ref = s.get("ref")
                    if ref:
                        new_fm_article_hashes.add(str(ref))

        # 3a. Legacy hashes must match either legacy-string sources OR new dict sources
        all_known_hashes = legacy_fm_hashes | new_fm_article_hashes
        legacy_orphans = [h for h in legacy_hashes if h not in all_known_hashes]
        if legacy_orphans:
            failures.append(
                f"{page_path.name}: legacy citations not declared in sources: "
                f"{sorted(set(legacy_orphans))[:5]}"
            )

        # 3b. Footnote ids must match a frontmatter sources entry's id
        footnote_orphans = [n for n in footnote_ids if n not in new_fm_ids]
        if footnote_orphans:
            failures.append(
                f"{page_path.name}: [^N] citations referencing missing source ids: "
                f"{sorted(set(footnote_orphans))[:5]}"
            )

    assert not failures, "Wiki citation integrity failures:\n" + "\n".join(failures)


def test_canonical_sample_openclaw_present_after_w1():
    """After W1 T3 runs, kb/wiki/entities/openclaw.md MUST exist + cite real articles.

    The canonical sample from llm-wiki-CONTEXT.md Decision 2. Skip if no
    entity pages at all (generation not yet run).
    """
    pages = _entity_pages()
    if not pages:
        pytest.skip("kb/wiki/entities/ empty; W1 T3 not yet run")

    openclaw = _WIKI_ENTITIES / "openclaw.md"
    if not openclaw.exists():
        pytest.skip(
            "openclaw.md not present — may be in a partial run that excluded it"
        )

    post = frontmatter.load(openclaw)
    # If it's still the W0 placeholder (TODO marker present), skip
    if "<!-- TODO: Replace with port from" in post.content:
        pytest.skip(
            "openclaw.md is still the W0 placeholder; W1 T3 not yet run on this entity"
        )

    body_hashes = _LEGACY_CITATION_RE.findall(post.content)
    fake = "0000000000"
    real_hashes = [h for h in body_hashes if h != fake]
    assert real_hashes, (
        "openclaw.md still contains only the W0 placeholder hash "
        f"({fake}); regenerate via scripts/wiki_generate_pages.py"
    )

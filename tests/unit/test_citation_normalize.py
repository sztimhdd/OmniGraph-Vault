"""ISSUES #29 behavior pin: kb.services.synthesize._normalize_citations must
normalize all 7 LLM-emitted orphan citation shapes to clickable markdown links
``[<hash6>](articles/<hash>.html)`` and dedupe duplicate References sections —
server-side, so non-browser consumers (Hermes skill, /api/synthesize JSON, CLI)
get clean markdown without relying on the client-side qa.js sweep.

Mirrors qa.js rewriteOrphanCitations Pass 1 + Pass 2 + References dedupe.
"""
from __future__ import annotations

import pytest

from kb.services.synthesize import _normalize_citations

H = "abc1234567"  # canonical 10-hex test hash
LINK = f"[{H[:6]}](articles/{H}.html)"

# 7 orphan formats from ISSUES #29 → all must normalize to LINK.
ORPHAN_CASES = [
    pytest.param(f"See [/article/{H}] here.", f"See {LINK} here.", id="slash-article-slash"),
    pytest.param(f"See [/article:{H}] here.", f"See {LINK} here.", id="slash-article-colon"),
    pytest.param(f"See [article/{H}] here.", f"See {LINK} here.", id="article-slash"),
    pytest.param(f"See [article:{H}] here.", f"See {LINK} here.", id="article-colon"),
    pytest.param(f"See [article-{H}] here.", f"See {LINK} here.", id="article-dash"),
    pytest.param(f"See [article {H}] here.", f"See {LINK} here.", id="article-space"),
    pytest.param(f"See [{H}] here.", f"See {LINK} here.", id="bare-hash"),
]


@pytest.mark.unit
@pytest.mark.parametrize("raw, expected", ORPHAN_CASES)
def test_orphan_citation_normalized(raw: str, expected: str) -> None:
    assert _normalize_citations(raw) == expected


@pytest.mark.unit
def test_already_clean_link_is_idempotent() -> None:
    """A correct ``[label](articles/<hash>.html)`` link must pass through
    untouched, and a second pass must not double-rewrite (Pass 2's negative
    look-ahead skips already-linked hashes)."""
    clean = f"Result [{H[:6]}](articles/{H}.html) done."
    once = _normalize_citations(clean)
    assert once == clean
    assert _normalize_citations(once) == clean  # idempotent


@pytest.mark.unit
def test_dual_references_dedup_keeps_densest() -> None:
    """Two References sections → keep the one with more links, drop the other."""
    h2 = "def4567890"
    md = (
        "# Answer\n\nBody text.\n\n"
        "## References\n\n"
        "- disclaimer, no links here\n\n"
        "## References\n\n"
        f"- [{H[:6]}](articles/{H}.html)\n"
        f"- [{h2[:6]}](articles/{h2}.html)\n"
    )
    out = _normalize_citations(md)
    # Exactly one References heading survives.
    assert out.count("## References") == 1
    # The surviving section is the link-dense one.
    assert f"articles/{H}.html" in out
    assert f"articles/{h2}.html" in out
    assert "disclaimer, no links here" not in out


@pytest.mark.unit
def test_real_markdown_link_not_double_processed() -> None:
    """A bare-hash regex must not touch ``[hash](...)`` that is already a link."""
    md = f"[{H}](articles/{H}.html) and orphan [{H}]"
    out = _normalize_citations(md)
    # The already-linked one is unchanged; the orphan becomes a link.
    assert out == f"[{H}](articles/{H}.html) and orphan {LINK}"

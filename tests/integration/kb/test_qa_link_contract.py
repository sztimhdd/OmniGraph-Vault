"""Regression tests pinning qa.js source-chip link contract and state name.

Closes kb-3-12 test gap: these were the exact defects applied as hotfixes on
Aliyun production (2026-05-15) that the prior test suite did not cover.

Test strategy: mock-free string assertion against qa.js source file.
No DOM, no browser, no server — pure pattern matching on the JS source text.
This is intentional: the contract is about what strings are PRESENT and ABSENT
in the source; a wrong string in qa.js is the defect we're guarding against.
"""
import pathlib

_QA_JS = (pathlib.Path(__file__).parent.parent.parent.parent / "kb" / "static" / "qa.js").read_text(encoding="utf-8")


def test_source_chip_path_uses_articles_plural():
    """Source chip href must use /articles/ (plural) to match the SSG output path.

    kb-3-12 defect: qa.js had /article/ (singular) which caused 404 on click.
    The SSG writes articles to kb/output/articles/{hash}.html (plural).
    """
    assert "/articles/' + encodeURIComponent" in _QA_JS, (
        "qa.js source chip must use /articles/ (plural) — not /article/ (singular)"
    )
    assert "/article/' + encodeURIComponent" not in _QA_JS, (
        "qa.js must NOT contain the old /article/ (singular) href pattern"
    )


def test_source_chip_path_includes_kb_base_path():
    """Source chip href must prepend window.KB_BASE_PATH so /kb-prefixed deploys work.

    Without KB_BASE_PATH the chip resolves to /articles/{hash}.html which 404s
    on a sub-path Aliyun deploy (e.g. hosted at /kb/).
    """
    assert "(window.KB_BASE_PATH || '') + '/articles/'" in _QA_JS, (
        "qa.js source chip must prepend (window.KB_BASE_PATH || '') to the /articles/ path"
    )


def test_state_name_is_fts5_fallback():
    """Both fallback setState calls must use 'fts5_fallback', not bare 'fallback'.

    kb-3-12 defect: qa.js used setState('fallback') which does not match the
    CSS selector [data-qa-state='fts5_fallback'] defined in style.css (UI-SPEC §3.2 D-8).
    The timeout branch AND the fallback_used=true branch both must use fts5_fallback.
    """
    import re
    hits = re.findall(r"setState\('fts5_fallback'\)", _QA_JS)
    assert len(hits) >= 2, (
        f"Expected >=2 setState('fts5_fallback') calls in qa.js, found {len(hits)}"
    )
    # Forbidden: bare 'fallback' state (would not match CSS selector)
    bare_hits = re.findall(r"setState\('fallback'\)", _QA_JS)
    assert len(bare_hits) == 0, (
        f"qa.js must NOT contain setState('fallback') — found {len(bare_hits)} instance(s)"
    )

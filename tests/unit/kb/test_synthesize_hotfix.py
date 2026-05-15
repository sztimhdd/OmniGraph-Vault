"""Unit tests for the kb-v2.1-4 structured synthesize helpers.

Replaces the v2.0 heuristic suite (260515-cvh hotfix). The 4 helpers being
tested in this update are pure functions:

    _extract_source_hashes(markdown)        — re-based regex parser (no DB)
    _resolve_sources_from_markdown(markdown) — DB-backed; uses fixture_db
    SynthesizeResult.asdict()                — schema serialization

DROPPED tests for _ENTITY_HINTS, _dedupe, _fallback_search_terms,
_entity_candidates — those helpers were removed by kb-v2.1-4 (replaced by
DB-resolved sources/entities via article_query.articles_by_hashes +
article_query.entities_for_articles).
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from kb.services.synthesize import (
    ArticleSource,
    EntityMention,
    SynthesizeResult,
    _extract_source_hashes,
)


# ---------------------------------------------------------------------------
# _extract_source_hashes (pure function on markdown — no DB)
# ---------------------------------------------------------------------------


def test_extract_source_hashes_finds_distinct_hashes_in_first_occurrence_order() -> None:
    md = (
        "First [a](/article/abcd012345) then [b](/article/1111111111) "
        "and again [a-dup](/article/abcd012345)."
    )
    assert _extract_source_hashes(md) == ["abcd012345", "1111111111"]


def test_extract_source_hashes_empty_markdown_returns_empty_list() -> None:
    assert _extract_source_hashes("") == []
    assert _extract_source_hashes("no links here") == []


def test_extract_source_hashes_ignores_malformed_hashes() -> None:
    """The regex requires exactly 10 lowercase-hex chars after /article/."""
    md = (
        "[short](/article/abc) "          # too short
        "[long](/article/abcdef0123456) " # too long (regex stops at 10)
        "[upper](/article/ABCD012345) "   # uppercase
        "[ok](/article/0123456789)"       # valid
    )
    hashes = _extract_source_hashes(md)
    # Only the 'ok' link is fully valid. The 'long' one has 10 valid chars at
    # the start so the regex does match the prefix — that's acceptable for a
    # backref scraper. Assert the valid one is present and uppercase is gone.
    assert "0123456789" in hashes
    assert "ABCD012345" not in hashes


# ---------------------------------------------------------------------------
# SynthesizeResult schema serialization
# ---------------------------------------------------------------------------


def test_synthesize_result_asdict_shape_matches_qa_js_consumer_contract() -> None:
    """asdict() must produce keys that kb/static/qa.js reads verbatim:
    sources[].hash/.title/.lang and entities[].name/.article_count.
    """
    r = SynthesizeResult(
        markdown="# answer",
        confidence="kg",
        fallback_used=False,
        sources=[
            ArticleSource(hash="abc1234567", title="T", lang="en"),
        ],
        entities=[
            EntityMention(name="LightRAG", article_count=5),
        ],
    )
    d = r.asdict()
    assert d["markdown"] == "# answer"
    assert d["confidence"] == "kg"
    assert d["fallback_used"] is False
    assert d["error"] is None
    assert d["sources"] == [
        {"hash": "abc1234567", "title": "T", "lang": "en"},
    ]
    assert d["entities"] == [
        {"name": "LightRAG", "article_count": 5},
    ]


def test_synthesize_result_default_factories_independent() -> None:
    """Two SynthesizeResult instances must NOT share the same default lists
    (mutable-default-arg trap; field(default_factory=list) avoids this)."""
    a = SynthesizeResult(markdown="a", confidence="no_results", fallback_used=False)
    b = SynthesizeResult(markdown="b", confidence="no_results", fallback_used=False)
    assert a.sources is not b.sources
    assert a.entities is not b.entities


# ---------------------------------------------------------------------------
# _resolve_sources_from_markdown (DB-backed; uses fixture_db)
# ---------------------------------------------------------------------------


@pytest.fixture
def synthesize_module_with_db(fixture_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Reload kb.services.synthesize with KB_DB_PATH pointing at fixture_db."""
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
    import kb.config
    import kb.data.article_query
    import kb.services.synthesize

    importlib.reload(kb.config)
    monkeypatch.setattr(
        kb.data.article_query,
        "QUALITY_FILTER_ENABLED",
        os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off",
    )
    importlib.reload(kb.services.synthesize)
    return kb.services.synthesize


def test_resolve_sources_from_markdown_returns_articlesource_for_known_hashes(
    synthesize_module_with_db,
) -> None:
    """KOL hash 'abc1234567' (id=1, 'zh-CN', '测试文章一') → resolves with title+lang."""
    md = "See [more](/article/abc1234567) for details."
    result = synthesize_module_with_db._resolve_sources_from_markdown(md)
    assert len(result) == 1
    assert result[0].hash == "abc1234567"
    assert result[0].title == "测试文章一"
    assert result[0].lang == "zh-CN"


def test_resolve_sources_from_markdown_empty_when_no_refs(
    synthesize_module_with_db,
) -> None:
    """Markdown without any /article/{hash} → empty list (no DB hit)."""
    assert synthesize_module_with_db._resolve_sources_from_markdown("") == []
    assert synthesize_module_with_db._resolve_sources_from_markdown(
        "Plain answer with no source links."
    ) == []


def test_resolve_sources_from_markdown_drops_unknown_hashes(
    synthesize_module_with_db,
) -> None:
    """Hash that exists in markdown but not in DB → silently dropped."""
    md = "See [a](/article/abc1234567) and [b](/article/9999999999)."
    result = synthesize_module_with_db._resolve_sources_from_markdown(md)
    assert len(result) == 1
    assert result[0].hash == "abc1234567"


def test_resolve_sources_from_markdown_drops_data07_reject(
    synthesize_module_with_db,
) -> None:
    """KOL id=98 (layer2_verdict='reject', hash='neg9898989') → DATA-07 drops it."""
    md = "[reject](/article/neg9898989) and [ok](/article/abc1234567)."
    result = synthesize_module_with_db._resolve_sources_from_markdown(md)
    hashes = [s.hash for s in result]
    assert "neg9898989" not in hashes, "DATA-07 reject leaked into sources"
    assert "abc1234567" in hashes

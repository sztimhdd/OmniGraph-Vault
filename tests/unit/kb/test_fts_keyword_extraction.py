"""#75: QA fallback keyword extraction — _extract_fts_keywords.

The FTS5 fallback used to feed the whole natural-language question to a phrase-
literal MATCH, which almost never hit (e.g. "什么是AI Agent" → 0 rows although
"AI Agent" → 3). _extract_fts_keywords strips EN/ZH stopwords + leading ZH
stop-prefixes so the per-keyword union query reliably matches the trigram index
without any embedding/network (works while #75 cross-border egress is down).

Pure function — these are fast, deterministic, no DB / no LightRAG.
"""

import pytest

from kb.services.synthesize import _extract_fts_keywords


@pytest.mark.unit
@pytest.mark.parametrize(
    "question,expected",
    [
        # ZH question with embedded EN term — stop-prefix "什么是" stripped off "AI"
        ("什么是AI Agent", ["AI", "Agent"]),
        # mixed ZH/EN with ZH possessive — keeps content tokens
        ("什么是agent的harness", ["agent", "harness"]),
        # English question — EN stopwords dropped
        ("What is an AI agent", ["AI", "agent"]),
        # comparison question — "和"/"的"/"区别" are stopwords
        ("AI Agent和RPA的区别", ["AI", "Agent", "RPA"]),
        # pure-English with vs
        ("LangGraph vs CrewAI", ["LangGraph", "CrewAI"]),
    ],
)
def test_extracts_content_keywords(question, expected):
    assert _extract_fts_keywords(question) == expected


@pytest.mark.unit
def test_all_stopwords_returns_empty():
    # caller falls back to the raw question when nothing survives
    assert _extract_fts_keywords("什么是") == []
    assert _extract_fts_keywords("what is the") == []


@pytest.mark.unit
def test_empty_and_none_safe():
    assert _extract_fts_keywords("") == []
    assert _extract_fts_keywords(None) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_order_preserved_first_seen():
    # keyword order follows the question, not sorted
    assert _extract_fts_keywords("RAG 检索质量 评估") == ["RAG", "检索质量", "评估"]

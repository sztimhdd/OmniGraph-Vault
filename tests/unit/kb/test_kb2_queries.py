"""TDD tests for kb-2 article_query.py extensions (plan kb-2-04).

Consumes the shared fixture_db from tests/integration/kb/conftest.py.
Tests use direct sqlite3.connect(fixture_path) + conn= injection — no mocks.
Per Testing Trophy: integration > E2E > unit; these are integration-flavored
unit tests against real SQLite.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from kb.data.article_query import (
    EntityCount,
    TopicSummary,
    cooccurring_entities_in_topic,
    entity_articles_query,
    related_entities_for_article,
    related_topics_for_article,
    slugify_entity_name,
    topic_articles_query,
)

# Reuse the shared fixture (build_kb2_fixture_db + fixture_db)
pytest_plugins = ["tests.integration.kb.conftest"]


# ---------- slugify_entity_name (5 tests) ----------


def test_slugify_ascii_normal():
    """Test 1: lowercased ASCII."""
    assert slugify_entity_name("OpenAI") == "openai"


def test_slugify_ascii_with_space():
    """Test 2: internal whitespace collapses to '-'."""
    assert slugify_entity_name("Lang Chain") == "lang-chain"


def test_slugify_ascii_with_slash():
    """Test 3: slash dropped (not replaced)."""
    assert slugify_entity_name("foo/bar") == "foobar"


def test_slugify_unicode_cjk():
    """Test 4: CJK preserved verbatim."""
    assert slugify_entity_name("叶小钗") == "叶小钗"


def test_slugify_collapses_whitespace():
    """Test 5: leading/trailing whitespace stripped."""
    assert slugify_entity_name("  hi  ") == "hi"


# ---------- topic_articles_query (4 tests) ----------


def _conn(fixture_db: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(fixture_db))


def test_topic_articles_agent_returns_union(fixture_db):
    """Test 6 + Test 9: Agent returns 5 articles UNION-ed across KOL + RSS."""
    with _conn(fixture_db) as c:
        results = topic_articles_query("Agent", conn=c)
    assert len(results) == 5  # 3 KOL (1, 3, 5) + 2 RSS (10, 11) per fixture
    sources = {r.source for r in results}
    assert sources == {"wechat", "rss"}  # UNION proven


def test_topic_articles_cv_sorted_desc(fixture_db):
    """Test 7: CV sorted by update_time DESC.

    Fixture: article 2 KOL (update_time epoch 1778180400 → ISO via
    _row_to_record_kol normalization) + article 12 RSS published_at
    "2026-05-08 08:00:00". Both ISO-comparable; the RSS string starts
    "2026-05-08" while the KOL epoch normalizes to "2026-05-03T..." so
    article 12 comes first lexicographically DESC.
    """
    with _conn(fixture_db) as c:
        results = topic_articles_query("CV", conn=c)
    assert len(results) == 2
    assert results[0].source == "rss" and results[0].id == 12


def test_topic_articles_depth_3_filter(fixture_db):
    """Test 8: depth_min=3 narrows to exactly article 5 for LLM."""
    with _conn(fixture_db) as c:
        results = topic_articles_query("LLM", depth_min=3, conn=c)
    assert len(results) == 1
    assert results[0].id == 5


class _SpyConn:
    """Proxy connection capturing every SQL string passed to .execute().

    sqlite3.Connection.execute is a read-only built-in attribute on Python
    3.13, so it can't be monkeypatched directly. This proxy mirrors the
    kb-1 SpyConn pattern.
    """

    def __init__(self, real: sqlite3.Connection):
        self._real = real
        self.statements: list[str] = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        return self._real.execute(sql, params)

    def __getattr__(self, name):
        # Delegate any other attribute (row_factory, close, etc.) to real conn.
        return getattr(self._real, name)


def test_topic_articles_read_only(fixture_db):
    """Test 10: every SQL emitted by topic_articles_query starts with SELECT."""
    with _conn(fixture_db) as c:
        c.row_factory = sqlite3.Row
        spy = _SpyConn(c)
        topic_articles_query("Agent", conn=spy)
    assert spy.statements, "no SQL captured"
    assert all(s.lstrip().upper().startswith("SELECT") for s in spy.statements)


def test_dataclass_shapes_importable():
    """Test 11: EntityCount + TopicSummary dataclasses are constructable."""
    e = EntityCount(name="OpenAI", slug="openai", article_count=42)
    assert e.name == "OpenAI" and e.slug == "openai" and e.article_count == 42
    t = TopicSummary(slug="agent", raw_topic="Agent")
    assert t.slug == "agent" and t.raw_topic == "Agent"


# ---------- entity_articles_query (3 tests) ----------


def test_entity_articles_above_threshold(fixture_db):
    """Test 12: OpenAI freq=5 returns 5 articles (3 KOL + 2 RSS)."""
    with _conn(fixture_db) as c:
        results = entity_articles_query("OpenAI", min_freq=5, conn=c)
    assert len(results) == 5  # OpenAI in 1, 3, 5 KOL + 10, 11 RSS
    ids = {(r.id, r.source) for r in results}
    assert (1, "wechat") in ids and (10, "rss") in ids


def test_entity_articles_below_threshold_empty(fixture_db):
    """Test 13: ObscureLib freq=2 below threshold 5 returns []."""
    with _conn(fixture_db) as c:
        results = entity_articles_query("ObscureLib", min_freq=5, conn=c)
    assert results == []


def test_entity_articles_lowered_threshold_returns_all(fixture_db):
    """Test 14: lowering min_freq to 2 reveals ObscureLib's 2 articles."""
    with _conn(fixture_db) as c:
        results = entity_articles_query("ObscureLib", min_freq=2, conn=c)
    assert len(results) == 2


# ---------- related_entities_for_article (2 tests) ----------


def test_related_entities_for_article(fixture_db):
    """Test 15: article 1 returns ≤5 EntityCounts; all above global threshold; slugified."""
    with _conn(fixture_db) as c:
        results = related_entities_for_article(1, "wechat", conn=c)
    assert all(isinstance(r, EntityCount) for r in results)
    assert len(results) <= 5
    # Each entity's article_count is its global frequency, which must be ≥ 5
    for r in results:
        assert r.article_count >= 5
    # OpenAI slugified
    names_to_slugs = {r.name: r.slug for r in results}
    if "OpenAI" in names_to_slugs:
        assert names_to_slugs["OpenAI"] == "openai"


def test_related_entities_limit_honored(fixture_db):
    """Test 16: limit=3 caps result at 3."""
    with _conn(fixture_db) as c:
        results = related_entities_for_article(1, "wechat", limit=3, conn=c)
    assert len(results) <= 3


# ---------- related_topics_for_article (2 tests) ----------


def test_related_topics_for_article(fixture_db):
    """Test 17: article 1 has Agent (depth=3), LLM (depth=2), RAG (depth=2)."""
    with _conn(fixture_db) as c:
        results = related_topics_for_article(1, "wechat", conn=c)
    assert len(results) == 3
    slugs = [t.slug for t in results]
    assert slugs[0] == "agent"  # depth=3 first


def test_related_topics_depth_filter(fixture_db):
    """Test 18: depth_min=3 narrows to only Agent."""
    with _conn(fixture_db) as c:
        results = related_topics_for_article(1, "wechat", depth_min=3, conn=c)
    assert len(results) == 1
    assert results[0].slug == "agent"
    assert results[0].raw_topic == "Agent"


# ---------- cooccurring_entities_in_topic (1 test) ----------


def test_cooccurring_entities_in_topic(fixture_db):
    """Test 19: top entities within Agent cohort, ranked DESC by topic frequency."""
    with _conn(fixture_db) as c:
        results = cooccurring_entities_in_topic("Agent", limit=5, conn=c)
    assert all(isinstance(r, EntityCount) for r in results)
    assert len(results) <= 5
    # Sorted by topic frequency DESC
    if len(results) >= 2:
        assert results[0].article_count >= results[1].article_count
    # All slugged
    for r in results:
        assert r.slug == slugify_entity_name(r.name)


# ---------- read-only enforcement across all 4 new queries (1 test) ----------


def test_kb2_queries_read_only(fixture_db):
    """Test 20: every SQL emitted by the 4 new queries starts with SELECT or WITH (CTE)."""
    with _conn(fixture_db) as c:
        c.row_factory = sqlite3.Row
        spy = _SpyConn(c)
        entity_articles_query("OpenAI", conn=spy)
        related_entities_for_article(1, "wechat", conn=spy)
        related_topics_for_article(1, "wechat", conn=spy)
        cooccurring_entities_in_topic("Agent", conn=spy)
    assert spy.statements, "no SQL captured"
    for s in spy.statements:
        head = s.lstrip().upper()
        assert head.startswith("SELECT") or head.startswith("WITH"), (
            f"non-read SQL leaked: {s[:80]!r}"
        )

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


# Sanity: dataclass shapes are importable (they will be exercised in Task 2).
def test_dataclass_shapes_importable():
    """Test 11: EntityCount + TopicSummary dataclasses are constructable."""
    e = EntityCount(name="OpenAI", slug="openai", article_count=42)
    assert e.name == "OpenAI" and e.slug == "openai" and e.article_count == 42
    t = TopicSummary(slug="agent", raw_topic="Agent")
    assert t.slug == "agent" and t.raw_topic == "Agent"

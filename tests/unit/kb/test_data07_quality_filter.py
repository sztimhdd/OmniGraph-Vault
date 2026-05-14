"""DATA-07 content-quality filter tests.

Two parts:
- Task 1: env override + schema guard + fixture extension (tests 1-7).
- Task 2: filter applied to 6 list-style query functions + carve-out
  preserved on get_article_by_hash + env-off override + read-only spy
  (tests 8-17).

All tests use the shared fixture_db from tests/integration/kb/conftest.py
which has positive AND negative DATA-07 rows on both KOL + RSS tables.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# Reuse the shared fixture (build_kb2_fixture_db + fixture_db)
pytest_plugins = ["tests.integration.kb.conftest"]


def _eval_quality_filter_env(env_value):
    """Reproduce the import-time expression used by article_query.py.

    Tests verify the expression's behavior without reloading the module
    (reload would invalidate EntityCount/TopicSummary class identity for
    downstream test files).
    """
    import os

    raw = env_value if env_value is not None else os.environ.get(
        "KB_CONTENT_QUALITY_FILTER", "on"
    )
    return raw.lower() != "off"


@pytest.fixture(autouse=True)
def _restore_article_query_module():
    """Clear schema-verified cache + restore QUALITY_FILTER_ENABLED=True.

    Some tests flip the module-level flag via monkeypatch; after those,
    QUALITY_FILTER_ENABLED on the module may be False. Restore to True
    after each test so subsequent tests see expected state.
    """
    yield
    import kb.data.article_query as aq

    aq._SCHEMA_VERIFIED.clear()
    aq.QUALITY_FILTER_ENABLED = True


def _conn(fixture_db: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(fixture_db))
    c.row_factory = sqlite3.Row
    return c


# ---------- Task 1: env override (3 tests) ----------


def test_quality_filter_enabled_default():
    """Test 1: unset env -> QUALITY_FILTER_ENABLED expression evaluates True.

    Uses isolated re-evaluation (not module reload) to avoid invalidating
    EntityCount/TopicSummary class identity for downstream test files.
    """
    assert _eval_quality_filter_env(None) is True
    # Verify the actual import-time value matches when env is unset.
    # We need to construct the expression manually since the module-level
    # constant is bound once at import.
    import os

    if os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off":
        from kb.data.article_query import QUALITY_FILTER_ENABLED

        assert QUALITY_FILTER_ENABLED is True


def test_quality_filter_disabled_via_off():
    """Test 2: KB_CONTENT_QUALITY_FILTER=off makes the expression evaluate False."""
    assert _eval_quality_filter_env("off") is False


def test_quality_filter_disabled_case_insensitive():
    """Test 3: uppercase 'OFF' is treated identical to 'off' (case-insensitive)."""
    assert _eval_quality_filter_env("OFF") is False
    # Plus other casings to lock down the .lower() contract.
    assert _eval_quality_filter_env("Off") is False
    assert _eval_quality_filter_env("oFf") is False
    # And non-off values keep filter on.
    assert _eval_quality_filter_env("on") is True
    assert _eval_quality_filter_env("yes") is True
    assert _eval_quality_filter_env("anything") is True


# ---------- Task 1: schema guard (2 tests) ----------


def test_schema_guard_raises_on_missing_column():
    """Test 4: missing layer1_verdict on articles -> RuntimeError mentioning the column."""
    from kb.data.article_query import _SCHEMA_VERIFIED, _verify_quality_columns

    _SCHEMA_VERIFIED.clear()
    c = sqlite3.connect(":memory:")
    try:
        c.execute(
            "CREATE TABLE articles (id INTEGER PRIMARY KEY, body TEXT, layer2_verdict TEXT)"
        )
        c.execute(
            "CREATE TABLE rss_articles (id INTEGER PRIMARY KEY, body TEXT, "
            "layer1_verdict TEXT, layer2_verdict TEXT)"
        )
        with pytest.raises(RuntimeError, match=r"layer1_verdict"):
            _verify_quality_columns(c)
    finally:
        c.close()


def test_schema_guard_passes_on_healthy_fixture(fixture_db):
    """Test 5: fixture_db has all 3 columns on both tables -> no raise."""
    from kb.data.article_query import _SCHEMA_VERIFIED, _verify_quality_columns

    _SCHEMA_VERIFIED.clear()
    c = _conn(fixture_db)
    try:
        _verify_quality_columns(c)  # should NOT raise
    finally:
        c.close()


# ---------- Task 1: fixture extension (2 tests) ----------


def test_fixture_has_positive_verdict_rows(fixture_db):
    """Test 6: fixture has ≥3 positive KOL rows passing all 3 filter conditions."""
    c = _conn(fixture_db)
    try:
        kol_pos = c.execute(
            "SELECT COUNT(*) FROM articles "
            "WHERE body IS NOT NULL AND body != '' "
            "AND layer1_verdict = 'candidate' "
            "AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')"
        ).fetchone()[0]
        rss_pos = c.execute(
            "SELECT COUNT(*) FROM rss_articles "
            "WHERE body IS NOT NULL AND body != '' "
            "AND layer1_verdict = 'candidate' "
            "AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')"
        ).fetchone()[0]
        assert kol_pos >= 3, f"need ≥3 positive KOL rows, got {kol_pos}"
        assert rss_pos >= 3, f"need ≥3 positive RSS rows, got {rss_pos}"
    finally:
        c.close()


def test_fixture_has_negative_verdict_rows(fixture_db):
    """Test 7: fixture has ≥2 negative rows per source (rows DATA-07 must exclude)."""
    c = _conn(fixture_db)
    try:
        kol_neg = c.execute(
            "SELECT COUNT(*) FROM articles "
            "WHERE body IS NULL OR body = '' "
            "OR layer1_verdict = 'reject' OR layer2_verdict = 'reject'"
        ).fetchone()[0]
        rss_neg = c.execute(
            "SELECT COUNT(*) FROM rss_articles "
            "WHERE body IS NULL OR body = '' "
            "OR layer1_verdict = 'reject' OR layer2_verdict = 'reject'"
        ).fetchone()[0]
        assert kol_neg >= 2, f"need ≥2 negative KOL rows, got {kol_neg}"
        assert rss_neg >= 2, f"need ≥2 negative RSS rows, got {rss_neg}"
    finally:
        c.close()


# ---------- Task 2 helpers ----------


class _SpyConn:
    """Proxy connection capturing every SQL string passed to .execute().
    Mirrors the kb-1/kb-2 SpyConn pattern.
    """

    def __init__(self, real: sqlite3.Connection):
        self._real = real
        self.statements: list[str] = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        return self._real.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _hash_for_layer2_reject_kol_row(fixture_db: Path) -> str:
    """Return URL hash of the layer2_verdict='reject' KOL fixture row (id=98)."""
    from kb.data.article_query import _row_to_record_kol, resolve_url_hash

    c = _conn(fixture_db)
    try:
        row = c.execute(
            "SELECT id, title, url, body, content_hash, lang, update_time "
            "FROM articles WHERE layer2_verdict = 'reject' LIMIT 1"
        ).fetchone()
        assert row is not None, "fixture must have a layer2_verdict='reject' row"
        return resolve_url_hash(_row_to_record_kol(row))
    finally:
        c.close()


# ---------- Task 2: filter applied to 6 list-style functions (6 tests) ----------


def _setup_filter_on(monkeypatch):
    """Force QUALITY_FILTER_ENABLED=True via setattr (no reload).

    Avoids module reload — reload would create new EntityCount/TopicSummary
    class objects that invalidate isinstance() checks in other test files.
    """
    from kb.data import article_query

    monkeypatch.setattr(article_query, "QUALITY_FILTER_ENABLED", True)
    article_query._SCHEMA_VERIFIED.clear()
    return article_query


def test_list_articles_excludes_negative_rows(fixture_db, monkeypatch):
    """Test 8: list_articles() excludes the 4 negative-case rows when filter on."""
    article_query = _setup_filter_on(monkeypatch)
    with _conn(fixture_db) as c:
        results = article_query.list_articles(limit=1000, conn=c)
    ids = {(r.id, r.source) for r in results}
    # Negative-case rows must NOT appear:
    assert (99, "wechat") not in ids  # body='' AND layer1='reject'
    assert (98, "wechat") not in ids  # layer2='reject'
    assert (97, "rss") not in ids  # body=NULL
    assert (96, "rss") not in ids  # layer1='reject'
    # Positive rows DO appear:
    assert (1, "wechat") in ids
    assert (10, "rss") in ids


def test_topic_articles_query_excludes_negatives(fixture_db, monkeypatch):
    """Test 9: topic_articles_query("Agent") excludes negative rows even if classified.

    Schema reality (Hermes prod 2026-05-14): `classifications` is KOL-only
    (no `source` column).
    """
    article_query = _setup_filter_on(monkeypatch)
    # Inject a classification row for negative KOL id=98 (layer2 reject)
    # to prove DATA-07 gate is the discriminator (not classification absence).
    c = _conn(fixture_db)
    try:
        c.execute(
            "INSERT INTO classifications (article_id, topic, depth_score, classified_at) "
            "VALUES (98, 'Agent', 3, '2026-05-13 10:00:00')"
        )
        c.commit()
        results = article_query.topic_articles_query("Agent", conn=c)
        ids = {(r.id, r.source) for r in results}
        assert (98, "wechat") not in ids, "DATA-07 must exclude layer2_verdict='reject'"
    finally:
        c.close()


def test_entity_articles_query_excludes_negatives(fixture_db, monkeypatch):
    """Test 10: entity_articles_query excludes negatives even if entity-mentioned.

    Schema reality: `extracted_entities` is KOL-only (`entity_name` not `name`,
    no `source` column).
    """
    article_query = _setup_filter_on(monkeypatch)
    c = _conn(fixture_db)
    try:
        # Inject extracted_entities row pointing to negative KOL id=98 with entity_name 'OpenAI'.
        # OpenAI already has freq=5 from positive rows, so threshold gate is already passed.
        c.execute(
            "INSERT INTO extracted_entities (article_id, entity_name, extracted_at) "
            "VALUES (98, 'OpenAI', '2026-05-13 10:00:00')"
        )
        c.commit()
        results = article_query.entity_articles_query("OpenAI", min_freq=5, conn=c)
        ids = {(r.id, r.source) for r in results}
        assert (98, "wechat") not in ids, "DATA-07 must exclude id=98 from entity list"
    finally:
        c.close()


def test_cooccurring_entities_in_topic_excludes_negatives(fixture_db, monkeypatch):
    """Test 11: cooccurring_entities_in_topic cohort excludes negative rows."""
    article_query = _setup_filter_on(monkeypatch)
    c = _conn(fixture_db)
    try:
        # Inject classification + a unique entity 'NegOnly' that ONLY appears on
        # negative KOL id=98 — if cohort excludes negatives, NegOnly will not surface.
        c.execute(
            "INSERT INTO classifications (article_id, topic, depth_score, classified_at) "
            "VALUES (98, 'Agent', 3, '2026-05-13 10:00:00')"
        )
        c.execute(
            "INSERT INTO extracted_entities (article_id, entity_name, extracted_at) "
            "VALUES (98, 'NegOnly', '2026-05-13 10:00:00')"
        )
        c.commit()
        results = article_query.cooccurring_entities_in_topic(
            "Agent", limit=50, min_global_freq=1, conn=c
        )
        names = {r.name for r in results}
        assert "NegOnly" not in names, (
            "DATA-07 cohort must exclude negative rows, so entities only "
            "appearing in negative rows must not surface"
        )
    finally:
        c.close()


def test_related_entities_for_article_returns_empty_for_negative_source(
    fixture_db, monkeypatch
):
    """Test 12: related_entities_for_article on a negative-row source returns []."""
    article_query = _setup_filter_on(monkeypatch)
    c = _conn(fixture_db)
    try:
        # Inject extracted_entities for negative KOL id=98 — even though
        # entity rows exist, source article fails DATA-07 → return [].
        c.execute(
            "INSERT INTO extracted_entities (article_id, entity_name, extracted_at) "
            "VALUES (98, 'OpenAI', '2026-05-13 10:00:00')"
        )
        c.commit()
        results = article_query.related_entities_for_article(98, "wechat", conn=c)
        assert results == [], "negative source article must yield empty related-entities"
    finally:
        c.close()


def test_related_topics_for_article_returns_empty_for_negative_source(
    fixture_db, monkeypatch
):
    """Test 13: related_topics_for_article on negative-row source returns []."""
    article_query = _setup_filter_on(monkeypatch)
    c = _conn(fixture_db)
    try:
        c.execute(
            "INSERT INTO classifications (article_id, topic, depth_score, classified_at) "
            "VALUES (98, 'Agent', 3, '2026-05-13 10:00:00')"
        )
        c.commit()
        results = article_query.related_topics_for_article(98, "wechat", conn=c)
        assert results == [], "negative source article must yield empty related-topics"
    finally:
        c.close()


# ---------- Task 2: carve-out + env override + read-only (4 tests) ----------


def test_get_article_by_hash_carve_out_preserved(fixture_db, monkeypatch):
    """Test 14: get_article_by_hash STILL returns negative-case row (DATA-07 carve-out)."""
    article_query = _setup_filter_on(monkeypatch)
    h = _hash_for_layer2_reject_kol_row(fixture_db)
    with _conn(fixture_db) as c:
        rec = article_query.get_article_by_hash(h, conn=c)
    assert rec is not None, "carve-out: direct hash access must still resolve"
    assert rec.source == "wechat"
    assert rec.id == 98


def test_list_articles_env_off_returns_all_rows(fixture_db, monkeypatch):
    """Test 15: KB_CONTENT_QUALITY_FILTER=off reverts list_articles to unfiltered."""
    from kb.data import article_query

    monkeypatch.setattr(article_query, "QUALITY_FILTER_ENABLED", False)
    article_query._SCHEMA_VERIFIED.clear()
    with _conn(fixture_db) as c:
        results = article_query.list_articles(limit=1000, conn=c)
    ids = {(r.id, r.source) for r in results}
    # With filter off, negative rows must reappear.
    assert (99, "wechat") in ids
    assert (98, "wechat") in ids
    assert (97, "rss") in ids
    assert (96, "rss") in ids


def test_filter_disabled_does_not_run_schema_guard(monkeypatch):
    """Test 16: with filter off, missing-column DB does NOT raise (guard skipped).

    Confirms KB_CONTENT_QUALITY_FILTER=off is a true bypass — operators can
    use it on a pre-DATA-07 schema without first migrating columns.
    """
    from kb.data import article_query

    monkeypatch.setattr(article_query, "QUALITY_FILTER_ENABLED", False)
    article_query._SCHEMA_VERIFIED.clear()
    # Build a stripped-down DB missing layer1_verdict on articles.
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    try:
        c.executescript(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT,
                content_hash TEXT, lang TEXT, update_time TEXT
            );
            CREATE TABLE rss_articles (
                id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT,
                content_hash TEXT, lang TEXT, published_at TEXT, fetched_at TEXT
            );
            INSERT INTO articles (id, title, url, body, content_hash, lang, update_time)
            VALUES (1, 't', 'u', 'b', 'h1', 'en', '2026-01-01');
            """
        )
        # Should NOT raise — filter-off bypasses schema guard.
        results = article_query.list_articles(conn=c, limit=10)
        assert len(results) == 1
    finally:
        c.close()


def test_data07_queries_remain_read_only(fixture_db, monkeypatch):
    """Test 17: every SQL emitted by the 6 filtered functions is SELECT/WITH/PRAGMA."""
    article_query = _setup_filter_on(monkeypatch)
    with _conn(fixture_db) as c:
        spy = _SpyConn(c)
        article_query.list_articles(limit=10, conn=spy)
        article_query.topic_articles_query("Agent", conn=spy)
        article_query.entity_articles_query("OpenAI", min_freq=5, conn=spy)
        article_query.cooccurring_entities_in_topic("Agent", conn=spy)
        article_query.related_entities_for_article(1, "wechat", conn=spy)
        article_query.related_topics_for_article(1, "wechat", conn=spy)
    assert spy.statements, "no SQL captured"
    for s in spy.statements:
        head = s.lstrip().upper()
        # PRAGMA is read-only metadata access (used by schema guard); allow it.
        assert (
            head.startswith("SELECT")
            or head.startswith("WITH")
            or head.startswith("PRAGMA")
        ), f"non-read SQL leaked: {s[:80]!r}"

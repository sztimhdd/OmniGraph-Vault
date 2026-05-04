"""Phase 19 Wave 2 GREEN test for SCH-01."""
import sqlite3


def test_ensure_columns_idempotent():
    """Calling init_rss_schema twice must be safe and leave exactly 5 new columns."""
    from enrichment.rss_schema import init_rss_schema, _ensure_rss_columns

    conn = sqlite3.connect(":memory:")

    # First call creates the table + adds Phase-19 columns.
    init_rss_schema(conn)
    cols_after_first = {r[1] for r in conn.execute("PRAGMA table_info(rss_articles)")}
    expected = {"body", "body_scraped_at", "depth", "topics", "classify_rationale"}
    assert expected <= cols_after_first, (
        f"Phase-19 columns missing after first init: want {expected}, got {cols_after_first}"
    )

    # Second call is a no-op (no exception).
    init_rss_schema(conn)
    cols_after_second = {r[1] for r in conn.execute("PRAGMA table_info(rss_articles)")}
    # Idempotent: column set is unchanged, no duplicates.
    assert cols_after_second == cols_after_first

    # Explicit _ensure_rss_columns call on a fresh connection that already has
    # a pre-existing rss_articles table WITHOUT the Phase-19 columns (simulates
    # an upgrade from a pre-Phase-19 database).
    conn2 = sqlite3.connect(":memory:")
    conn2.execute(
        "CREATE TABLE rss_articles ("
        "id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL, "
        "feed_id INTEGER NOT NULL, enriched INTEGER DEFAULT 0)"
    )
    _ensure_rss_columns(conn2)
    cols_legacy = {r[1] for r in conn2.execute("PRAGMA table_info(rss_articles)")}
    assert expected <= cols_legacy, (
        f"Phase-19 ALTER failed on legacy table: want {expected}, got {cols_legacy}"
    )

    # Second call still no-op.
    _ensure_rss_columns(conn2)
    cols_legacy2 = {r[1] for r in conn2.execute("PRAGMA table_info(rss_articles)")}
    assert cols_legacy2 == cols_legacy

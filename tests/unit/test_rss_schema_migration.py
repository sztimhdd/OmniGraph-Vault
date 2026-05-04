"""RED stub for Phase 19 Wave 2 SCH-01 idempotent ALTER.
Go GREEN when plan 19-02 lands _ensure_rss_columns into enrichment/rss_schema.py."""
import pytest


def test_ensure_columns_idempotent():
    """SCH-01: enrichment.rss_schema._ensure_rss_columns adds 5 columns
    (body, body_scraped_at, depth, topics, classify_rationale) to
    rss_articles; second invocation is a no-op (no IntegrityError, no
    duplicate columns). Test uses sqlite3.connect(':memory:')."""
    pytest.fail("RED — awaiting plan 19-02 (_ensure_rss_columns)")

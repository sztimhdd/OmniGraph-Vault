"""RED stubs for Phase 19 Wave 2 batch_ingest_from_spider.py patches.
Go GREEN when plan 19-02 lands SCR-06 + SCH-02."""
import pytest


def test_classify_full_body_uses_scraper():
    """SCR-06: batch_ingest_from_spider._classify_full_body calls
    lib.scraper.scrape_url(url, site_hint='wechat') instead of
    ingest_wechat.scrape_wechat_ua. Verifies the line-940 hotfix by
    mock-patching lib.scraper.scrape_url and asserting it's awaited."""
    pytest.fail("RED — awaiting plan 19-02 (line-940 hotfix)")


def test_hash_is_sha256_16():
    """SCH-02: batch_ingest_from_spider uses lib.checkpoint.get_article_hash
    at line 275 (16-char SHA-256 hex), NOT inline hashlib.md5(...)[:10]."""
    pytest.fail("RED — awaiting plan 19-02 (hash unification)")

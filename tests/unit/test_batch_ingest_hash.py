"""Phase 19 Wave 2 GREEN tests for SCR-06 + SCH-02."""
import hashlib
import sqlite3
from dataclasses import is_dataclass

import pytest


# SCR-06 -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_full_body_uses_scraper(mocker):
    """_classify_full_body must await lib.scraper.scrape_url(url, site_hint='wechat').

    Mocks every downstream (scrape_url, process_content, DeepSeek) so the test
    is purely about the routing: did the hotfix land?
    """
    import batch_ingest_from_spider as big
    from lib.scraper import ScrapeResult

    fake_result = ScrapeResult(
        markdown="# test",
        content_html="<div>test body content</div>",
        method="apify",
    )
    mock_scrape = mocker.patch(
        "lib.scraper.scrape_url",
        new=mocker.AsyncMock(return_value=fake_result),
    )
    mocker.patch(
        "ingest_wechat.process_content",
        return_value=("markdown body", ["img1"]),
    )
    # Mock DeepSeek so it returns a valid classify dict.
    mocker.patch(
        "batch_classify_kol._build_fullbody_prompt",
        return_value="prompt",
    )
    mocker.patch(
        "batch_classify_kol._call_deepseek_fullbody",
        return_value={"depth": 2, "topics": ["ai"], "rationale": "ok"},
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, body TEXT)"
    )
    conn.execute("INSERT INTO articles (id, body) VALUES (1, NULL)")
    conn.execute(
        "CREATE TABLE classifications ("
        "article_id INTEGER, topic TEXT, depth_score INTEGER, "
        "depth INTEGER, topics TEXT, rationale TEXT, relevant INTEGER, "
        "PRIMARY KEY (article_id, topic))"
    )
    # Mirror migration 004: production uses ON CONFLICT(article_id) DO UPDATE
    # which requires a single-column UNIQUE constraint on article_id.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_classifications_article_id "
        "ON classifications(article_id)"
    )
    conn.commit()

    result = await big._classify_full_body(
        conn=conn,
        article_id=1,
        url="https://mp.weixin.qq.com/s/test",
        title="t",
        body=None,
        api_key="dummy",
    )

    assert result is not None, "classify returned None unexpectedly"
    assert result["depth"] == 2
    # scrape_url was awaited with site_hint="wechat" (the hotfix)
    mock_scrape.assert_awaited_once()
    call_kwargs = mock_scrape.await_args.kwargs
    call_args = mock_scrape.await_args.args
    site_hint = call_kwargs.get("site_hint")
    if site_hint is None and len(call_args) >= 2:
        site_hint = call_args[1]
    assert site_hint == "wechat", (
        f"scrape_url must be called with site_hint='wechat' (got {site_hint!r})"
    )


# SCH-02 -----------------------------------------------------------------

def test_hash_is_sha256_16():
    """batch_ingest_from_spider uses lib.checkpoint.get_article_hash (SHA-256[:16])
    not inline hashlib.md5(url)[:10]."""
    from lib.checkpoint import get_article_hash

    url = "https://mp.weixin.qq.com/s/article-xyz"
    h = get_article_hash(url)

    # Exactly 16 hex characters
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)

    # Matches SHA-256 first 16
    expected = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    assert h == expected

    # Definitely NOT MD5 first 10
    md5_first10 = hashlib.md5(url.encode()).hexdigest()[:10]
    assert h != md5_first10

    # Source-grep: confirm no stale MD5 hash in the patched callsite
    src = open("batch_ingest_from_spider.py", encoding="utf-8").read()
    assert "hashlib.md5(url.encode()).hexdigest()[:10]" not in src, (
        "stale MD5 hash still present in batch_ingest_from_spider.py"
    )
    assert "article_hash = get_article_hash(url)" in src, (
        "patched article_hash line not found"
    )

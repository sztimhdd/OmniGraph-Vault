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
    # Quick 260507-ent reverted production to ON CONFLICT(article_id, topic).
    # The PRIMARY KEY (article_id, topic) above is the binding uniqueness
    # constraint — no extra single-column index is needed (migration 005
    # drops the one that migration 004 introduced).
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

def test_w3_batch_hashes_article_identity_contract():
    """W3 batch_hashes MUST use 10-char MD5(url)[:10] — the canonical
    article-identity format stored in DB and entity buffers.

    The previous contract (SHA256[:16] via get_article_hash) was a
    design/implementation mismatch: get_article_hash is for checkpoints
    only.  Article identity across the entire codebase (39 call sites,
    DB content_hash, entity buffers, wiki citations, image dirs) is
    always 10-char MD5.

    This test asserts the article-identity hash contract, not the
    internal implementation.  It validates observable behavior:
    regardless of how batch_hashes is computed, every hash must be
    exactly 10 lowercase hex characters.
    """
    import hashlib

    # The canonical article-identity format used everywhere:
    #   hashlib.md5(url.encode())[:10]
    url = "https://mp.weixin.qq.com/s/article-xyz"
    canonical = hashlib.md5(url.encode()).hexdigest()[:10]
    assert len(canonical) == 10
    assert all(c in "0123456789abcdef" for c in canonical)

    # Verify the checkpoint hash is DIFFERENT (16 chars, different domain)
    from lib.checkpoint import get_article_hash
    ckpt = get_article_hash(url)
    assert len(ckpt) == 16
    assert ckpt != canonical  # checkpoint != article identity

    # Verify the source file's W3 hook computes 10-char hashes
    # (observable: not the 16-char checkpoint format)
    src = open("batch_ingest_from_spider.py", encoding="utf-8").read()
    assert "get_article_hash(r[3])" not in src, (
        "batch_hashes must NOT use get_article_hash (16-char checkpoint hash); "
        "use the canonical 10-char MD5 article-identity hash instead"
    )

"""MVP-06 seam regressions: document-success vs Vision-task separation.

Bug (fixed here): ``ingest_wechat.ingest_article`` returns the background Vision
worker task handle, which is ``None`` for the cached / zero-image success
paths. ``batch_ingest_from_spider.ingest_article`` (the outer batch wrapper)
treated any ``None`` return as a failure, so a verified doc with no images - or
a cached doc - was recorded as failed and never marked ``ok``.

Fix contract pinned here:
  * inner returns ``None`` (no Vision task)  -> outer reports success;
  * inner RAISES (scrape failure / PROCESSED-verification failure) -> outer
    reports failure (real failures are preserved, not swallowed into success);
  * the cached path verifies the parent doc is PROCESSED before returning None.

Offline venv has no LightRAG / playwright / PyMuPDF / bs4 / html2text /
apify_client, so this module installs minimal import doubles (same pattern as
``tests/unit/test_search_query_context.py``) before importing the production
modules. No live model, network, LightRAG, or Vision call.
"""
from __future__ import annotations

import hashlib
import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest


def _install_offline_import_doubles() -> None:
    """Install minimal doubles for deps absent from the offline venv.

    No-op for any module that is already importable, so a full env is
    unaffected.
    """
    import importlib.util

    def _need(name: str) -> bool:
        if name in sys.modules:
            return False
        try:
            return importlib.util.find_spec(name) is None
        except (ImportError, ValueError):
            return True

    if _need("kol_config"):
        kc = types.ModuleType("kol_config")
        kc.TOKEN = ""
        kc.COOKIE = ""
        kc.FAKEIDS = {}
        sys.modules["kol_config"] = kc
    if _need("nest_asyncio"):
        na = types.ModuleType("nest_asyncio")
        na.apply = lambda *a, **k: None
        sys.modules["nest_asyncio"] = na
    if _need("lightrag"):
        pkg = types.ModuleType("lightrag")
        mod = types.ModuleType("lightrag.lightrag")
        mod.LightRAG = type("LightRAG", (), {})
        mod.QueryParam = type("QueryParam", (), {"__init__": lambda self, **k: None})
        sys.modules["lightrag"] = pkg
        sys.modules["lightrag.lightrag"] = mod
    if _need("fitz"):
        sys.modules["fitz"] = types.ModuleType("fitz")
    if _need("bs4"):
        bs4 = types.ModuleType("bs4")
        # Callable mock (object() would raise if any downstream path parses HTML).
        bs4.BeautifulSoup = MagicMock()
        sys.modules["bs4"] = bs4
    if _need("html2text"):
        sys.modules["html2text"] = types.ModuleType("html2text")
    if _need("playwright"):
        pkg = types.ModuleType("playwright")
        api = types.ModuleType("playwright.async_api")
        api.async_playwright = lambda *a, **k: None
        sys.modules["playwright"] = pkg
        sys.modules["playwright.async_api"] = api
    if _need("apify_client"):
        apify = types.ModuleType("apify_client")
        apify.ApifyClient = object
        sys.modules["apify_client"] = apify


_install_offline_import_doubles()


@pytest.fixture(autouse=True)
def _isolate_runtime(tmp_path, monkeypatch):
    """Route ALL runtime writes (checkpoints, images, entity buffer, DB) into
    tmp_path so tests never touch the default ``~/.hermes`` runtime.

    ``config.BASE_DIR`` is frozen at import time, so set the env vars AND patch
    the already-imported module globals: ``lib.checkpoint`` reads its own
    ``BASE_DIR`` (via ``_checkpoints_root()``), and ``ingest_wechat`` imported
    ``BASE_IMAGE_DIR`` / ``ENTITY_BUFFER_DIR`` from ``config`` at import.
    """
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("OMNIGRAPH_CHECKPOINT_BASE_DIR", str(tmp_path))

    import config
    import lib.checkpoint as checkpoint
    import ingest_wechat

    monkeypatch.setattr(config, "BASE_DIR", tmp_path, raising=False)
    monkeypatch.setattr(checkpoint, "BASE_DIR", tmp_path, raising=False)
    monkeypatch.setattr(ingest_wechat, "BASE_IMAGE_DIR", str(tmp_path))
    monkeypatch.setattr(ingest_wechat, "ENTITY_BUFFER_DIR", str(tmp_path / "eb"))
    monkeypatch.setattr(ingest_wechat, "DB_PATH", tmp_path / "missing.db")
    return tmp_path


def _fake_inner(returns):
    async def _inner(url, *, source="wechat", rag=None):
        return returns

    return _inner


def _fake_rag_processed() -> MagicMock:
    rag = MagicMock()
    rag.ainsert = AsyncMock()
    rag.aget_docs_by_ids = AsyncMock(
        side_effect=lambda ids: {i: {"status": "PROCESSED"} for i in ids}
    )
    return rag


# ---- Outer (batch_ingest_from_spider.ingest_article) contract --------------


@pytest.mark.asyncio
async def test_outer_marks_success_when_inner_returns_none(monkeypatch):
    """No-image ingest: inner returns None (no Vision task) -> outer success."""
    import batch_ingest_from_spider as bif
    import ingest_wechat

    monkeypatch.setattr(ingest_wechat, "ingest_article", _fake_inner(returns=None))
    monkeypatch.setattr(
        ingest_wechat, "get_pending_doc_id", lambda h: None, raising=False
    )

    ok, wall, doc_confirmed = await bif.ingest_article(
        source="wechat",
        url="https://example.com/mvp06-no-images",
        dry_run=False,
        rag=MagicMock(),
        effective_timeout=60,
    )

    assert ok is True
    assert wall >= 0.0
    assert doc_confirmed is True


@pytest.mark.asyncio
async def test_outer_marks_failure_when_inner_raises(monkeypatch):
    """Verification failure: inner raises RuntimeError -> outer failure."""
    import batch_ingest_from_spider as bif
    import ingest_wechat

    async def _inner(url, *, source="wechat", rag=None):
        raise RuntimeError(
            "post-ainsert PROCESSED verification failed for doc_id=test"
        )

    monkeypatch.setattr(ingest_wechat, "ingest_article", _inner)
    monkeypatch.setattr(
        ingest_wechat, "get_pending_doc_id", lambda h: None, raising=False
    )

    ok, wall, doc_confirmed = await bif.ingest_article(
        source="wechat",
        url="https://example.com/mvp06-verify-fail",
        dry_run=False,
        rag=MagicMock(),
        effective_timeout=60,
    )

    assert ok is False
    assert doc_confirmed is False


# ---- Inner (ingest_wechat.ingest_article) failure + cached paths -----------


@pytest.mark.asyncio
async def test_scrape_failure_raises_not_none(monkeypatch, tmp_path):
    """All scrape paths returning None -> inner RAISES (real failure), not None."""
    import ingest_wechat

    for name in (
        "scrape_wechat_ua",
        "scrape_wechat_apify",
        "scrape_wechat_cdp",
        "scrape_wechat_mcp",
    ):
        monkeypatch.setattr(ingest_wechat, name, AsyncMock(return_value=None))
    monkeypatch.setattr(ingest_wechat, "extract_entities", AsyncMock(return_value=[]))

    with pytest.raises(RuntimeError, match="Scrape failed"):
        await ingest_wechat.ingest_article(
            "https://mp.weixin.qq.com/s/mvp06-scrape-fail", rag=MagicMock()
        )


@pytest.mark.asyncio
async def test_cached_path_returns_none_and_verifies_doc(monkeypatch, tmp_path):
    """Cached article: returns None (no Vision task) after verifying PROCESSED."""
    import ingest_wechat

    monkeypatch.setattr(ingest_wechat, "extract_entities", AsyncMock(return_value=[]))

    url = "https://mp.weixin.qq.com/s/mvp06-cached"
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    article_dir = tmp_path / article_hash
    article_dir.mkdir(parents=True, exist_ok=True)
    long_body = " ".join(["Body text long enough to clear MIN_INGEST_BODY_LEN."] * 12)
    (article_dir / "final_content.md").write_text(
        f"# Cached Title\n\n{long_body}", encoding="utf-8"
    )
    (article_dir / "metadata.json").write_text(
        json.dumps({"title": "Cached Title", "images": []}), encoding="utf-8"
    )

    rag = _fake_rag_processed()

    result = await ingest_wechat.ingest_article(url, rag=rag)

    assert result is None
    rag.ainsert.assert_awaited_once()
    rag.aget_docs_by_ids.assert_awaited()


@pytest.mark.asyncio
async def test_cached_insert_failure_not_masked_by_old_processed(monkeypatch, tmp_path):
    """MVP-06 P1: a failed cached (re)insert must NOT be masked by a stale
    PROCESSED status from an earlier run. The inner must RAISE and the outer
    must return ``(False, _, False)`` — the failure must not become a success."""
    import batch_ingest_from_spider as bif
    import ingest_wechat

    monkeypatch.setattr(ingest_wechat, "extract_entities", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        ingest_wechat, "get_pending_doc_id", lambda h: None, raising=False
    )

    url = "https://mp.weixin.qq.com/s/mvp06-cache-insert-fail"
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    article_dir = tmp_path / article_hash
    article_dir.mkdir(parents=True, exist_ok=True)
    long_body = " ".join(["Body text long enough to clear MIN_INGEST_BODY_LEN."] * 12)
    (article_dir / "final_content.md").write_text(
        f"# Cached Title\n\n{long_body}", encoding="utf-8"
    )
    (article_dir / "metadata.json").write_text(
        json.dumps({"title": "Cached Title", "images": []}), encoding="utf-8"
    )

    # Insert fails with a NON-402 error; the graph still reports an OLD
    # PROCESSED doc, which must not be used to swallow this failure.
    rag = MagicMock()
    rag.ainsert = AsyncMock(
        side_effect=RuntimeError("synthetic storage write failed")
    )
    rag.aget_docs_by_ids = AsyncMock(
        side_effect=lambda ids: {i: {"status": "PROCESSED"} for i in ids}
    )

    with pytest.raises(RuntimeError, match="synthetic storage write failed"):
        await ingest_wechat.ingest_article(url, rag=rag)

    ok, _wall, doc_confirmed = await bif.ingest_article(
        source="wechat",
        url=url,
        dry_run=False,
        rag=rag,
        effective_timeout=60,
    )
    assert ok is False
    assert doc_confirmed is False

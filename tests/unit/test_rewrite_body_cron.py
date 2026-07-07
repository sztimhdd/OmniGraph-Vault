"""Behavior-anchor tests for scripts/rewrite_body_cron.py (kb-v2.3-3, RW-1..RW-7).

Per CLAUDE.md Behavior-Anchor Harness discipline: anchored on OBSERVABLE
post-conditions — seeded in-memory DB row state, mocked-LLM call count, and
the captured ``body_text`` argument — NOT internal call shape.

RW-6 is the anchor for the CRITICAL CORRECTION: the cron must feed the LLM the
D-14-resolved DISPLAY content (final_content.md with localhost:8765 URLs), not
raw DB body (CDN URLs). RW-7 pins the content_hash-NULL md5(url)[:10] fallback
(the articles id=861 case).
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.rewrite_body_cron as cron  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE articles (
    id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, content_hash TEXT,
    lang TEXT, update_time TEXT, layer1_verdict TEXT, layer2_verdict TEXT,
    layer2_at TEXT, body_cleaned TEXT, body_repositioned TEXT,
    body_rewritten TEXT, rewritten_at DATETIME
);
CREATE TABLE rss_articles (
    id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, content_hash TEXT,
    lang TEXT, published_at TEXT, fetched_at TEXT, layer2_at TEXT,
    layer1_verdict TEXT, layer2_verdict TEXT, body_cleaned TEXT,
    body_rewritten TEXT, rewritten_at DATETIME
);
"""


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(_DDL)
    yield c
    c.close()


def _seed_kol(conn, art_id, *, body="dirty body", content_hash=None, url=None,
              body_rewritten=None, layer2_at="2026-06-01"):
    conn.execute(
        "INSERT INTO articles (id,title,url,body,content_hash,lang,update_time,"
        "layer1_verdict,layer2_verdict,layer2_at,body_rewritten) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (art_id, f"title-{art_id}", url or f"https://mp.weixin.qq.com/s/a{art_id}",
         body, content_hash, "zh-CN", "2026-06-01", "candidate", "ok",
         layer2_at, body_rewritten),
    )
    conn.commit()


class _MockRewrite:
    """Async mock capturing (title, body_text) calls; returns a fixed value."""

    def __init__(self, result="CLEAN OUTPUT"):
        self.calls: list[tuple[str, str]] = []
        self.result = result
        self.raise_on: set[int] = set()  # 0-based call indices that raise

    async def __call__(self, title, body_text):
        idx = len(self.calls)
        self.calls.append((title, body_text))
        if idx in self.raise_on:
            raise RuntimeError("boom")
        return self.result


@pytest.fixture
def mock_rewrite(monkeypatch):
    """Patch lib.rewrite.rewrite_body_with_deepseek (the lazy-import target)."""
    import lib.rewrite as rewrite_mod

    mock = _MockRewrite()
    monkeypatch.setattr(rewrite_mod, "rewrite_body_with_deepseek", mock)
    return mock


def _run(conn, *, dry_run=False, limit=10, logger=None):
    import logging

    log = logger or logging.getLogger("test-rewrite-cron")
    rows = cron._select_candidate_rows(conn, limit)
    tally = {"ok": 0, "fail": 0, "skipped_oversize": 0, "dry_run": 0}
    for row in rows:
        outcome = asyncio.run(cron._rewrite_one_row(row, conn, dry_run, log))
        tally[outcome] = tally.get(outcome, 0) + 1
    return tally


def _rewritten(conn, table, art_id):
    return conn.execute(
        f"SELECT body_rewritten, rewritten_at FROM {table} WHERE id=?", (art_id,)
    ).fetchone()


# ---------------------------------------------------------------------------
# RW-1 dry-run: no LLM call, no UPDATE
# ---------------------------------------------------------------------------

def test_rw1_dry_run_no_llm_no_update(conn, mock_rewrite):
    for i in (1, 2, 3):
        _seed_kol(conn, i, content_hash=f"hash{i:07d}00")
    tally = _run(conn, dry_run=True)
    assert tally["dry_run"] == 3
    assert mock_rewrite.calls == []
    for i in (1, 2, 3):
        assert _rewritten(conn, "articles", i) == (None, None)


# ---------------------------------------------------------------------------
# RW-2 idempotency: populated rows skipped by WHERE guard
# ---------------------------------------------------------------------------

def test_rw2_populated_rows_skipped(conn, mock_rewrite):
    _seed_kol(conn, 1, content_hash="aaaaaaaaaa", body_rewritten="ALREADY DONE")
    _seed_kol(conn, 2, content_hash="bbbbbbbbbb")
    tally = _run(conn)
    assert len(mock_rewrite.calls) == 1
    assert tally["ok"] == 1
    assert _rewritten(conn, "articles", 1)[0] == "ALREADY DONE"
    assert _rewritten(conn, "articles", 2)[0] == "CLEAN OUTPUT"


# ---------------------------------------------------------------------------
# RW-3 per-row failure isolated
# ---------------------------------------------------------------------------

def test_rw3_per_row_failure_isolated(conn, mock_rewrite):
    _seed_kol(conn, 1, content_hash="aaaaaaaaaa", layer2_at="2026-06-01")
    _seed_kol(conn, 2, content_hash="bbbbbbbbbb", layer2_at="2026-06-02")
    mock_rewrite.raise_on = {0}  # first row raises
    tally = _run(conn)
    assert tally == {"ok": 1, "fail": 1, "skipped_oversize": 0, "dry_run": 0}
    assert _rewritten(conn, "articles", 1)[0] is None
    assert _rewritten(conn, "articles", 2)[0] == "CLEAN OUTPUT"


# ---------------------------------------------------------------------------
# RW-4 --limit N
# ---------------------------------------------------------------------------

def test_rw4_limit_caps_llm_calls(conn, mock_rewrite):
    for i in range(1, 6):
        _seed_kol(conn, i, content_hash=f"cc{i:08d}")
    _run(conn, limit=2)
    assert len(mock_rewrite.calls) == 2


# ---------------------------------------------------------------------------
# RW-5 UPDATE persists both columns
# ---------------------------------------------------------------------------

def test_rw5_update_persists_both_columns(conn, mock_rewrite):
    _seed_kol(conn, 1, content_hash="aaaaaaaaaa")
    _run(conn)
    body_rewritten, rewritten_at = _rewritten(conn, "articles", 1)
    assert body_rewritten == "CLEAN OUTPUT"
    assert rewritten_at is not None


# ---------------------------------------------------------------------------
# RW-6 INPUT-IS-DISPLAY-CONTENT (the CRITICAL CORRECTION anchor)
# ---------------------------------------------------------------------------

def test_rw6_input_is_display_content_not_db_body(conn, mock_rewrite, tmp_path, monkeypatch):
    monkeypatch.setattr(cron.kb_config, "KB_IMAGES_DIR", tmp_path)
    cdn_body = "text ![](https://mmbiz.qpic.cn/mmbiz_jpg/abc/0.jpg) more"
    fs_content = (
        "clean text ![](http://localhost:8765/deadbeef01/0.jpg)\n\n"
        "Image 1 from article 'title-1': http://localhost:8765/deadbeef01/1.jpg\n"
    )
    _seed_kol(conn, 1, body=cdn_body, content_hash="deadbeef01")
    d = tmp_path / "deadbeef01"
    d.mkdir()
    (d / "final_content.md").write_text(fs_content, encoding="utf-8")

    _run(conn)

    assert len(mock_rewrite.calls) == 1
    captured_body = mock_rewrite.calls[0][1]
    assert captured_body == fs_content, "cron must feed fs display content"
    assert "localhost:8765" in captured_body
    assert "mmbiz.qpic.cn" not in captured_body, "raw DB body must NOT be the input"


def test_rw6b_enriched_preferred_over_plain(conn, mock_rewrite, tmp_path, monkeypatch):
    monkeypatch.setattr(cron.kb_config, "KB_IMAGES_DIR", tmp_path)
    _seed_kol(conn, 1, content_hash="deadbeef01")
    d = tmp_path / "deadbeef01"
    d.mkdir()
    (d / "final_content.enriched.md").write_text("ENRICHED", encoding="utf-8")
    (d / "final_content.md").write_text("PLAIN", encoding="utf-8")
    _run(conn)
    assert mock_rewrite.calls[0][1] == "ENRICHED"


# ---------------------------------------------------------------------------
# RW-7 content_hash-NULL fs lookup via md5(url)[:10]
# ---------------------------------------------------------------------------

def test_rw7_content_hash_null_resolves_via_md5_url(conn, mock_rewrite, tmp_path, monkeypatch):
    import hashlib

    monkeypatch.setattr(cron.kb_config, "KB_IMAGES_DIR", tmp_path)
    url = "https://mp.weixin.qq.com/s/id861-like-row"
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    _seed_kol(conn, 861, content_hash=None, url=url)
    d = tmp_path / url_hash
    d.mkdir()
    (d / "final_content.md").write_text("MD5-RESOLVED CONTENT", encoding="utf-8")

    _run(conn)

    assert len(mock_rewrite.calls) == 1
    assert mock_rewrite.calls[0][1] == "MD5-RESOLVED CONTENT"


# ---------------------------------------------------------------------------
# RW-OVERSIZE: resolved content > MAX_REWRITE_CHARS skipped, no LLM call
# ---------------------------------------------------------------------------

def test_rw_oversize_skipped_no_llm(conn, mock_rewrite, tmp_path, monkeypatch):
    monkeypatch.setattr(cron.kb_config, "KB_IMAGES_DIR", tmp_path)
    big = "x" * (cron.MAX_REWRITE_CHARS + 1)
    _seed_kol(conn, 1, body=big, content_hash="aaaaaaaaaa")
    tally = _run(conn)
    assert tally["skipped_oversize"] == 1
    assert mock_rewrite.calls == []
    assert _rewritten(conn, "articles", 1)[0] is None


# ---------------------------------------------------------------------------
# RSS branch roundtrip (source='rss', hash truncation)
# ---------------------------------------------------------------------------

def test_rss_row_rewritten(conn, mock_rewrite, tmp_path, monkeypatch):
    monkeypatch.setattr(cron.kb_config, "KB_IMAGES_DIR", tmp_path)
    conn.execute(
        "INSERT INTO rss_articles (id,title,url,body,content_hash,lang,"
        "published_at,fetched_at,layer2_at,layer1_verdict,layer2_verdict) "
        "VALUES (10,'rss','https://e.com/r','rss body',"
        "'deadbeefcafebabe1234567890abcdef','en','2026-06-01','2026-06-01',"
        "'2026-06-01','candidate','ok')"
    )
    conn.commit()
    d = tmp_path / "deadbeefca"  # content_hash[:10]
    d.mkdir()
    (d / "final_content.md").write_text("RSS FS CONTENT", encoding="utf-8")

    tally = _run(conn)

    assert tally["ok"] == 1
    assert mock_rewrite.calls[0][1] == "RSS FS CONTENT"
    assert _rewritten(conn, "rss_articles", 10)[0] == "CLEAN OUTPUT"

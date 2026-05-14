"""Integration tests for /api/articles + /api/article/{hash} endpoints.

Covers kb-3-05 acceptance criteria:
    - GET /api/articles paginated list (API-02, DATA-07 inheritance)
    - GET /api/article/{hash} single article (API-03, DATA-07 carve-out)

TestClient-based; no live uvicorn. Uses shared `fixture_db` from conftest.py
which has 5 KOL + 3 RSS positive rows AND 4 negative-case rows (DATA-07
must filter the 4 negatives out of the list endpoint, but they remain
addressable by /api/article/{hash}).

Skill(skill="python-patterns", args="Idiomatic FastAPI APIRouter test pattern with TestClient — fastapi.testclient avoids needing a running uvicorn. monkeypatch.setenv + importlib.reload chain (kb.config -> kb.data.article_query -> kb.api_routers.articles -> kb.api) so the router picks up KB_DB_PATH pointing at fixture_db. KB_CONTENT_QUALITY_FILTER deliberately deleted from env so DATA-07 default-on path is exercised. No mocks for SQLite — tests exercise the full router → data layer → SQLite path.")

Skill(skill="writing-tests", args="TestClient integration tests for /api/articles + /api/article/{hash}. Coverage matrix: (1) basic shape, (2) pagination math, (3) source filter wechat/rss, (4) lang filter, (5) q LIKE search, (6) 422 on invalid params, (7) DATA-07 inherited (negatives absent), (8) hash field correctness, (9) p50 latency < 100ms, (10) detail full shape, (11) 404 miss, (12) body_html rendered, (13) body_source enum, (14) carve-out preserves negative rows, (15) images is list, (16) detail latency. Real SQLite throughout — no mocks.")
"""
from __future__ import annotations

import importlib
import re
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---- App-client fixture: reload chain so router picks up monkeypatched env ----


@pytest.fixture
def app_client(fixture_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient against kb.api with KB_DB_PATH pointed at fixture_db.

    Reload chain order matters: kb.config (env reads), kb.data.article_query
    (re-read QUALITY_FILTER_ENABLED), kb.api_routers.articles (router
    references article_query), kb.api (mounts router).
    """
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    # KB_CONTENT_QUALITY_FILTER unset → defaults to "on" (DATA-07 active)
    monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
    import kb.config
    import kb.data.article_query
    import kb.api_routers.articles
    import kb.api

    importlib.reload(kb.config)
    importlib.reload(kb.data.article_query)
    importlib.reload(kb.api_routers.articles)
    importlib.reload(kb.api)
    return TestClient(kb.api.app)


# ============================================================================
# Task 1 — GET /api/articles
# ============================================================================


def test_list_articles_basic_shape(app_client: TestClient) -> None:
    """Response envelope must have items/page/limit/total/has_more."""
    r = app_client.get("/api/articles")
    assert r.status_code == 200
    body = r.json()
    for key in ("items", "page", "limit", "total", "has_more"):
        assert key in body, f"missing top-level key: {key}"
    assert body["page"] == 1 and body["limit"] == 20
    assert isinstance(body["items"], list)


def test_pagination_math(app_client: TestClient) -> None:
    """page=2&limit=2 returns the 3rd-4th elements of the merged list."""
    r = app_client.get("/api/articles?page=2&limit=2")
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 2 and body["limit"] == 2
    all_r = app_client.get("/api/articles?limit=100").json()
    assert body["items"] == all_r["items"][2:4]


def test_source_filter_wechat(app_client: TestClient) -> None:
    """source=wechat → all items have source='wechat'."""
    r = app_client.get("/api/articles?source=wechat&limit=100").json()
    assert r["items"], "fixture must have at least one wechat row passing DATA-07"
    assert all(item["source"] == "wechat" for item in r["items"])


def test_source_filter_rss(app_client: TestClient) -> None:
    """source=rss → all items have source='rss'."""
    r = app_client.get("/api/articles?source=rss&limit=100").json()
    assert r["items"], "fixture must have at least one rss row passing DATA-07"
    assert all(item["source"] == "rss" for item in r["items"])


def test_lang_filter_zh(app_client: TestClient) -> None:
    """lang=zh-CN → all items have lang='zh-CN'."""
    r = app_client.get("/api/articles?lang=zh-CN&limit=100").json()
    assert all(item["lang"] == "zh-CN" for item in r["items"])


def test_q_filter_title_substring(app_client: TestClient) -> None:
    """q='agent' → items where title contains 'agent' (case-insensitive)."""
    r = app_client.get("/api/articles?q=agent&limit=100").json()
    for item in r["items"]:
        assert "agent" in (item["title"] or "").lower()


def test_invalid_page_param_422(app_client: TestClient) -> None:
    """page=0 violates ge=1 → FastAPI returns 422."""
    r = app_client.get("/api/articles?page=0")
    assert r.status_code == 422


def test_invalid_limit_param_422(app_client: TestClient) -> None:
    """limit=200 violates le=100 → FastAPI returns 422."""
    r = app_client.get("/api/articles?limit=200")
    assert r.status_code == 422


def test_data07_filter_applied(app_client: TestClient) -> None:
    """DATA-07: negative-case fixture rows (REJECTED titles) MUST NOT appear."""
    r = app_client.get("/api/articles?limit=10000").json()
    assert not any(
        "REJECTED" in (item["title"] or "") for item in r["items"]
    ), "DATA-07 violation: REJECTED row leaked into list endpoint"
    # NULL BODY RSS row is also a negative — confirm absent
    assert not any(
        "NULL BODY" in (item["title"] or "") for item in r["items"]
    )


def test_each_item_has_resolvable_hash(app_client: TestClient) -> None:
    """Every item exposes a 10-char hash field."""
    r = app_client.get("/api/articles?limit=10").json()
    assert r["items"], "fixture must have at least one positive row"
    for item in r["items"]:
        assert "hash" in item
        assert isinstance(item["hash"], str) and len(item["hash"]) == 10


def test_p50_latency_under_100ms_list(app_client: TestClient) -> None:
    """5-call latency p50 on fixture DB must be under 100ms (API-02 contract)."""
    durations: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        r = app_client.get("/api/articles?limit=20")
        durations.append(time.perf_counter() - t0)
        assert r.status_code == 200
    durations.sort()
    p50 = durations[2]  # median of 5
    assert p50 < 0.1, f"p50 latency {p50 * 1000:.1f}ms exceeds 100ms target"


# ============================================================================
# Task 2 — GET /api/article/{hash}
# ============================================================================


def _first_positive_hash(fixture_db: Path) -> str:
    """Pick a known-good hash from the fixture: positive KOL row id=1."""
    from kb.data.article_query import _row_to_record_kol, resolve_url_hash

    c = sqlite3.connect(str(fixture_db))
    c.row_factory = sqlite3.Row
    try:
        row = c.execute(
            "SELECT id, title, url, body, content_hash, lang, update_time "
            "FROM articles WHERE layer1_verdict='candidate' "
            "AND (layer2_verdict IS NULL OR layer2_verdict != 'reject') "
            "AND body != '' "
            "ORDER BY id LIMIT 1"
        ).fetchone()
        assert row is not None, "fixture must have at least one DATA-07 positive KOL row"
        return resolve_url_hash(_row_to_record_kol(row))
    finally:
        c.close()


def test_article_detail_full_shape(app_client: TestClient, fixture_db: Path) -> None:
    """All 9 contract fields present on a detail response."""
    h = _first_positive_hash(fixture_db)
    r = app_client.get(f"/api/article/{h}")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in (
        "hash",
        "title",
        "body_md",
        "body_html",
        "lang",
        "source",
        "images",
        "metadata",
        "body_source",
    ):
        assert key in body, f"missing key: {key}"


def test_article_detail_404(app_client: TestClient) -> None:
    """Unknown hash → 404."""
    r = app_client.get("/api/article/zzzzzzzzzz")
    assert r.status_code == 404


def test_article_detail_body_html_rendered(
    app_client: TestClient, fixture_db: Path
) -> None:
    """body_html must contain rendered HTML (markdown lib produced tags)."""
    h = _first_positive_hash(fixture_db)
    body = app_client.get(f"/api/article/{h}").json()
    # Fixture body starts with '# Test Article One' → rendered to <h1>
    assert "<p>" in body["body_html"] or re.search(r"<h\d", body["body_html"])


def test_article_detail_body_source_enum(
    app_client: TestClient, fixture_db: Path
) -> None:
    """body_source must be one of vision_enriched / raw_markdown."""
    h = _first_positive_hash(fixture_db)
    body = app_client.get(f"/api/article/{h}").json()
    assert body["body_source"] in ("vision_enriched", "raw_markdown")


def test_article_detail_carve_out_preserves_negative(
    app_client: TestClient, fixture_db: Path
) -> None:
    """DATA-07 carve-out: hash of a layer2='reject' row still resolves (200)."""
    from kb.data.article_query import _row_to_record_kol, resolve_url_hash

    c = sqlite3.connect(str(fixture_db))
    c.row_factory = sqlite3.Row
    try:
        row = c.execute(
            "SELECT id, title, url, body, content_hash, lang, update_time "
            "FROM articles WHERE layer2_verdict='reject' AND body != '' LIMIT 1"
        ).fetchone()
        assert (
            row is not None
        ), "fixture must have layer2_verdict='reject' row from kb-3-02"
        h = resolve_url_hash(_row_to_record_kol(row))
    finally:
        c.close()
    r = app_client.get(f"/api/article/{h}")
    assert (
        r.status_code == 200
    ), "carve-out: direct hash access must resolve negative-case row (got "
    f"{r.status_code})"


def test_article_detail_images_is_list(
    app_client: TestClient, fixture_db: Path
) -> None:
    """images field is always a list (possibly empty)."""
    h = _first_positive_hash(fixture_db)
    body = app_client.get(f"/api/article/{h}").json()
    assert isinstance(body["images"], list)


def test_article_detail_p50_latency(
    app_client: TestClient, fixture_db: Path
) -> None:
    """5-call latency p50 on fixture DB must be under 100ms."""
    h = _first_positive_hash(fixture_db)
    durs: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        r = app_client.get(f"/api/article/{h}")
        durs.append(time.perf_counter() - t0)
        assert r.status_code == 200
    durs.sort()
    assert durs[2] < 0.1, f"p50 = {durs[2] * 1000:.1f}ms exceeds 100ms"

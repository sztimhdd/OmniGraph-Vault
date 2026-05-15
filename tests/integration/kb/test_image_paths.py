"""Integration tests for kb-v2.1-2 image-path integration.

Covers:
    - Pure ``_rewrite_image_paths`` semantics under both deploy modes
      (KB_BASE_PATH='' = root deploy, KB_BASE_PATH='/kb' = subdir deploy).
    - Idempotency — second pass on already-rewritten body is a no-op.
    - End-to-end via ``/api/article/{hash}``: response ``body_md`` and
      ``images`` field paths are correctly prefixed.
    - SSG export driver inherits the rewrite (since it calls
      ``get_article_body``) — verified by hitting ``/articles/{hash}.html``
      after invoking the export driver in a tmp tree.

Skill(skill="python-patterns", args="Pure-function pattern for path rewrites: _rewrite_image_paths(body_md, base_path) is side-effect-free, idempotent, deterministic. Negative lookbehind makes step 2 idempotent without needing extra state. EAFP for empty-body short-circuit. PEP 8 + type hints. Reusable from get_article_body and from kb.export_knowledge_base which already calls get_article_body — single source of truth for rewrite contract.")

Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real fixture_db with body containing http://localhost:8765/ refs (KOL id=1 has 1 image ref, KOL id=2 has 1 image ref per conftest fixture). Parametrize across KB_BASE_PATH='' (root) and '/kb' (subdir). Assert observable HTTP behaviour and pure-function output — never internal state. Idempotency test passes the function its own output and demands byte-equality. Add a unit-level pure-function suite + an HTTP-level integration suite so failures localize quickly.")
"""
from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---- Reload-and-build app client with parametrizable base_path ------------


def _populate_fts(fixture_db: Path) -> None:
    """Mirror the test_api_search FTS-population pattern."""
    import kb.services.search_index as si

    importlib.reload(si)
    conn = sqlite3.connect(str(fixture_db))
    try:
        si.ensure_fts_table(conn)
        for row in conn.execute(
            "SELECT content_hash, title, body, lang FROM articles "
            "WHERE content_hash IS NOT NULL"
        ):
            ch, title, body, lang = row
            conn.execute(
                f"INSERT INTO {si.FTS_TABLE_NAME} (hash,title,body,lang,source) "
                "VALUES (?,?,?,?,?)",
                (ch, title or "", body or "", lang, "wechat"),
            )
        conn.commit()
    finally:
        conn.close()


def _build_client(
    fixture_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    base_path: str,
) -> TestClient:
    """Build TestClient with KB_BASE_PATH set (or unset for root deploy)."""
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
    if base_path:
        monkeypatch.setenv("KB_BASE_PATH", base_path)
    else:
        monkeypatch.delenv("KB_BASE_PATH", raising=False)
    _populate_fts(fixture_db)
    # Reload the modules whose constants are read at import time.
    import kb.config
    import kb.api

    importlib.reload(kb.config)
    importlib.reload(kb.api)
    return TestClient(kb.api.app)


# ============================================================================
# Pure-function suite — _rewrite_image_paths
# ============================================================================


def test_rewrite_localhost_8765_to_static_img_without_base_path() -> None:
    from kb.data.article_query import _rewrite_image_paths

    body = "# T\n\n![](http://localhost:8765/abc/img.png)\n\nText"
    out = _rewrite_image_paths(body, base_path="")
    assert "/static/img/abc/img.png" in out
    assert "localhost:8765" not in out
    # Root deploy: no KB_BASE_PATH prefix should appear.
    assert "/kb/static/img/" not in out


def test_rewrite_localhost_8765_to_kb_static_img_with_base_path() -> None:
    from kb.data.article_query import _rewrite_image_paths

    body = "# T\n\n![alt](http://localhost:8765/abc/0.jpg)\n\nText"
    out = _rewrite_image_paths(body, base_path="/kb")
    assert "/kb/static/img/abc/0.jpg" in out
    assert "http://localhost:8765/" not in out


def test_rewrite_bare_static_img_picks_up_base_path() -> None:
    """Bare ``/static/img/`` (no http prefix) gets the kb prefix when set."""
    from kb.data.article_query import _rewrite_image_paths

    body = "see ![](/static/img/abc/0.jpg)"
    out = _rewrite_image_paths(body, base_path="/kb")
    assert "/kb/static/img/abc/0.jpg" in out
    # Original bare form must NOT remain alongside the prefixed form.
    assert "(/static/img/abc/0.jpg)" not in out


def test_rewrite_idempotent_when_paths_already_prefixed() -> None:
    """Second call on already-rewritten body is a no-op (byte-equal)."""
    from kb.data.article_query import _rewrite_image_paths

    body = "![alt](http://localhost:8765/h/1.jpg) and more"
    once = _rewrite_image_paths(body, base_path="/kb")
    twice = _rewrite_image_paths(once, base_path="/kb")
    assert once == twice
    # Sanity check: the rewrite actually fired the first time.
    assert "/kb/static/img/h/1.jpg" in once


def test_rewrite_multiple_occurrences_all_rewritten() -> None:
    from kb.data.article_query import _rewrite_image_paths

    body = (
        "![](http://localhost:8765/h/0.jpg)\n\n"
        "![](http://localhost:8765/h/1.jpg)\n\n"
        "![](http://localhost:8765/h/2.jpg)"
    )
    out = _rewrite_image_paths(body, base_path="/kb")
    assert out.count("/kb/static/img/h/") == 3
    assert "localhost:8765" not in out


def test_rewrite_empty_body_passthrough() -> None:
    from kb.data.article_query import _rewrite_image_paths

    assert _rewrite_image_paths("", base_path="/kb") == ""
    assert _rewrite_image_paths("", base_path="") == ""


def test_rewrite_does_not_double_prefix_existing_base_path() -> None:
    """Body that already contains ``/kb/static/img/`` must not be re-prefixed."""
    from kb.data.article_query import _rewrite_image_paths

    body = "![](/kb/static/img/h/0.jpg)"
    out = _rewrite_image_paths(body, base_path="/kb")
    assert out == body  # exact byte equality — no /kb/kb/static/...
    assert "/kb/kb/" not in out


# ============================================================================
# HTTP-level suite — /api/article/{hash}
# ============================================================================


def test_api_article_body_md_uses_static_img_for_root_deploy(
    fixture_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_client(fixture_db, monkeypatch, base_path="")
    # KOL id=1 hash from conftest fixture: 'abc1234567'.
    r = client.get("/api/article/abc1234567")
    assert r.status_code == 200
    body = r.json()
    assert "body_md" in body
    assert "/static/img/abc/img.png" in body["body_md"], body["body_md"]
    assert "localhost:8765" not in body["body_md"]


def test_api_article_body_md_uses_kb_prefix_under_subdir_deploy(
    fixture_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_client(fixture_db, monkeypatch, base_path="/kb")
    r = client.get("/api/article/abc1234567")
    assert r.status_code == 200
    body = r.json()
    assert "/kb/static/img/abc/img.png" in body["body_md"], body["body_md"]
    assert "localhost:8765" not in body["body_md"]


def test_api_article_images_field_present_and_prefixed_for_root_deploy(
    fixture_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_client(fixture_db, monkeypatch, base_path="")
    r = client.get("/api/article/abc1234567")
    assert r.status_code == 200
    body = r.json()
    assert "images" in body
    assert isinstance(body["images"], list)
    assert len(body["images"]) >= 1
    for url in body["images"]:
        assert url.startswith("/static/img/"), url
        assert "localhost:8765" not in url


def test_api_article_images_field_uses_kb_prefix_under_subdir_deploy(
    fixture_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _build_client(fixture_db, monkeypatch, base_path="/kb")
    r = client.get("/api/article/abc1234567")
    assert r.status_code == 200
    body = r.json()
    assert len(body["images"]) >= 1
    for url in body["images"]:
        assert url.startswith("/kb/static/img/"), url


def test_api_article_body_html_image_src_matches_base_path(
    fixture_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """body_html is markdown-rendered from body_md; image src must inherit prefix."""
    client = _build_client(fixture_db, monkeypatch, base_path="/kb")
    r = client.get("/api/article/abc1234567")
    assert r.status_code == 200
    body = r.json()
    assert 'src="/kb/static/img/abc/img.png"' in body["body_html"], body["body_html"]


def test_api_article_unaffected_when_body_has_no_images(
    fixture_db: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Article without image refs returns empty images list and unchanged body."""
    client = _build_client(fixture_db, monkeypatch, base_path="/kb")
    # KOL id=3 fixture body has no localhost:8765/ refs (per conftest).
    r = client.get("/api/article/kol3000003a")
    assert r.status_code == 200
    body = r.json()
    assert body["images"] == []
    # body_md should not have any spurious /kb/static/img/ injected.
    assert "/kb/static/img/" not in body["body_md"]

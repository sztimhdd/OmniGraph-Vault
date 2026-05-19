"""Integration tests for quick-260519-s65 long_form image URL rewrite.

Covers the belt-and-suspenders rewrite added to `kb.services.synthesize`:

    1. `_rewrite_image_urls(markdown)` rewrites `http(s)://...:8765/` to `/static/img/`
    2. `_rewrite_image_urls(markdown)` is idempotent (no double-rewrite)
    3. `_rewrite_image_urls` preserves non-:8765 URLs unchanged
    4. `_resolve_sources_from_markdown(markdown)` returns non-empty sources for
       markdown containing `/article/{hash}.html` references that match fixture_db
    5. End-to-end: `kb_synthesize(mode='long_form')` rewrites localhost:8765 URLs
       in the stored markdown so qa.js never sees a broken URL.

Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB +
real fixture_db + MOCKED kg_synthesize.synthesize_response (LLM boundary). Reuse
the reload-chain + monkeypatch C1 pattern from test_synthesize_citation_format.py.")
"""
from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

from kb.services import job_store
from kb.services import synthesize as kb_synth_mod


# ---- helpers (mirror test_synthesize_citation_format.py patterns) ----------


def _patch_base_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import config as og_config

    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))
    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(kb_synth_mod, "KG_MODE_AVAILABLE", True)
    monkeypatch.setattr(kb_synth_mod, "KG_MODE_UNAVAILABLE_REASON", "")


def _reload_synthesize(monkeypatch: pytest.MonkeyPatch) -> object:
    import kb.config
    import kb.services.synthesize as sm

    importlib.reload(kb.config)
    importlib.reload(sm)
    return sm


def _patch_c1_returns(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    async def fake_synthesize(query_text: str, mode: str = "hybrid"):
        return output

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_synthesize)


# ---- pure-function tests for _rewrite_image_urls ---------------------------


def test_rewrite_image_urls_replaces_localhost_8765() -> None:
    from kb.services.synthesize import _rewrite_image_urls

    md = "Some prose ![](http://localhost:8765/abc1234567/0.jpg) more prose."
    out = _rewrite_image_urls(md)
    assert "localhost:8765" not in out
    assert "/static/img/abc1234567/0.jpg" in out


def test_rewrite_image_urls_replaces_https_and_arbitrary_host() -> None:
    """Pattern matches any host, http or https, on port 8765."""
    from kb.services.synthesize import _rewrite_image_urls

    md = (
        "![](http://localhost:8765/h1/0.jpg)\n"
        "![](https://192.168.1.5:8765/h2/3.jpg)\n"
        "![](http://image-server.local:8765/h3/9.jpg)\n"
    )
    out = _rewrite_image_urls(md)
    assert ":8765" not in out
    assert "/static/img/h1/0.jpg" in out
    assert "/static/img/h2/3.jpg" in out
    assert "/static/img/h3/9.jpg" in out


def test_rewrite_image_urls_is_idempotent() -> None:
    """Applying twice yields the same string — already-rewritten URLs untouched."""
    from kb.services.synthesize import _rewrite_image_urls

    md = "![](http://localhost:8765/abc/0.jpg)"
    once = _rewrite_image_urls(md)
    twice = _rewrite_image_urls(once)
    assert once == twice == "![](/static/img/abc/0.jpg)"


def test_rewrite_image_urls_preserves_non_8765_urls() -> None:
    """Only the legacy port 8765 prefix is rewritten — other URLs pass through."""
    from kb.services.synthesize import _rewrite_image_urls

    md = (
        "![](http://example.com/external.png)\n"
        "[link](https://github.com/repo)\n"
        "![](/static/img/already/0.jpg)\n"
    )
    assert _rewrite_image_urls(md) == md


def test_rewrite_image_urls_handles_empty_and_no_matches() -> None:
    from kb.services.synthesize import _rewrite_image_urls

    assert _rewrite_image_urls("") == ""
    assert _rewrite_image_urls("plain text with no urls") == "plain text with no urls"


# ---- DB-backed source resolution tests -------------------------------------


def test_resolve_sources_returns_non_empty_for_article_hash_refs(
    tmp_path, fixture_db, monkeypatch
):
    """Markdown containing `/article/{hash}.html` matches fixture_db hashes →
    `_resolve_sources_from_markdown` returns ArticleSource entries."""
    _patch_base_dir(tmp_path, monkeypatch)
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    sm = _reload_synthesize(monkeypatch)

    md = (
        "## Answer\n\n"
        "Frameworks include LangChain [/article/abc1234567.html] "
        "(resolves to fixture_db id=1)."
    )
    sources = sm._resolve_sources_from_markdown(md)
    hashes = [s.hash for s in sources]
    assert "abc1234567" in hashes, (
        "Hash present in fixture_db (id=1, layer1='candidate', layer2='ok') "
        "should resolve through DATA-07"
    )
    # Negative-case hash that does not exist in fixture_db should be silently
    # dropped (decorative chip, MUST NOT poison the never-500 contract).
    md_with_unknown = (
        "## Answer\n\nReal: [/article/abc1234567.html]\n"
        "Bogus: [/article/9999999999.html]"
    )
    sources_two = sm._resolve_sources_from_markdown(md_with_unknown)
    hashes_two = [s.hash for s in sources_two]
    assert "abc1234567" in hashes_two
    assert "9999999999" not in hashes_two


# ---- end-to-end: kb_synthesize rewrites localhost:8765 in stored markdown --


def test_long_form_kb_synthesize_rewrites_localhost_8765_in_stored_markdown(
    tmp_path, fixture_db, monkeypatch
):
    """Belt-and-suspenders: even if C1 returns markdown with `localhost:8765`
    URLs (because LLM ignored the prompt prohibition), the stored job result
    contains rewritten `/static/img/` paths — qa.js never sees broken URLs."""
    _patch_base_dir(tmp_path, monkeypatch)
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    _patch_c1_returns(
        monkeypatch,
        output=(
            "## The Agent\n\n"
            "An overview [/article/abc1234567.html].\n\n"
            "![](http://localhost:8765/abc1234567/0.jpg)\n\n"
            "More text.\n\n"
            "![](http://localhost:8765/kol3000003a/3.jpg)"
        ),
    )
    sm = _reload_synthesize(monkeypatch)
    monkeypatch.setattr(sm, "KG_MODE_AVAILABLE", True)
    monkeypatch.setattr(sm, "KG_MODE_UNAVAILABLE_REASON", "")

    jid = job_store.new_job(kind="synthesize")
    asyncio.run(sm.kb_synthesize("What is an Agent", "en", jid, mode="long_form"))

    job = job_store.get_job(jid)
    assert job is not None
    assert job["status"] == "done"
    stored_md = job["result"]["markdown"]
    assert "localhost:8765" not in stored_md, (
        "kb_synthesize MUST strip legacy :8765 URLs from stored markdown"
    )
    assert "/static/img/abc1234567/0.jpg" in stored_md
    assert "/static/img/kol3000003a/3.jpg" in stored_md
    # Citation resolution should still work over rewritten markdown
    assert job["confidence"] == "kg", (
        "Citations resolve from /article/{hash}.html → confidence='kg'"
    )
    sources_hashes = [s["hash"] for s in job["result"]["sources"]]
    assert "abc1234567" in sources_hashes

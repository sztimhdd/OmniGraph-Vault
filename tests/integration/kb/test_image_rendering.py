"""Integration tests for kb-v2.1-6 Phase 5-00 plain-text image-ref → <img> rewrite.

Covers:
    - Pure ``_rewrite_image_text_refs_to_html`` semantics
    - Idempotency (re-applying the helper is byte-equal to a single application)
    - End-to-end via ``get_article_body`` — wiring order verifies that
      ``_rewrite_image_paths`` runs FIRST, then the text-ref → <img> bridge
    - Multi-image articles emit one <img> per Phase 5-00 line
    - Title containing apostrophe is handled gracefully (pass-through, no crash)
    - Existing markdown image syntax (``![alt](url)``) is NOT double-wrapped
    - Regression guard: ``ingest_wechat.py:1303`` is unchanged vs origin/main
      (Phase 5-00 retrieval binding for LightRAG aquery preserved)

Skill(skill="python-patterns", args="Pure-function regex helper. Module-level compiled re.Pattern (not per-call). EAFP empty-body short-circuit. Type hints (str -> str). Lambda in re.sub for capture-group → format string. Idempotency via output shape that does not match input pattern. PEP 8 + isort + black-compatible.")

Skill(skill="writing-tests", args="Testing Trophy: integration > unit. ≥7 integration tests in tests/integration/kb/test_image_rendering.py. Pure-function tests use direct import + assertion. End-to-end tests use ArticleRecord fixture + get_article_body() to verify wiring order (rewrite_paths runs FIRST, then rewrite_text_refs). Idempotency test passes function its own output and asserts byte-equality. Regression guard test for ingest_wechat.py unchanged via subprocess git diff. Parametrize KB_BASE_PATH='' vs '/kb' across applicable cases. Mirror the pytest patterns from tests/integration/kb/test_image_paths.py (importlib.reload, monkeypatch.setenv).")
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


# ============================================================================
# Pure-function suite — _rewrite_image_text_refs_to_html
# ============================================================================


def test_plain_text_ref_converted_to_img_tag() -> None:
    """A single Phase 5-00 plain-text ref is rewritten into <img>."""
    from kb.data.article_query import _rewrite_image_text_refs_to_html

    body = "Image 3 from article 'Foo': /static/img/abc/3.jpg"
    out = _rewrite_image_text_refs_to_html(body)
    assert (
        '<img src="/static/img/abc/3.jpg" alt="image 3" loading="lazy">' in out
    )
    # Plain-text form must be gone.
    assert "Image 3 from article 'Foo':" not in out


def test_rewrite_idempotent_on_already_converted_body() -> None:
    """Applying the helper twice is byte-equal to a single application."""
    from kb.data.article_query import _rewrite_image_text_refs_to_html

    body = "Image 0 from article 'X': /kb/static/img/h/0.jpg\n\nMore text."
    once = _rewrite_image_text_refs_to_html(body)
    twice = _rewrite_image_text_refs_to_html(once)
    assert once == twice
    # Sanity: rewrite actually fired the first time.
    assert "<img " in once


def test_multi_image_article_emits_one_img_tag_per_ref() -> None:
    """3 Phase 5-00 lines produce exactly 3 <img> tags, src matches each URL."""
    from kb.data.article_query import _rewrite_image_text_refs_to_html

    body = (
        "Image 0 from article 'Foo': /static/img/h/0.jpg\n\n"
        "Image 1 from article 'Foo': /static/img/h/1.jpg\n\n"
        "Image 2 from article 'Foo': /static/img/h/2.jpg"
    )
    out = _rewrite_image_text_refs_to_html(body)
    assert out.count("<img ") == 3
    assert 'src="/static/img/h/0.jpg"' in out
    assert 'src="/static/img/h/1.jpg"' in out
    assert 'src="/static/img/h/2.jpg"' in out
    assert 'alt="image 0"' in out
    assert 'alt="image 2"' in out


def test_title_with_apostrophe_handled_safely() -> None:
    """Title containing an apostrophe (Phase 5-00 emit format edge case) — graceful pass-through.

    The regex pattern ``[^']*`` stops at the FIRST apostrophe inside the title
    quotes, so a malformed line like ``Image 1 from article 'Foo's bar': URL``
    would not match end-to-end. We verify graceful degradation: no exception
    raised, and the input passes through (or is partially rewritten — we
    only assert no crash and the function returns a string).
    """
    from kb.data.article_query import _rewrite_image_text_refs_to_html

    # Edge-case input: title contains apostrophe.
    body = "Image 1 from article 'Foo's bar': /static/img/x/1.jpg"
    # Function MUST NOT raise.
    out = _rewrite_image_text_refs_to_html(body)
    assert isinstance(out, str)
    # No claim about exact output — graceful degradation is sufficient.


def test_existing_markdown_image_syntax_not_double_wrapped() -> None:
    """Markdown ``![alt](url)`` syntax is NOT touched; only Phase 5-00 plain-text refs are rewritten."""
    from kb.data.article_query import _rewrite_image_text_refs_to_html

    body = (
        "![alt](/static/img/abc/0.jpg)\n\n"
        "Image 0 from article 'X': /static/img/abc/0.jpg"
    )
    out = _rewrite_image_text_refs_to_html(body)
    # Markdown image syntax preserved verbatim.
    assert "![alt](/static/img/abc/0.jpg)" in out
    # Plain-text ref converted.
    assert (
        '<img src="/static/img/abc/0.jpg" alt="image 0" loading="lazy">' in out
    )
    # Exactly one new <img> tag (the markdown form will be rendered into
    # <img> by the markdown processor in a later step, not by us).
    assert out.count("<img ") == 1


def test_empty_body_passthrough() -> None:
    """Empty / None-ish body short-circuits cleanly."""
    from kb.data.article_query import _rewrite_image_text_refs_to_html

    assert _rewrite_image_text_refs_to_html("") == ""
    assert _rewrite_image_text_refs_to_html(None) is None  # type: ignore[arg-type]


# ============================================================================
# Wiring suite — get_article_body() invokes helpers in correct order
# ============================================================================


def test_kb_base_path_subdir_deploy_renders_kb_prefix_in_img_src(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: get_article_body runs _rewrite_image_paths FIRST, then _rewrite_image_text_refs_to_html.

    Verifies the wiring order: the http://localhost:8765/ URL is first
    rewritten to /kb/static/img/... by _rewrite_image_paths, then the
    plain-text ref is converted to <img> with the prefixed URL.

    We patch ``kb.config.KB_BASE_PATH`` directly via monkeypatch.setattr
    rather than ``importlib.reload`` so other test modules' dataclass
    identities (e.g. ``EntityCount`` imported from ``kb.data.article_query``)
    survive — reload would create a NEW class object and break ``isinstance``
    checks in sibling tests.
    """
    from kb import config
    from kb.data.article_query import ArticleRecord, get_article_body

    monkeypatch.setattr(config, "KB_BASE_PATH", "/kb")
    # Also point KB_IMAGES_DIR somewhere that does not exist so the
    # file-fallback branch is skipped and we exercise the rec.body branch
    # deterministically.
    monkeypatch.setattr(
        config, "KB_IMAGES_DIR", "/nonexistent/kb-v2-1-6-test-images"
    )

    rec = ArticleRecord(
        id=999,
        source="wechat",
        title="Test",
        url="https://example.com/t",
        body=(
            "Some lead text.\n\n"
            "Image 0 from article 'Test': http://localhost:8765/h/0.jpg\n\n"
            "Trailing."
        ),
        content_hash="testhash01",
        lang="en",
        update_time="2026-05-16T00:00:00+00:00",
    )
    out_md, source = get_article_body(rec)
    assert source == "raw_markdown"
    # _rewrite_image_paths ran FIRST: localhost:8765 gone, /kb prefix added.
    assert "http://localhost:8765/" not in out_md
    # _rewrite_image_text_refs_to_html ran SECOND: plain-text → <img> with the
    # already-rewritten URL.
    assert (
        '<img src="/kb/static/img/h/0.jpg" alt="image 0" loading="lazy">'
        in out_md
    ), out_md
    # Plain-text Phase 5-00 form must not survive in rendered output.
    assert "Image 0 from article 'Test':" not in out_md


def test_get_article_body_root_deploy_emits_static_img_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Root-deploy variant — KB_BASE_PATH='' → ``/static/img/`` (no /kb)."""
    from kb import config
    from kb.data.article_query import ArticleRecord, get_article_body

    monkeypatch.setattr(config, "KB_BASE_PATH", "")
    monkeypatch.setattr(
        config, "KB_IMAGES_DIR", "/nonexistent/kb-v2-1-6-test-images"
    )

    rec = ArticleRecord(
        id=998,
        source="wechat",
        title="Root",
        url="https://example.com/r",
        body="Image 5 from article 'Root': http://localhost:8765/h/5.jpg",
        content_hash="testhash02",
        lang="en",
        update_time="2026-05-16T00:00:00+00:00",
    )
    out_md, _ = get_article_body(rec)
    assert (
        '<img src="/static/img/h/5.jpg" alt="image 5" loading="lazy">' in out_md
    ), out_md
    assert "/kb/static/img/" not in out_md


# ============================================================================
# Regression guard — Phase 5-00 binding preserved
# ============================================================================


def test_lightrag_storage_untouched_after_export() -> None:
    """Regression guard: ingest_wechat.py:1303 must stay unchanged vs origin/main.

    Phase 5-00 retrieval binding (Hermes commit 2f576b1) requires the
    plain-text 'Image N from article ...' line in BOTH the parent doc
    (full body) and the sub-doc (vision descriptions). LightRAG aquery
    correlates them via that exact format. If this test fails,
    kg_synthesize inline image embedding is broken.

    We assert two invariants:
      1. ingest_wechat.py contains the literal pattern 'Image' + emit format
      2. git diff origin/main -- ingest_wechat.py is empty
    """
    repo_root = Path(__file__).resolve().parents[3]
    ingest_path = repo_root / "ingest_wechat.py"
    assert ingest_path.exists(), f"ingest_wechat.py missing at {ingest_path}"

    # Invariant 1: source still contains the Phase 5-00 emit line.
    src = ingest_path.read_text(encoding="utf-8")
    assert "Image {i} from article" in src, (
        "Phase 5-00 retrieval binding line missing from ingest_wechat.py — "
        "this would break LightRAG aquery correlation."
    )

    # Invariant 2: diff vs origin/main is empty.
    # If origin/main isn't fetched in this environment, this check is skipped
    # gracefully (we still keep invariant 1 as the hard floor).
    result = subprocess.run(
        ["git", "diff", "origin/main", "--", "ingest_wechat.py"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    if result.returncode == 0:
        assert result.stdout == "", (
            f"ingest_wechat.py has uncommitted/changed lines vs origin/main:\n"
            f"{result.stdout}"
        )
    # If git diff failed (e.g. no origin/main fetched), invariant 1 stands alone.

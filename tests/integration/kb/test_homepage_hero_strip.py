"""Integration tests for kb-v2.1-3 hero-strip migration.

Covers homepage hero-image-strip rendering via the SSG export driver under
both deploy modes:

  - KB_BASE_PATH=''   (root deploy)   → bare /static/img/ paths
  - KB_BASE_PATH='/kb' (subdir deploy) → /kb/static/img/ paths

The strip lives in kb/templates/index.html (kb-v2.1-3 migration); previously
it existed only in the deployed Aliyun artifact, so any SSG re-export wiped
it. This test guards the migration: SSG output now contains the strip with
KB_BASE_PATH-correct image paths.

Skill(skill="frontend-design", args="Templatize the prod hero-strip snippet for index.html: image URLs through {{ base_path }}/static/img/{hash}/{file}; ZERO new :root vars; reuse kb-1/2/3 token classes. aria-label uses dual-language i18n concat per base.html line 4 pattern.")

Skill(skill="writing-tests", args="Testing Trophy: integration. Real fixture_db + real Jinja2 render via export_module. Parametrized over KB_BASE_PATH. Assert hero-strip present + 5 images + correct prefix + aria-label both langs. No internal mocks.")
"""
from __future__ import annotations

import importlib
import os
import re
from pathlib import Path

import pytest


# ---- Reload kb modules with KB_DB_PATH + KB_BASE_PATH parametrized -------


@pytest.fixture
def export_module_with_base_path(
    fixture_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Factory: returns a fresh `kb.export_knowledge_base` module reloaded
    with the requested KB_BASE_PATH (and KB_DB_PATH pointed at fixture_db).

    Mirrors test_export.py::export_module fixture pattern, but parametrizes
    base_path so a single test body can render both deploy modes.
    """
    def _build(base_path: str):
        monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
        if base_path:
            monkeypatch.setenv("KB_BASE_PATH", base_path)
        else:
            monkeypatch.delenv("KB_BASE_PATH", raising=False)
        images_dir = tmp_path / "images"
        images_dir.mkdir(exist_ok=True)
        monkeypatch.setenv("KB_IMAGES_DIR", str(images_dir))

        import kb.config
        import kb.data.article_query
        import kb.export_knowledge_base
        import kb.i18n

        importlib.reload(kb.config)
        importlib.reload(kb.i18n)
        # test_export pattern: don't reload article_query (would break
        # isinstance() in unit tests); patch its env-derived constant only.
        monkeypatch.setattr(
            kb.data.article_query,
            "QUALITY_FILTER_ENABLED",
            os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off",
        )
        importlib.reload(kb.export_knowledge_base)
        return kb.export_knowledge_base

    return _build


# ============================================================================
# Hero-strip presence + path-prefix assertions
# ============================================================================


def test_hero_strip_present_in_rendered_index_html_root_deploy(
    export_module_with_base_path,
    tmp_path: Path,
) -> None:
    """Default (no KB_BASE_PATH) deploy: hero-strip in output, bare paths."""
    mod = export_module_with_base_path(base_path="")
    out = tmp_path / "out_root"
    rc = mod.main(["--output-dir", str(out)])
    assert rc == 0

    html = (out / "index.html").read_text(encoding="utf-8")
    assert "hero-image-strip" in html, html[:1000]


def test_hero_strip_present_in_rendered_index_html_subdir_deploy(
    export_module_with_base_path,
    tmp_path: Path,
) -> None:
    """Subdir deploy (KB_BASE_PATH=/kb): hero-strip in output."""
    mod = export_module_with_base_path(base_path="/kb")
    out = tmp_path / "out_subdir"
    rc = mod.main(["--output-dir", str(out)])
    assert rc == 0

    html = (out / "index.html").read_text(encoding="utf-8")
    assert "hero-image-strip" in html, html[:1000]


def test_hero_strip_image_paths_use_kb_prefix_under_subdir_deploy(
    export_module_with_base_path,
    tmp_path: Path,
) -> None:
    """KB_BASE_PATH=/kb: all 5 hero-strip images use /kb/static/img/ prefix."""
    mod = export_module_with_base_path(base_path="/kb")
    out = tmp_path / "out_subdir_paths"
    rc = mod.main(["--output-dir", str(out)])
    assert rc == 0

    html = (out / "index.html").read_text(encoding="utf-8")

    # All 5 image filenames present and prefixed with /kb/static/img/.
    expected_paths = [
        f'/kb/static/img/009b932a7d/{n}.jpg' for n in (1, 10, 11, 12, 13)
    ]
    for p in expected_paths:
        assert p in html, f"missing prefixed path: {p}"

    # No bare /static/img/009b932a7d/ in the hero-strip block.
    # Extract just the strip block to scope the negative assertion.
    m = re.search(
        r'<div class="hero-image-strip".*?</div>', html, flags=re.DOTALL
    )
    assert m is not None, "hero-image-strip block missing"
    strip_block = m.group(0)
    assert 'src="/static/img/009b932a7d/' not in strip_block, strip_block


def test_hero_strip_image_paths_bare_when_no_base_path(
    export_module_with_base_path,
    tmp_path: Path,
) -> None:
    """Default deploy: hero-strip images use bare /static/img/ (no /kb/)."""
    mod = export_module_with_base_path(base_path="")
    out = tmp_path / "out_root_paths"
    rc = mod.main(["--output-dir", str(out)])
    assert rc == 0

    html = (out / "index.html").read_text(encoding="utf-8")

    # All 5 images on bare /static/img/ path.
    for n in (1, 10, 11, 12, 13):
        assert f'/static/img/009b932a7d/{n}.jpg' in html

    # Hero-strip block contains no /kb/static/img/ path.
    m = re.search(
        r'<div class="hero-image-strip".*?</div>', html, flags=re.DOTALL
    )
    assert m is not None
    strip_block = m.group(0)
    assert '/kb/static/img/' not in strip_block, strip_block


def test_hero_strip_aria_label_renders_both_languages(
    export_module_with_base_path,
    tmp_path: Path,
) -> None:
    """aria-label uses dual-language i18n concat per base.html title pattern.

    Both Chinese (知识库图片预览) and English (Knowledge base image preview)
    must appear in the rendered aria-label so screen readers in either
    locale receive a meaningful description.
    """
    mod = export_module_with_base_path(base_path="")
    out = tmp_path / "out_aria"
    rc = mod.main(["--output-dir", str(out)])
    assert rc == 0

    html = (out / "index.html").read_text(encoding="utf-8")

    m = re.search(
        r'<div class="hero-image-strip"[^>]*aria-label="([^"]+)"',
        html,
    )
    assert m is not None, "hero-image-strip aria-label missing"
    aria = m.group(1)
    assert "知识库图片预览" in aria, aria
    assert "Knowledge base image preview" in aria, aria

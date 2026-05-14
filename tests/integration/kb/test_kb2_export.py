"""kb-2 end-to-end integration test (plan 10).

Exercises the FULL SSG pipeline against the shared fixture_db (plan 01).
Asserts kb-2 outputs exist, structural patterns present, JSON-LD emitted,
and UI-SPEC §8 acceptance grep patterns pass.

Testing Trophy: integration with real SQLite fixture, real driver subprocess,
real generated output. No mocks. Mirrors the kb-1 test_export.py invocation
pattern; this test is the integrating gate for plans 04-09.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPORT_SCRIPT = REPO_ROOT / "kb" / "export_knowledge_base.py"


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def kb2_export(tmp_path_factory) -> tuple[Path, Path]:
    """Run the export driver once per module; subsequent tests share the output dir.

    Returns (output_dir, fixture_db_path). The fixture builds its own DB rather
    than reusing the function-scoped `fixture_db` from conftest.py because we
    want module-scope sharing — running the full export per test would be ~1s ×
    N tests; running once and reading output is ~1s + ms per assertion.
    """
    # Build fixture DB at module scope (mirrors conftest.fixture_db logic).
    from tests.integration.kb.conftest import build_kb2_fixture_db

    base = tmp_path_factory.mktemp("kb2_export")
    fixture_db = base / "fixture.db"
    build_kb2_fixture_db(fixture_db)

    output_dir = base / "kb_output"
    output_dir.mkdir()
    images_dir = base / "images"
    images_dir.mkdir()

    env = {
        **os.environ,
        "KB_DB_PATH": str(fixture_db),
        "KB_OUTPUT_DIR": str(output_dir),
        "KB_IMAGES_DIR": str(images_dir),
        "KB_ENTITY_MIN_FREQ": "5",
    }
    before_md5 = _md5(fixture_db)
    result = subprocess.run(
        [sys.executable, str(EXPORT_SCRIPT), "--output-dir", str(output_dir)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"driver failed: stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # Read-only enforcement: DB unchanged
    after_md5 = _md5(fixture_db)
    assert after_md5 == before_md5, (
        f"Driver wrote to fixture_db (EXPORT-02 violation): "
        f"pre={before_md5} post={after_md5}"
    )
    return output_dir, fixture_db


# ---- Read-only enforcement (EXPORT-02) ----


@pytest.mark.integration
def test_fixture_db_unchanged_after_export(kb2_export: tuple[Path, Path]) -> None:
    """The kb2_export fixture itself asserts md5 invariance; this test makes the
    contract visible at the test-layer level."""
    output_dir, fixture_db = kb2_export
    assert fixture_db.exists()
    # If we got here, the kb2_export fixture's md5 check passed.
    # Re-verify the DB still exists and is readable.
    assert fixture_db.stat().st_size > 0


# ---- Topic page outputs (TOPIC-01, TOPIC-03) ----


@pytest.mark.integration
@pytest.mark.parametrize("slug", ["agent", "cv", "llm", "nlp", "rag"])
def test_topic_html_generated(kb2_export: tuple[Path, Path], slug: str) -> None:
    """TOPIC-01: 5 topic HTMLs generated (one per fixed kb-2 topic)."""
    output_dir, _ = kb2_export
    path = output_dir / "topics" / f"{slug}.html"
    assert path.exists(), f"Topic HTML missing for slug={slug} at {path}"


@pytest.mark.integration
def test_topic_html_contains_required_classes(kb2_export: tuple[Path, Path]) -> None:
    """UI-SPEC §8 #3-7: topic-pillar-header / -layout / -sidebar, chip--entity, article-card."""
    output_dir, _ = kb2_export
    sample_path = output_dir / "topics" / "agent.html"
    assert sample_path.exists()
    sample = sample_path.read_text(encoding="utf-8")
    for cls in (
        "topic-pillar-header",
        "topic-pillar-layout",
        "topic-pillar-sidebar",
        "chip--entity",
        "article-card",
    ):
        assert cls in sample, f"Missing class {cls!r} in {sample_path}"


@pytest.mark.integration
def test_topic_html_has_collectionpage_jsonld(kb2_export: tuple[Path, Path]) -> None:
    """UI-SPEC §8 #8: CollectionPage JSON-LD emitted on topic pages."""
    output_dir, _ = kb2_export
    sample_path = output_dir / "topics" / "agent.html"
    sample = sample_path.read_text(encoding="utf-8")
    assert "CollectionPage" in sample, "CollectionPage JSON-LD type missing"
    assert "application/ld+json" in sample, "JSON-LD script tag missing"
    # The JSON-LD block should be valid JSON; extract + parse to confirm.
    m = re.search(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        sample,
        re.DOTALL,
    )
    assert m, "Could not locate JSON-LD <script> body"
    payload = json.loads(m.group(1))
    assert payload.get("@type") == "CollectionPage"


# ---- Entity page outputs (ENTITY-01, ENTITY-02, ENTITY-03) ----


@pytest.mark.integration
def test_entity_html_count_meets_threshold(kb2_export: tuple[Path, Path]) -> None:
    """ENTITY-01: at least 6 entity HTMLs (fixture has 6 above-threshold)."""
    output_dir, _ = kb2_export
    entity_files = list((output_dir / "entities").glob("*.html"))
    assert len(entity_files) >= 6, (
        f"Expected >=6 entity HTMLs (fixture above-threshold), got {len(entity_files)}: "
        f"{[f.name for f in entity_files]}"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "slug",
    ["openai", "langchain", "lightrag", "anthropic", "autogen", "mcp"],
)
def test_entity_html_for_known_fixture_entities(
    kb2_export: tuple[Path, Path], slug: str
) -> None:
    """ENTITY-02: each above-threshold fixture entity has an HTML at expected slug."""
    output_dir, _ = kb2_export
    path = output_dir / "entities" / f"{slug}.html"
    assert path.exists(), f"No entity HTML for slug={slug} at {path}"


@pytest.mark.integration
def test_entity_html_contains_required_classes(kb2_export: tuple[Path, Path]) -> None:
    """UI-SPEC §8 #9-12: entity-header, entity-lang-distribution, lang-badge, article-card."""
    output_dir, _ = kb2_export
    sample_path = output_dir / "entities" / "openai.html"
    assert sample_path.exists()
    sample = sample_path.read_text(encoding="utf-8")
    for cls in (
        "entity-header",
        "entity-lang-distribution",
        "lang-badge",
        "article-card",
    ):
        assert cls in sample, f"Missing class {cls!r} in {sample_path}"


@pytest.mark.integration
def test_entity_html_has_thing_jsonld(kb2_export: tuple[Path, Path]) -> None:
    """UI-SPEC §8 #13: generic Thing JSON-LD on entity pages.

    Negative assertion: must NOT typed as Person/Organization/SoftwareApplication
    (typed entities deferred to v2.1 TYPED-* per UI-SPEC §6).
    """
    output_dir, _ = kb2_export
    sample_path = output_dir / "entities" / "openai.html"
    sample = sample_path.read_text(encoding="utf-8")
    # Match @type: "Thing" with JSON whitespace tolerance
    assert re.search(r'"@type"\s*:\s*"Thing"', sample), (
        f"No generic Thing JSON-LD in {sample_path}"
    )
    # Negative: not typed yet (v2.0 baseline)
    for forbidden in ("Person", "Organization", "SoftwareApplication"):
        assert re.search(rf'"@type"\s*:\s*"{forbidden}"', sample) is None, (
            f"Forbidden typed JSON-LD @type={forbidden!r} found in {sample_path}"
        )


@pytest.mark.integration
def test_below_threshold_entities_have_no_pages(kb2_export: tuple[Path, Path]) -> None:
    """Negative test: ObscureLib (freq=2) and OneOffMention (freq=3) MUST NOT have pages."""
    output_dir, _ = kb2_export
    entity_files = list((output_dir / "entities").glob("*.html"))
    names = {f.stem for f in entity_files}
    assert "obscurelib" not in names, "ObscureLib (below threshold) leaked into entity output"
    assert "oneoffmention" not in names, (
        "OneOffMention (below threshold) leaked into entity output"
    )


# ---- Homepage extensions (LINK-03) ----


@pytest.mark.integration
def test_homepage_has_topic_section(kb2_export: tuple[Path, Path]) -> None:
    """UI-SPEC §8 #14, #16: section--topics + article-list--topics on homepage."""
    output_dir, _ = kb2_export
    index_path = output_dir / "index.html"
    assert index_path.exists()
    sample = index_path.read_text(encoding="utf-8")
    assert "section--topics" in sample, "section--topics missing from index.html"
    assert "article-list--topics" in sample, "article-list--topics missing from index.html"


@pytest.mark.integration
def test_homepage_has_entity_section(kb2_export: tuple[Path, Path]) -> None:
    """UI-SPEC §8 #15, #17, #18: section--entities + entity-cloud + chip--entity-cloud."""
    output_dir, _ = kb2_export
    index_path = output_dir / "index.html"
    sample = index_path.read_text(encoding="utf-8")
    assert "section--entities" in sample, "section--entities missing from index.html"
    assert "entity-cloud" in sample, "entity-cloud missing from index.html"
    assert "chip--entity-cloud" in sample, "chip--entity-cloud missing from index.html"


# ---- Article aside (LINK-01 + LINK-02) ----


@pytest.mark.integration
def test_article_html_has_detail_layout_and_aside(
    kb2_export: tuple[Path, Path],
) -> None:
    """UI-SPEC §8 #19, #20: article-detail-layout + article-aside present in articles."""
    output_dir, _ = kb2_export
    article_files = list((output_dir / "articles").glob("*.html"))
    # Filter out articles/index.html (the list page, not a detail page)
    detail_files = [f for f in article_files if f.name != "index.html"]
    assert detail_files, "No article detail HTML files found"
    # At least one detail HTML must contain the layout + aside hooks (the article
    # template emits both unconditionally; the aside content is conditional on
    # related_entities / related_topics being non-empty).
    matches = [
        f
        for f in detail_files
        if "article-detail-layout" in f.read_text(encoding="utf-8")
        and "article-aside" in f.read_text(encoding="utf-8")
    ]
    assert matches, (
        "No article HTML contains article-detail-layout + article-aside; "
        f"checked {len(detail_files)} files"
    )


# ---- Sitemap auto-extension (EXPORT-06) ----


@pytest.mark.integration
def test_sitemap_contains_topic_and_entity_urls(
    kb2_export: tuple[Path, Path],
) -> None:
    """UI-SPEC §8 #32, #33: sitemap.xml lists /topics/* + /entities/* paths."""
    output_dir, _ = kb2_export
    sitemap_path = output_dir / "sitemap.xml"
    assert sitemap_path.exists(), "sitemap.xml not generated"
    sample = sitemap_path.read_text(encoding="utf-8")
    assert "topics/agent.html" in sample, (
        f"sitemap missing /topics/agent.html: {sample[:500]}"
    )
    # At least one entity URL present
    assert "/entities/" in sample, (
        f"sitemap missing /entities/ paths: {sample[:500]}"
    )
    # Verify count: 3 index + 8 articles + 5 topics + 6 entities = 22
    url_count = sample.count("<url>")
    assert url_count == 22, f"Expected 22 <url> entries (3+8+5+6), got {url_count}"


# ---- UI-SPEC §8 #1-2: template existence ----


@pytest.mark.integration
@pytest.mark.parametrize(
    "template_name",
    ["topic.html", "entity.html"],
)
def test_template_file_exists(template_name: str) -> None:
    """UI-SPEC §8 #1, #2: kb/templates/topic.html + entity.html exist on disk."""
    path = REPO_ROOT / "kb" / "templates" / template_name
    assert path.exists(), f"Template missing: {path}"


# ---- UI-SPEC §8 #3-22: template-source structural class regression ----


@pytest.mark.integration
@pytest.mark.parametrize(
    "filename,pattern",
    [
        # Topic page (#3-8)
        ("topic.html", "topic-pillar-header"),
        ("topic.html", "topic-pillar-layout"),
        ("topic.html", "topic-pillar-sidebar"),
        ("topic.html", "chip--entity"),
        ("topic.html", "article-card"),
        ("topic.html", "CollectionPage"),
        # Entity page (#9-13)
        ("entity.html", "entity-header"),
        ("entity.html", "entity-lang-distribution"),
        ("entity.html", "lang-badge"),
        ("entity.html", "article-card"),
        ("entity.html", "Thing"),
        # Homepage extensions (#14-18)
        ("index.html", "section--topics"),
        ("index.html", "section--entities"),
        ("index.html", "article-list--topics"),
        ("index.html", "entity-cloud"),
        ("index.html", "chip--entity-cloud"),
        # Article extensions (#19-22)
        ("article.html", "article-detail-layout"),
        ("article.html", "article-aside"),
        ("article.html", "related_entities"),
        ("article.html", "related_topics"),
    ],
)
def test_template_source_contains_pattern(filename: str, pattern: str) -> None:
    """UI-SPEC §8 #3-22 source-side regression: each template carries required structural classes."""
    source = (REPO_ROOT / "kb" / "templates" / filename).read_text(encoding="utf-8")
    assert pattern in source, f"{filename} missing UI-SPEC §8 pattern: {pattern!r}"


# ---- UI-SPEC §8 #23-27: locale key parity (i18n) ----


@pytest.mark.integration
@pytest.mark.parametrize(
    "filename,key",
    [
        # #23-24: home section titles
        ("zh-CN.json", "home.section.topics_title"),
        ("en.json", "home.section.topics_title"),
        ("zh-CN.json", "home.section.entities_title"),
        ("en.json", "home.section.entities_title"),
        # #25: topic display names
        ("zh-CN.json", "topic.agent.name"),
        ("en.json", "topic.agent.name"),
        # #26: article related-row heading
        ("zh-CN.json", "article.related_entities"),
        ("en.json", "article.related_entities"),
        # #27: entity lang-distribution aria
        ("zh-CN.json", "entity.lang_distribution_aria"),
        ("en.json", "entity.lang_distribution_aria"),
    ],
)
def test_locale_contains_key(filename: str, key: str) -> None:
    """UI-SPEC §8 #23-27: i18n keys present in BOTH locale files."""
    path = REPO_ROOT / "kb" / "locale" / filename
    content = path.read_text(encoding="utf-8")
    assert f'"{key}"' in content, f"{filename} missing i18n key: {key!r}"


# ---- UI-SPEC §8 #28-29: new icon clauses ----


@pytest.mark.integration
@pytest.mark.parametrize("icon_name", ["folder-tag", "users"])
def test_icon_clause_exists(icon_name: str) -> None:
    """UI-SPEC §8 #28-29: new icons exist in kb/templates/_icons.html macro."""
    content = (REPO_ROOT / "kb" / "templates" / "_icons.html").read_text(encoding="utf-8")
    assert f"name == '{icon_name}'" in content, (
        f"Icon clause missing in _icons.html: {icon_name!r}"
    )


# ---- UI-SPEC §8 #30-31: build-output structural existence (already covered above by
#      test_topic_html_generated + test_entity_html_count_meets_threshold; this test
#      provides the explicit §8 #30 multi-file check). ----


@pytest.mark.integration
def test_all_five_topic_outputs_exist(kb2_export: tuple[Path, Path]) -> None:
    """UI-SPEC §8 #30: kb/output/topics/{agent,cv,llm,nlp,rag}.html all exist."""
    output_dir, _ = kb2_export
    for slug in ("agent", "cv", "llm", "nlp", "rag"):
        path = output_dir / "topics" / f"{slug}.html"
        assert path.exists(), f"UI-SPEC §8 #30: missing topic page {path}"


# ---- UI-SPEC §8 #35: style.css LOC budget ----


@pytest.mark.integration
def test_style_css_under_loc_budget() -> None:
    """UI-SPEC §8 #35: style.css LOC budget (kb-3-rebased ceiling).

    Original UI-SPEC §8 #35 budget: ≤ 1937 LOC (kb-1 1737 + kb-2 budget +200).
    kb-2-08 SUMMARY pre-escalated a 42-LOC overrun (1979 actual) caused by
    consolidating §3.2 + §3.3 + §3.4 CSS blocks into a single plan, rebasing
    the ceiling to ≤ 2000.

    kb-3-UI-SPEC §8 line 440 re-escalates the ceiling to ≤ 2100 to fund the
    Q&A 8-state matrix component (kb-3-10) + search inline reveal (kb-3-11).
    This test enforces the kb-3-rebased budget so future drift is still
    caught loudly. Any genuine new feature CSS beyond kb-3 should re-escalate
    to a new budget.
    """
    path = REPO_ROOT / "kb" / "static" / "style.css"
    loc = sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
    assert loc <= 2100, (
        f"style.css LOC {loc} exceeds kb-3-rebased UI-SPEC §8 #35 budget of 2100 "
        f"({loc - 2100} over) — escalate before adding more CSS"
    )

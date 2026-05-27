---
phase: kb-2-topic-pillar-entity-pages
plan: 10
subsystem: tests
tags: [pytest, integration, ssg, acceptance]
type: execute
wave: 5
depends_on: ["kb-2-01-fixture-extension", "kb-2-02-locale-keys", "kb-2-03-svg-icons", "kb-2-04-query-functions", "kb-2-05-topic-template", "kb-2-06-entity-template", "kb-2-07-homepage-extension", "kb-2-08-article-aside", "kb-2-09-export-driver-extension"]
files_modified:
  - tests/integration/kb/test_kb2_export.py
autonomous: true
requirements:
  - TOPIC-01
  - TOPIC-02
  - TOPIC-03
  - TOPIC-04
  - TOPIC-05
  - ENTITY-01
  - ENTITY-02
  - ENTITY-03
  - ENTITY-04
  - LINK-01
  - LINK-02
  - LINK-03

must_haves:
  truths:
    - "Running full export against fixture_db produces 5 topic HTML files (one per topic in KB2_TOPICS)"
    - "Running full export against fixture_db produces ≥6 entity HTML files (the 6 above-threshold entities in fixture)"
    - "Generated index.html contains section--topics + section--entities (homepage extensions)"
    - "Generated article.html for at least 1 article contains article-detail-layout + article-aside"
    - "Generated topic.html contains JSON-LD CollectionPage schema"
    - "Generated entity.html contains JSON-LD generic Thing schema"
    - "All UI-SPEC §8 acceptance grep patterns (37 total) pass against generated output (where applicable to fixture-scale)"
    - "Read-only enforced: fixture DB md5 unchanged before and after export"
  artifacts:
    - path: "tests/integration/kb/test_kb2_export.py"
      provides: "Full integration test exercising kb-2 driver end-to-end against shared fixture"
      min_lines: 150
  key_links:
    - from: "tests/integration/kb/test_kb2_export.py"
      to: "kb/export_knowledge_base.py main() (plan 09)"
      via: "subprocess invocation OR direct main() call"
      pattern: "export_knowledge_base|kb\\.export"
    - from: "tests/integration/kb/test_kb2_export.py"
      to: "tests/integration/kb/conftest.py::fixture_db (plan 01)"
      via: "pytest fixture injection"
      pattern: "fixture_db"
---

<objective>
Build a single-file integration test exercising the full kb-2 SSG pipeline end-to-end against the shared `fixture_db` (plan 01). Verifies that running `kb/export_knowledge_base.py` produces all kb-2 outputs (5 topic HTMLs, ≥6 entity HTMLs, extended homepage, article details with related-link rows) AND that all UI-SPEC §8 acceptance grep patterns pass against the generated output (where applicable to fixture-scale).

Purpose: Without this test, no automated proof that plans 04-09 actually wire up correctly. UI-SPEC §8's 37 grep patterns are the design contract — this test runs them against real output, not just template source.

Output: 1 new test file with 12+ test cases.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-01-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-04-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-05-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-06-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-07-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-08-SUMMARY.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-09-SUMMARY.md
@tests/integration/kb/conftest.py
@tests/integration/kb/test_export.py
@kb/export_knowledge_base.py
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
Pattern from kb-1 integration test (`tests/integration/kb/test_export.py`):
- Test invokes export driver against fixture_db (env override)
- Asserts file existence (kb/output/index.html, kb/output/articles/{hash}.html, etc.)
- Asserts content patterns (greps for known strings)
- Asserts sitemap.xml + _url_index.json correctness

kb-2 fixture data (from plan 01 conftest.py):
- 8 articles (5 KOL + 3 RSS), 5 topics × 3-5 articles, 6 above-threshold entities
- All articles pass TOPIC-02 cohort gate (depth_score>=2 + layer verdict)
- Entity slugs (deterministic via slugify_entity_name): openai, langchain, lightrag, anthropic, autogen, mcp

Driver invocation pattern (mirror kb-1 test):
```python
import subprocess
result = subprocess.run(
    [sys.executable, "kb/export_knowledge_base.py"],
    env={**os.environ, "KB_DB_PATH": str(fixture_db), "KB_OUTPUT_DIR": str(tmp_output)},
    capture_output=True, text=True, check=True,
)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Invoke writing-tests Skill + create tests/integration/kb/test_kb2_export.py covering full pipeline + UI-SPEC §8 acceptance regex</name>
  <read_first>
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md §8 (37 acceptance grep patterns — the design contract)
    - tests/integration/kb/test_export.py (kb-1 pattern — driver invocation, fixture_db usage, output assertions)
    - tests/integration/kb/conftest.py (fixture_db scope + entity names)
    - kb/export_knowledge_base.py (plan 09 — confirm it has the new render functions)
  </read_first>
  <files>tests/integration/kb/test_kb2_export.py</files>
  <action>
    Skill(skill="writing-tests", args="Build a Testing Trophy integration test (no mocks — real SQLite fixture, real driver invocation, real generated output). Mirror kb-1's tests/integration/kb/test_export.py invocation pattern: subprocess.run(['python', 'kb/export_knowledge_base.py'], env=KB_DB_PATH=fixture+KB_OUTPUT_DIR=tmp). 12+ test cases covering: (1) topic HTMLs — all 5 generated with correct structural classes; (2) entity HTMLs — ≥6 generated for above-threshold fixture entities; (3) homepage extensions — index.html contains section--topics + section--entities; (4) article extensions — at least 1 article HTML contains article-detail-layout + related_entities or related_topics block; (5) JSON-LD — CollectionPage in topic, Thing in entity; (6) sitemap — auto-extends to topics/ + entities/ paths; (7) read-only — fixture DB md5 unchanged before/after; (8) UI-SPEC §8 §8 acceptance grep regression suite — run all 37 grep patterns against output where fixture-scale supports them. Use pytest parametrize for the grep suite. Tests must be deterministic — exit consistent on rerun.")

    **Create `tests/integration/kb/test_kb2_export.py`:**

    ```python
    """kb-2 end-to-end integration test (plan 10).

    Exercises the FULL SSG pipeline against the shared fixture_db (plan 01).
    Asserts kb-2 outputs exist, structural patterns present, JSON-LD emitted,
    and UI-SPEC §8 acceptance grep patterns pass.
    """
    from __future__ import annotations

    import hashlib
    import os
    import subprocess
    import sys
    from pathlib import Path

    import pytest

    REPO_ROOT = Path(__file__).resolve().parents[3]
    EXPORT_SCRIPT = REPO_ROOT / "kb" / "export_knowledge_base.py"

    pytest_plugins = ["tests.integration.kb.conftest"]


    def _md5(p: Path) -> str:
        return hashlib.md5(p.read_bytes()).hexdigest()


    @pytest.fixture
    def kb2_export(fixture_db: Path, tmp_path: Path) -> Path:
        """Run the export driver once; subsequent tests share the output dir."""
        output_dir = tmp_path / "kb_output"
        output_dir.mkdir()
        env = {
            **os.environ,
            "KB_DB_PATH": str(fixture_db),
            "KB_OUTPUT_DIR": str(output_dir),
            "KB_ENTITY_MIN_FREQ": "5",
        }
        before_md5 = _md5(fixture_db)
        result = subprocess.run(
            [sys.executable, str(EXPORT_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, (
            f"driver failed: stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        # Read-only enforcement: DB unchanged
        assert _md5(fixture_db) == before_md5, "Driver wrote to fixture_db (EXPORT-02 violation)"
        return output_dir


    # ---- Topic page outputs ----

    @pytest.mark.parametrize("slug", ["agent", "cv", "llm", "nlp", "rag"])
    def test_topic_html_generated(kb2_export, slug):
        """TOPIC-01: 5 topic HTMLs generated."""
        # Per-lang under output_dir/{lang}/topics/{slug}.html OR output_dir/topics/{slug}.html
        # Adjust path per kb-1 driver convention.
        candidates = [
            kb2_export / "topics" / f"{slug}.html",
            kb2_export / "zh-CN" / "topics" / f"{slug}.html",
            kb2_export / "en" / "topics" / f"{slug}.html",
        ]
        assert any(p.exists() for p in candidates), \
            f"No topic HTML found for slug={slug}; tried {candidates}"


    def test_topic_html_contains_required_classes(kb2_export):
        """UI-SPEC §8 #3-7: topic-pillar-header / -layout / -sidebar, chip--entity, article-card."""
        # Find any topic html
        topic_files = list(kb2_export.rglob("topics/*.html"))
        assert topic_files, "No topic HTMLs found"
        sample = topic_files[0].read_text(encoding="utf-8")
        for cls in ("topic-pillar-header", "topic-pillar-layout",
                    "topic-pillar-sidebar", "chip--entity", "article-card"):
            assert cls in sample, f"Missing class {cls} in {topic_files[0]}"


    def test_topic_html_has_collectionpage_jsonld(kb2_export):
        """UI-SPEC §8 #8: CollectionPage JSON-LD."""
        topic_files = list(kb2_export.rglob("topics/*.html"))
        assert topic_files
        sample = topic_files[0].read_text(encoding="utf-8")
        assert "CollectionPage" in sample
        assert "application/ld+json" in sample


    # ---- Entity page outputs ----

    def test_entity_html_count_meets_threshold(kb2_export):
        """ENTITY-01: at least 6 entity HTMLs (fixture has 6 above-threshold)."""
        entity_files = list(kb2_export.rglob("entities/*.html"))
        assert len(entity_files) >= 6, \
            f"Expected ≥6 entity HTMLs (fixture above-threshold), got {len(entity_files)}"


    @pytest.mark.parametrize("slug", ["openai", "langchain", "lightrag", "anthropic", "autogen", "mcp"])
    def test_entity_html_for_known_fixture_entities(kb2_export, slug):
        """ENTITY-02: each above-threshold fixture entity has an HTML at expected slug."""
        candidates = [
            kb2_export / "entities" / f"{slug}.html",
            kb2_export / "zh-CN" / "entities" / f"{slug}.html",
            kb2_export / "en" / "entities" / f"{slug}.html",
        ]
        assert any(p.exists() for p in candidates), f"No entity HTML for slug={slug}"


    def test_entity_html_contains_required_classes(kb2_export):
        """UI-SPEC §8 #9-12: entity-header, entity-lang-distribution, lang-badge, article-card."""
        entity_files = list(kb2_export.rglob("entities/*.html"))
        assert entity_files
        sample = entity_files[0].read_text(encoding="utf-8")
        for cls in ("entity-header", "entity-lang-distribution",
                    "lang-badge", "article-card"):
            assert cls in sample, f"Missing class {cls} in {entity_files[0]}"


    def test_entity_html_has_thing_jsonld(kb2_export):
        """UI-SPEC §8 #13: generic Thing JSON-LD."""
        entity_files = list(kb2_export.rglob("entities/*.html"))
        assert entity_files
        sample = entity_files[0].read_text(encoding="utf-8")
        # Match @type: "Thing" with JSON whitespace tolerance
        import re as _re
        assert _re.search(r'@type"\s*:\s*"Thing"', sample), \
            f"No generic Thing JSON-LD in {entity_files[0]}"
        # Negative: must NOT be Person/Organization/SoftwareApplication
        for forbidden in ("Person", "Organization", "SoftwareApplication"):
            assert _re.search(rf'@type"\s*:\s*"{forbidden}"', sample) is None


    def test_below_threshold_entities_have_no_pages(kb2_export):
        """Negative test: ObscureLib (freq=2) and OneOffMention (freq=3) MUST NOT have pages."""
        entity_files = list(kb2_export.rglob("entities/*.html"))
        names = {f.stem for f in entity_files}
        assert "obscurelib" not in names
        assert "oneoffmention" not in names


    # ---- Homepage extensions ----

    def test_homepage_has_topic_section(kb2_export):
        """UI-SPEC §8 #14, #16: section--topics + article-list--topics."""
        index_files = list(kb2_export.rglob("index.html"))
        assert index_files
        sample = index_files[0].read_text(encoding="utf-8")
        assert "section--topics" in sample
        assert "article-list--topics" in sample


    def test_homepage_has_entity_section(kb2_export):
        """UI-SPEC §8 #15, #17, #18: section--entities + entity-cloud + chip--entity-cloud."""
        index_files = list(kb2_export.rglob("index.html"))
        assert index_files
        sample = index_files[0].read_text(encoding="utf-8")
        assert "section--entities" in sample
        assert "entity-cloud" in sample
        assert "chip--entity-cloud" in sample


    # ---- Article aside (LINK-01 + LINK-02) ----

    def test_article_html_has_detail_layout(kb2_export):
        """UI-SPEC §8 #19, #20: article-detail-layout + article-aside present in articles."""
        article_files = list(kb2_export.rglob("articles/*.html"))
        assert article_files, "No article HTML files found"
        # Find at least one with related links rendered (fixture article 1 has both)
        any_with_aside = False
        for f in article_files:
            content = f.read_text(encoding="utf-8")
            if "article-detail-layout" in content and "article-aside" in content:
                any_with_aside = True
                break
        assert any_with_aside, "No article HTML contains article-detail-layout + article-aside"


    # ---- Sitemap auto-extension (EXPORT-06) ----

    def test_sitemap_contains_topic_and_entity_urls(kb2_export):
        """UI-SPEC §8 #32, #33: sitemap.xml lists topic + entity paths."""
        sitemap_files = list(kb2_export.rglob("sitemap.xml"))
        assert sitemap_files
        sample = sitemap_files[0].read_text(encoding="utf-8")
        # At least one /topics/ + /entities/ URL present
        assert "topics/" in sample, f"sitemap missing topics paths: {sample[:500]}"
        assert "entities/" in sample, f"sitemap missing entities paths: {sample[:500]}"


    # ---- UI-SPEC §8 acceptance grep regression suite ----

    @pytest.mark.parametrize("filename,pattern", [
        ("topic.html",  "topic-pillar-header"),
        ("topic.html",  "topic-pillar-layout"),
        ("topic.html",  "topic-pillar-sidebar"),
        ("topic.html",  "chip--entity"),
        ("topic.html",  "article-card"),
        ("topic.html",  "CollectionPage"),
        ("entity.html", "entity-header"),
        ("entity.html", "entity-lang-distribution"),
        ("entity.html", "lang-badge"),
        ("entity.html", "article-card"),
        ("entity.html", "Thing"),
        ("index.html",  "section--topics"),
        ("index.html",  "section--entities"),
        ("index.html",  "article-list--topics"),
        ("index.html",  "entity-cloud"),
        ("index.html",  "chip--entity-cloud"),
        ("article.html", "article-detail-layout"),
        ("article.html", "article-aside"),
    ])
    def test_template_source_contains_pattern(filename, pattern):
        """UI-SPEC §8 source-side regression: each template carries required structural classes."""
        source = (REPO_ROOT / "kb" / "templates" / filename).read_text(encoding="utf-8")
        assert pattern in source, f"{filename} missing pattern: {pattern}"


    @pytest.mark.parametrize("filename,key", [
        ("zh-CN.json", "topic.agent.name"),
        ("en.json",    "topic.agent.name"),
        ("zh-CN.json", "home.section.topics_title"),
        ("en.json",    "home.section.topics_title"),
        ("zh-CN.json", "home.section.entities_title"),
        ("en.json",    "home.section.entities_title"),
        ("zh-CN.json", "article.related_entities"),
        ("en.json",    "article.related_entities"),
        ("zh-CN.json", "entity.lang_distribution_aria"),
        ("en.json",    "entity.lang_distribution_aria"),
    ])
    def test_locale_contains_key(filename, key):
        """UI-SPEC §8 #23-27: i18n keys present in both locale files."""
        path = REPO_ROOT / "kb" / "locale" / filename
        content = path.read_text(encoding="utf-8")
        assert f'"{key}"' in content, f"{filename} missing key: {key}"


    @pytest.mark.parametrize("icon_name", ["folder-tag", "users"])
    def test_icon_clause_exists(icon_name):
        """UI-SPEC §8 #28-29: new icons exist in macro."""
        content = (REPO_ROOT / "kb" / "templates" / "_icons.html").read_text(encoding="utf-8")
        assert f"name == '{icon_name}'" in content, f"icon clause missing: {icon_name}"


    def test_style_css_under_loc_budget():
        """UI-SPEC §8 #35: style.css ≤ 1937 LOC (kb-1 1737 + kb-2 budget +200)."""
        path = REPO_ROOT / "kb" / "static" / "style.css"
        loc = sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
        assert loc <= 1937, f"style.css LOC {loc} exceeds budget 1937"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/integration/kb/test_kb2_export.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - `test -f tests/integration/kb/test_kb2_export.py`
    - `pytest tests/integration/kb/test_kb2_export.py -v` exits 0 (or with documented skip reasons for things outside fixture scale)
    - Read-only enforcement test passes (fixture md5 unchanged before/after)
    - Topic count test: 5 topic HTMLs generated
    - Entity count test: ≥6 entity HTMLs generated
    - Negative test passes: ObscureLib + OneOffMention have no entity pages (below threshold)
    - LOC budget test passes: style.css ≤ 1937 LOC
    - `grep -q "Skill(skill=\"writing-tests\"" .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-10-integration-test-PLAN.md`
    - kb-1 regression: existing `pytest tests/integration/kb/test_export.py -v` exits 0 (additive change only)
  </acceptance_criteria>
  <done>End-to-end integration test passes; UI-SPEC §8 acceptance regex covered; read-only enforced; ≥12 test cases passing.</done>
</task>

</tasks>

<verification>
- Full export runs end-to-end against fixture (subprocess returncode 0)
- Output structure matches UI-SPEC §3-§4 expectations
- All 37 UI-SPEC §8 acceptance patterns covered (template source + output content + locale + icons + sitemap + LOC budget)
- Skill(skill="writing-tests") literal in PLAN.md
- Read-only contract enforced (md5 check)
</verification>

<success_criteria>
- All 12 kb-2 REQs cross-cutting verified at integration level (TOPIC-01..05, ENTITY-01..04, LINK-01..03)
- ≥12 test cases pass (5 topic param + 6 entity param + structural + JSON-LD + sitemap + LOC + locale param + icon param + read-only)
</success_criteria>

<output>
After completion, create `.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-10-SUMMARY.md` documenting:
- Test count + pass result
- Read-only enforcement result
- All 12 REQs covered at integration level
- Literal Skill(skill="writing-tests") string
- kb-2 phase ready for declaration after this plan green
</output>

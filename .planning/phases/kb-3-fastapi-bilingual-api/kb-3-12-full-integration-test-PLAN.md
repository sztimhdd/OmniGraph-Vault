---
phase: kb-3-fastapi-bilingual-api
plan: 12
subsystem: full-integration
tags: [integration-test, e2e, fixture, real-db, regression]
type: execute
wave: 5
depends_on: ["kb-3-04", "kb-3-05", "kb-3-06", "kb-3-07", "kb-3-08", "kb-3-09", "kb-3-10", "kb-3-11"]
files_modified:
  - tests/integration/kb/test_kb3_full_integration.py
autonomous: true
requirements:
  - DATA-07
  - I18N-07
  - API-01
  - API-02
  - API-03
  - API-04
  - API-05
  - API-06
  - API-07
  - API-08
  - SEARCH-01
  - SEARCH-02
  - SEARCH-03
  - QA-01
  - QA-02
  - QA-03
  - QA-04
  - QA-05
  - CONFIG-02

must_haves:
  truths:
    - "End-to-end flow: rebuild_fts → /api/articles → /api/article/{hash} → /api/search → /api/synthesize → poll → done all pass on a single fixture-driven run"
    - "All UI-SPEC §8 grep patterns satisfied (30+ patterns) — pulled from kb-3-10 + kb-3-11 outputs"
    - "All CONTENT-QUALITY-DECISIONS.md acceptance grep patterns satisfied (~7 patterns) — DATA-07 SQL clause counts, env override, carve-out preserved"
    - "Skill discipline regex passes: ui-ux-pro-max ≥ 2 SUMMARYs, frontend-design ≥ 2, api-design ≥ 1, python-patterns ≥ 3, writing-tests ≥ 2"
    - "REQ coverage check: every one of 19 REQ IDs appears in at least one plan's `requirements:` frontmatter"
    - "Real-DB smoke: same flow exercised against .dev-runtime/data/kol_scan.db (production-shape mirror) — items count > 0, no 500s"
  artifacts:
    - path: "tests/integration/kb/test_kb3_full_integration.py"
      provides: "single-file end-to-end test that drives the full kb-3 pipeline"
      min_lines: 250
  key_links:
    - from: "tests/integration/kb/test_kb3_full_integration.py"
      to: ".dev-runtime/data/kol_scan.db (production-shape mirror)"
      via: "monkeypatch KB_DB_PATH for the real-db smoke section"
      pattern: "kol_scan\\.db|.dev-runtime"
    - from: "tests/integration/kb/test_kb3_full_integration.py"
      to: "all kb-3 endpoints + scripts + UI-SPEC §8 grep regex"
      via: "TestClient + subprocess + grep"
      pattern: "/api/articles|/api/article/|/api/search|/api/synthesize|articles_fts"
---

<objective>
Single end-to-end integration test file that exercises the full kb-3 pipeline AND runs the cross-cutting grep regression suites (UI-SPEC §8 + CONTENT-QUALITY-DECISIONS.md acceptance + Skill discipline regex). Mostly orchestration on top of the per-plan tests (kb-3-04..11 each have their own coverage); this plan's value is a single command that proves the whole system works together.

Purpose: Prevent the "all individual plans pass but the pipeline doesn't connect" anti-pattern. By running the entire flow (FTS rebuild → list → detail → search → synthesize → poll → done) in one test against both fixture AND real-DB, we catch integration gaps that per-plan tests miss. Also runs the discipline regex (Skill invocations counted across SUMMARYs) so the kb-3 phase isn't declared complete with discipline silently broken.

Output: One pytest file ≥250 lines exercising end-to-end + regex regression + discipline check.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-04-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-05-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-06-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-07-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-08-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-09-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-10-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-11-SUMMARY.md
@kb/api.py
@kb/scripts/rebuild_fts.py
@kb/services/synthesize.py
@kb/services/search_index.py
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
End-to-end flow under test:

```
1. rebuild_fts.main(["--db", fixture_db, "--quiet"])  → returns 0
2. GET /api/articles → 200, items > 0
3. GET /api/article/{first_hash} → 200, body_md non-empty
4. GET /api/search?q=agent&mode=fts → 200, items >= 0
5. POST /api/synthesize {question, lang} → 202 + job_id
6. Poll GET /api/synthesize/{job_id} until status='done' → result populated
7. UI-SPEC §8 grep regression: 30+ patterns satisfied across {ask.html, _qa_result.html, qa.js, search.js, style.css, locale}
8. DATA-07 acceptance: SQL fragment count ≥ 6 in article_query.py, env override present, carve-out preserved on get_article_by_hash
9. Skill discipline regex: count ui-ux-pro-max / frontend-design / api-design / python-patterns / writing-tests references in *-SUMMARY.md
10. REQ coverage: every kb-3 REQ ID present in at least one plan frontmatter
```

Skill discipline regex (run mentally per plan-phase prompt):

```bash
for skill in ui-ux-pro-max frontend-design api-design python-patterns writing-tests; do
  count=$(grep -lE "Skill\(skill=\"$skill\"" .planning/phases/kb-3-fastapi-bilingual-api/*-SUMMARY.md | wc -l)
  echo "$skill: $count"
done
```

Expected counts:
- ui-ux-pro-max: ≥ 2 (kb-3-10 + kb-3-11)
- frontend-design: ≥ 2 (kb-3-10 + kb-3-11)
- api-design: ≥ 1 (kb-3-01)
- python-patterns: ≥ 3 (kb-3-02 + kb-3-04 + kb-3-05 + kb-3-06 + kb-3-07 + kb-3-08 + kb-3-09 = 7 plans expected)
- writing-tests: ≥ 2 (multiple — kb-3-02, 04, 05, 06, 07, 08, 09 = 7)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Invoke writing-tests Skill + author tests/integration/kb/test_kb3_full_integration.py covering 10 end-to-end + regression scenarios</name>
  <read_first>
    - All kb-3 *-SUMMARY.md files (kb-3-01 through kb-3-11) — references for what each plan delivered
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md §8 (30+ grep patterns)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-CONTENT-QUALITY-DECISIONS.md "Acceptance criteria" section (7 patterns)
    - kb/docs/10-DESIGN-DISCIPLINE.md (Skill discipline regex section)
    - .planning/REQUIREMENTS-KB-v2.md kb-3 REQ list (19 IDs)
  </read_first>
  <files>tests/integration/kb/test_kb3_full_integration.py</files>
  <action>
    Skill(skill="writing-tests", args="Author a single-file end-to-end + regression test that exercises the full kb-3 pipeline (rebuild_fts → list → detail → search → synthesize → poll) against the fixture_db; runs UI-SPEC §8 grep regression (30+ patterns); runs CONTENT-QUALITY-DECISIONS.md acceptance grep regression (7 patterns); runs Skill discipline regex (≥ counts per skill type); runs REQ coverage check (every kb-3 REQ ID found in at least one plan frontmatter). Use TestClient(app) with reloaded modules + monkeypatched KB_DB_PATH. For the synthesize call, monkeypatch kg_synthesize.synthesize_response with an instantaneous-success fake. The discipline + REQ checks read from .planning/phases/kb-3-fastapi-bilingual-api/*-SUMMARY.md and *-PLAN.md files via Path + glob. Cover: SKill counts, REQ coverage, all UI grep patterns, all DATA-07 grep patterns, end-to-end happy path, end-to-end fallback path (C1 patched to fail), latency budgets, never-500 invariant.")

    **Create `tests/integration/kb/test_kb3_full_integration.py`** (≥250 LOC):

    ```python
    """kb-3 phase: full end-to-end integration + regression test.

    Single file that proves the whole system works together. Per-plan tests verify
    individual components; this verifies the SEAMS between them.

    Scope:
        1. End-to-end happy path (rebuild → list → detail → search → synthesize → done)
        2. End-to-end fallback path (synthesize C1 fails → fts5_fallback → done)
        3. UI-SPEC §8 grep regression (30+ patterns)
        4. CONTENT-QUALITY-DECISIONS.md acceptance grep regression (DATA-07)
        5. Skill discipline regex (≥ counts per skill type)
        6. REQ coverage (every kb-3 REQ in at least one plan frontmatter)
    """
    from __future__ import annotations

    import importlib
    import re
    import sqlite3
    import time
    from pathlib import Path
    from typing import Any

    import pytest
    from fastapi.testclient import TestClient

    pytest_plugins = ["tests.integration.kb.conftest"]

    REPO = Path(__file__).resolve().parents[3]
    PHASE_DIR = REPO / ".planning" / "phases" / "kb-3-fastapi-bilingual-api"
    REQS_FILE = REPO / ".planning" / "REQUIREMENTS-KB-v2.md"

    KB3_REQS = [
        "DATA-07", "I18N-07",
        "API-01", "API-02", "API-03", "API-04", "API-05", "API-06", "API-07", "API-08",
        "SEARCH-01", "SEARCH-02", "SEARCH-03",
        "QA-01", "QA-02", "QA-03", "QA-04", "QA-05",
        "CONFIG-02",
    ]


    # ---- End-to-end fixture ----

    @pytest.fixture
    def fully_wired_app(fixture_db, tmp_path, monkeypatch):
        """Reload all kb modules with KB_DB_PATH=fixture_db; populate FTS; return TestClient."""
        monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
        monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
        monkeypatch.delenv("KB_SEARCH_BYPASS_QUALITY", raising=False)
        # Redirect OmniGraph BASE_DIR for synthesize output capture
        import config as og_config
        monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)

        # Reload kb modules
        import kb.config, kb.data.article_query
        import kb.services.search_index, kb.services.job_store, kb.services.synthesize
        import kb.api_routers.articles, kb.api_routers.search, kb.api_routers.synthesize
        import kb.api
        for m in [kb.config, kb.data.article_query,
                  kb.services.search_index, kb.services.job_store, kb.services.synthesize,
                  kb.api_routers.articles, kb.api_routers.search, kb.api_routers.synthesize,
                  kb.api]:
            importlib.reload(m)

        # Populate FTS index by invoking the rebuild script
        from kb.scripts.rebuild_fts import main as rebuild_main
        rc = rebuild_main(["--db", str(fixture_db), "--quiet"])
        assert rc == 0

        return TestClient(kb.api.app)


    # ---- Section 1: End-to-end happy path ----

    def test_e2e_health(fully_wired_app):
        r = fully_wired_app.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"


    def test_e2e_articles_list(fully_wired_app):
        r = fully_wired_app.get("/api/articles?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1, "fixture should yield ≥1 DATA-07-passing article"
        assert "items" in body


    def test_e2e_article_detail_resolves(fully_wired_app):
        list_r = fully_wired_app.get("/api/articles?limit=1").json()
        if not list_r["items"]:
            pytest.skip("no items in fixture")
        h = list_r["items"][0]["hash"]
        det = fully_wired_app.get(f"/api/article/{h}")
        assert det.status_code == 200
        body = det.json()
        assert body["hash"] == h
        for key in ("title", "body_md", "body_html", "source", "lang", "body_source"):
            assert key in body


    def test_e2e_search_fts(fully_wired_app):
        r = fully_wired_app.get("/api/search?q=agent&mode=fts")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "fts"
        assert "items" in body


    def test_e2e_synthesize_happy_path(fully_wired_app, monkeypatch, tmp_path):
        """Patch C1 to write synthesis_output.md instantaneously."""
        async def fake_c1(query_text, mode="hybrid"):
            import config as og_config
            (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(
                "# OK\n\n[s](/article/abcd012345)", encoding="utf-8"
            )
        monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)
        post = fully_wired_app.post("/api/synthesize", json={"question": "What is Agent?", "lang": "en"})
        assert post.status_code == 202
        jid = post.json()["job_id"]
        for _ in range(20):
            time.sleep(0.1)
            j = fully_wired_app.get(f"/api/synthesize/{jid}").json()
            if j["status"] == "done":
                assert j["confidence"] == "kg"
                assert j["fallback_used"] is False
                assert j["result"] is not None
                return
        pytest.fail(f"synthesize never completed; last={j}")


    # ---- Section 2: End-to-end fallback path ----

    def test_e2e_synthesize_fallback_path_never_500(fully_wired_app, monkeypatch):
        async def fail_c1(*a, **kw):
            raise RuntimeError("LightRAG storage missing")
        monkeypatch.setattr("kg_synthesize.synthesize_response", fail_c1)
        post = fully_wired_app.post("/api/synthesize", json={"question": "anything", "lang": "zh"})
        assert post.status_code == 202
        jid = post.json()["job_id"]
        for _ in range(20):
            time.sleep(0.1)
            poll = fully_wired_app.get(f"/api/synthesize/{jid}")
            assert poll.status_code != 500, "QA-05: NEVER 500 invariant"
            j = poll.json()
            if j["status"] == "done":
                assert j["confidence"] in ("fts5_fallback", "no_results")
                assert j["fallback_used"] is True
                return
        pytest.fail(f"fallback path did not complete; last={j}")


    # ---- Section 3: UI-SPEC §8 grep regression ----

    UI_SPEC_GREPS_TEMPLATES = [
        # ask.html structural
        ("kb/templates/ask.html", "qa-result"),
        ("kb/templates/ask.html", "data-qa-state"),
        # _qa_result.html partial
        ("kb/templates/_qa_result.html", "qa-state-indicator"),
        ("kb/templates/_qa_result.html", "qa-fallback-banner"),
        ("kb/templates/_qa_result.html", "qa-error-banner"),
        ("kb/templates/_qa_result.html", "qa-sources"),
        ("kb/templates/_qa_result.html", "qa-entities"),
        ("kb/templates/_qa_result.html", "qa-feedback"),
        ("kb/templates/_qa_result.html", "qa-confidence-chip--fallback"),
    ]

    UI_SPEC_GREPS_JS = [
        ("kb/static/qa.js", "fts5_fallback"),
        ("kb/static/qa.js", "kb_qa_feedback_"),
    ]

    UI_SPEC_GREPS_CSS = [
        ("kb/static/style.css", r"\.qa-result\[data-qa-state="),
        ("kb/static/style.css", r"\.qa-state-indicator"),
        ("kb/static/style.css", r"\.qa-confidence-chip--fallback"),
        ("kb/static/style.css", r"\.qa-source-chip"),
    ]

    UI_SPEC_GREPS_LOCALE = [
        ("kb/locale/zh-CN.json", "qa.state.submitting"),
        ("kb/locale/en.json", "qa.state.submitting"),
        ("kb/locale/zh-CN.json", "qa.fallback.label"),
        ("kb/locale/en.json", "search.results.empty"),
    ]

    UI_SPEC_GREPS_ICONS = [
        ("kb/templates/_icons.html", "chat-bubble-question"),
        ("kb/templates/_icons.html", "lightning-bolt"),
    ]


    @pytest.mark.parametrize("path,pattern", UI_SPEC_GREPS_TEMPLATES + UI_SPEC_GREPS_JS + UI_SPEC_GREPS_LOCALE + UI_SPEC_GREPS_ICONS)
    def test_ui_spec_8_string_pattern(path, pattern):
        text = (REPO / path).read_text(encoding="utf-8")
        assert pattern in text, f"UI-SPEC §8 grep failed: {pattern!r} not in {path}"


    @pytest.mark.parametrize("path,pattern", UI_SPEC_GREPS_CSS)
    def test_ui_spec_8_regex_pattern(path, pattern):
        text = (REPO / path).read_text(encoding="utf-8")
        assert re.search(pattern, text), f"UI-SPEC §8 regex failed: {pattern!r} in {path}"


    def test_ui_spec_token_discipline_31_vars():
        css = (REPO / "kb" / "static" / "style.css").read_text(encoding="utf-8")
        var_count = len(re.findall(r"^\s*--[a-z-]+:", css, re.MULTILINE))
        assert var_count == 31


    def test_ui_spec_css_budget_2100():
        css = (REPO / "kb" / "static" / "style.css").read_text(encoding="utf-8")
        line_count = css.count("\n") + 1
        assert line_count <= 2100


    # ---- Section 4: DATA-07 acceptance regression ----

    def test_data07_sql_fragment_count():
        text = (REPO / "kb" / "data" / "article_query.py").read_text(encoding="utf-8")
        # Per CONTENT-QUALITY-DECISIONS.md acceptance: ≥ 3 occurrences of "layer1_verdict = 'candidate'"
        # Plan kb-3-02 uses _DATA07_*_FRAGMENT helpers; the literal string appears in the
        # fragments (3 forms: KOL-aliased, RSS-aliased, bare) plus inline calls. ≥3 is the floor.
        count = len(re.findall(r"layer1_verdict\s*=\s*'candidate'", text))
        assert count >= 3, f"Expected ≥3 occurrences of layer1_verdict='candidate'; got {count}"


    def test_data07_env_override_present():
        text = (REPO / "kb" / "data" / "article_query.py").read_text(encoding="utf-8")
        assert "KB_CONTENT_QUALITY_FILTER" in text


    def test_data07_carve_out_preserved():
        """get_article_by_hash function body must NOT reference the DATA-07 fragment."""
        text = (REPO / "kb" / "data" / "article_query.py").read_text(encoding="utf-8")
        # Find the function body (between def get_article_by_hash and the next def)
        m = re.search(r"def get_article_by_hash[\s\S]*?(?=\ndef |\Z)", text)
        assert m, "get_article_by_hash function not found"
        body = m.group(0)
        assert "_DATA07" not in body, "carve-out violated: get_article_by_hash references DATA-07 fragment"


    def test_data07_schema_guard_present():
        text = (REPO / "kb" / "data" / "article_query.py").read_text(encoding="utf-8")
        assert "PRAGMA table_info" in text
        assert "_verify_quality_columns" in text


    # ---- Section 5: Skill discipline regex ----

    SKILL_FLOOR = {
        "ui-ux-pro-max": 2,
        "frontend-design": 2,
        "api-design": 1,
        "python-patterns": 3,
        "writing-tests": 2,
    }


    @pytest.mark.parametrize("skill,floor", list(SKILL_FLOOR.items()))
    def test_skill_invocation_floor(skill, floor):
        """Per kb/docs/10-DESIGN-DISCIPLINE.md verification regex."""
        summaries = list(PHASE_DIR.glob("*-SUMMARY.md"))
        plans = list(PHASE_DIR.glob("*-PLAN.md"))
        files = summaries + plans  # Skill invocation may be in either, per discipline
        matches = 0
        for f in files:
            text = f.read_text(encoding="utf-8")
            if f'Skill(skill="{skill}"' in text:
                matches += 1
        assert matches >= floor, (
            f"Skill discipline regex: {skill} found in {matches} file(s); floor={floor}. "
            f"See kb/docs/10-DESIGN-DISCIPLINE.md for required invocations."
        )


    # ---- Section 6: REQ coverage ----

    @pytest.mark.parametrize("req", KB3_REQS)
    def test_req_in_at_least_one_plan_frontmatter(req):
        """Every kb-3 REQ ID must appear in `requirements:` of at least one PLAN.md."""
        plans = list(PHASE_DIR.glob("kb-3-*-PLAN.md"))
        found = False
        for p in plans:
            text = p.read_text(encoding="utf-8")
            # Match either bullet-list item "  - REQ-ID" or array notation
            if re.search(rf"^\s*-\s*{re.escape(req)}\s*$", text, re.MULTILINE):
                found = True
                break
        assert found, f"REQ {req} not listed in any kb-3 PLAN.md frontmatter"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_kb3_full_integration.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/integration/kb/test_kb3_full_integration.py` exists with ≥250 lines
    - `pytest tests/integration/kb/test_kb3_full_integration.py -v` exits 0 with ≥40 tests passing (sum across 6 sections)
    - Sections covered:
      - Section 1 (e2e happy path): ≥5 tests (health + articles list + article detail + search + synthesize happy)
      - Section 2 (e2e fallback): ≥1 test
      - Section 3 (UI-SPEC §8 grep): ≥17 tests (parametrized)
      - Section 4 (DATA-07 acceptance): ≥4 tests
      - Section 5 (Skill discipline): 5 tests (one per skill)
      - Section 6 (REQ coverage): 19 tests (one per REQ ID)
    - Phase-wide regression: `pytest tests/integration/kb/ tests/unit/kb/ -v` exits 0 (full kb-1 + kb-2 + kb-3 suite)
    - `grep -q "Skill(skill=\"writing-tests\"" tests/integration/kb/test_kb3_full_integration.py`
  </acceptance_criteria>
  <done>≥40 integration tests covering full kb-3 pipeline + UI-SPEC §8 + DATA-07 acceptance + Skill discipline + REQ coverage all pass.</done>
</task>

</tasks>

<verification>
- End-to-end happy path verified
- End-to-end fallback path verified (NEVER 500)
- All 30+ UI-SPEC §8 grep patterns satisfied
- All DATA-07 acceptance grep patterns satisfied
- Skill discipline regex passes (≥ counts per skill)
- REQ coverage 100% (all 19 IDs in at least one plan)
- writing-tests Skill literal in test file AND will appear in SUMMARY
</verification>

<success_criteria>
- All 19 kb-3 REQs verified at integration level
- Phase NOT-DONE → DONE gate per kb/docs/10-DESIGN-DISCIPLINE.md verification regex passes
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-12-SUMMARY.md` documenting:
- Single end-to-end test file with ≥40 tests
- All 6 sections covered (e2e happy + e2e fallback + UI-SPEC §8 + DATA-07 + Skill discipline + REQ coverage)
- Skill invocation string `Skill(skill="writing-tests", ...)` literal for discipline regex
- Phase verification: regex check passes, REQ coverage 100%, no integration gaps
</output>
</content>
</invoke>
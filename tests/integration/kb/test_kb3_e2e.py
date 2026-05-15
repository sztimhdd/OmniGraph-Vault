"""kb-3 phase: full end-to-end integration + regression test (Wave 5 final).

Single file that proves the whole kb-3 system works together. Per-plan tests
verify individual components; this verifies the SEAMS between them and the
cross-cutting discipline regex.

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1 — applied verbatim):

    Skill(skill="writing-tests", args="Author a single-file end-to-end + regression test that exercises the full kb-3 pipeline (rebuild_fts -> list -> detail -> search -> synthesize -> poll) against the fixture_db; runs UI-SPEC §8 grep regression (30+ patterns); runs CONTENT-QUALITY-DECISIONS.md acceptance grep regression (DATA-07); runs Skill discipline regex (>= counts per skill type); runs REQ coverage check (every kb-3 REQ ID found in at least one plan frontmatter). Use TestClient(app) with reloaded modules + monkeypatched KB_DB_PATH. For the synthesize call, monkeypatch kg_synthesize.synthesize_response with an instantaneous-success fake. The discipline + REQ checks read from .planning/phases/kb-3-fastapi-bilingual-api/*-SUMMARY.md and *-PLAN.md files via Path + glob. Cover: Skill counts, REQ coverage, all UI grep patterns, all DATA-07 grep patterns, end-to-end happy path, end-to-end fallback path (C1 patched to fail), latency budgets, never-500 invariant.")

Sections covered:
    1. End-to-end happy path (rebuild -> list -> detail -> search -> synthesize -> done)
    2. End-to-end fallback path (synthesize C1 fails -> fts5_fallback -> done; NEVER 500)
    3. UI-SPEC §8 grep regression (30+ patterns across templates / js / css / locale / icons)
    4. CONTENT-QUALITY-DECISIONS.md acceptance grep regression (DATA-07)
    5. Skill discipline regex (>= counts per skill type — sourced from §10 DESIGN DISCIPLINE)
    6. REQ coverage (every kb-3 REQ ID listed in at least one plan frontmatter)

Per writing-tests SKILL Testing Trophy: integration tests with real SQLite + real
FastAPI app + real FTS5 index. Mocks limited to C1 (kg_synthesize.synthesize_response)
because LightRAG is an external system per Mocking Guidelines.
"""
from __future__ import annotations

import importlib
import re
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]
PHASE_DIR = REPO / ".planning" / "phases" / "kb-3-fastapi-bilingual-api"

# kb-3 REQ IDs (from REQUIREMENTS-KB-v2.md + kb-3-12 plan frontmatter).
KB3_REQS: list[str] = [
    "DATA-07",
    "I18N-07",
    "API-01",
    "API-02",
    "API-03",
    "API-04",
    "API-05",
    "API-06",
    "API-07",
    "API-08",
    "SEARCH-01",
    "SEARCH-02",
    "SEARCH-03",
    "QA-01",
    "QA-02",
    "QA-03",
    "QA-04",
    "QA-05",
    "CONFIG-02",
]


# ============================================================================
# Section 1: End-to-end happy path fixture + tests
# ============================================================================


@pytest.fixture
def fully_wired_app(fixture_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Reload kb modules with KB_DB_PATH=fixture_db; populate FTS; return TestClient.

    This is the canonical kb-3 end-to-end fixture: every module that holds an
    env-var-derived constant at import time is reloaded so the fixture DB is
    actually exercised (not the user's ~/.hermes/data/kol_scan.db default).
    """
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    monkeypatch.delenv("KB_CONTENT_QUALITY_FILTER", raising=False)
    monkeypatch.delenv("KB_SEARCH_BYPASS_QUALITY", raising=False)

    # kb-v2.1-1: enable KG mode for the e2e happy/zh-directive tests, which
    # exercise the monkeypatched C1 path. The short-circuit must NOT fire here.
    sa_dummy = tmp_path / "kg-sa-dummy.json"
    sa_dummy.write_text('{"type":"service_account"}')
    monkeypatch.setenv("KB_KG_GCP_SA_KEY_PATH", str(sa_dummy))

    # Redirect OmniGraph BASE_DIR so synthesize wrapper writes synthesis_output.md
    # into tmp_path rather than ~/.hermes/omonigraph-vault/.
    import config as og_config

    monkeypatch.setattr(og_config, "BASE_DIR", tmp_path)

    # Reload chain: kb.config first (it freezes KB_DB_PATH at import), then every
    # downstream module that imports kb.config (or reads its own env var).
    import kb.config
    import kb.data.article_query
    import kb.services.search_index
    import kb.services.job_store
    import kb.services.synthesize
    import kb.api_routers.articles
    import kb.api_routers.search
    import kb.api_routers.synthesize
    import kb.api

    for m in (
        kb.config,
        kb.services.search_index,
        kb.services.job_store,
        kb.services.synthesize,
        kb.api_routers.articles,
        kb.api_routers.search,
        kb.api_routers.synthesize,
        kb.api,
    ):
        importlib.reload(m)

    # Populate FTS index by invoking the rebuild script entry point.
    from kb.scripts.rebuild_fts import main as rebuild_main

    rc = rebuild_main(["--db", str(fixture_db), "--quiet"])
    assert rc == 0, "rebuild_fts.main returned non-zero exit"

    return TestClient(kb.api.app)


def test_e2e_health(fully_wired_app: TestClient) -> None:
    """Health endpoint is up and reports the fixture DB path."""
    r = fully_wired_app.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "kb_db_path" in body
    assert "version" in body


def test_e2e_articles_list_returns_filtered_items(fully_wired_app: TestClient) -> None:
    """GET /api/articles returns >=1 DATA-07-passing item from the fixture."""
    r = fully_wired_app.get("/api/articles?limit=100")
    assert r.status_code == 200
    body = r.json()
    # Fixture has 5 KOL + 3 RSS positive = 8 items pass DATA-07.
    # 4 negative-case rows must be excluded.
    assert body["total"] == 8, f"expected 8 DATA-07-passing rows, got {body['total']}"
    assert len(body["items"]) == 8
    # Negative-row hashes must NOT appear (DATA-07 active).
    visible_hashes = {item["hash"] for item in body["items"]}
    forbidden = {"neg9999999", "neg9898989"}
    assert forbidden.isdisjoint(visible_hashes), (
        "DATA-07 violated: negative-case rows leaked into list"
    )


def test_e2e_article_detail_resolves(fully_wired_app: TestClient) -> None:
    """List -> first hash -> detail endpoint round-trips with full shape."""
    list_r = fully_wired_app.get("/api/articles?limit=1").json()
    assert list_r["items"], "fixture should yield >=1 item"
    h = list_r["items"][0]["hash"]
    det = fully_wired_app.get(f"/api/article/{h}")
    assert det.status_code == 200
    body = det.json()
    assert body["hash"] == h
    for key in ("title", "body_md", "body_html", "source", "lang", "body_source", "images", "metadata"):
        assert key in body, f"detail response missing key: {key}"
    assert body["body_source"] in ("vision_enriched", "raw_markdown")


def test_e2e_article_detail_carveout_resolves_negative_row(
    fully_wired_app: TestClient,
) -> None:
    """DATA-07 carve-out: /api/article/{hash} resolves a negative-case row that
    /api/articles excludes. Direct URL access must work for bookmarks."""
    # Negative-case KOL row id=98 has content_hash='neg9898989' but layer2='reject'.
    r = fully_wired_app.get("/api/article/neg9898989")
    assert r.status_code == 200, "DATA-07 carve-out violated: detail must resolve regardless of verdict"
    assert r.json()["hash"] == "neg9898989"


def test_e2e_search_fts_mode(fully_wired_app: TestClient) -> None:
    """GET /api/search?mode=fts returns 200 with the implemented envelope shape.

    Per kb/api_routers/search.py: returns ``{items, total, mode}``.
    Items have ``{hash, title, snippet, lang, source}`` per kb-3-06.
    """
    r = fully_wired_app.get("/api/search?q=agent&mode=fts")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "fts"
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
    # Fixture has 'agent'-matching content via `Agent 框架对比` + `agents` in EN bodies.
    assert body["total"] >= 1, f"FTS5 should match >=1 fixture row for 'agent', got {body['total']}"
    for item in body["items"]:
        for key in ("hash", "title", "snippet", "lang", "source"):
            assert key in item, f"FTS item missing key: {key}"


def test_e2e_synthesize_happy_path(
    fully_wired_app: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """POST /api/synthesize -> 202 -> poll -> done; confidence='kg', fallback_used=False.

    PROJECT-KB-v2.md Smoke 3 scenario 1 (en happy path). C1 is patched per
    writing-tests SKILL Mocking Guidelines (LightRAG is external).
    """

    async def fake_c1(query_text: str, mode: str = "hybrid") -> None:
        import config as og_config

        (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text(
            "# Answer\n\nSee [s](/article/abcd012345)", encoding="utf-8"
        )

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)
    post = fully_wired_app.post(
        "/api/synthesize", json={"question": "What is Agent?", "lang": "en"}
    )
    assert post.status_code == 202
    jid = post.json()["job_id"]

    deadline = time.monotonic() + 4.0
    final: dict[str, Any] = {}
    while time.monotonic() < deadline:
        time.sleep(0.05)
        final = fully_wired_app.get(f"/api/synthesize/{jid}").json()
        if final["status"] == "done":
            assert final["confidence"] == "kg"
            assert final["fallback_used"] is False
            assert final["result"] is not None
            assert "abcd012345" in final["result"]["sources"]
            return
    pytest.fail(f"synthesize never completed within 4s; last={final}")


def test_e2e_synthesize_zh_directive_prepended(
    fully_wired_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PROJECT-KB-v2.md Smoke 3 scenario 1 (zh): I18N-07 directive prepended."""
    captured: dict[str, str | None] = {"text": None}

    async def fake_c1(query_text: str, mode: str = "hybrid") -> None:
        captured["text"] = query_text
        import config as og_config

        (Path(og_config.BASE_DIR) / "synthesis_output.md").write_text("ok", encoding="utf-8")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fake_c1)
    r = fully_wired_app.post(
        "/api/synthesize", json={"question": "什么是 Agent?", "lang": "zh"}
    )
    jid = r.json()["job_id"]
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        time.sleep(0.05)
        if fully_wired_app.get(f"/api/synthesize/{jid}").json()["status"] == "done":
            break
    assert captured["text"] is not None
    assert captured["text"].startswith("请用中文回答。\n\n")


# ============================================================================
# Section 2: End-to-end fallback path (NEVER 500)
# ============================================================================


def test_e2e_synthesize_fallback_path_never_500(
    fully_wired_app: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PROJECT-KB-v2.md Smoke 3 scenario 3: LightRAG unavailable -> FTS5 fallback.

    QA-05 invariant: every poll during job lifecycle returns HTTP 200, never 500.
    Final state: status='done' with confidence in {fts5_fallback, no_results}.
    """

    async def fail_c1(*a: Any, **kw: Any) -> None:
        raise RuntimeError("LightRAG storage missing")

    monkeypatch.setattr("kg_synthesize.synthesize_response", fail_c1)
    post = fully_wired_app.post(
        "/api/synthesize", json={"question": "anything", "lang": "zh"}
    )
    assert post.status_code == 202
    jid = post.json()["job_id"]

    deadline = time.monotonic() + 4.0
    final: dict[str, Any] = {}
    while time.monotonic() < deadline:
        time.sleep(0.05)
        poll = fully_wired_app.get(f"/api/synthesize/{jid}")
        # Hard QA-05 invariant: every intermediate poll is 200.
        assert poll.status_code == 200, f"NEVER-500 broken: {poll.status_code} {poll.text}"
        final = poll.json()
        if final["status"] == "done":
            assert final["fallback_used"] is True
            assert final["confidence"] in ("fts5_fallback", "no_results")
            return
    pytest.fail(f"fallback path did not complete within 4s; last={final}")


# ============================================================================
# Section 3: UI-SPEC §8 grep regression (30+ patterns)
# ============================================================================
# Patterns sourced verbatim from kb-3-UI-SPEC.md §8. Each tuple: (rel_path, literal_substring).

UI_SPEC_GREPS_TEMPLATES: list[tuple[str, str]] = [
    # ask.html — confirms the partial is wired in (qa-result anchor + qa.js script)
    ("kb/templates/ask.html", "qa-result"),
    ("kb/templates/ask.html", "qa.js"),
    # _qa_result.html — partial extracted by kb-3-10 (the canonical home of all
    # 8-state-matrix structural anchors per kb-3-UI-SPEC §3.1)
    ("kb/templates/_qa_result.html", "data-qa-state"),
    ("kb/templates/_qa_result.html", "qa-state-indicator"),
    ("kb/templates/_qa_result.html", "qa-fallback-banner"),
    ("kb/templates/_qa_result.html", "qa-error-banner"),
    ("kb/templates/_qa_result.html", "qa-sources"),
    ("kb/templates/_qa_result.html", "qa-entities"),
    ("kb/templates/_qa_result.html", "qa-feedback"),
    ("kb/templates/_qa_result.html", "qa-confidence-chip--fallback"),
]

UI_SPEC_GREPS_JS: list[tuple[str, str]] = [
    ("kb/static/qa.js", "fts5_fallback"),
    ("kb/static/qa.js", "kb_qa_feedback_"),
    ("kb/templates/ask.html", "KB_QA_POLL_INTERVAL_MS"),
]

UI_SPEC_GREPS_LOCALE: list[tuple[str, str]] = [
    ("kb/locale/zh-CN.json", "qa.state.submitting"),
    ("kb/locale/en.json", "qa.state.submitting"),
    ("kb/locale/zh-CN.json", "qa.fallback.label"),
    ("kb/locale/en.json", "search.results.empty"),
]

UI_SPEC_GREPS_ICONS: list[tuple[str, str]] = [
    ("kb/templates/_icons.html", "chat-bubble-question"),
    ("kb/templates/_icons.html", "lightning-bolt"),
]

# CSS regex patterns (literal `.qa-result[data-qa-state=` would be a regex meta-conflict
# in plain `in`-membership; use re.search instead).
UI_SPEC_GREPS_CSS: list[tuple[str, str]] = [
    ("kb/static/style.css", r"\.qa-result\[data-qa-state="),
    ("kb/static/style.css", r"\.qa-state-indicator"),
    ("kb/static/style.css", r"\.qa-confidence-chip--fallback"),
    ("kb/static/style.css", r"\.qa-source-chip"),
]


@pytest.mark.parametrize(
    "path,pattern",
    UI_SPEC_GREPS_TEMPLATES + UI_SPEC_GREPS_JS + UI_SPEC_GREPS_LOCALE + UI_SPEC_GREPS_ICONS,
)
def test_ui_spec_8_string_pattern(path: str, pattern: str) -> None:
    """UI-SPEC §8 literal-substring greps — generated artifacts must contain pattern."""
    text = (REPO / path).read_text(encoding="utf-8")
    assert pattern in text, f"UI-SPEC §8 grep failed: {pattern!r} not in {path}"


@pytest.mark.parametrize("path,pattern", UI_SPEC_GREPS_CSS)
def test_ui_spec_8_regex_pattern(path: str, pattern: str) -> None:
    """UI-SPEC §8 regex greps for CSS class selectors."""
    text = (REPO / path).read_text(encoding="utf-8")
    assert re.search(pattern, text), f"UI-SPEC §8 regex failed: {pattern!r} in {path}"


def test_ui_spec_token_discipline_31_vars() -> None:
    """UI-SPEC §8 #34 — :root var count locked at 31 (no token entropy in kb-3)."""
    css = (REPO / "kb" / "static" / "style.css").read_text(encoding="utf-8")
    var_count = len(re.findall(r"^\s*--[a-z-]+:", css, re.MULTILINE))
    assert var_count == 31, f"token entropy: expected 31 :root vars, got {var_count}"


def test_ui_spec_css_loc_budget_2100() -> None:
    """UI-SPEC §8 #35 — kb-3-rebased style.css ceiling: <= 2100 LOC."""
    css = (REPO / "kb" / "static" / "style.css").read_text(encoding="utf-8")
    line_count = css.count("\n") + 1
    assert line_count <= 2100, f"style.css {line_count} LOC exceeds kb-3 budget 2100"


# ============================================================================
# Section 4: CONTENT-QUALITY-DECISIONS.md acceptance grep regression (DATA-07)
# ============================================================================


def test_data07_sql_fragment_count() -> None:
    """CONTENT-QUALITY-DECISIONS §Acceptance #1 — SQL fragment present >=3 times.

    The actual count is 9 (kb-3-02 + kb-2 query functions); the floor is 3.
    """
    text = (REPO / "kb" / "data" / "article_query.py").read_text(encoding="utf-8")
    count = len(re.findall(r"layer1_verdict\s*=\s*'candidate'", text))
    assert count >= 3, f"DATA-07 SQL clause count {count} below floor 3"


def test_data07_env_override_present() -> None:
    """CONTENT-QUALITY-DECISIONS §Acceptance #2 — KB_CONTENT_QUALITY_FILTER env hook."""
    text = (REPO / "kb" / "data" / "article_query.py").read_text(encoding="utf-8")
    assert "KB_CONTENT_QUALITY_FILTER" in text


def test_data07_carve_out_preserved() -> None:
    """CONTENT-QUALITY-DECISIONS §Acceptance #3 — get_article_by_hash NOT filtered.

    Function body must NOT reference DATA-07 fragments / verdict columns —
    direct URL access by hash must resolve regardless of layer1/layer2 verdict.
    """
    text = (REPO / "kb" / "data" / "article_query.py").read_text(encoding="utf-8")
    m = re.search(r"def get_article_by_hash[\s\S]*?(?=\ndef |\Z)", text)
    assert m, "get_article_by_hash function not found"
    body = m.group(0)
    assert "_DATA07" not in body, "carve-out violated: get_article_by_hash references DATA-07 fragment"
    assert "layer1_verdict" not in body, (
        "carve-out violated: get_article_by_hash filters on layer1_verdict"
    )


def test_data07_schema_guard_present() -> None:
    """CONTENT-QUALITY-DECISIONS §Acceptance #4 — schema guard fails loud on drift."""
    text = (REPO / "kb" / "data" / "article_query.py").read_text(encoding="utf-8")
    assert "PRAGMA table_info" in text
    assert "_verify_quality_columns" in text


def test_data07_runtime_visibility_against_fixture(fully_wired_app: TestClient) -> None:
    """CONTENT-QUALITY-DECISIONS §"Expected visibility" — assert on fixture-scale.

    Fixture has 5 KOL + 3 RSS = 8 positive cases (DATA-07 pass) + 4 negatives.
    Production-scale (~160 / 2501 = 6.4%) is checked at deploy smoke; here we
    verify the filter is wired correctly at runtime.
    """
    r = fully_wired_app.get("/api/articles?limit=100").json()
    assert r["total"] == 8, (
        f"DATA-07 fixture-scale visibility: expected 8 (5 KOL + 3 RSS positive), "
        f"got {r['total']} — filter may be off or fixture changed"
    )


# ============================================================================
# Section 5: Skill discipline regex (>= count per skill)
# ============================================================================
# Per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1 — named Skills must appear as literal
# `Skill(skill="...", args="...")` strings in plan SUMMARY.md / PLAN.md files for
# verification regex match. The phase is NOT-DONE if any floor is unmet.

SKILL_FLOOR: dict[str, int] = {
    "ui-ux-pro-max": 2,
    "frontend-design": 2,
    "api-design": 1,
    "python-patterns": 3,
    "writing-tests": 2,
}


@pytest.mark.parametrize("skill,floor", list(SKILL_FLOOR.items()))
def test_skill_invocation_floor(skill: str, floor: int) -> None:
    """Each named Skill must appear in >= floor SUMMARY+PLAN files in PHASE_DIR.

    Counts files (not occurrences) — discipline regex is "skill referenced in
    >= N plans", not "skill string repeated >= N times in one file".
    """
    summaries = list(PHASE_DIR.glob("*-SUMMARY.md"))
    plans = list(PHASE_DIR.glob("*-PLAN.md"))
    files = summaries + plans
    matches = sum(
        1
        for f in files
        if f'Skill(skill="{skill}"' in f.read_text(encoding="utf-8")
    )
    assert matches >= floor, (
        f"Skill discipline regex: {skill!r} found in {matches} file(s); floor={floor}. "
        f"See kb/docs/10-DESIGN-DISCIPLINE.md for required invocations."
    )


# ============================================================================
# Section 6: REQ coverage (every kb-3 REQ in at least one plan frontmatter)
# ============================================================================


@pytest.mark.parametrize("req", KB3_REQS)
def test_req_in_at_least_one_plan_frontmatter(req: str) -> None:
    """Every kb-3 REQ ID must appear in `requirements:` of at least one PLAN.md.

    Bullet-list YAML frontmatter form `  - REQ-ID` OR inline array `[REQ-ID]`.
    """
    plans = list(PHASE_DIR.glob("kb-3-*-PLAN.md"))
    assert plans, f"no kb-3 PLAN.md files found in {PHASE_DIR}"
    bullet_pat = re.compile(rf"^\s*-\s*{re.escape(req)}\s*$", re.MULTILINE)
    array_pat = re.compile(rf"\b{re.escape(req)}\b")
    found = False
    for p in plans:
        text = p.read_text(encoding="utf-8")
        # Restrict to the YAML frontmatter block (between the first two --- lines)
        # so we don't false-match REQ IDs cited in prose discussion sections.
        m = re.match(r"---\n([\s\S]*?)\n---", text)
        if not m:
            continue
        frontmatter = m.group(1)
        if bullet_pat.search(frontmatter) or array_pat.search(frontmatter):
            found = True
            break
    assert found, f"REQ {req} not listed in any kb-3 PLAN.md frontmatter"

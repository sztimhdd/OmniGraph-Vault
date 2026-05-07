---
phase: 20
slug: rss-full-body-classify-multimodal-ingest-rewrite-cognee-routing-fix
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-06
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: `20-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (no `pytest.ini`; runs as `python -m pytest`) |
| **Config file** | None — `tests/unit/` flat layout, mocks use `unittest.mock` + `pytest-asyncio` |
| **Quick run command** | `DEEPSEEK_API_KEY=dummy python -m pytest tests/unit/test_rss_classify_fullbody.py tests/unit/test_rss_ingest_5stage.py tests/unit/test_cognee_remember_detaches.py -x -v` |
| **Full suite command** | `DEEPSEEK_API_KEY=dummy python -m pytest tests/unit/ -v --tb=short` |
| **Estimated runtime** | ~30 seconds (quick) / ~90 seconds (full, with the 13 known pre-existing failures from Phase 19 deferred-items.md) |

---

## Sampling Rate

- **After every task commit:** Run quick run command (3 phase-20 test files only — fast feedback)
- **After every plan wave:** Run full suite (regression check; expect baseline 464 passed + ≤13 pre-existing fails per Phase 19 deferred-items.md, no new failures)
- **Before `/gsd:verify-work`:** Full suite green + COG-03 live Hermes 3-article smoke complete (operator action)
- **Max feedback latency:** ≤30 seconds per task commit

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 20-RCL-01 | 20-01 | 1 | RCL-01 | unit + mock | `python -m pytest tests/unit/test_rss_classify_fullbody.py::test_classify_reads_body -x` | ❌ W0 | ⬜ pending |
| 20-RCL-02 | 20-01 | 1 | RCL-02 | unit | `python -m pytest tests/unit/test_rss_classify_fullbody.py::test_single_call_multi_topic -x` | ❌ W0 | ⬜ pending |
| 20-RCL-03 | 20-01 | 1 | RCL-03 | unit | `python -m pytest tests/unit/test_rss_classify_fullbody.py::test_daily_cap_gates_article -x` | ❌ W0 | ⬜ pending |
| 20-RIN-01 | 20-02 | 2 | RIN-01 | unit + mock | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_5_stage_checkpoints -x` | ❌ W0 | ⬜ pending |
| 20-RIN-02 | 20-02 | 2 | RIN-02, RIN-03, RIN-04 (download_images Referer + SVG filter) | unit | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_download_images_referer_svg -x` | ❌ W0 | ⬜ pending |
| 20-RIN-03 | 20-02 | 2 | RIN-03 (per-module tracker) | unit | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_pending_doc_ids_isolated -x` | ❌ W0 | ⬜ pending |
| 20-RIN-04 | 20-02 | 2 | RIN-05 (timeout rollback) | unit + mock | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_timeout_rollback -x` | ❌ W0 | ⬜ pending |
| 20-RIN-05 | 20-02 | 2 | RIN-01..06 (sub-doc format) | unit | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_vision_subdoc_format -x` | ❌ W0 | ⬜ pending |
| 20-RIN-06 | 20-02 | 2 | RIN-02 (`_build_contents` regex) | unit | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_image_url_pattern_match -x` | ❌ W0 | ⬜ pending |
| 20-COG-02 | 20-03 | 1 | COG-02 | mock-only | `python -m pytest tests/unit/test_cognee_remember_detaches.py::test_remember_returns_fast -x` | ❌ W0 | ⬜ pending |
| 20-COG-03 | 20-03 | 3 | COG-03 | live-Hermes manual | N/A — operator SSH per `~/.claude/projects/.../memory/hermes_ssh.md` | N/A manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Wave assignment rationale:**
- **Wave 0 (prerequisite):** Plan 20-00 RED stubs — drive TDD for all downstream plans; no production code touched
- **Wave 1 (parallel):** Plan 20-01 (RCL — pure-classify changes) + Plan 20-03 Tasks 3.1+3.2 (COG-01 verify + COG-02 cognee_wrapper refactor — independent file)
- **Wave 2 (sequential after Wave 1):** Plan 20-02 (RIN — depends on RCL because rewritten `rss_ingest.py` calls upgraded classify)
- **Wave 3 (operator):** Plan 20-03 Task 3.3 (COG-03 retirement gate — live Hermes 3-article smoke + env-gate deletion)

Plan 20-03 frontmatter `wave: 3` reflects the LAST wave this plan participates in (Option A from revision iter 1 blocker #3 — single-plan COG semantics; Tasks 3.1+3.2 still scheduled in Wave 1 by `gsd:execute-phase` because their `depends_on` resolves there, while Task 3.3 is held until Plan 20-02 completes).

---

## Wave 0 Requirements

- [ ] `tests/unit/test_rss_classify_fullbody.py` — RED stubs for RCL-01, RCL-02, RCL-03 (mock `_build_fullbody_prompt`, `_call_fullbody_llm`; in-memory SQLite with `rss_articles` table from `enrichment/rss_schema.py`)
- [ ] `tests/unit/test_rss_ingest_5stage.py` — RED stubs for RIN-01 through RIN-06 (mock `rag.ainsert`, `rag.adelete_by_doc_id`, `download_images`, `describe_images`, tmp checkpoint dir)
- [ ] `tests/unit/test_cognee_remember_detaches.py` — RED stub for COG-02 (monkeypatch `cognee.remember = asyncio.sleep(10)`, assert `<100ms`)
- [ ] `tests/conftest.py` (existing) — verify the project-wide fixtures (env loading, sqlite tmp DB) are reusable; add new fixtures only if missing

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cognee episodic store grows on live Hermes after `OMNIGRAPH_COGNEE_INLINE=1` smoke | COG-03 | Live Cognee state only exists on Hermes runtime volume; SSH-only access; cannot mock | (1) SSH per `memory/hermes_ssh.md`; (2) `git pull --ff-only`; (3) `OMNIGRAPH_COGNEE_INLINE=1 venv/bin/python batch_ingest_from_spider.py --from-db --topic-filter agent --min-depth 2 --max-articles 3`; (4) Verify all 3 articles complete in <30 min total wall-clock; (5) Confirm Cognee status query shows new entries; (6) Confirm no 422 errors in stderr |
| RSS doc with `rss-{id}` doc_id reaches PROCESSED status | RIN-01..06 (success criterion #2) | Live LightRAG store only exists on Hermes | Operator runs `python enrichment/rss_ingest.py --max-articles 3` on Hermes; verifies via `aget_docs_by_ids` script that all 3 doc_ids return PROCESSED |
| Localhost image URLs render correctly in synthesis output | RIN-02 (success criterion #3) | Image server (port 8765) only running on Hermes | Operator runs `kg_synthesize.py "<query>"` on Hermes after RSS ingest; visually inspects markdown output for `![*](http://localhost:8765/...)` URLs |

---

## Validation Sign-Off

- [ ] All Phase 20 tasks have automated `<verify>` commands or Wave 0 dependencies declared
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (all RCL/RIN/COG-02 tasks have unit tests; only COG-03 is manual)
- [ ] Wave 0 covers all MISSING test file references (3 new test files listed above)
- [ ] No watch-mode flags (every command is one-shot, exit-code-clean)
- [ ] Feedback latency <30s for the per-task quick-run (3 test files, all mock-driven)
- [ ] `nyquist_compliant: true` set in frontmatter once all Wave 0 stubs land

**Approval:** pending — flips to `approved YYYY-MM-DD` when planner finalizes test file paths in PLAN.md frontmatter `files_modified` blocks.

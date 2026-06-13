---
phase: arx-2-finish
slug: arx-2-finish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase arx-2-finish — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: arx-2-finish-RESEARCH.md §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (confirmed by existing `tests/unit/research/` + `tests/integration/test_research_router.py`) |
| **Config file** | `pytest.ini` / `pyproject.toml` at project root (existing) |
| **Quick run command** | `venv/Scripts/python.exe -m pytest tests/unit/research/test_synthesizer_llm.py -v` |
| **Full suite command** | `venv/Scripts/python.exe -m pytest tests/unit/research/ tests/integration/test_research_router.py -v` |
| **Estimated runtime** | ~30 seconds (unit + transport-mocked integration) |

---

## Sampling Rate

- **After every task commit:** Run quick run command (Wave 1) / `make` test or local bake (Wave 2)
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green + real E2E evidence cited (Principle #6)
- **Max feedback latency:** 30 seconds for code waves; minutes for E2E ops waves (real LLM + deploy)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| W1 synthesizer all-chunk | 01 | 1 | GAP-A | unit | `pytest tests/unit/research/test_synthesizer_llm.py::test_synthesizer_uses_all_chunks_in_prompt -v` | ❌ W0 | ⬜ pending |
| W1 synthesizer degrade | 01 | 1 | GAP-A | unit | `pytest tests/unit/research/test_synthesizer_llm.py::test_synthesizer_degrades_gracefully_on_llm_failure -v` | ❌ W0 | ⬜ pending |
| W1 synthesizer not-stub | 01 | 1 | GAP-A | unit | `pytest tests/unit/research/test_synthesizer_llm.py::test_synthesizer_real_prose_not_chunks0_verbatim -v` | ❌ W0 | ⬜ pending |
| W1 existing synth tests stay green | 01 | 1 | GAP-A regression | unit | `pytest tests/unit/research/test_synthesizer_caption_embeds.py -v` | ✅ (needs conftest get_llm_func mock) | ⬜ pending |
| W2 SSG research page renders | 02 | 2 | REQ-1.1-B (UI) | integration | test bake → assert `kb/output/research/index.html` exists | ❌ W0 | ⬜ pending |
| W2 transport tests stay green | 02 | 2 | REQ-1.1-B-1/2/3 | integration | `pytest tests/integration/test_research_router.py -v` | ✅ | ⬜ pending |
| W2 CSS budget gate | 02 | 2 | ISSUE #6 | integration | `pytest tests/integration/kb/test_search_inline_reveal.py::test_css_budget_within_2100 -v` | ✅ (ALREADY RED — must raise ceiling) | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/unit/research/test_synthesizer_llm.py` — NEW; 3+ test functions pinning GAP-A real synthesis observables (all-chunk usage, graceful degrade, not-chunks[0]-verbatim) — per RESEARCH.md §Risk C
- [ ] `tests/unit/research/conftest.py` — NEW autouse fixture patching `lib.research.stages.synthesizer.get_llm_func` so the 10 existing `test_synthesizer_caption_embeds.py` tests don't break when synthesizer.py starts calling `get_llm_func()` directly (RESEARCH.md Pitfall 6)

*Existing transport/integration infrastructure covers REQ-1.1-B-1/2/3 (already green).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Browser UI: stepper lights up live across 5 stages | REQ-1.1-B-4 (UI) | SSE visual progression not unit-testable | Playwright MCP (main session) navigate → submit query → screenshot stepper transitions → `.playwright-mcp/arx-uat-*.png` |
| Aliyun E2E: real cited report from real KG | REQ-1.1-B-4 + GAP E | Requires real LLM + real KG; depends on ISSUE #44 query selection | `python -m lib.research "<source-returning query>" --dump-state` on Aliyun (env-sourced) → assert retriever chunks>0 + real prose; then browser UAT against Aliyun KB URL |
| Databricks E2E: deployed URL serves working Deep Research | REQ-1.1-B-5 + GAP E | Real deployed app + real serving endpoint | FULL `make deploy` (Principle #9) → Playwright UAT against deployed URL → triple-verify (network 200 + log SDK call + content marker) |

---

## ⚠️ Cross-cutting Risk: ISSUE #44 blocks Aliyun E2E KG-join

**Probed live 2026-06-12 by orchestrator (read-only SSH):** every `/api/synthesize`
long_form query on current Aliyun KG returns `status=done confidence=kg sources=0
md_len=0` (FTS search works: 20 items). graphml = 31432 nodes. This is the live
ISSUE #44 signature (graphml↔Qdrant divergence → hybrid KG-join yields 0 sources).
Deep Research shares this exact retriever.

**Consequence for GAP E:** if the research CLI on Aliyun also returns 0 chunks,
the Aliyun E2E "real cited report" cannot be produced from the KG path. The plan
MUST address this — see PLAN Wave 0/3. The #44 graphml-rebuild fix is OUT of scope;
the in-scope question is whether ANY query (or the web_baseline / web_search stage)
yields a non-empty, useful report on Aliyun, OR whether the Aliyun E2E acceptance
criterion must be re-scoped (e.g. prove the pipeline runs end-to-end + UI works
with a documented #44 caveat on KG-sourced content).

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (test_synthesizer_llm.py + conftest.py)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (code waves)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

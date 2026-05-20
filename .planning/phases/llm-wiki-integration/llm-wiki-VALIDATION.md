---
phase: llm-wiki-integration
slug: llm-wiki-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-19
---

# Phase llm-wiki-integration — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing OmniGraph-Vault setup; `tests/conftest.py` present) |
| **Config file** | `pyproject.toml` (existing) |
| **Quick run command** | `venv/Scripts/python.exe -m pytest tests/unit/test_wiki_*.py -v` (Windows dev) |
| **Full suite command** | `venv/Scripts/python.exe -m pytest tests/unit/test_wiki_*.py tests/integration/test_wiki_*.py -v` |
| **Estimated runtime** | ~30s unit / ~2min integration |
| **Manual UAT** | Per CLAUDE.md Rule 6 — KB local UAT is mandatory before any phase touching `kb/` is marked complete |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite + relevant integration tests
- **Before `/gsd:verify-work`:** Full suite green + manual UAT complete with screenshots cited in VERIFICATION.md
- **Max feedback latency:** 60s for unit, 300s for integration

---

## Per-Task Verification Map

(Filled by planner — leave skeleton for planner to populate per wave/task)

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| W0-01 | 01 | 0 | scaffold | file-existence | `test -d kb/wiki/entities && test -f kb/wiki/SCHEMA.md` | ❌ W0 creates | ⬜ pending |
| W0-02 | 01 | 0 | seed page port | file-existence + content | `test -f kb/wiki/entities/openclaw.md && grep -q '\\^\\[article:' kb/wiki/entities/openclaw.md` | ❌ W0 creates | ⬜ pending |
| W1-01 | 02 | 1 | centrality ranking | unit | `pytest tests/unit/test_wiki_centrality.py -v` | ❌ W1 creates | ⬜ pending |
| W1-02 | 02 | 1 | wiki page generation | integration | `pytest tests/integration/test_wiki_generate.py::test_one_entity_full -v` | ❌ W1 creates | ⬜ pending |
| W1-03 | 02 | 1 | citation integrity | unit | `pytest tests/unit/test_wiki_citations.py::test_all_pages_cited -v` | ❌ W1 creates | ⬜ pending |
| W2-01 | 03 | 2 | Hermes skill diff | local-artifact + grep | `grep -q 'Wiki-first lookup' .planning/phases/llm-wiki-integration/llm-wiki-03-SKILL-DIFF.md` (local diff artifact; Hermes-side `grep -q "wiki" ~/.hermes/skills/omnigraph_query/SKILL.md` is in Manual-Only Verifications below) | ❌ W2 creates | ⬜ pending |
| W3-01 | 04 | 2 | hook fires after cron | integration | `pytest tests/integration/test_wiki_hook.py::test_end_of_cron_fires -v` | ❌ W3 creates | ⬜ pending |
| W3-02 | 04 | 2 | lint blocks bad citation | unit | `pytest tests/unit/test_wiki_lint.py::test_unresolved_citation -v` | ❌ W3 creates | ⬜ pending |
| W3-03 | 04 | 2 | lint blocks contradiction | unit | `pytest tests/unit/test_wiki_lint.py::test_contradicts_existing -v` | ❌ W3 creates | ⬜ pending |
| W4-01 | 05 | 2 | wiki context injected into prompt | integration | `pytest tests/integration/kb/test_synthesize_wiki_inject.py -v` | ❌ W4 creates | ⬜ pending |
| W4-02 | 05 | 2 | falls through if wiki missing | unit | `pytest tests/unit/kb/test_synthesize_wiki_fallthrough.py -v` | ❌ W4 creates | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> **Wave numbering note** (per plan-checker revision 2026-05-19): plan-01 = wave 0; plan-02 = wave 1; plans 03/04/05 all = wave 2 (parallel after W1). The "Wave" column in this table reflects the actual plan frontmatter `wave:` field.

---

## Wave 0 Requirements

Wave 0 of this phase is the wiki scaffold itself (not test infrastructure). For test infrastructure:

- [ ] `tests/unit/test_wiki_lint.py` — unit tests for lint checks (citation, contradiction, backlink, staleness)
- [ ] `tests/unit/test_wiki_centrality.py` — unit tests for entity ranking
- [ ] `tests/unit/test_wiki_citations.py` — unit tests for citation regex / page-level citation coverage
- [ ] `tests/integration/test_wiki_hook.py` — integration tests for end-of-cron hook
- [ ] `tests/integration/test_wiki_generate.py` — integration tests for wiki page generation (uses fixture article set)
- [ ] `tests/integration/kb/test_synthesize_wiki_inject.py` — integration tests for synthesize wiki injection
- [ ] `tests/unit/kb/test_synthesize_wiki_fallthrough.py` — unit tests for synthesize fallthrough when wiki missing
- [ ] `tests/conftest.py` already provides shared fixtures — reuse, no new top-level conftest needed

Wave 0 plan task should create the empty test stubs above with `@pytest.mark.skip("not implemented")` markers, to be filled in by subsequent waves.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Wiki content quality | W1 deliverable | LLM-generated synthesis quality is partially subjective | Read 5 sampled wiki pages from W1 output, verify each claim has `^[article:<hash>]` citation, no obvious hallucinations, cross-references resolve |
| Hermes skill applied + reachable | W2 deliverable | Hermes runs on user PC; can't unit test SKILL.md change from Claude Code | Generate Hermes operator prompt to apply diff; user pastes to Hermes; verify with `omnigraph_query "<entity>"` against an entity that has a wiki page; confirm wiki content returned. Hermes-side grep: `grep -q "wiki" ~/.hermes/skills/omnigraph_query/SKILL.md` |
| End-of-cron hook live | W3 deliverable | Real cron run is multi-hour; can't fully simulate in unit tests | After W3 ships, observe next 09:00 ADT cron run on Hermes; verify `kb/wiki/entities/<entity>.md` updated for at least one entity (or `kb/wiki/_suggestions/` populated if zero changes met lint criteria) |
| Synthesize injection visible in prod | W4 deliverable | Live LLM behavior depends on prompt content | Run KB local UAT per CLAUDE.md Rule 6: query `/api/synthesize?question="What is OpenClaw"&mode=long_form`, inspect server logs for `<wiki_context>` tag in prompt, verify response references wiki claims |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING test references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s for unit, < 300s for integration
- [ ] Manual UAT performed and cited in `llm-wiki-VERIFICATION.md` per CLAUDE.md Rule 6
- [ ] `nyquist_compliant: true` set in frontmatter (NTH-1: flipped by plan-05 Task 3 Step 10 after all 5 plans complete and the items above are checked)

**Approval:** pending
</content>

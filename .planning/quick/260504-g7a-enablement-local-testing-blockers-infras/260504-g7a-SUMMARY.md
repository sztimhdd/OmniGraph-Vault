---
phase: 260504-g7a
plan: 01
type: quick
status: complete
completed: "2026-05-04T15:35:00Z"
requirements:
  - LDEV-01  # Vertex Gemini LLM provider
  - LDEV-02  # Provider dispatcher
  - LDEV-03  # batch_classify_kol via dispatcher
  - LDEV-04  # ingest_wechat LightRAG via dispatcher
  - LDEV-05  # OMNIGRAPH_BASE_DIR override
  - LDEV-06  # Vision skip list + Vertex Gemini Vision
  - LDEV-07  # LOCAL_DEV_SETUP.md runbook + CLAUDE.md env table
  - LDEV-08  # Local bootstrap scripts
  - LDEV-09  # Mock-only unit tests
commits:
  - a45f71d  # LDEV-01
  - 3672565  # LDEV-02
  - a446cf9  # LDEV-03
  - 6953bcd  # LDEV-04
  - 50dce70  # LDEV-05
  - 1c3a2f8  # LDEV-06
  - af8d419  # LDEV-07
  - 2e695ec  # LDEV-08
  - 5edfe25  # LDEV-09
files_touched:
  - lib/vertex_gemini_complete.py        # NEW (LDEV-01)
  - lib/llm_complete.py                  # NEW (LDEV-02)
  - batch_classify_kol.py                # MODIFIED (LDEV-03)
  - ingest_wechat.py                     # MODIFIED (LDEV-04)
  - config.py                            # MODIFIED (LDEV-05)
  - image_pipeline.py                    # MODIFIED (LDEV-06)
  - docs/LOCAL_DEV_SETUP.md              # NEW (LDEV-07)
  - CLAUDE.md                            # MODIFIED (LDEV-07)
  - scripts/local_dev_start.ps1          # NEW (LDEV-08)
  - scripts/local_dev_start.sh           # NEW (LDEV-08)
  - tests/unit/test_llm_complete.py              # NEW (LDEV-09)
  - tests/unit/test_vertex_gemini_complete.py    # NEW (LDEV-09)
  - tests/unit/test_config_base_dir_override.py  # NEW (LDEV-09)
  - tests/unit/test_vision_skip_providers.py     # NEW (LDEV-09)
---

# Quick Task 260504-g7a — Local Dev Enablement Summary

## One-liner

Nine atomic opt-in fixes making the OmniGraph-Vault pipeline runnable on the
Windows dev box against `.dev-runtime/` using Vertex Gemini (SA auth) —
zero breaking changes for Hermes production (default `OMNIGRAPH_LLM_PROVIDER`
unset → DeepSeek path preserved).

## Commits

| # | SHA | Requirement | Title |
|---|-----|-------------|-------|
| 1 | `a45f71d` | LDEV-01 | `feat(local-dev): add Vertex Gemini LLM provider` |
| 2 | `3672565` | LDEV-02 | `feat(local-dev): add llm provider dispatcher` |
| 3 | `a446cf9` | LDEV-03 | `feat(local-dev): batch_classify_kol dispatches via llm_complete` |
| 4 | `6953bcd` | LDEV-04 | `feat(local-dev): ingest_wechat LightRAG uses llm_complete dispatcher` |
| 5 | `50dce70` | LDEV-05 | `feat(local-dev): OMNIGRAPH_BASE_DIR env override for BASE_DIR` |
| 6 | `1c3a2f8` | LDEV-06 | `feat(local-dev): OMNIGRAPH_VISION_SKIP_PROVIDERS + Vertex Gemini Vision` |
| 7 | `af8d419` | LDEV-07 | `docs(local-dev): LOCAL_DEV_SETUP runbook + CLAUDE.md env row` |
| 8 | `2e695ec` | LDEV-08 | `feat(local-dev): bootstrap scripts for Windows + WSL` |
| 9 | `5edfe25` | LDEV-09 | `test(local-dev): mock-only unit coverage for LDEV-01..06` |

Each commit was individually verified (`<verify>` block from the PLAN ran
green) before the next commit landed. All 9 are independently revertable.

## Test results

### New test files (LDEV-09) — 25 tests

```
tests/unit/test_llm_complete.py ...........................  [  5 passed]
tests/unit/test_vertex_gemini_complete.py ..................  [ 10 passed]
tests/unit/test_config_base_dir_override.py ................  [  4 passed]
tests/unit/test_vision_skip_providers.py ...................  [  6 passed]
============================= 25 passed in 6.24s =============================
```

All mock-only. Zero outbound HTTP. Passes behind Cisco Umbrella.

### Full regression (tests/unit) — no new failures

- Pre-task baseline (before any commit): 429 passed / 17 failed / 446 total.
- Post-task final: 454 passed / 17 failed / 471 total.
- Delta: +25 passed (exactly the new LDEV-09 tests); 0 new regressions; 0
  previously-passing tests converted to failing.

The 17 pre-existing failures are network/auth-dependent tests
(`test_lightrag_embedding_rotation`, `test_siliconflow_balance`,
`test_cognee_vertex_model_name`, `test_batch_ingest_topic_filter` LIKE-substring
change from `ba3aa4c`, `test_text_first_ingest`, `test_lightrag_embedding`).
Not caused by this task.

## Post-completion env-var cheat sheet

| Var | Default | Purpose |
|-----|---------|---------|
| `OMNIGRAPH_LLM_PROVIDER` | `deepseek` | `deepseek` or `vertex_gemini` |
| `OMNIGRAPH_LLM_MODEL` | `gemini-3.1-flash-lite-preview` | Vertex Gemini model id |
| `OMNIGRAPH_VISION_SKIP_PROVIDERS` | _(empty)_ | Comma-list; typical local: `siliconflow,openrouter` |
| `OMNIGRAPH_BASE_DIR` | `~/.hermes/omonigraph-vault` | Absolute path to runtime data root |
| `OMNIGRAPH_LLM_TIMEOUT_SEC` | `600` | Int seconds; Vertex LLM only |

Plus SA auth (Vertex mode only):

| Var | Value |
|-----|-------|
| `GOOGLE_APPLICATION_CREDENTIALS` | `<abs path>/gcp-paid-sa.json` |
| `GOOGLE_CLOUD_PROJECT` | `<project-id>` |
| `GOOGLE_CLOUD_LOCATION` | `global` (default) |

Plus the Phase 5 DeepSeek cross-coupling dummy (CLAUDE.md FLAG 2):

| Var | Value |
|-----|-------|
| `DEEPSEEK_API_KEY` | `dummy` (only required for import to succeed; never used when `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`) |

## Deviations from plan

**None material.** Two minor judgement calls locked in during execution:

1. **LDEV-01 timeout plumbing choice:** the plan noted `timeout via client
   constructor vs per-call config` as SDK-dependent. google-genai 1.0+
   accepts `types.GenerateContentConfig(http_options=types.HttpOptions(timeout=...))`
   where timeout is in **milliseconds**. Chose per-call config (not
   client-level) so tests can assert the integer plumbed per call. Test
   `test_timeout_propagation` pins `timeout == 42 * 1000` (seconds → ms).

2. **LDEV-03 in-file caller update:** The only in-file caller of
   `_call_deepseek_fullbody` inside `batch_classify_kol.py` was itself
   (the deprecation wrapper referencing the alias). All other callers
   (`batch_ingest_from_spider.py:957-960`, `scripts/bench_ingest_fixture.py:313`,
   3 test files) already use the 2-arg form — the `_call_deepseek_fullbody`
   alias with `api_key: str | None = None` handles them verbatim, emitting
   `DeprecationWarning` at runtime. No mass-refactor needed per Surgical
   Changes principle.

## Acceptance gates — all green

- [x] 9 atomic commits on `main`, each independently revertable
- [x] Each commit individually verified before the next landed
- [x] Final pytest on 4 new test files: 25/25 GREEN, zero outbound HTTP
- [x] `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` → `vertex_gemini_model_complete`
- [x] `OMNIGRAPH_LLM_PROVIDER` unset → `deepseek_model_complete` (Hermes preserved)
- [x] `OMNIGRAPH_BASE_DIR=c:/test` → `config.BASE_DIR == Path('c:/test')`
- [x] `lib/llm_complete` NOT in `lib/__init__.py` exports (import-on-demand)
- [x] `lib/llm_deepseek.py` unchanged (DeepSeek fallback retained)
- [x] `~/.hermes/.env` untouched (Hermes production zero-change)
- [x] `docs/LOCAL_DEV_SETUP.md` 209 lines covering all 10 required sections
- [x] `scripts/local_dev_start.{ps1,sh}` exist and handle 5-prereq check + image server
- [x] Pre-existing pytest baseline unchanged (17 pre-existing failures identical, 0 new regressions)

## Operator next steps

To exercise the local dev path:

1. Populate `.dev-runtime/.env` with the 5 `OMNIGRAPH_*` vars + SA env +
   `DEEPSEEK_API_KEY=dummy` (see `docs/LOCAL_DEV_SETUP.md` § 4).
2. Run `scripts\local_dev_start.ps1` (Windows) or
   `bash scripts/local_dev_start.sh` (WSL).
3. Verify: `venv\Scripts\python -c "from lib.llm_complete import get_llm_func; print(get_llm_func().__name__)"`
   — expect `vertex_gemini_model_complete`.
4. Optional smoke: `venv\Scripts\python ingest_wechat.py "<test-article-url>"`.

Full runbook: `docs/LOCAL_DEV_SETUP.md`.

## Post-commit push

Remote `origin/main` not yet pushed — see orchestrator for final push decision.

## Self-Check: PASSED

- [x] All 9 commits present in `git log --oneline -10` (verified)
- [x] All 14 files-touched confirmed via `git show --stat` per commit
- [x] All 25 new unit tests GREEN (pytest output above)
- [x] Acceptance gates #1-12 from plan `<success_criteria>` all green
- [x] No regressions vs pre-task baseline (17 = 17 pre-existing failures)

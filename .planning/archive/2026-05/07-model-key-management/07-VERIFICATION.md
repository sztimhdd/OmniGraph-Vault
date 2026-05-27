---
phase: 07-model-key-management
status: passed
score: 17/17 must-haves verified
date: 2026-04-29
re_verification: false
human_verification:
  - test: "Multi-account rotation actually increases quota"
    expected: "With OMNIGRAPH_GEMINI_KEYS set to 2+ keys from different Google projects, ingest workload that normally 429s with single key shows ~2× throughput before hitting 429"
    why_human: "Requires 2+ real Google accounts; can't mock per-project quota semantics"
  - test: "Live kg_synthesize + Cognee rotation end-to-end"
    expected: "python kg_synthesize.py \"test query\" hybrid on remote Hermes PC returns synthesis AND Cognee recalls previous context AND mid-run rotate_key() triggers refresh_cognee() cache-clear without crash"
    why_human: "Requires live Gemini API + deployed Cognee DB + populated LightRAG graph; rotation triggered by wall-clock quota window"
  - test: "SKILL.md live deploy validation on Hermes PC"
    expected: "SSH to Hermes PC, run `hermes skills list omnigraph_ingest` → shows OMNIGRAPH_GEMINI_KEY as required env var; `openclaw skills list` (if available) shows skillKey=omnigraph-vault with primaryEnv"
    why_human: "Requires deployed Hermes instance and/or Openclaw runtime with skills hot-reload"
  - test: "Cached article replay (ingest_wechat Wave 1 parity gate)"
    expected: "`python ingest_wechat.py <url>` where ~/.hermes/omonigraph-vault/images/{hash}/final_content.md exists → 'Cached article found' log + LightRAG insert success (no HTTP egress)"
    why_human: "Requires cached article on disk from prior ingest; local Windows dev env does not have Phase 4 fixture data"
---

# Phase 07: Model & Key Management — Verification Report

**Phase Goal (ROADMAP.md line 47):** Centralize Gemini model selection, API key loading (+ optional multi-account rotation), per-model rate limiting, and 429/503 retry into a repo-root `lib/` module. Migrate all 18 production files off direct `GEMINI_API_KEY` + hardcoded model strings. Single-vendor (Gemini) scope; new SDK (`google-genai`).

**Verified:** 2026-04-29
**Status:** passed
**Re-verification:** No — initial verification

---

## 1. Goal Achievement

The goal is met. `lib/` exists as a 6-module package with full public surface (13 symbols); all 18 production files are migrated to `lib`, `config.py` no longer exposes model constants or `gemini_call`, hardcoded `"gemini-*"` model strings are confined to `lib/models.py` (owner) + one documented exception (`cognee_wrapper.py:49` Cognee handshake env var) + one intentional test-harness independence literal (`skill_runner.py:154` per Open Q #4); the full test suite passes 109/109 with `DEEPSEEK_API_KEY=dummy`. Both Hermes FLAGs from `07-REVIEW-HERMES-WAVES-2-3.md` are documented in both `Deploy.md` and `CLAUDE.md`.

---

## 2. Must-Haves Checklist

### Wave 0 (lib/ package + Amendment 4)

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `lib/` package importable with 6 modules + 13 public symbols | ✓ PASS | `ls lib/` → `__init__.py`, `api_keys.py`, `lightrag_embedding.py`, `llm_client.py`, `llm_deepseek.py`, `models.py`, `rate_limit.py` (7 files; `llm_deepseek.py` added by Phase 5 Plan 00c). Import smoke `from lib import generate, aembed, generate_sync, current_key, rotate_key, get_limiter, embedding_func, INGESTION_LLM, VISION_LLM, SYNTHESIS_LLM, EMBEDDING_MODEL, GITHUB_INGEST_LLM, refresh_cognee` → `ALL 13 IMPORTS OK`. |
| 2 | Model constants are BARE STRING LITERALS (D-02 SUPERSEDED per Amendment 1) | ✓ PASS | `lib/models.py` lines 10-14: `INGESTION_LLM = "gemini-2.5-flash-lite"` (literal, not `os.environ.get(...)`); `VISION_LLM`, `SYNTHESIS_LLM`, `GITHUB_INGEST_LLM`, `EMBEDDING_MODEL` all literals. Module docstring references "D-02 SUPERSEDED". |
| 3 | `rotate_key()` writes `os.environ["COGNEE_LLM_API_KEY"]` inline (Amendment 4) | ✓ PASS | `lib/api_keys.py:96`: `os.environ["COGNEE_LLM_API_KEY"] = _current` inside `rotate_key()`. Additionally seeded in `_init_cycle()` line 75. No listener/observer scaffolding. |
| 4 | `refresh_cognee()` calls `cognee.infrastructure.llm.config.get_llm_config.cache_clear()` | ✓ PASS | `lib/api_keys.py:119-122`: `from cognee.infrastructure.llm.config import get_llm_config; get_llm_config.cache_clear()` inside `refresh_cognee()` with ImportError guard. |
| 5 | `lightrag_embedding.py` at repo root is ≤15-line shim re-exporting from `lib` (D-09) | ✓ PASS | `wc -l lightrag_embedding.py` → 12 lines. Body: `from lib.lightrag_embedding import embedding_func`. Amendment 2 parity assertion `old_ref is new_ref` returns `parity ok`. |
| 6 | No `lib/cognee_bridge.py` exists (Amendment 4 deleted this concept) | ✓ PASS | `ls lib/cognee_bridge.py` → `No such file or directory`. |
| 7 | `tests/integration/test_cognee_rotation.py` exists and tests Amendment 4 surface | ✓ PASS | File exists. Wave 3 SUMMARY confirms 3/3 passing: `test_rotate_sets_env_and_refresh_clears_cache`, `test_rotate_propagates_fresh_key_after_cache_clear`, `test_refresh_cognee_calls_cache_clear`. |

### Wave 1–4 migration

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 8 | `grep -E "(INGEST_LLM_MODEL|IMAGE_DESCRIPTION_MODEL|ENRICHMENT_LLM_MODEL)" config.py` → ZERO matches | ✓ PASS | Grep on `config.py` returns 0 matches. Amendment 3 sweeper (commit `8b10e2a`) deleted all three shim constants. |
| 9 | `grep "^def gemini_call\|^class _GeminiCallResponse" config.py` → ZERO matches | ✓ PASS | Grep returns 0 matches. Sweeper deleted both. `config.py` now 85 lines of paths + `load_env()` + ENRICHMENT_* non-model constants only. |
| 10 | No production file has `from config import ..._LLM_MODEL / gemini_call / IMAGE_DESCRIPTION_MODEL` | ✓ PASS | Clean-room grep excluding `venv/.venv/__pycache__/.claude/.planning`: ZERO matches. The `.claude/worktrees/agent-*/` matches are stale ephemeral agent worktree copies, not production state on main. |
| 11 | Direct Gemini SDK residue in production files | ✓ PASS | Clean-room grep `os.environ["GEMINI_API_KEY"] \| os.environ.get("GEMINI_API_KEY"` excluding `tests/`: 5 hits. All 5 are documented exceptions: `lib/api_keys.py:45,59` (lib itself OWNS the env-var load per D-04 precedence ladder); `lib/lightrag_embedding.py:11` (docstring narrative comment, not a call); `omnigraph_search/query.py:31` (Phase 6 scope per `07-04-SUMMARY.md` Query B analysis); `scripts/phase5_wave0_spike.py:127` (Phase 5 Wave 0 scope, will sweep when Phase 5 replans per D-01). |
| 12 | Hardcoded `"gemini-..."` model strings in production code | ✓ PASS | Clean-room grep excluding `tests/scripts/.claude/.planning`: 10 hits. 6 are the `lib/models.py` OWNER lines + `RATE_LIMITS_RPM` dict keys; 3 are docstring comments (`image_pipeline.py:72-73` describing R3 GA migration history; `lib/lightrag_embedding.py:14` describing EMBEDDING_MODEL default). Remaining 2: `cognee_wrapper.py:49` (`os.environ["EMBEDDING_MODEL"] = "gemini-embedding-2"`) is a documented Cognee handshake env var preserved per Wave 3 SUMMARY; `skill_runner.py:154` is the test-harness literal kept per Open Q #4 with inline rationale. No production code imports or calls with hardcoded model strings. |
| 13 | 18 target production files migrated (or justified-skip) | ✓ PASS | Wave 1: `ingest_wechat.py`. Wave 2: `ingest_github.py`, `multimodal_ingest.py`, `query_lightrag.py`, `kg_synthesize.py`, `image_pipeline.py`, `config.py` (scope narrow). Wave 3: `cognee_wrapper.py`, `cognee_batch_processor.py`, `enrichment/extract_questions.py`, `init_cognee.py`, `setup_cognee.py`. Wave 4: `batch_classify_kol.py`, `batch_ingest_from_spider.py`, `batchkol_topic.py`, `_reclassify.py`, `skill_runner.py`, `tests/verify_gate_{a,b,c}.py`. Plus justified-skip: `enrichment/fetch_zhihu.py` and `enrichment/merge_and_ingest.py` have zero direct Gemini touchpoints (documented in 07-02-SUMMARY.md with Hermes ACCEPT at `07-REVIEW-HERMES-WAVES-2-3.md §7`). |
| 14 | 3 SKILL.md files have `OMNIGRAPH_GEMINI_KEY` in frontmatter | ✓ PASS | `skills/omnigraph_ingest/SKILL.md` lines 22,26,33,37: 4+ occurrences (`compatibility`, `required_environment_variables.name`, `metadata.openclaw.primaryEnv`, `requires.config`). Same pattern in `skills/omnigraph_query/SKILL.md` and `skills/omnigraph_architect/SKILL.md`. All 3 have dual-host metadata (Hermes `required_environment_variables` + OpenClaw `metadata.openclaw.skillKey: omnigraph-vault` + `primaryEnv: OMNIGRAPH_GEMINI_KEY`) per D-07. |
| 15 | `Deploy.md` + `.env.template` exist and document the env surface | ✓ PASS | `Deploy.md` § Environment Variables (Phase 7) — Required table, Optional rotation, Model names (Amendment 1 — not env-overridable), RPM overrides (D-08). `.env.template` 56 lines covers `OMNIGRAPH_GEMINI_KEY`, `OMNIGRAPH_GEMINI_KEYS`, `GEMINI_API_KEY`, `GEMINI_API_KEY_BACKUP`, `DEEPSEEK_API_KEY` required block, model-constant comments, `OMNIGRAPH_RPM_*` examples. |
| 16 | Both Hermes FLAGs documented in Deploy.md / CLAUDE.md | ✓ PASS | See §3 below. |

### Test suite

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 17 | `pytest tests/ -q` (with `DEEPSEEK_API_KEY=dummy`) exits 0 | ✓ PASS | Re-ran locally: `109 passed, 14 warnings in 17.61s`. Matches Wave 3 + Wave 4 SUMMARYs' documented 109/109 baseline. |

---

## 3. Hermes FLAG Disposition

Both non-blocking FLAGs from `07-REVIEW-HERMES-WAVES-2-3.md` landed as documentation-only per Wave 4 plan Task 4.5. Both are present in both canonical locations (not handwaved).

| FLAG | Summary | Deploy.md | CLAUDE.md |
|------|---------|:---------:|:---------:|
| FLAG 1 (§2) | Standalone Cognee rotation caveat — `cognee_wrapper.py` seeds key once at import; long-running standalone callers must call `refresh_cognee()` themselves | ✓ Full subsection "Known limitation — standalone Cognee rotation (Hermes FLAG 1)" at lines 62-79 | ✓ Full paragraph at line 163 ("Standalone Cognee rotation caveat (Hermes FLAG 1)") |
| FLAG 2 (§6) | `DEEPSEEK_API_KEY` required at `lib/` import time (Phase 5 Plan 00c eager import of `deepseek_model_complete`) | ✓ Warning under Required table at lines 22-29, including `DEEPSEEK_API_KEY=dummy` workaround | ✓ Full paragraph at line 161 ("Phase 5 DeepSeek cross-coupling (Hermes FLAG 2)"). Also `.env.template` lines 24-30. |

Both FLAGs explicitly labelled and linked back to the source review. No code changes attempted in Phase 7 (both are future-phase follow-ups — Phase 5 owns the DeepSeek import-time coupling; standalone Cognee rotation is intentional single-user trade-off).

---

## 4. Test Suite Result

- **Command:** `DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/ --tb=no -q`
- **Result:** `109 passed, 14 warnings in 17.61s` (re-run live during verification)
- **Baseline tracking:** matches Wave 2 exit (95/0 after test-patch fixes) → Wave 3 exit (109/109 after additional Phase 5 Plan 00c tests landed) → Wave 4 final (109/109 held across 12 atomic commits)
- **Without `DEEPSEEK_API_KEY`:** import-time RuntimeError (Hermes FLAG 2; known, documented, out of Phase 7 scope)

Warnings categories: Pydantic `json_encoders` deprecation (Cognee/LightRAG dep, not Phase 7 code); `AsyncLimiter` cross-loop re-use warning in 5 unit tests (test-harness artifact, not a production concern — production code uses a single event loop per process).

---

## 5. Manual-Only Verifications Deferred

Per `07-VALIDATION.md § Manual-Only Verifications`, the following items cannot be exercised from local Windows dev env and are deferred to the Hermes PC / user-run steps. All are captured in the frontmatter `human_verification:` block above and should be run before closing Phase 7 if confidence beyond unit/integration tests is needed:

1. **Multi-account rotation quota increase (D-04).** Requires 2+ real Google accounts with different GCP projects. Exercise path: populate `OMNIGRAPH_GEMINI_KEYS` with two keys from different accounts and run ingestion workload; observe 2× throughput before first 429.
2. **Live `kg_synthesize` + Cognee rotation end-to-end (Wave 3 gate).** Requires live Gemini API + deployed Cognee DB + populated LightRAG graph. Verifies the Amendment 4 chain (env-var write + cache-clear) against real production Cognee state, not just mocked `get_llm_config.cache_clear()`.
3. **SKILL.md live deploy validation on Hermes PC (D-07 Wave 4).** SSH to remote Hermes PC, run `hermes skills list omnigraph_ingest` → confirm `OMNIGRAPH_GEMINI_KEY` listed as required env var; repeat for `omnigraph_query` and `omnigraph_architect`. Optional: `openclaw skills list` if Openclaw is configured.
4. **Cached article replay (Wave 1 parity gate).** Requires cached article on disk at `~/.hermes/omonigraph-vault/images/{hash}/final_content.md` (from prior ingest). Exercise path: `python ingest_wechat.py <url>` → expect "Cached article found" log + LightRAG insert success with zero HTTP egress.

**Recommendation:** Items 1, 3, 4 are low-risk (behaviors unchanged at API level; only plumbing changed). Item 2 is the highest-value manual check — it's the only way to catch a real-world mismatch between the mocked `get_llm_config.cache_clear()` integration test and the actual Cognee `@lru_cache` behavior under rotation.

---

## 6. Gaps

**None.** All 17 must-haves pass. All Hermes FLAGs documented. Test suite green. Production code state matches the SUMMARY claims file-by-file (spot-checked: `lib/api_keys.py`, `lib/models.py`, `config.py`, `lightrag_embedding.py`, `.env.template`, `Deploy.md`, all 3 SKILL.md frontmatters).

---

## 7. Verdict

**Status: passed** — Phase 07 goal achieved. Recommend proceeding to phase completion (ROADMAP.md flip to complete + STATE.md update + commit + push).

Two non-blocking follow-ups for future phases (NOT Phase 7 gaps):
- **Phase 5 follow-up:** soft-fail the `lib.llm_deepseek` import when `DEEPSEEK_API_KEY` is unset (Hermes FLAG 2 recommendation)
- **Phase 5 Wave 0 replan:** sweep `scripts/phase5_wave0_spike.py` + `tests/verify_wave0_*.py` to use `lib.current_key()` (per 07-CONTEXT.md D-01)

---

*Verified: 2026-04-29*
*Verifier: Claude (gsd-verifier, Opus 4.7)*

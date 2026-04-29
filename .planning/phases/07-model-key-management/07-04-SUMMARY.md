---
phase: 07-model-key-management
plan: 04
subsystem: infra
tags: [gemini, wave-4, cleanup, d-07, amendment-3, sweeper, deploy-story, p2-migration]

requires:
  - phase: 07-model-key-management
    provides: Wave 0 lib/ + Wave 1 ingest_wechat reference + Wave 2 P0 migration + Wave 3 P1 Cognee chain
provides:
  - P2 batch scripts (batch_classify_kol, batch_ingest_from_spider, batchkol_topic, _reclassify) migrated to lib/
  - skill_runner.py key handling migrated (model literal kept per Open Q #4)
  - 3 verify_gate tests migrated (Cognee handshake mirrors cognee_wrapper Wave 3 pattern)
  - 3 Hermes skill SKILL.md frontmatters updated with OMNIGRAPH_GEMINI_KEY + OpenClaw primaryEnv (D-07)
  - Deploy story complete (.env.template + Deploy.md + CLAUDE.md) — includes both Hermes FLAGs
  - Amendment 3 sweeper: config.py D-11 shims + gemini_call + _GeminiCallResponse DELETED
  - ingest_wechat.extract_entities migrated to lib.generate_sync (last remaining gemini_call caller)
affects: [batch_classify_kol, batch_ingest_from_spider, batchkol_topic, _reclassify, skill_runner, verify_gate_a, verify_gate_b, verify_gate_c, skills/omnigraph_ingest, skills/omnigraph_query, skills/omnigraph_architect, Deploy, CLAUDE, config, ingest_wechat, image_pipeline]

tech-stack:
  added: []
  patterns:
    - "Batch script migration: from config.gemini_call → lib.generate_sync(INGESTION_LLM, ...); DeepSeek branch left intact (not Phase 7 scope)"
    - "skill_runner test-harness exception (Open Q #4): _GEMINI_MODEL kept as string literal for test independence; current_key() used for auth"
    - "verify_gate tests mirror cognee_wrapper Wave 3 handshake: INGESTION_LLM + EMBEDDING_MODEL sourced from lib (not hardcoded)"
    - "Dual-host SKILL.md frontmatter (D-07): Hermes required_environment_variables + OpenClaw primaryEnv/skillKey declare OMNIGRAPH_GEMINI_KEY with GEMINI_API_KEY fallback documented in help text"
    - "Amendment 3 sweeper: config.py scope permanently narrowed to paths + env; lib/ owns all LLM concerns"

key-files:
  created:
    - .env.template
  modified:
    - batch_classify_kol.py
    - batch_ingest_from_spider.py
    - batchkol_topic.py
    - _reclassify.py
    - skill_runner.py
    - tests/verify_gate_a.py
    - tests/verify_gate_b.py
    - tests/verify_gate_c.py
    - skills/omnigraph_ingest/SKILL.md
    - skills/omnigraph_query/SKILL.md
    - skills/omnigraph_architect/SKILL.md
    - Deploy.md
    - CLAUDE.md
    - config.py
    - ingest_wechat.py
    - image_pipeline.py
    - tests/unit/test_fetch_zhihu.py
    - tests/unit/test_extract_questions.py

key-decisions:
  - "Plan listed 4.1a-4.1d as separate commits per D-03 (MED 3 resolution); honored — 4 atomic commits + 109/109 pytest green between each"
  - "ingest_wechat.extract_entities was the LAST active gemini_call caller at start of Wave 4 (Wave 2 Task 2.7 kept the shim specifically for this + enrichment.extract_questions; the latter migrated in Wave 3 Task 3.3). Wave 4 required a pre-sweep migration commit (1f19675) before Task 4.7 could cleanly sweep config.py"
  - "skill_runner.py _GEMINI_MODEL kept as string literal per 07-RESEARCH Open Q #4 (test-harness independence — updating production INGESTION_LLM should not implicitly change skill test behavior). Literal value updated 'gemini-3.1-flash-lite-preview' → 'gemini-2.5-flash-lite' with rationale comment"
  - "verify_gate tests adopted cognee_wrapper.py Wave 3 handshake pattern: LLM_MODEL/EMBEDDING_MODEL env vars reference lib.INGESTION_LLM/EMBEDDING_MODEL constants, not hardcoded strings. Cognee still sees deterministic string values via os.environ at handshake time"
  - "Amendment 3 sweeper: D-11 'shims may remain indefinitely' text officially superseded. config.py scope permanently narrowed to paths + env loading; lib.models is single source of truth for model names"
  - "Both Hermes FLAGs from 07-REVIEW-HERMES-WAVES-2-3.md landed as documentation only — no code changes. FLAG 1 (standalone Cognee rotation caveat) and FLAG 2 (DEEPSEEK_API_KEY required at lib import time) documented in both Deploy.md and CLAUDE.md"

requirements-completed: [D-03, D-04, D-06, D-07]

metrics:
  duration: "~45 min (Claude executor, autonomous)"
  completed: "2026-04-29"
  tasks_completed: 10
  files_modified: 18
  files_created: 1
  commits: 12

---

# Phase 7 Plan 04: Wave 4 Cleanup + Amendment 3 Sweeper Summary

**Ten tasks landed in 12 atomic commits: 4 P2 batch scripts migrated to lib/, skill_runner key handling swapped (model literal preserved per Open Q #4), 3 verify_gate tests rewired to lib, 3 Hermes SKILL.md frontmatters updated with dual-host metadata (D-07), deploy story closed (.env.template + Deploy.md + CLAUDE.md paragraphs), ingest_wechat.extract_entities pre-sweep migration (the last remaining gemini_call caller), and finally Amendment 3 sweeper DELETED config.py D-11 shims + gemini_call + _GeminiCallResponse wrapper. Pytest held at 109/109 green across every commit.**

## Performance

- **Duration:** ~45 min (Claude executor, autonomous)
- **Completed:** 2026-04-29
- **Tasks:** 10 (4.1a, 4.1b, 4.1c, 4.1d, 4.2, 4.3 [×3 files], 4.4, 4.5, 4.7 sweeper + pre-sweep migration, 4.6 final gate)
- **Commits:** 12 atomic per D-03
- **Files modified:** 18 + 1 created (.env.template)

## Accomplishments

### Task 4.1a — batch_classify_kol.py (commit `9d9772f`)
- Swap `genai.Client(api_key=...).models.generate_content(...)` → `lib.generate_sync(INGESTION_LLM, prompt, config=...)`
- Drop `get_gemini_api_key()` helper (lib.current_key owns key resolution)
- Remove unused `from google import genai` — `genai_types` kept for `GenerateContentConfig(response_mime_type=...)` kwarg
- DeepSeek classifier branch untouched (not Phase 7 scope)

### Task 4.1b — batch_ingest_from_spider.py (commit `7ddb5e3`) — CLI PRESERVED
- Same migration pattern as 4.1a
- Gemini precheck in `batch_classify_articles()` now uses `lib.current_key()` (fail-open semantics preserved)
- **`--from-db` / `--topic-filter` argparse CLI preserved verbatim** (Phase 5 D-11 contract)

### Task 4.1c — batchkol_topic.py (commit `c1832fc`)
- Same migration pattern as 4.1a
- `config.load_env()` call chain preserved (intended — batchkol_topic imports config.load_env explicitly)

### Task 4.1d — _reclassify.py (commit `d0cc3e2`)
- Same migration pattern as 4.1a
- Drop `get_gemini_api_key()` + hand-rolled `~/.hermes/auth.json` scan (lib.api_keys handles all of it)

### Task 4.2 — skill_runner.py (commit `b5ab408`)
- Key: `os.environ.get("GEMINI_API_KEY")` → `current_key()` (rotation-aware)
- Model: `_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"` → `_GEMINI_MODEL = "gemini-2.5-flash-lite"`
- **Model literal retained (not from lib.models) per 07-RESEARCH Open Q #4** — test-harness independence from production model changes; added inline rationale comment

### Task 4.3 — verify_gate_{a,b,c}.py (commits `490c3a7`, `e7a26f5`, `b705a14`)
- Separate commits per D-03
- All 3: `from lib import current_key, INGESTION_LLM, EMBEDDING_MODEL`
- `os.environ['LLM_MODEL'] = INGESTION_LLM`, `os.environ['EMBEDDING_MODEL'] = EMBEDDING_MODEL` (mirrors cognee_wrapper.py Wave 3 handshake)
- verify_gate_c: drop hand-rolled dotenv parser (~15 lines); lib.api_keys.load_keys handles it via config.load_env
- Note: `os.environ['GEMINI_API_KEY'] = _key` assignment preserved — Cognee's downstream SDK reads GEMINI_API_KEY from env at its own init time

### Task 4.4 — 3 SKILL.md frontmatters (commit `4676fb3`) — D-07
- Added Hermes `required_environment_variables` block with `OMNIGRAPH_GEMINI_KEY` + prompt/help (fallback documented) / required_for
- Added OpenClaw `skillKey: omnigraph-vault` + `primaryEnv: OMNIGRAPH_GEMINI_KEY` in metadata.openclaw
- Updated `requires.config`: `GEMINI_API_KEY` → `OMNIGRAPH_GEMINI_KEY`
- Updated `compatibility:` block to mention OMNIGRAPH_GEMINI_KEY (preferred) + fallback
- Preserved name, description, body verbatim
- YAML validates cleanly for all 3 files

### Task 4.5 — Deploy story (commit `19ff273`)
- **Created `.env.template`** (was stub; now full template with OMNIGRAPH_* precedence, model-constant comment block per Amendment 1, DEEPSEEK_API_KEY required comment, OMNIGRAPH_RPM_* examples)
- **Updated `Deploy.md`** with new `## Environment Variables (Phase 7)` section: required table, rotation table, model-constant table (Amendment 1), RPM override examples, **Hermes FLAG 1 + FLAG 2 documentation** (standalone Cognee rotation caveat + DEEPSEEK_API_KEY import-time coupling)
- **Updated `CLAUDE.md`** with 3 paragraphs: Phase 7 env var convention + FLAG 1 caveat + FLAG 2 caveat
- Both Hermes FLAGs land as documentation-only (no code changes); per plan Task 4.5 scope

### Task 4.7 pre-sweep — ingest_wechat.extract_entities (commit `1f19675`)
- The ONE remaining active `config.gemini_call` caller at start of Wave 4
- Migrated to `lib.generate_sync(INGESTION_LLM, prompt)` — `response.text` access collapses to a plain string
- Also swept 3 historical-narrative comments that referenced `config.gemini_call` or `config.IMAGE_DESCRIPTION_MODEL` (image_pipeline.py docstring, test_fetch_zhihu.py comment, test_extract_questions.py docstring)

### Task 4.7 SWEEPER — config.py (commit `8b10e2a`) — Amendment 3
- **DELETED `from lib.models import INGESTION_LLM, VISION_LLM`** (only fed the shims)
- **DELETED 3 D-11 shim constants:**
  - `INGEST_LLM_MODEL = INGESTION_LLM`
  - `ENRICHMENT_LLM_MODEL = INGESTION_LLM`
  - `IMAGE_DESCRIPTION_MODEL = VISION_LLM`
- **DELETED `class _GeminiCallResponse`** (back-compat `.text` wrapper)
- **DELETED `def gemini_call(...)`** (~25-line shim)
- **PRESERVED:** `BASE_DIR`, `RAG_WORKING_DIR`, `BASE_IMAGE_DIR`, `SYNTHESIS_OUTPUT`, `ENTITY_BUFFER_DIR`, `CANONICAL_MAP_FILE`, `CDP_URL`, `FIRECRAWL_API_KEY`, `load_env()`, `ENRICHMENT_*` non-model constants, `ZHIHAO_SKILL_NAME`, `IMAGE_SERVER_BASE_URL`
- Net: `1 file changed, 7 insertions(+), 55 deletions(-)` — config.py scope permanently narrowed to paths + env loading

### Task 4.6 — Final phase gate
- Clean-room greps (see below) run with `--exclude-dir=.claude` (worktree copies excluded)
- Full pytest: **109/109 green** with `DEEPSEEK_API_KEY=dummy`
- SUMMARY.md written (this file)

## Commit Hashes

1. Task 4.1a: `9d9772f` — refactor(07-04): migrate batch_classify_kol.py to lib/
2. Task 4.1b: `7ddb5e3` — refactor(07-04): migrate batch_ingest_from_spider.py to lib/ (CLI preserved)
3. Task 4.1c: `c1832fc` — refactor(07-04): migrate batchkol_topic.py to lib/
4. Task 4.1d: `d0cc3e2` — refactor(07-04): migrate _reclassify.py to lib/
5. Task 4.2: `b5ab408` — refactor(07-04): migrate skill_runner.py key handling (model literal kept per Open Q #4)
6. Task 4.3a: `490c3a7` — refactor(07-04): migrate tests/verify_gate_a.py to lib/
7. Task 4.3b: `e7a26f5` — refactor(07-04): migrate tests/verify_gate_b.py to lib/
8. Task 4.3c: `b705a14` — refactor(07-04): migrate tests/verify_gate_c.py to lib/
9. Task 4.4: `4676fb3` — feat(07-04): dual-host SKILL.md frontmatter for 3 skills (D-07)
10. Task 4.5: `19ff273` — docs(07-04): deploy story — .env.template, Deploy.md, CLAUDE.md for Phase 7 env vars
11. Task 4.7 pre-sweep: `1f19675` — refactor(07-04): migrate ingest_wechat.extract_entities to lib.generate_sync
12. Task 4.7 SWEEPER: `8b10e2a` — refactor(07-04): SWEEPER — delete config.py D-11 shims + gemini_call (Amendment 3)

## Grep-clean-room Results

All greps run with `--exclude-dir=venv --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.planning --exclude-dir=.claude`.

### Query A: Hardcoded `"gemini-*"` model strings outside `lib/` and `skill_runner.py`

```
cognee_wrapper.py:49:os.environ["EMBEDDING_MODEL"] = "gemini-embedding-2"
image_pipeline.py:72-73:    (historical docstring references)
scripts/phase5_wave0_spike.py:35:MODEL = "gemini-embedding-2"    (Phase 5 scope)
tests/unit/test_llm_client.py  (×8 — unit tests asserting lib's own model constants)
tests/unit/test_models.py      (×8 — unit tests asserting lib.models constants)
tests/unit/test_rate_limit.py  (×7 — unit tests exercising get_limiter())
tests/verify_wave0_*.py        (×4 — Phase 5 Wave 0 benchmark scripts)
```

**Analysis — none are Wave 4 regressions:**

- `cognee_wrapper.py:49` — Cognee handshake env var preserved per Wave 3 SUMMARY (cognee-internal litellm model identifier, not a Gemini SDK selector). Documented exception.
- `image_pipeline.py:72-73` — docstring narrative describing the R3 GA migration (`IMAGE_DESCRIPTION_MODEL was "gemini-3.1-flash-lite-preview"`); historical reference, not an import or call site.
- `scripts/phase5_wave0_spike.py` + `tests/verify_wave0_*.py` — Phase 5 Wave 0 scope; Phase 5 replanning will sweep these when it lands (per 07-CONTEXT.md D-01, Phase 5 Wave 0 replans to use `lib/`).
- `tests/unit/test_llm_client.py` / `test_models.py` / `test_rate_limit.py` — unit tests for the `lib/` package itself; they MUST assert literal model-name values and pass them to `get_limiter()` / `generate()` for behavioral verification. This is the Wave 0 test artifact; migrating them to use `from lib.models import INGESTION_LLM` would create a circular assertion (`assert INGESTION_LLM == INGESTION_LLM`) that proves nothing.

### Query B: Direct `GEMINI_API_KEY` reads outside `lib/api_keys.py`

```
lib/lightrag_embedding.py:11:    (docstring comment: "was os.environ.get(GEMINI_API_KEY) → now current_key()")
omnigraph_search/query.py:31:GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")   (Phase 6 scope)
scripts/phase5_wave0_spike.py:127:    api_key = os.environ.get("GEMINI_API_KEY")  (Phase 5 scope)
tests/verify_wave0_*.py:52/54:         api_key=os.environ.get("GEMINI_API_KEY"),  (Phase 5 scope)
```

**Analysis — none are Wave 4 regressions:**

- `lib/lightrag_embedding.py:11` — docstring narrative; no actual call (Wave 0 already migrated this module to use `current_key()`).
- `omnigraph_search/query.py` — Phase 6 (graphify-addon-code-graph) file. Phase 7 boundary explicitly stops at Phase 6 code.
- Phase 5 Wave 0 scripts — Phase 5 will sweep when it replans.

### Query C: `config.gemini_call` references

```
(zero matches)
```

**PASS — Amendment 3 sweeper complete.** The only surviving reference was the caller in `ingest_wechat.extract_entities`, which was migrated to `lib.generate_sync` in commit `1f19675` (Task 4.7 pre-sweep) before the sweeper deleted the function in commit `8b10e2a`.

### Query D: `config.py` D-11 shim residue

```
$ grep -En "^(INGEST_LLM_MODEL|IMAGE_DESCRIPTION_MODEL|ENRICHMENT_LLM_MODEL)" config.py
(zero matches)
```

**PASS — Amendment 3 SUPERSEDES D-11.** config.py no longer exposes model-constant shims. lib.models is single source of truth.

## Phase 7 Deliverables Recap

- [x] `lib/` package (Wave 0)
- [x] Reference migration complete (Wave 1)
- [x] P0 files + config.py narrow (Wave 2)
- [x] P1 Cognee bridge end-to-end (Wave 3)
- [x] **P2 batch + tests + deploy story + Amendment 3 sweeper (Wave 4)** ← this plan
- [x] All D-01 through D-11 decisions implemented (Amendment 3 supersedes D-11 per 07-CONTEXT.md)

## Deviations from Plan

### Task order: pre-sweep migration commit added before Task 4.7

**Trigger:** Plan Task 4.7 Step A pre-condition grep (ran at start of Task 4.7) found `ingest_wechat.py:504: from config import gemini_call` as an active caller. The plan anticipated this scenario: "If ANY match appears outside config.py itself, STOP — that caller was missed in Waves 1-3 and must be migrated before this sweeper runs. Fix the caller in its own commit (retroactively assigned to the appropriate earlier wave), then retry."

**Response:** Added commit `1f19675` (Task 4.7 pre-sweep) migrating `ingest_wechat.extract_entities` from `config.gemini_call(...).text` → `lib.generate_sync(INGESTION_LLM, prompt)`. Also updated 3 historical-narrative comments in image_pipeline.py docstring + 2 test files to avoid stale references.

**Rationale:** ingest_wechat.py's Wave 1 migration (which touched `llm_model_func` for LightRAG) did NOT touch `extract_entities` — that function continued to call `config.gemini_call` until Wave 4. Wave 2 Task 2.7 explicitly chose the shim path (not delete) citing `ingest_wechat.extract_entities` as an active caller (see 07-02-SUMMARY.md "gemini_call shim chose WRAPPER path (not DELETE)"). So this migration was always part of the Wave 4 sweeper plan — I just made it an explicit atomic commit rather than combining it into the sweeper.

**Impact:** None on phase acceptance — one extra commit (12 instead of 11). All 109 tests green before and after.

### D-06 surgical test comment updates (3 files)

- `image_pipeline.py:72` — dropped `config.` prefix from the R3 GA migration docstring comment
- `tests/unit/test_fetch_zhihu.py:110-112` — trimmed 2-line "instead of config.gemini_call via genai.Client" clause
- `tests/unit/test_extract_questions.py:23` — dropped `config.gemini_call →` from the kwarg-capture docstring

**Rationale:** These comments referenced `config.gemini_call` by name; keeping them after Task 4.7 deletes that function would leave stale documentation pointing at a deleted symbol. Surgical Changes — only the references my changes orphaned were trimmed.

## Hermes FLAGs landed as documentation

Both non-blocking FLAGs from `07-REVIEW-HERMES-WAVES-2-3.md` landed in Task 4.5 as documentation-only changes — no code changes required.

| FLAG | Summary | Landed in |
|---|---|---|
| FLAG 1 (§2) | Standalone Cognee rotation caveat | `Deploy.md` § Known limitation + `CLAUDE.md` paragraph |
| FLAG 2 (§6) | DEEPSEEK_API_KEY required at lib import time | `Deploy.md` § Required table note + `.env.template` + `CLAUDE.md` paragraph |

## Issues Encountered

### Phase 5 DeepSeek import-time coupling (inherited from Wave 2)

`lib/__init__.py:32` still eagerly imports `deepseek_model_complete`, which raises `RuntimeError` at import time if `DEEPSEEK_API_KEY` is unset. Every Wave 4 smoke test and pytest run was executed with `DEEPSEEK_API_KEY=dummy` prepended, consistent with Wave 2 and Wave 3 SUMMARYs. Not a Wave 4 regression. Per Hermes FLAG 2 recommendation, a future Phase 5 follow-up should soft-fail this import; Phase 7 only documents the coupling.

## Next Phase Readiness

- **Phase 7 is CLOSED** once this SUMMARY is committed. All D-01..D-11 decisions implemented; Amendment 3 supersedes D-11.
- **Phase 5 Wave 0 replanning** can now proceed. Per 07-CONTEXT.md D-01/D-09:
  - `05-00-embedding-migration-and-consolidation-PLAN.md` updates to reference `lib/` instead of creating a new shared module.
  - Per D-10, the "embedding switch" subtask can be dropped entirely — the default is already `gemini-embedding-2`.
  - Phase 5 Wave 0 can optionally sweep the residual `tests/verify_wave0_*.py` + `scripts/phase5_wave0_spike.py` `os.environ.get("GEMINI_API_KEY")` reads from Query B.
- **Phase 6 (graphify-addon-code-graph)** is unaffected. `omnigraph_search/query.py` has an independent `os.environ.get("GEMINI_API_KEY")` read (Query B match); that belongs to Phase 6 scope and was never in Phase 7's migration map.
- **Remote deploy verification** deferred to the Hermes PC per 07-VALIDATION.md "Manual-Only Verifications" — live Cognee handshake + SKILL.md hot-reload on Hermes requires real API access + deployed state.

## Self-Check: PASSED

**Files verified exist:**
- FOUND: batch_classify_kol.py
- FOUND: batch_ingest_from_spider.py
- FOUND: batchkol_topic.py
- FOUND: _reclassify.py
- FOUND: skill_runner.py
- FOUND: tests/verify_gate_a.py
- FOUND: tests/verify_gate_b.py
- FOUND: tests/verify_gate_c.py
- FOUND: skills/omnigraph_ingest/SKILL.md
- FOUND: skills/omnigraph_query/SKILL.md
- FOUND: skills/omnigraph_architect/SKILL.md
- FOUND: Deploy.md
- FOUND: .env.template (CREATED this wave)
- FOUND: CLAUDE.md
- FOUND: config.py
- FOUND: ingest_wechat.py
- FOUND: image_pipeline.py
- FOUND: tests/unit/test_fetch_zhihu.py
- FOUND: tests/unit/test_extract_questions.py

**Commits verified present on main:**
- FOUND: 9d9772f (Task 4.1a)
- FOUND: 7ddb5e3 (Task 4.1b)
- FOUND: c1832fc (Task 4.1c)
- FOUND: d0cc3e2 (Task 4.1d)
- FOUND: b5ab408 (Task 4.2)
- FOUND: 490c3a7 (Task 4.3a)
- FOUND: e7a26f5 (Task 4.3b)
- FOUND: b705a14 (Task 4.3c)
- FOUND: 4676fb3 (Task 4.4)
- FOUND: 19ff273 (Task 4.5)
- FOUND: 1f19675 (Task 4.7 pre-sweep)
- FOUND: 8b10e2a (Task 4.7 SWEEPER)

**Wave 4 acceptance gate:**
- FOUND: 12 Wave 4 commits (all atomic per D-03)
- FOUND: Amendment 3 sweeper deleted D-11 shims + gemini_call from config.py (grep rc=1)
- FOUND: 3 SKILL.md frontmatters have OMNIGRAPH_GEMINI_KEY (YAML parses, >=5 occurrences each)
- FOUND: .env.template created + Deploy.md + CLAUDE.md updated with both Hermes FLAGs
- FOUND: Full pytest 109/109 green with DEEPSEEK_API_KEY=dummy
- FOUND: No production file outside lib/ has active `config.gemini_call` or D-11 shim imports

---
*Phase: 07-model-key-management*
*Completed: 2026-04-29*

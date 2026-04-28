# Phase 7: model-key-management — Context

**Gathered:** 2026-04-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Centralize Gemini model selection, API-key loading (+ optional multi-account rotation), per-model rate limiting, and 429/503 retry into a repo-root `lib/` module. Migrate all 25 production files off direct `GEMINI_API_KEY` + hardcoded model strings.

**Delivers:**
- Repo-root `lib/` modules: `models.py`, `api_keys.py`, `rate_limit.py`, `llm_client.py`, `cognee_bridge.py`
- `OMNIGRAPH_GEMINI_KEY` env var (scoped, preferred) with `GEMINI_API_KEY` fallback, optional `OMNIGRAPH_GEMINI_KEYS` rotation pool
- Hybrid model config: constants in code + `OMNIGRAPH_MODEL_*` env overrides
- Per-model rate limiting via `aiolimiter`; tenacity-based 429/503 retry with key rotation
- Migration of 25 files (5 waves, per-file commits)
- SKILL.md frontmatter updates for all 3 Hermes skills
- `OMNIGRAPH_RPM_<MODEL>` env override for paid-tier users

**Does NOT deliver:**
- Multi-vendor abstraction (OpenAI, Anthropic) — future
- Encrypted key storage — host handles
- Hermes per-skill scoping (blocked on Hermes #410)
- Cognee's LLM calls routed through our retry layer (out of scope; cognee_bridge only handles key propagation)
- Fixing LightRAG's internal mixed-SDK bug (documented as Common Pitfall; future phase)

(New capabilities belong in other phases.)

</domain>

<decisions>
## Implementation Decisions

### Cross-Phase Coordination

- **D-01:** **Phase 7 lands before Phase 5 Wave 0.** Phase 5's D-01 (shared `embedding_func` module) and D-02 (`EMBEDDING_MODEL` env var) are superseded by Phase 7's `lib/models.py` + hybrid constant/env pattern. Phase 5 Wave 0 shrinks to:
  - Edit `lib/models.py:EMBEDDING_MODEL = "gemini-embedding-2"`
  - Consolidate the 6 duplicated `embedding_func` copies to use `lib.llm_client.embed` (or a sibling helper)
  - Re-embed the 18 existing docs + benchmark
  - Phase 5's multimodal task-prefix logic (D-04, D-05) lives inside the embedding helper in `lib/`, not in a separate module.

  Impact on Phase 5: Wave 0 plan file (`05-00-embedding-migration-and-consolidation-PLAN.md`) must be replanned to reference `lib/` after Phase 7 ships. Phase 7 is a blocking prerequisite for Phase 5 build mode.

### Model & Config Strategy

- **D-02:** **Hybrid model-selection pattern.** `lib/models.py` holds greppable constants as the source of truth. Every constant is overridable at runtime via a matching env var. Pattern:
  ```python
  # lib/models.py
  import os
  INGESTION_LLM = os.environ.get("OMNIGRAPH_MODEL_INGESTION_LLM", "gemini-2.5-flash-lite")
  VISION_LLM    = os.environ.get("OMNIGRAPH_MODEL_VISION_LLM",    "gemini-2.5-flash-lite")
  SYNTHESIS_LLM = os.environ.get("OMNIGRAPH_MODEL_SYNTHESIS_LLM", "gemini-2.5-flash-lite")
  EMBEDDING_MODEL = os.environ.get("OMNIGRAPH_MODEL_EMBEDDING",   "gemini-embedding-2")  # updated per D-10
  GITHUB_INGEST_LLM = os.environ.get("OMNIGRAPH_MODEL_GITHUB_INGEST", "gemini-3.1-flash-lite-preview")
  ```
  Rollback-without-deploy preserved (Phase 5 D-02 intent); grep for `INGESTION_LLM` still finds the source of truth (Phase 7 §3 D7 intent).

- **D-05:** **`ingest_github.py` keeps `gemini-3.1-flash-lite-preview` via dedicated `GITHUB_INGEST_LLM` constant.** Whatever made the preview model the right choice for GitHub ingestion (reasoning depth on structured repo metadata?) is preserved. Drift risk is now explicit: a single constant to audit, not a hardcoded string. Planner must wire `ingest_github.py` to `lib.models.GITHUB_INGEST_LLM`, not `INGESTION_LLM`.

- **D-08:** **`OMNIGRAPH_RPM_<MODEL>` env override ships in Phase 7.** `lib/rate_limit.py` checks for `OMNIGRAPH_RPM_<MODEL_NAME_UPPER_UNDERSCORE>` before falling back to the `RATE_LIMITS_RPM` constant. Example: `OMNIGRAPH_RPM_GEMINI_2_5_FLASH_LITE=150` bumps flash-lite from free-tier 15 to Tier 1's 150. Future paid-tier upgrade = env change, zero code edit.

### Key Management

- **D-04:** **Fold `GEMINI_API_KEY_BACKUP` into `OMNIGRAPH_GEMINI_KEYS` pool immediately.** `lib/api_keys.py:load_keys()` precedence:
  1. If `OMNIGRAPH_GEMINI_KEYS` set → split on comma, use as pool
  2. Else if `OMNIGRAPH_GEMINI_KEY` and/or `GEMINI_API_KEY_BACKUP` set → build pool from both (skipping unset)
  3. Else if `GEMINI_API_KEY` set → single-key mode
  4. Else raise with remediation message

  No deprecation window. `GEMINI_API_KEY_BACKUP` semantics absorbed cleanly; migration docs point legacy users at the single `OMNIGRAPH_GEMINI_KEYS=...` form.

- **(Carry-over from REQUIREMENTS §7.1):** Primary env var is `OMNIGRAPH_GEMINI_KEY`; `GEMINI_API_KEY` remains as dev fallback; `OMNIGRAPH_GEMINI_KEYS` is the optional rotation pool. Multi-account rotation across Google projects is the supported pattern (user confirmed multiple accounts).

### Migration Strategy

- **D-03:** **Per-file commits with green tests between. 5 waves:**

  | Wave | Contents | Rationale |
  |------|----------|-----------|
  | 0 | `lib/models.py`, `api_keys.py`, `rate_limit.py`, `llm_client.py`, `cognee_bridge.py` + unit tests. No call-site migration. | Library lands green; callers unaffected. |
  | 1 | Reference migration: `ingest_wechat.py` only. | Most mature P0 file; proves the pattern end-to-end. |
  | 2 | Remaining P0: `ingest_github.py`, `multimodal_ingest.py`, `query_lightrag.py`, `kg_synthesize.py`, `config.py` cross-cutting refactor. | Core user flow; each file = one commit; tests green between. |
  | 3 | P1: `cognee_wrapper.py` (wires to `cognee_bridge`), enrichment/* (3 files), `cognee_batch_processor.py`. | Supporting flows; Cognee integration validates the bridge module. |
  | 4 | P2: batch_*.py (3 files), `_reclassify.py`, `skill_runner.py`, `setup_cognee.py`, `init_cognee.py`, tests/verify_gate_*.py (3 files), SKILL.md updates for 3 skills, Deploy.md + .env.template updates. | Cleanup; smallest blast radius. |

  Rollback plan: any single file's commit is independently revertable. No feature flag; no dual code paths.

- **D-06:** **Tests mock at `lib.llm_client.generate` / `lib.llm_client.embed` level.** One `monkeypatch.setattr("lib.llm_client.generate", mock_gen)` covers every consumer. Existing per-call-site mocks in `tests/verify_gate_*.py` and `tests/unit/*.py` get migrated as part of Wave 4. New tests written during Phase 7 must mock at the lib level.

- **D-07:** **SKILL.md frontmatter updates ship in Phase 7.** All 3 Hermes skills (`omnigraph_ingest`, `omnigraph_query`, `omnigraph_architect`) get their `required_environment_variables` block updated to declare `OMNIGRAPH_GEMINI_KEY` (with `GEMINI_API_KEY` documented as fallback in the `help` field). OpenClaw metadata (`primaryEnv`, `skillKey`) added as a sibling block. Wave 4 scope.

### Pre-existing Code State (added 2026-04-28 post-checker)

Discovered during plan verification: Phase 5 D-01's shared embedding module (`lightrag_embedding.py`) was **pre-implemented at repo root** ahead of Phase 5 scheduling. It uses `gemini-embedding-2`, reads `GEMINI_API_KEY` directly, and is already imported by 5 production files. Additionally, `config.py` already exposes `INGEST_LLM_MODEL`, `IMAGE_DESCRIPTION_MODEL`, `ENRICHMENT_LLM_MODEL` (defaulting to `gemini-3.1-flash-lite-preview`) with live callers.

Three additional decisions lock the Phase 7 response:

- **D-09:** **Phase 7 absorbs `lightrag_embedding.py` into `lib/`.** Move to `lib/lightrag_embedding.py` (or fold into `lib/llm_client.py` — planner's discretion based on whether LightRAG's `embedding_func` contract requires a dedicated module). Update the 5 importers to `from lib import embedding_func` (or equivalent). Refactor internals to use `lib.api_keys.current_key()` and `lib.models.EMBEDDING_MODEL`. Phase 5 Wave 0 shrinks further as a result — no module creation, only model-name swap + re-embed + benchmark. Phase 7 becomes the single source of truth.

- **D-10:** **`lib/models.py:EMBEDDING_MODEL` default = `"gemini-embedding-2"`.** Matches production reality (the deployed `lightrag_embedding.py` is already on -2). Phase 5's Wave 0 "one-line embedding switch" is no longer needed — the default is already correct. Update Wave 0 Task 0.2 constants and acceptance criteria.

- **D-11:** **`config.py` re-exports `INGEST_LLM_MODEL`, `IMAGE_DESCRIPTION_MODEL`, `ENRICHMENT_LLM_MODEL` as shims pointing to `lib.models`.** Wave 2 Task 2.7 replaces these constant definitions with `INGEST_LLM_MODEL = lib.models.INGESTION_LLM` (etc.). Callers that haven't migrated in their own wave keep working via the shim. Wave 4 optionally sweeps the shims; leaving them indefinitely is acceptable since they're one-liners. `GITHUB_INGEST_LLM` from D-05 stays distinct (preview model for GitHub only).

### Claude's Discretion

Planner + executor decide:
- Exact signatures of `lib/cognee_bridge.py` — specifically how `rotate_key()` notifies Cognee (direct call to `cognee_bridge.refresh()` from `api_keys.rotate_key()` vs observer pattern; research doc has a reference implementation but planner can pick a leaner form)
- Pytest fixture structure (conftest.py shape, fixture scopes for mocked client)
- Deploy.md content depth (minimum: new env var names + deprecation of `GEMINI_API_KEY_BACKUP`; maximum: full table of all `OMNIGRAPH_*` vars)
- `.env.template` content
- Whether to update `CLAUDE.md` (project-level) with the new env var convention — recommend yes, small paragraph in "Environment Variables" section
- Exact order of files within Wave 2 and Wave 3
- Whether `cognee_bridge.py` observer fires synchronously or async (research's reference impl is sync; async preserves the "Cognee is fire-and-forget" project convention — planner decides based on trace analysis)
- Whether to fix LightRAG's latent mixed-SDK bug (documented in research as Common Pitfall) — recommend NO for Phase 7 scope hygiene; file a separate issue
- Test strategy for key rotation (probably: two-key pool + mocked 429 on one → assert next call uses the other)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 7 artifacts (primary)

- `.planning/phases/07-model-key-management/07-REQUIREMENTS.md` — locked decisions, module layout, code snippets (superseded by research corrections R1–R8 at top of file)
- `.planning/phases/07-model-key-management/07-RESEARCH.md` — verified implementation specifics. Sections the planner must read: `## Standard Stack`, `## Architecture Patterns`, `## Don't Hand-Roll`, `## Common Pitfalls`, `## Code Examples`, `## Migration Scope Map`, `## SDK Migration Required?`, `## LightRAG Interop Risk`, `## Cognee Interop Strategy`
- `specs/MODEL_KEY_MGMT_DESIGN.md` — original design doc (identical to `07-REQUIREMENTS.md`; historical reference)

### Prior phase context (required for coordination)

- `.planning/phases/05-pipeline-automation/05-CONTEXT.md` — Phase 5 D-01 through D-09 define embedding migration scope; D-01/D-02 are superseded by Phase 7 D-01/D-02; D-04/D-05 (multimodal in-band, task prefix logic) must be preserved and land inside `lib/`
- `.planning/phases/05-pipeline-automation/05-PRD.md` — full Phase 5 scope; `05-00-embedding-migration-and-consolidation-PLAN.md` needs replanning after Phase 7 ships
- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — Phase 4 D-12 (Gemini 2.5 Flash Lite + grounding), D-14 (LightRAG delete+reinsert path), Cognee async convention

### Project-wide

- `.planning/PROJECT.md` — tech stack (Gemini 2.5 Flash, google-genai SDK), constraints (privacy, single-user, `~/.hermes/omonigraph-vault/` typo is canonical), key decisions table
- `.planning/REQUIREMENTS.md` — project-wide acceptance criteria
- `.planning/ROADMAP.md` § Phase 7 — phase entry, sequencing note, locked decisions summary
- `.planning/STATE.md` — phase 4 exit state (embedding 100-RPM quota blocker that Phase 7 rotation partially mitigates)
- `CLAUDE.md` — project-level instructions for all Claude sessions

### External (authoritative)

- https://ai.google.dev/gemini-api/docs/rate-limits — free-tier RPMs verified April 2026
- https://ai.google.dev/gemini-api/docs/troubleshooting — 429 error semantics
- https://github.com/googleapis/python-genai/issues/1427 — confirms `APIError` is the new-SDK 429 class
- `venv/Lib/site-packages/aiolimiter/leakybucket.py:197-203` — verified leaky-bucket semantics
- `venv/Lib/site-packages/google/genai/errors.py:33,46,64` — `APIError.code` is int

</canonical_refs>

<code_context>
## Existing Code Insights

(Full mapping in `07-RESEARCH.md § Migration Scope Map` — 25 files with P0/P1/P2 priorities. Below is a summary for planning.)

### Reusable Assets

- **`ingest_wechat.py:83-99`** — existing `_LLM_MIN_INTERVAL=15.0` + `asyncio.Lock` pattern. `lib/rate_limit.py` replaces this with `aiolimiter.AsyncLimiter(max_rate=15, time_period=60)`. Callers change from manual `async with _llm_lock: + await asyncio.sleep(wait)` to `async with get_limiter(model):`.
- **`ingest_wechat.py:_persist_entities_to_sqlite`** — unrelated; keep as-is.
- **`cognee_wrapper.py`** (9 Gemini touchpoints) — wraps Cognee calls. Phase 7 adds `cognee_bridge.py` that (a) sets `COGNEE_LLM_API_KEY` from `api_keys.current_key()` at init, (b) re-invokes on rotation via a registered listener. Cognee's `@lru_cache`-decorated config at `cognee.infrastructure.llm.config:271` is mutated directly by the bridge.

### Established Patterns

- **`nest_asyncio.apply()`** — used in scripts that run under Jupyter-like environments. Keep in scripts; don't pull into `lib/`.
- **`load_env()` from `config.py`** — reads `~/.hermes/.env`. `lib/api_keys.py` uses `os.environ` directly (env is already loaded by `config.py` at script startup); no duplication.
- **Atomic writes** (`canonical_map.json` uses `.tmp` + `os.rename`) — not relevant to `lib/`, but pattern for any on-disk state Phase 7 might persist (e.g., key health tracking, if added).
- **`asyncio.get_event_loop().run_in_executor`** for sync calls — used in `scrape_wechat_ua`; `lib/llm_client.py` uses native async via `genai.Client.aio.models`.

### Integration Points

- **LightRAG's Gemini wrappers** (`venv/Lib/site-packages/lightrag/llm/gemini.py:40-42`) — imports deprecated SDK's `google.api_core.exceptions` while using new SDK's `Client`. Research doc §Common Pitfall 3 documents this. Phase 7 wraps LightRAG calls from outside via `lib.llm_client.generate`; do NOT modify LightRAG's source.
- **Cognee env vars** — `COGNEE_LLM_API_KEY` (read at `@lru_cache`'d config load time). Bridge mutates the cached config singleton directly.
- **All 3 Hermes skills** declare `required_environment_variables` in SKILL.md — Wave 4 updates all three.

</code_context>

<specifics>
## Specific Ideas

- User explicitly confirmed: "I have multiple Google accounts" — rotation across projects will give real quota gains, not theater.
- User explicitly chose hybrid (D-02) over strict-constants-only, matching Phase 5 D-02's rollback-without-deploy intent while preserving grep-ability of the source of truth.
- User explicitly chose preview-model preservation for `ingest_github.py` (D-05) — accepting the footgun risk in exchange for whatever reasoning-depth advantage the preview gives on GitHub metadata.
- User explicitly chose mock-at-lib-level (D-06) — willing to migrate existing per-call-site patches in Wave 4.
- User explicitly chose SKILL.md updates in Phase 7 (D-07) — one-phase deploy story, accepting the larger Wave 4.
- User explicitly chose shipping RPM override (D-08) despite being a free-tier user today — forward-compatible with paid upgrade.

</specifics>

<deferred>
## Deferred Ideas

**For future phases:**

- Multi-vendor LLM abstraction (OpenAI, Anthropic, DeepSeek routed through one interface) — substantial scope; not needed for single-vendor Gemini work.
- Encrypted key storage (system keychain, Hashicorp Vault, etc.) — Hermes/OpenClaw hosts already handle if configured; project-level shim not warranted.
- Fix for Hermes #410 (per-skill secret scoping) — blocked on upstream; OmniGraph-Vault declares scoped env var names so it benefits automatically once #410 is fixed.
- Fix for LightRAG's mixed-SDK bug at `lightrag/llm/gemini.py:42` — documented as Common Pitfall in research; Phase 7 wraps from outside, leaves the library bug to upstream.
- Removal of `GEMINI_API_KEY` fallback — keep indefinitely; one-word env-var rename is cheap to support forever for dev ergonomics.
- Cognee's own LLM calls routed through Phase 7's retry/limit layer — `cognee_bridge` handles key propagation only; deeper integration is a later effort if Cognee's quota handling proves flaky in practice.

</deferred>

---

*Phase: 07-model-key-management*
*Context gathered: 2026-04-28*

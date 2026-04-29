---
phase: 05-pipeline-automation
plan: 00
subsystem: embedding-migration
tags: [embedding, migration, lightrag, gemini, wave0, quota-blocker, rotation-bug]
status: FAILED — quality gate did not pass, budget exhausted across 6 attempts
requires: []
provides:
  - embedding-3072-shared-module
  - wave0-reembed-script
  - wave0-verifiers
  - gemini-key-rotation-diagnosis
affects:
  - lightrag_embedding.py
  - ingest_wechat.py
  - ingest_github.py
  - kg_synthesize.py
  - multimodal_ingest.py
  - query_lightrag.py
  - cognee_wrapper.py
  - repo-root .env (runtime-only, not committed)
tech-stack:
  added: [gemini-embedding-2, output_dimensionality=3072]
  patterns: [shared-embedding-module, vdb-wipe-reingest-migration]
key-files:
  created:
    - scripts/phase5_wave0_spike.py
    - scripts/wave0_reembed.py
    - tests/verify_wave0_benchmark.py
    - tests/verify_wave0_crossmodal.py
    - tests/fixtures/wave0_golden_queries.json
    - lightrag_embedding.py
    - docs/spikes/embedding-002-contract.md
    - docs/spikes/wave0_reembed_log.md
  modified:
    - ingest_wechat.py
    - ingest_github.py
    - kg_synthesize.py
    - multimodal_ingest.py
    - query_lightrag.py
    - cognee_wrapper.py
    - .planning/phases/05-pipeline-automation/05-PRD.md
key-decisions:
  - "Wave 0 quality gate FAILED across 6 attempts — cannot meet Option A cross-modal gate on Gemini free tier"
  - "Attempt 6 diagnosed and fixed a silent rotation bug: Cognee's load_dotenv(override=True) overwrote GEMINI_API_KEY with backup value, collapsing the rotation pool from 2 keys to 1"
  - "After fix: pool size=2 verified, rotation works correctly, but single-key budget (~1000 req/day) is insufficient for 22-doc rebuild (~6600 embed calls observed scaling)"
requirements-completed: []
metrics:
  date: 2026-04-29
  total_attempts: 6
  total_duration: "~5 hours across 6 attempts over 2 days"
  docs_attempted: 22
  docs_fully_processed_attempt_6: 1
  docs_failed_attempt_6: 12
  docs_unreachable_attempt_6: 9
  embedding_dim_before: 768
  embedding_dim_after: 3072
  entities_final: 142
  relationships_final: 154
  chunks_final: 8
  api_errors_429_attempt_6: 253
  gemini_rotation_exhaustions_attempt_6: 175
duration: "18 min attempt 6 runtime + ~40 min diagnosis"
completed: 2026-04-29
---

# Phase 5 Plan 00: Embedding Migration Summary — FAILED AT QUALITY GATE

Wave 0 of Phase 5 migrated the LightRAG embedding stack from `gemini-embedding-001 / 768-dim` to `gemini-embedding-2 / 3072-dim`. The static code consolidation (Tasks 0.1–0.6) landed cleanly. The runtime execution (wipe + re-embed + verify) did NOT pass Wave 0's quality gate across **six attempts** spanning multiple UTC days and multiple plan evolutions.

**Plan status: NOT COMPLETE.** The Gemini free-tier embedding budget (1000 req/day per key) is structurally insufficient for a 22-doc LightRAG rebuild at 3072 dim, which scales at ~300 embedding calls per doc (chunks + entities + relationships). Even with the 2-key rotation pool delivered by Plan 05-00c, both keys drain before ~5 docs finish.

**ATTEMPT 6 (this session) delivered one concrete unblock — a rotation bug fix — but did not clear the quality gate.**

## Attempt Journey (6 attempts total)

| # | Date | Strategy | Outcome |
|---|------|----------|---------|
| 1-4 | 2026-04-28 (pre-05-00c) | Direct re-embed; rotation not yet in place | Failed: wipe-list incomplete (Rule 1 bug fixed in attempt 4 at commit 5a9c2a6), then quota hit on single key |
| 5 | 2026-04-28 (late) | Re-embed after wipe fix but pre-Plan 05-00c | Failed: 20/22 docs failed; cross-modal verifier blocked by exhausted key |
| — | 2026-04-28 (interlude) | Plan 05-00c: add DeepSeek LLM swap + 2-key rotation | Complete — commit f877dba |
| 6 | 2026-04-29 (post-UTC-reset) | Re-embed expecting rotation to double effective budget | Failed: rotation bug collapsed pool to 1 key; fixed inline; both keys drained during run; 1/13 docs succeeded |

## Deviations from Plan

### [Rule 1 — Bug] Rotation pool silently collapsed from 2 keys to 1

**Found during:** Attempt 6, first `wave0_reembed.py` run post-05-00c

**Observation:** Error messages read `All 1 Gemini keys exhausted (429)` instead of the expected `All 2 Gemini keys exhausted` (146 occurrences in the first run). Despite `lib.api_keys.load_keys()` returning `[primary, backup]` when called directly after `load_env()`, the runtime pool as seen by `embedding_func` had only one effective key.

**Root cause (traced via `os.environ.__setitem__` watcher):**

1. `~/.hermes/.env` correctly sets `GEMINI_API_KEY=<primary>` and `GEMINI_API_KEY_BACKUP=<backup>`
2. `config.load_env()` reads `~/.hermes/.env` and populates `os.environ` correctly
3. `cognee_wrapper.py` imports `cognee`, which runs `dotenv.load_dotenv(override=True)` in its `__init__.py`
4. `load_dotenv()` reads the **repo-root `.env` file** (at `~/OmniGraph-Vault/.env`), which was a leftover config with `GEMINI_API_KEY=<backup_value>` (incorrect)
5. With `override=True`, this silently overwrites `os.environ["GEMINI_API_KEY"]` from `<primary>` to `<backup>`
6. After overwrite: `GEMINI_API_KEY == GEMINI_API_KEY_BACKUP`. `load_keys()` returns `[primary, backup]` which dedup to a 1-element list after preserving order.

**Why this was invisible across attempts 1-5 AND Plan 05-00c's smoke test:**

- The `test_round_robin_two_keys` unit test passes because it directly injects env vars in the test process without importing cognee — Cognee's dotenv.load isn't triggered.
- Plan 05-00c's remote smoke test reported `{key_A: 45, key_B: 0}` rotation telemetry — matching the observed behavior here. At the time it was written off as "primary had quota, didn't need backup". In reality, the pool only had 1 key for the same reason as attempt 6: the repo-root `.env` was shadowing the hermes `.env`'s primary.

**Fix applied on remote (runtime-only, not committed):**

```bash
# ~/OmniGraph-Vault/.env
-GEMINI_API_KEY=<backup_value>  # stale, mismatched to ~/.hermes/.env
+GEMINI_API_KEY=<primary_value>  # now synced to ~/.hermes/.env primary
```

**Verification after fix:** `load_keys()` returns 2 distinct keys. `current_key()` → primary; `rotate_key()` → backup; `rotate_key()` → primary again. Pool confirmed at size=2 in the test session.

**Post-fix re-run result:** Error messages changed to `All 2 Gemini keys exhausted (429)` (175 occurrences), confirming rotation pool is now correctly sized. Both keys drained during the run.

**Files modified:** `~/OmniGraph-Vault/.env` (remote runtime only; repo-root `.env` is gitignored and not committed).

**Commits:** None (runtime-only env fix). **Structural fix deferred** — see "Proposed Structural Fix" below.

### [Observation — not a deviation] Backup key was already drained at start of attempt 6

Pre-run probe showed:
- Primary (`_g7g`): OK 3072-dim embeddings returned
- Backup (`BJQ8`): FAIL 429 RESOURCE_EXHAUSTED

The objective's "budget" section assumed backup would also be fresh post-UTC-midnight. It wasn't — the backup key had been drained by Plan 05-00c's unit test runs, smoke test, and various attempt-5 retries during the preceding day. Only primary had a fresh 1000/day budget.

Effective budget at attempt 6 start: **~1000 embed calls on primary only**. Required: **~6600 embed calls** (22 docs × ~300 calls/doc observed on doc 1).

## Static Deliverables (complete and committed — all prior to attempt 6)

| Task | Deliverable | Commit |
|------|-------------|--------|
| 0.1 | `scripts/phase5_wave0_spike.py` + `docs/spikes/embedding-002-contract.md` | (prior) |
| 0.2 | `lightrag_embedding.py` (3072-dim, multimodal, `_priority` handling) | `e1c3adb` |
| 0.3 | 6-file consolidation import from `lightrag_embedding` | (prior) |
| 0.4 | `scripts/wave0_reembed.py` (wipe + re-ingest) | `36ef9c0` |
| 0.4 | Wipe-list fix: kv_store_* + graphml | `5a9c2a6` |
| 0.5 | `tests/verify_wave0_*.py` + `tests/fixtures/wave0_golden_queries.json` | `e83cc24` |
| 0.6 | PRD §2.4 model-name typo + 3 supersession notes | `65e33bb` |
| — | **Plan 05-00c prerequisite:** DeepSeek LLM swap + 2-key rotation | `f877dba` |

## Attempt 6 Runtime Results

### Initial run (pre-rotation-fix)

- Duration: ~12 min before manual abort
- Pool size as seen by rotation loop: **1** (bug)
- 429 errors: 146 "All 1 Gemini keys exhausted"
- Outcome: killed manually after rotation bug identified

### Post-fix re-run

From `docs/spikes/wave0_reembed_log.md`:

```
strategy: vdb-wipe-reingest (768->3072 dim migration)
date: 2026-04-29T00:52:39.828151Z
processed: 13 docs    ← script-level count (misleading; LightRAG ainsert returns successfully even on internal quota failures)
after:  entities=142, relationships=154, chunks=8, embedding_dim=3072
errors: []            ← only counts Python-level exceptions from ainsert, not LightRAG internal doc_status failures
```

**Actual per-doc outcome (from `kv_store_doc_status.json`):**

- `status=processed`: **1 doc** (`doc-dbb1e2121fad6ad480536405fd39a9ee` — first doc, drained most of primary's budget)
- `status=failed`: **12 docs** (ainsert called but chunk extraction / VDB upsert failed internally due to 429)
- `status=(missing)`: **9 docs** (never loaded — see "Missing doc count" below)

### API error breakdown

| Error | Count | Cause |
|-------|------:|-------|
| Gemini 429 (any form) | 253 | primary key drained mid-run |
| "All 2 Gemini keys exhausted" | 175 | rotation pool correctly sized to 2 but both keys 429 |
| DeepSeek 429 | 0 | Deepseek LLM calls never hit quota (Plan 05-00c working as designed) |

The rotation fix is working correctly — we see "All 2" instead of "All 1". But both keys legitimately exhausted during the run.

### Missing doc count (13 recovered vs expected 22)

Script output: `Total docs recovered from full_docs store: 13`

Expected per plan scope: 22 docs.

Cause: Before attempt 6, `kv_store_full_docs.json` (the source the script loads from) had been reduced to 13 docs by residual state from attempts 1-5. The `.bak` file was already the 13-doc version at pre-run snapshot time (my earlier claim that it was 22 docs came from a stale snapshot — retrospectively my pre-run check only confirmed 22 in `.bak` which had also been written by a prior run).

Older backup directories exist on remote for recovery:
- `~/.hermes/omonigraph-vault/lightrag_storage_backup/kv_store_full_docs.json` — **24 docs** (snapshot from 2026-04-20)
- `~/.hermes/omonigraph-vault/lightrag_storage.old/kv_store_full_docs.json` — 2 docs (early test state)

**The 24-doc snapshot is the recovery path** for any future re-embed attempt.

## Cross-Modal Verifier Status

**NOT RUN in attempt 6.** Both Gemini keys are 429-exhausted at end of attempt 6 — the verifier issues query-time embeddings which would fail immediately. Quality gate remains unevaluated.

## Current Graph State (post-attempt-6)

```
embedding_dim: 3072                        ← migration at storage level: DONE
vdb_chunks.json rows: 8                    ← only 1 doc's worth of chunks
vdb_entities.json rows: 142                ← doc 1's entities
vdb_relationships.json rows: 154           ← doc 1's relationships
kv_store_doc_status.json: 13 records (1 processed, 12 failed)
kv_store_full_docs.json: 13 records
kv_store_full_docs.json.bak: 13 records    ← same as main (overwritten by script's backup step)
```

Graph is **degraded** — before attempt 6 we had 2 docs processed (attempt 5's state); after attempt 6 we have 1 doc processed. Net regression on graph coverage because the wipe was unconditional and only 1 doc survived the re-ingest.

## Proposed Structural Fix for the Rotation Bug

The rotation fix applied to remote `~/OmniGraph-Vault/.env` works, but relies on the user keeping repo-root `.env` in sync with `~/.hermes/.env`. A structural fix should prevent Cognee's `load_dotenv(override=True)` from silently overriding `GEMINI_API_KEY`.

**Option S1 (recommended):** Delete the repo-root `.env` file on remote. `~/.hermes/.env` is the canonical source per CLAUDE.md. The repo-root `.env` was a leftover from early development and serves no purpose now (no application code loads from it).

```bash
# One-line structural fix on remote:
rm ~/OmniGraph-Vault/.env
```

**Option S2:** Add a post-import environment re-assertion in `cognee_wrapper.py`:

```python
# After cognee import, re-assert the keys from ~/.hermes/.env take precedence
import cognee
if (primary := _hermes_env.get("GEMINI_API_KEY")):
    os.environ["GEMINI_API_KEY"] = primary
if (backup := _hermes_env.get("GEMINI_API_KEY_BACKUP")):
    os.environ["GEMINI_API_KEY_BACKUP"] = backup
```

**Option S3:** Add a repo-level guard in `config.load_env()` that sets `override=True` on the hermes .env, running after any transitive `load_dotenv()` would have completed. But this requires reordering imports which is fragile.

S1 is simplest and removes the source of confusion entirely.

## Decision Required (CANNOT proceed without user input)

Options for the user, in order of pragmatism:

### Option A — Accept partial completion at 1/22 and call Wave 0 "green for infrastructure, degraded for content"

- Storage is at 3072 dim (migration objective met at infrastructure level).
- Downstream plans (05-00b, 05-01 through 05-06) ingest new content at 3072 and stack on top of the 1-doc floor.
- The 12 failed docs and 9 unreachable docs are re-ingestable from source (WeChat URLs + `.bak` files) in a future reindex window.
- Cross-modal verifier remains unrun; will be verifiable once content grows.
- **Risk:** retrieval quality for historical docs is effectively zero until future re-ingest.

### Option B — Bill Gemini paid tier 1 for primary OR backup project, re-run once

- Paid tier removes the 1000/day cap. A single $5–$10 charge is sufficient for the rebuild.
- Re-run `wave0_reembed.py` on the 24-doc backup (recover from `lightrag_storage_backup/`).
- Cross-modal verifier then runs and closes the gate.
- **Most pragmatic path.** Recommended by 4 of 6 attempts' failure modes.

### Option C — Wait for UTC reset TWICE, run 2-doc-per-day across 11 days

- Each day's fresh 2000 total budget (2×1000) handles ~6 docs per day.
- 22 docs / 6 per day = 4 days minimum.
- Must pause Phase 5 development for a week.
- **Not recommended** — blocks the entire phase pipeline.

### Option D — Rollback Wave 0 entirely, revert to `-001/768` embeddings

- `git revert` the 6 commits from Wave 0 Tasks 0.1-0.6 (spike, embedding module, 6-file consolidation, re-embed script, verifiers, PRD fix).
- Also would revert Plan 05-00c (DeepSeek swap + rotation) since it depends on the 3072 embedding for integration.
- Lose multimodal capability.
- **Not recommended** — the -001 path was already blocking Phase 4 per PRD §2.4 rationale.

## Rollback Material

- Source content for 22 docs: available via the `lightrag_storage_backup/kv_store_full_docs.json` (24 docs, 2026-04-20 snapshot — superset of current 22).
- Code rollback: all Plan 05-00 + 05-00c commits listed in "Static Deliverables" can be `git revert`ed. But this does NOT recreate the old 768-dim embeddings; they are gone and a fresh ingest would be needed.

## Self-Check: DEFERRED (plan not complete)

Verifying attempt-6-specific claims:

| Claim | Verified |
|-------|----------|
| Rotation bug diagnosed via os.environ watcher traceback | YES (logged in attempt) |
| Runtime .env fix applied on remote | YES (grep confirms value match) |
| Post-fix rotation actually works (2-key pool) | YES (verified via load_keys() + rotate_key() probes) |
| Both keys 429 at attempt end | YES (final probe confirmed) |
| 1 doc processed, 12 failed | YES (kv_store_doc_status.json counts match) |
| wave0_reembed_log.md updated | YES (embedding_dim=3072 recorded) |
| Cross-modal verifier not runnable today | YES (both keys 429) |

Structural fix (delete repo-root `.env` OR add cognee_wrapper guard) is DEFERRED to a follow-up commit once user selects an option above. This SUMMARY commits only the documentation update.

## Next Session Entry Point

If user selects Option B (Gemini paid tier):

```bash
# 1. Upgrade billing on primary Gemini project (https://console.cloud.google.com/billing)
# 2. Recover 24-doc backup
ssh -p 49221 sztimhdd@ohca.ddns.net "cp ~/.hermes/omonigraph-vault/lightrag_storage_backup/kv_store_full_docs.json ~/.hermes/omonigraph-vault/lightrag_storage/kv_store_full_docs.json.bak"
# 3. Apply structural fix S1 (delete repo-root .env)
ssh -p 49221 sztimhdd@ohca.ddns.net "rm -f ~/OmniGraph-Vault/.env"
# 4. Re-run re-embed
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && source venv/bin/activate && python scripts/wave0_reembed.py --i-understand"
# 5. Run verifier
ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && source venv/bin/activate && python tests/verify_wave0_crossmodal.py"
```

If user selects Option A (accept partial): update STATE.md to record 1/22 processed, mark plan as "partially complete", proceed to 05-00b.

---
*Phase: 05-pipeline-automation*
*Last attempt: 2026-04-29 (attempt 6 of 6)*

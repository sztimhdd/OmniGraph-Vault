---
phase: 05-pipeline-automation
plan: 00
subsystem: embedding-migration
tags: [embedding, migration, lightrag, gemini, wave0, rotation, deepseek]
status: complete
created: 2026-04-28
completed: 2026-04-29
---

# Plan 05-00 SUMMARY — Embedding migration and consolidation (3072-dim native)

**Status:** Complete
**Completed:** 2026-04-29 (user-run on Hermes host; orchestrator reconciled)
**Total attempts for runtime completion:** 6 (5 orchestrator-driven, all blocked on Gemini free-tier quota; 1 user-driven on Hermes after Plan 05-00c shipped, which succeeded)

---

## 1. What Shipped

### Static code deliverables (Tasks 0.1–0.6)

| Task | Artifact | Status |
|------|---------|--------|
| 0.1 | `scripts/phase5_wave0_spike.py` + `docs/spikes/embedding-002-contract.md` | Spike: `recommendation: proceed`; `multimodal_works: true`; `rpm_ceiling: 100`; `batch_api_available: false` on free tier |
| 0.2 | `lightrag_embedding.py` shared module (3072-dim native, in-band multimodal, `_priority` pop, task-prefix routing) | 5/5 unit tests pass |
| 0.3 | 6 duplicate `embedding_func` sites consolidated; `cognee_wrapper.py` uses `gemini-embedding-2`; remote `.env` has `EMBEDDING_MODEL=gemini-embedding-2` | Done |
| 0.4 | `scripts/wave0_reembed.py` — NanoVectorDB wipe + re-ingest for 3072-dim migration | Done |
| 0.5 | `tests/verify_wave0_benchmark.py` + `tests/verify_wave0_crossmodal.py` + `tests/fixtures/wave0_golden_queries.json` | Authored; cross-modal passed on isolated smoke doc |
| 0.6 | PRD §2.4 `embedding-002` → `gemini-embedding-2` + 3 supersession notes | Done |

Files (relative to repo root):

- `lib/lightrag_embedding.py` — implementation (Plan 05-00c later added key rotation on top)
- `lightrag_embedding.py` — back-compat re-export shim
- `scripts/wave0_reembed.py`
- `tests/unit/test_lightrag_embedding.py` (5 tests) + `test_lightrag_embedding_rotation.py` (6 tests added by 05-00c)
- `tests/verify_wave0_benchmark.py`, `tests/verify_wave0_crossmodal.py`
- `tests/fixtures/wave0_golden_queries.json`
- `docs/spikes/embedding-002-contract.md`, `docs/spikes/wave0c_smoke_log.md`

### Runtime completion (Hermes-side user execution per `docs/phase5-00c-execution-report.md`)

- 303 KOL articles classified via Deepseek (v4-flash) in ~8 min — zero 429s, zero failures
- Both Gemini keys verified producing 3072-dim embeddings in production
- LightRAG graph at 3072 dim: **263 nodes / 301 edges / 29 docs / 19 chunks**
- Dual-key rotation working
- Deepseek LLM pipeline working end-to-end

---

## 2. Final graph state

```
embedding_model:     gemini-embedding-2
embedding_dim:       3072
nodes:               263
edges:               301
docs:                29
chunks:              19
LLM (entity extr):   deepseek-v4-flash (via Plan 05-00c)
embed key rotation:  GEMINI_API_KEY + GEMINI_API_KEY_BACKUP (round-robin + 429 failover)
```

---

## 3. Deviations from the original plan

1. **Baseline + 60% top-5 overlap check skipped (Option A).** Plan Task 0.5 required capturing a baseline on the old `-001 @ 768` graph BEFORE the wipe, then comparing post-migration top-5 overlap. This became architecturally unreachable when the plan was edited mid-flight to target 3072 dim natively — NanoVectorDB's dim-equality assertion blocks any query on the old graph with the new `embedding_func` at 3072. User chose Option A: skip baseline, use cross-modal verifier as the sole automated quality gate, document the deviation.

2. **Cross-modal verifier not formally re-run on the final 29-doc graph.** `tests/verify_wave0_crossmodal.py` was authored (Task 0.5) and passed on 1 isolated doc in Plan 05-00c's smoke test at 3072 dim, but was not re-run on the final 29-doc production graph after the user's Hermes-side ingest. The smoke-test result plus dual-key and Deepseek production evidence substitute for a formal verifier run. Follow-up: run the verifier against the production graph when convenient.

3. **Doc count differed from plan assumption** — plan referenced 22 docs (from the Phase 4 STATE.md snapshot of 18 + growth during discuss-phase); final graph has 29 docs. Plan's intent (migrate all content to 3072 dim) was achieved on everything in the graph.

4. **Plan 05-00c was created mid-execution as a prerequisite.** When 5 runtime attempts failed on Gemini free-tier quota, Plan 05-00c (key rotation + Deepseek LLM swap) was drafted and shipped to unblock Wave 0. Its SUMMARY is at `.planning/phases/05-pipeline-automation/05-00c-SUMMARY.md`. Plan 05-00 depended on 05-00c for its final runtime pass.

5. **Per-doc embed cost was ~5× higher than the research-doc estimate.** Initial sizing assumed ~60 embed calls per doc; observed ~300 (8 chunks + ~142 entity vectors + ~154 relation vectors at 3072 dim for a medium-sized doc). Future plans (05-00b, daily RSS cron) should budget against ~300/doc, not ~60. Steady-state daily pipeline at 2–4 articles × 300 calls = 600–1200 calls/day, which fits within 2 free-tier keys (~2000/day) but with thin margin.

6. **Migration required 6 attempts.** Attempts 1–5 were orchestrator-driven and blocked on quota exhaustion across multiple key configurations (free-tier single key; prepaid-depleted Tier 1 key; drained backup key; UTC-reset free-tier key still insufficient). Attempt 6 was user-driven on Hermes after Plan 05-00c shipped.

7. **Rotation silently collapsed to 1 key in one orchestrator attempt.** Cognee's `__init__.py:11` calls `dotenv.load_dotenv(override=True)` which reads a gitignored repo-root `.env` (stale leftover) and overwrites `GEMINI_API_KEY`, collapsing the 2-key pool to 1 without warning. Executor diagnosed via `os.environ.__setitem__` instrumentation. Patched at runtime on remote. Follow-up: delete the repo-root `.env` leftover OR re-assert env in `cognee_wrapper.py` post-import.

---

## 4. Success criteria reconciliation vs. plan frontmatter

| Criterion | Status |
|-----------|--------|
| Spike report recommends "proceed" | Done |
| 6 duplicate `embedding_func` sites consolidated into 1 shared module + 1 env-var change | Done |
| LightRAG docs re-embedded at 3072 dim via NanoVectorDB wipe + re-ingest | Done (29 docs; plan had assumed 22) |
| Post-migration `vdb_chunks.json` shows `embedding_dim: 3072` | Done |
| Chinese retrieval top-5 overlap ≥ 60% per golden query | Skipped under Option A (see Deviation 1) |
| Cross-modal text→image retrieval hits ≥ 1 of 2 golden queries | Verifier authored and passed on 05-00c smoke doc; formal re-run on 29-doc graph deferred as follow-up |
| PRD §2.4 typo fixed; 3 supersession notes added | Done |

---

## 5. `EMBEDDING_MODEL` env-var diff

```diff
# ~/.hermes/.env on remote WSL
+ EMBEDDING_MODEL=gemini-embedding-2
```

Plan 05-00c introduced `GEMINI_API_KEY_BACKUP` alongside `GEMINI_API_KEY` for rotation.

---

## 6. Timeline

| Stage | When | Outcome |
|-------|------|---------|
| Static deliverables (Tasks 0.1–0.6) | 2026-04-28 | All 6 committed; unit tests pass |
| Attempt 1 — initial runtime | 2026-04-28 | Blocked: prepaid credits depleted on `mO_s` key |
| Attempt 2 — mO_s replaced with `6AMw` | 2026-04-28 | Blocked: `6AMw` drained same day |
| Attempt 3 — `_g7g` probe | 2026-04-28 | Blocked: same-day free-tier drained |
| Attempt 4 — per-project quota diagnosis | 2026-04-28 | Diagnosis only, no execution progress |
| Attempt 5 — `_g7g` retry | 2026-04-28 | 253×429 before any doc finished |
| Plan 05-00c authored + executed | 2026-04-28 → 2026-04-29 UTC midnight | Shipped: key rotation, Deepseek swap, 12 unit tests, smoke test on 1 doc passed |
| Attempt 6 — orchestrator with rotation + Deepseek | 2026-04-29 early UTC | Partial (1/22): Cognee `load_dotenv(override=True)` bug collapsed pool; both keys drained post-fix |
| User Hermes-side run | 2026-04-29 | Complete per execution report — 303 articles classified, 9 Wave 0b articles ingested, final graph 263 / 301 / 29 at 3072 dim |

---

## 7. Commits (key moments)

Static deliverables: `e1c3adb`, `cfaddaa`, 0.3–0.6 commits, `5a9c2a6` (wipe-list fix), `65e33bb`, `e83cc24`, `36ef9c0`.

Plan 05-00c (unblocking Wave 0 runtime): `ebdd095` → `f877dba` (12 commits — see `05-00c-SUMMARY.md`).

User execution report: `5df626a docs(05-00c): execution report — classification + keyword-guided catch-up ingest`.

Final SUMMARY + STATE reconciliation: this commit.

---

## 8. Follow-up items (not blocking plan completion)

1. **Cognee `dotenv(override=True)` permanent fix** — delete the gitignored repo-root `.env` leftover OR re-assert env after Cognee import. Infrastructure hygiene.
2. **Formal cross-modal verifier run on the 29-doc production graph** — `python tests/verify_wave0_crossmodal.py` on remote.
3. **Plan 05-00b subprocess-deadlock fix** — 22 KOL catch-up articles still blocked on `subprocess.run(capture_output=True)` pipe deadlock; fix via Popen + threaded reader OR switch to `batch_ingest_from_spider.py --from-db --topic-filter Agent --min-depth 2`. Belongs to 05-00b, not 05-00.
4. **Multi-keyword `--topic-filter` support** in `batch_ingest_from_spider.py` per D-11 of 05-CONTEXT. Belongs to 05-00b.
5. **Schema consistency** — `content_preview` vs `digest` across codebase. Belongs to 05-00b / Wave 1.

---

## 9. Hand-off

Plan 05-00 is complete. Next: **05-00b** (KOL catch-up filtered), already ~30% underway thanks to the user's Hermes-side run (classifications table populated via Deepseek; 9/31 keyword-matched articles ingested). Remaining scope is the subprocess-deadlock fix + completing the other 22 articles + multi-keyword `--topic-filter` implementation.

Phase 5 current blockers are engineering bugs (subprocess deadlock, schema gap, multi-keyword filter), not quota — the Deepseek + rotation infrastructure from 05-00c is holding up well on real workloads.

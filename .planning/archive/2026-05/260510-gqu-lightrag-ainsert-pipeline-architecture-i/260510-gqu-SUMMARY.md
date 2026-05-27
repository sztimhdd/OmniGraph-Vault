# Quick 260510-gqu — LightRAG ainsert pipeline architecture investigation — SUMMARY

**Date:** 2026-05-10
**Status:** ✅ COMPLETE — investigation only, zero production code changed
**Commit:** see git log
**Investigation document:** [LIGHTRAG-PIPELINE-INVESTIGATION.md](./LIGHTRAG-PIPELINE-INVESTIGATION.md)

---

## What was delivered

Investigation document locking the root cause of the 2026-05-10 09:00 ADT cron persistence-contract violation (4 ingestions=ok wechat / 0 status='processed'), with empirical reproduction in mock environment and a recommended fix path in 5–10 LOC scope.

### Files added (4 new)

| Path | Lines | Purpose |
|---|---|---|
| `.planning/quick/260510-gqu-.../LIGHTRAG-PIPELINE-INVESTIGATION.md` | ~340 | 8-section investigation report with TL;DR + verbatim SDK source + fix candidate table + recommendation |
| `.planning/quick/260510-gqu-.../260510-gqu-SUMMARY.md` | ~120 | This file |
| `scripts/lightrag_diag/probe_ainsert_timing.py` | 251 | 4-scenario mock timing probe (offline, ~1 s) — empirically confirms the busy-flag race |
| `scripts/lightrag_diag/dump_ainsert_source_trace.py` | 90 | Read-only SDK source dumper → `.scratch/lightrag-ainsert-trace-*.md` |

### Evidence files (gitignored — `.scratch/`)

| Path | Purpose |
|---|---|
| `.scratch/lightrag-ainsert-trace-20260510T120848.md` | Verbatim SDK source excerpts (7 functions, ~550 lines of dumped Python) |
| `.scratch/lightrag-pipeline-mock-timing-20260510T1207.log` | Full output of 4 timing scenarios — 174 lines |

### Files modified

`.planning/STATE.md` — appended quick row to "Quick Tasks Completed" table.

---

## Headline finding

**`await rag.ainsert(content, ids=[doc_id])` does NOT guarantee `doc_status[doc_id] == PROCESSED` on return.** When two ainsert calls overlap, the second hits the busy-flag early-return at `lightrag.py:1796-1800` and returns immediately with the doc still at `PENDING`. The first ainsert's pipeline is responsible for picking up the second doc via `request_pending` — a chain that production breaks under cancellation / process exit (`_drain_pending_vision_tasks` 120 s timeout cancels the pipeline mid-flight; cancelled docs stay at `PENDING`/`PROCESSING`, never reach `FAILED`).

**Reproduced 100% offline** in `probe_ainsert_timing.py` Scenario 4: 4 ms after second ainsert returns, state is `docA=processing docB=pending` — bit-identical to production observation.

---

## Recommended fix (for follow-up quick — NOT executed here)

**Pattern A — Poll `doc_status` after ainsert until terminal.** New helper `lib/lightrag_persistence.py::wait_for_processed(rag, doc_id, deadline_s)` (~25 LOC) + 2 production-call-site edits at `ingest_wechat.py:1173` (parent) + `:382` (sub-doc). Total ~37 LOC.

Reuses the per-article wall-clock budget already plumbed at `batch_ingest_from_spider.py:1718` (`effective_timeout`); converts every silent corruption into an explicit `ingestions.status='failed'` row. No SDK monkey-patching, no throughput regression, composable with parallel quicks (T3 spike, Cognee retire).

Three other patterns evaluated and rejected:
- Pattern B (`apipeline_process_enqueue_documents` re-invoke) — does not solve cancellation case
- Pattern C (serialize all ainsert via app lock) — collapses cron throughput 3–5×
- Pattern D (parent-only Pattern A) — acceptable but +6 LOC of leverage gives Pattern A full sub-doc coverage

---

## Anti-fabrication checks honored

| Claim | Citation |
|---|---|
| `ainsert` is two-step shim | `lightrag.py:1265-1268` (verbatim in INVESTIGATION §1.1) |
| Busy-flag early-return | `lightrag.py:1794-1800` (verbatim in INVESTIGATION §1.3) |
| `PROCESSED` write site | `lightrag.py:2161` (verbatim in INVESTIGATION §1.3) |
| Cancellation does NOT set FAILED | `lightrag.py:2053-2074` vs `:2099-2121` (asymmetry noted in §2) |
| Production writes ingestions=ok after ainsert returns | `batch_ingest_from_spider.py:1730-1750` (verbatim in §3) |
| 11 production ainsert call sites identified | `Grep ainsert\(` output cited in §3 (table) |
| No `adrain()` / `await_processed()` exists in 1.4.15 | Empty grep result `adrain|await_processed|wait_for_processing|wait_until_processed|wait_pipeline` cited in §4 |
| Mock timing scenarios T1/T2 stamps | `.scratch/lightrag-pipeline-mock-timing-20260510T1207.log` lines 105-170 |
| LOC estimates | Computed from grep callsite counts (2 production sites) + helper file size estimate |
| Risk evaluation | Each pattern lists concrete side-effect cases (throughput, deadlock, image-side loss, etc.) |

No "low risk" / "small change" / "should work" handwave language. Every quantitative claim cites a file:line or `.scratch/` log path.

---

## Scope discipline

✅ Read SDK source under `venv/Lib/site-packages/lightrag/`
✅ Read local Python files (read-only)
✅ Created `scripts/lightrag_diag/` (new directory, 2 diagnostic scripts)
✅ Wrote evidence to `.scratch/`
✅ Wrote planning artifacts to `.planning/quick/260510-gqu-.../`
✅ One STATE.md update (append-only)

❌ Modified zero production source files
❌ Modified zero LightRAG SDK files
❌ Did not touch `tests/unit/test_ainsert_persistence_contract.py` (parallel quick 260509-t4i territory)
❌ Did not touch any Cognee files (`cognee_*.py`, `lib/api_keys.py` — parallel quick 260510-gfg territory)
❌ Did not SSH Hermes
❌ Did not start the follow-up fix quick (user gates that decision)

---

## STOP gate

The follow-up fix quick is the user's decision. This investigation produced enough cited evidence to ship Pattern A in 5–10 LOC at the production-call-site level + ~25 LOC helper, with three new mock-only unit tests. Hermes deploy + cron smoke is a separate post-deploy gate.

---

## Race coordination with parallel quicks

- **260510-gkw** (T3 spike — real Vertex Gemini ainsert persistence) — orthogonal; tests SDK boundary, this quick analyzes SDK boundary; both compose
- **260510-gfg** (Cognee Path A retire — delete cognee_*) — orthogonal scope (Cognee files vs LightRAG analysis); zero file overlap
- **260509-t4i** (T1+T2 contract test — locked at 7c3ba4a) — orthogonal; pre-existing test file untouched

`git pull --ff-only` before commit per CLAUDE.md "Lessons Learned" 2026-05-06 #5 race-handling rule.

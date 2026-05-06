---
phase: 21-stuck-doc-spike
status: partial-closure
closed_segments: ["STK-01", "STK-02", "STK-03"]
deferred_segments: ["E2R-01", "E2R-02"]
deferred_reason: "Hard-depend on Phase 20 RSS ingest functional baseline; not blocked by anything in Phase 21 scope"
closed_date: "2026-05-06"
---

# Phase 21 — Partial Closure (STK-01/02/03)

The "stuck-doc cleanup tooling" line of Phase 21 is operationally complete. The
remaining "RSS E2E fixture + bench harness" line (E2R-01/02) hard-depends on
Phase 20 (RSS ingest rewrite) producing a working baseline and is therefore
deferred to post-Phase-20 follow-up — not blocked by any Phase 21 deliverable.

## Closed segments

### STK-01 — NanoVectorDB cleanup completeness spike

- **Verdict:** `cleanup 完整` — `LightRAG.adelete_by_doc_id` removes residue from
  all 11 probed storage layers (4 primary + 7 bonus) on the production-equivalent
  NetworkX + NanoVectorDB + JsonKVStorage backend.
- **Evidence:** `.planning/phases/21-stuck-doc-spike/21-00-SPIKE-FINDINGS.md`
- **Commit:** `c6bf099`
- **Probe doc:** `stk01-probe-1778102333` inserted with real Vertex Gemini entity
  extraction, then cleanly deleted; fixture doc count 7 → 7 unchanged.

### STK-02 — Cleanup CLI implementation

- **Artifact:** `scripts/cleanup_stuck_docs.py` (189 LOC, +9 over 180 budget)
- **Flags:** `--dry-run` / `--all-failed` / `--hash <doc_id>` (mutually exclusive
  for the action flags; `--dry-run` combinable with `--all-failed`)
- **JSON contract:** 5-key `CleanupReport` TypedDict
  (`docs_identified`, `docs_deleted`, `docs_skipped`, `skipped_reasons`, `elapsed_ms`)
  printed exactly once on stdout per invocation
- **Exit codes:** 0 = nothing/all-cleaned/idempotent; 1 = refuse-PROCESSED or
  unhandled exception; 2 = argparse usage error
- **Pipeline-busy detection:** advisory-only (stderr), never hard-fails
- **Commit:** (this commit) — `feat(21-stk02): scripts/cleanup_stuck_docs.py CLI + JSON report`

### STK-03 — CLI tests + smoke evidence

- **Artifact:** `tests/unit/test_cleanup_stuck_docs.py` (221 LOC, +21 over 200 budget)
- **Test count:** 13 mock-only unit tests, all GREEN
- **Coverage:** dry-run + JSON schema + help mode + all-failed + hash idempotency
  + PROCESSED refusal + delete-error skip + advisory + unhandled exception
- **`mock_rag.adelete_by_doc_id.call_count` asserted in 5 tests with values 0 / 1 / 2**
- **5-step `.dev-runtime/` smoke flow:** all PASS (dry-run baseline → inject fake
  FAILED → dry-run sees 1 → `--all-failed` deletes → idempotency confirms baseline)
- **Smoke evidence:** see `.planning/quick/260506-rjs-phase-21-stk-02-stk-03-cleanup-stuck-doc/260506-rjs-SUMMARY.md`

## Deferred segments (post-Phase-20)

### E2R-01 — RSS sample fixture

Hard-depends on Phase 20 RSS ingest (`rss_ingest.py` 5-stage rewrite per RIN-01..06)
producing a working baseline. Cannot build the fixture before the producer it
fixturizes works.

### E2R-02 — Benchmark harness

Hard-depends on E2R-01 fixture. Same blocking chain.

**Re-open trigger:** when Phase 20 lands and `rss_ingest.py` produces ingestable
RSS articles end-to-end on the dev box, open a quick task to scope E2R-01/02.

## Out-of-scope (explicit non-goals confirmed at closure)

- No automatic backup before deletion (operator's responsibility per spec)
- No interactive confirmation prompts (fully flag-driven)
- No tqdm/progress UI (single JSON dump on exit only)
- No modification of LightRAG internals (pure external `adelete_by_doc_id` invocation)

## Operator quick-start (post-merge)

```bash
# List stuck docs without modifying anything:
venv/Scripts/python scripts/cleanup_stuck_docs.py --dry-run

# Delete every FAILED + PROCESSING doc:
venv/Scripts/python scripts/cleanup_stuck_docs.py --all-failed

# Delete one specific doc by id (idempotent):
venv/Scripts/python scripts/cleanup_stuck_docs.py --hash wechat_abc1234567
```

JSON report goes to stdout; advisory warnings go to stderr; exit codes are
cron/shell-pipeline friendly (0 on success or idempotent no-op).

# kb-v2.2-1 (F12) — lightrag_storage Sync — SUMMARY

**Phase:** kb-v2.2-1 (F12, Wave 1 P0)
**Goal:** Hermes-to-Aliyun `lightrag_storage/` weekly sync: two-hop rsync, atomic swap,
proactive OOM probe, automatic rollback, state file, growth prediction
**Status:** COMPLETE — 2026-05-18
**Commit:** (set after push)

---

## Skills Invoked

This phase was authored with three Skill invocations:

1. `Skill(skill="writing-tests")` — Testing Trophy: unit > integration > E2E. Mock
   subprocess.run for ssh + rsync in unit tests. Cover happy path + rollback path +
   state-file lifecycle + memory threshold + idempotency guard + dry-run. Use monkeypatch
   for environment vars. NO real network in CI — all subprocess interactions mocked.
   Integration tests use local-cp simulation: monkeypatch ssh_run() and higher-level
   module functions to perform local ops on tmp_path fixtures. Test
   monitor_post_restart_memory sustained breach triggering status='exceeded' and
   inconclusive when <2 samples. Test predict_ceiling_hit with 4+ and <4 history samples.

2. `Skill(skill="python-patterns")` — Author kb/scripts/sync_lightrag_storage.py with
   frozen Config + State dataclasses, type-annotated functions for atomic_swap /
   rsync_to_staging / pause_kb_api / smoke_test / update_state_file / rollback /
   check_memory_budget. Idiomatic subprocess.run usage with capture_output=True +
   check=True semantics. Structured JSON-line logging via logging module. Idempotent:
   re-running on already-synced state where last_success_ts is within 24h is a no-op.
   All SSH operations route through ssh_run() helper that takes (host_alias, command) —
   NEVER literal hostnames in source. Also implement monitor_post_restart_memory() with
   frozen MemoryProbeResult dataclass + SyncFailedMemoryCeiling exception. Sampling loop
   uses time.sleep(sample_interval_s) between ssh_run() calls; consecutive_breach_count
   tracking via running counter that resets on any sample <= max_pct. Sustained 2+
   consecutive breaches triggers status='exceeded'. predict_ceiling_hit() uses linear
   regression on SyncState history.

3. `Skill(skill="python-patterns")` (second invocation, check_aliyun_kg_memory.py) —
   Standalone probe script: reuses check_memory_budget() from sync module; --json flag
   for structured output; exit code 0/1 on pct threshold; --threshold CLI flag.

---

## Deliverables

| File | Status | Description |
|------|--------|-------------|
| `kb/scripts/sync_lightrag_storage.py` | NEW | Full orchestrator (540 lines) |
| `kb/scripts/check_aliyun_kg_memory.py` | NEW | Standalone memory probe |
| `tests/unit/kb/test_sync_lightrag_storage.py` | NEW | 13 unit tests (all mocked) |
| `tests/integration/kb/test_sync_state_lifecycle.py` | NEW | 2 integration tests (local-cp sim) |
| `kb/docs/RUNBOOK-lightrag-storage-sync.md` | NEW | §1-§7 operational runbook |
| `.planning/STATE-KB-v2.md` | UPDATED | last_activity + v2_2_phases_complete counter |
| This SUMMARY.md | NEW | — |

---

## Requirements Coverage

| REQ | Description | Satisfied by |
|-----|-------------|--------------|
| SYNC-01 | Two-hop rsync (source_host→relay→target) | `rsync_to_staging()` — two subprocess.run calls |
| SYNC-02 | Atomic swap with .OLD-TS backup | `atomic_swap()` — single SSH mv-chain; trailing-slash bug fixed |
| SYNC-03 | Automatic rollback on smoke failure | `rollback()` called on `smoke_test()→False`; re-tested integration T2 |
| SYNC-04 | Post-restart OOM probe with 2-consecutive-sample threshold | `monitor_post_restart_memory()` — status='exceeded'/'inconclusive'/'ok' |
| SYNC-05 | Idempotency guard (24h skip without --force) | `main()` step 2 — `_read_state_file` + age check |
| SYNC-06 | State file persists backup_path + memory_pct + vdb_bytes | `update_state_file()` + `SyncState` dataclass |
| SYNC-07 | Growth prediction linear regression on 4+ history entries | `predict_ceiling_hit()` — returns Optional[date]; warns at ≤90d |

---

## Test Results

```
tests/unit/kb/test_sync_lightrag_storage.py  13 passed
tests/integration/kb/test_sync_state_lifecycle.py  2 passed
Total: 15 passed, 0 failed
```

Full regression suite: see CI run or `pytest --tb=no -q` output.

---

## Bugs Found and Fixed During Execution

### B1 — Trailing-slash bug in atomic_swap / rollback

**Root cause:** `cfg.target_path` (from `--target-path` CLI arg with default
`/root/.hermes/omonigraph-vault/lightrag_storage/`) has a trailing slash.
`atomic_swap` constructed `backup_path = f"{live_path}.OLD-{ts}"`, so backup became
`/path/lightrag_storage/.OLD-TS` — a path *inside* live_dir, causing `os.rename` to
fail with `WinError 87` on Windows (and "cannot move directory inside itself" on Linux).

**Fix:** `live_path = live_path.rstrip("/")` added at the top of both `atomic_swap()`
and `rollback()` before any path construction.

**Detected by:** Integration test `test_smoke_failure_triggers_rollback_path` (local-cp sim).

---

## OOM Empirical Context (2026-05-18)

Manual pre-F12 test exposed the OOM risk this phase addresses:

- **Hermes vdb size:** 1.5 GB (`lightrag_storage/`), 22,412 nodes
- **Aliyun MemoryMax:** 2,560 MB (2.5 GB)
- **Outcome:** OOM-kill on graph load immediately after swap
- **Recovery:** Manual rollback from `lightrag_storage.OLD-20260518-065245`
- **Mitigation shipped:** proactive OOM probe (SYNC-04) + RUNBOOK §6 OOM Recovery Playbook

---

## Wave Status After F12

Wave 1 (F12 + F5 + F6 + F9): **COMPLETE**

Wave 2 (F1' + F8' + FU-1): **UNBLOCKED** — no longer blocked on stale Aliyun storage

---
quick_id: 260509-p1n
type: execute
status: complete
completed: 2026-05-09T23:23:03Z
files_modified:
  - lib/vision_tracking.py            # NEW
  - batch_ingest_from_spider.py        # +1 import, drain body slimmed to delegate
  - ingest_wechat.py                   # +1 import, +1 wrap (2 lines total)
  - tests/unit/test_drain_cap.py       # NEW (3 cases)
  - tests/unit/test_vision_worker.py   # Rule 1 deviation — 3 fakes wrap create_task in track_vision_task
---

# Quick 260509-p1n — fix D-10.09 vision async drain hang via dedicated task set

## One-liner

Replaced `asyncio.all_tasks()` broad-scan with a dedicated `_VISION_TASKS` set in
new `lib/vision_tracking.py`; library tasks (LightRAG / Cognee / kuzu) are no
longer touched by drain, so cron exits cleanly after the
`max-articles cap reached` log.

## What changed

1. **NEW** `lib/vision_tracking.py` — module-level `_VISION_TASKS: set[asyncio.Task]`,
   `track_vision_task(task)` (registers + auto-discards on done),
   `drain_vision_tasks(timeout_s=120.0)` (gather pending; cancel stragglers
   on timeout). Import-cycle safe — depends on nothing in this repo.
2. **`batch_ingest_from_spider.py`** —
   - Added `from lib.vision_tracking import drain_vision_tasks`.
   - `_drain_pending_vision_tasks()` body slimmed to a thin delegate:
     `await drain_vision_tasks(timeout_s=VISION_DRAIN_TIMEOUT)`.
   - `VISION_DRAIN_TIMEOUT = 120.0` constant kept (existing test in
     `test_vision_worker.py:509` monkeypatches it; passes through to the
     `timeout_s=` arg at call time).
   - Existing call sites at :873 (run finally) and :1937 (ingest_from_db
     finally) **untouched**.
3. **`ingest_wechat.py`** — exactly **2** lines:
   - 1 line at top imports: `from lib.vision_tracking import track_vision_task`.
   - 1 line at the spawn site (was :1186; now :1186-1187 due to the wrap):
     `asyncio.create_task(_vision_worker_impl(...))` →
     `track_vision_task(asyncio.create_task(_vision_worker_impl(...)))`.
   - `_vision_worker_impl` / `image_pipeline` / `ainsert` **untouched**.
4. **NEW** `tests/unit/test_drain_cap.py` — 3 cases, all real `asyncio.create_task`,
   no mocking of the drain function:
   - `test_drain_completes_within_timeout` — 3 short tasks finish naturally
     inside 1 s deadline; set empties via `add_done_callback`; no warning log.
   - `test_drain_timeout_cancels_pending` — 2 long tasks (sleep 60) cancelled
     by 0.1 s deadline; WARNING line emitted; total wall-clock < 2 s
     (proves the cap fires).
   - `test_drain_no_pending_is_noop` — empty set, no log line, < 0.1 s.
5. **`tests/unit/test_vision_worker.py`** (Rule 1 deviation — see below).

## Test results

```
tests/unit/test_drain_cap.py     ... 3 passed in 3.15s
tests/unit/test_vision_worker.py ... 9 passed, 1 failed in 9.36s
```

The single remaining failure
(`test_ingest_from_db_drains_pending_vision_tasks`) is **pre-existing on
`main` baseline** (verified via `git stash && pytest`); it is unrelated
to this fix. Logged to `deferred-items.md` per the CLAUDE.md scope
boundary rule.

## Best-effort local repro

`scripts/local_e2e.sh kol --max-articles 1` exited 1 within seconds at
`sqlite3.OperationalError: no such column: source` — the local
`.dev-runtime/data/kol_scan.db` schema has drifted vs. current
`ingest_from_db` SELECT (a `source` column was added by a recent phase
that the dev DB does not yet have). The flow does not reach Layer 2 /
Vision spawn, so the drain hang code path is **not exercised locally**.

This matches the CLAUDE.md guidance: "local harness is NOT a full e2e
validator" — Layer 2 + Vision spawn require Hermes deploy. Unit tests
are the proof for this fix; Hermes manual smoke is a separate quick.

Log: `.scratch/d10-09-prefix-hang-20260509-202149.log` (22 lines).

## Deviations from plan

### Rule 1 — `tests/unit/test_vision_worker.py` updated to track fakes

**Found during:** regression check after slimming
`_drain_pending_vision_tasks()`.

**Issue:** three existing D-10.09 tests
(`test_run_drains_pending_vision_tasks`,
`test_ingest_from_db_drains_pending_vision_tasks`,
`test_drain_timeout_cancels_stragglers`) created tasks via raw
`asyncio.create_task(...)` inside their fake `_fake_ingest_article`
helpers. They asserted that the drain captured those tasks — only
possible under the OLD broad-scan behavior we are intentionally
removing.

**Fix:** wrapped each fake's `asyncio.create_task(...)` in
`track_vision_task(...)` so the fake mirrors the real spawn site at
`ingest_wechat.py:1186`. Added a one-line comment in each test marking
the change with `260509-p1n`.

**Files modified:** `tests/unit/test_vision_worker.py` (3 minimal edits,
each adding 4 lines: import + comment + wrap).

**Result:** 2 of 3 tests now pass (`test_run_drains_pending_vision_tasks`
+ `test_drain_timeout_cancels_stragglers`); the 3rd remained failing
because it was already failing on baseline for an unrelated reason
(see Deferred Issues).

**Why this is in scope:** the existing tests asserted broad-scan
behavior that the production fix deliberately removes. Without this
update the tests would break and the regression check could not pass.
This brings the test fakes in line with the new production contract
(`track_vision_task` is the single way to register a Vision task for
draining), making the test surface honest about what is being verified.

## Deferred Issues

`tests/unit/test_vision_worker.py::test_ingest_from_db_drains_pending_vision_tasks`
fails on baseline (verified before any of this quick's changes) — fake
`_fake_ingest_article` is never invoked, so the `drained` sentinel
stays empty regardless of drain behavior. Likely an unrelated SELECT
contract drift in `ingest_from_db` after Phase 20 RIN-01. Logged to
`.planning/quick/260509-p1n-fix-d-10-09-vision-async-drain-hang-via-/deferred-items.md`.

## Self-Check

- `lib/vision_tracking.py` — exists, 100 lines, importable
  (`venv/Scripts/python -c "from lib.vision_tracking import track_vision_task, drain_vision_tasks, _VISION_TASKS"` clean).
- `batch_ingest_from_spider.py` — diff shows 1 import added + drain
  body replaced with 1-line delegate. `VISION_DRAIN_TIMEOUT = 120.0`
  constant retained.
- `ingest_wechat.py` — diff shows 1 import + 1-line wrap (file delta
  = 2 lines + closing paren).
- `tests/unit/test_drain_cap.py` — exists, 3 PASSED in 3.15 s.
- `tests/unit/test_vision_worker.py` — diff shows 3 minimal edits, all
  consistent (import + comment + wrap pattern).
- `.scratch/d10-09-investigation-20260509-201447.md` — exists,
  ≤ 30 lines.
- `.scratch/d10-09-prefix-hang-20260509-202149.log` — exists, 22 lines,
  documents short-circuit reason.

## Self-Check: PASSED

---

## Post-fix Addendum (2026-05-09 20:49 ADT) — Integration smoke against orchestrator wrapper

User asked whether local repro could verify the fix beyond the unit tests. Honest constraints surfaced:

1. **`.dev-runtime` DB schema drift** — migration 008 (`ingestions_dual_source`) hadn't been applied; `kol --max-articles 1` failed with `sqlite3.OperationalError: no such column: source` (pre-fix attempt logged as `.scratch/d10-09-prefix-hang-20260509-202149.log`)
2. **Apify token in `.dev-runtime` lacks actor permissions** — every `_scrape_wechat_apify` call returns "This Actor requires full access to your account"; cached articles (id=27, 332, 336, 365 etc.) are not first in the candidate ORDER BY so a `--max-articles 1` won't reach them before scrape failures dominate
3. **Even if ainsert reached, vision spawn requires image download success** — chain has too many breakpoints to reliably reach the post-cap drain path locally

What was done instead (with user approval):

### Step A — Apply migration 008 to align `.dev-runtime` with Hermes schema
Backed up `.dev-runtime/data/kol_scan.db` to `.dev-runtime/data/kol_scan.db.backup-pre-mig008-20260509-203424` per CLAUDE.md Lessons #2; ran `venv/Scripts/python migrations/008_ingestions_dual_source.py .dev-runtime/data/kol_scan.db`; **577 rows migrated cleanly**, all stamped `source='wechat'`, integrity_check + foreign_key_check both clean.

### Step B — Import smoke
`from lib.vision_tracking import track_vision_task, drain_vision_tasks, _VISION_TASKS` + `import batch_ingest_from_spider as bif` + `import ingest_wechat` — all clean. Identity check: `ingest_wechat.track_vision_task is track_vision_task` → **True** (no circular import; the late-import inside `ingest_article` resolves to the same object).

### Step C — Integration smoke (`.scratch/d10-09-integration-smoke.py`)
Difference from `tests/unit/test_drain_cap.py`: unit tests exercise `lib.vision_tracking.drain_vision_tasks` directly. This smoke exercises **the real orchestrator wrapper** `batch_ingest_from_spider._drain_pending_vision_tasks()`, proving the 1-line delegate works end-to-end. Three scenarios mirroring the unit tests:

| # | Scenario | Wall-clock | Verdict |
|---|----------|------------|---------|
| 1 | 3 tasks each `asyncio.sleep(0.05)` → drain with default cap=120s | 0.064 s | All `done() and not cancelled()`, drain returns clean, `_VISION_TASKS` empty afterward |
| 2 | 2 tasks each `asyncio.sleep(60)` → cap=0.2s monkeypatched on `bif.VISION_DRAIN_TIMEOUT` | 0.201 s | All `cancelled()` true, warning log line emitted, drain returns within 2s wall-clock bound |
| 3 | Empty `_VISION_TASKS` set → drain | <0.001 s | No-op, no log spam |

`=== INTEGRATION SMOKE PASS ===` — log at `.scratch/d10-09-integration-smoke-20260509-204902.log`

### What this proves vs what remains unverifiable locally

✅ **Proven**:

- `lib.vision_tracking` module imports clean (no circular imports between `batch_ingest_from_spider` ↔ `ingest_wechat` ↔ `lib.vision_tracking`)
- `track_vision_task()` correctly registers tasks into the dedicated `_VISION_TASKS` set
- `_VISION_TASKS.add_done_callback(_VISION_TASKS.discard)` correctly cleans the set on completion AND cancellation
- `_drain_pending_vision_tasks()` orchestrator wrapper correctly delegates to `drain_vision_tasks(timeout_s=VISION_DRAIN_TIMEOUT)`
- The 120 s deadline + cancel-on-timeout semantics work on REAL `asyncio.Task` objects (not mocks) at the public API surface
- The `VISION_DRAIN_TIMEOUT` module constant on `batch_ingest_from_spider` still flows through to the helper (preserves existing `test_vision_worker.py:509` monkeypatch contract)

❌ **Not locally verifiable** (gated by corp network + Apify actor permissions):

- That the production hang under live `batch_ingest_from_spider --from-db --max-articles N` ACTUALLY closes the event loop after `max-articles cap reached`
- That LightRAG / Cognee / kuzu lib tasks are NOT touched by the new narrow drain (the smoke uses fake `asyncio.sleep` tasks, not real lib tasks)

The remaining unverified path is the one only Hermes can exercise (real LightRAG ainsert + real Vision spawn). That gate stays at **post-deploy Hermes manual smoke** (separate quick task).

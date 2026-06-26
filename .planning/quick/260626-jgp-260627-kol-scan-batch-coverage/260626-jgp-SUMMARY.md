---
phase: quick-260626-jgp
plan: 01
subsystem: batch_scan_kol / systemd
tags: [kol-scan, staleness-partition, argparse, systemd, tdd]
dependency_graph:
  requires: []
  provides: [--max-accounts flag, staleness SELECT, 4-batch timers, retimed classify timer]
  affects: [batch_scan_kol.py, deploy/aliyun/systemd/]
tech_stack:
  added: []
  patterns: [behavior-anchor harness, version-safe SQLite ordering, systemd template units]
key_files:
  created:
    - tests/unit/test_scan_max_accounts.py
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer
  modified:
    - batch_scan_kol.py
    - deploy/aliyun/systemd/omnigraph-kol-classify.timer
    - deploy/aliyun/systemd/omnigraph-kol-scan.timer
decisions:
  - "Version-safe staleness SQL: `(MAX(a.scanned_at) IS NULL) DESC` boolean ordering used instead of NULLS FIRST keyword; Aliyun SQLite version unknown"
  - "run() new param placed LAST after summary_json to preserve all existing keyword-arg call sites"
  - "Plan-checker advisory folded in: monkeypatch.setattr(batch_scan_kol.time, 'sleep', lambda *_a, **_k: None) added to tests (a) and (b) to avoid 5s per-account sleep accumulation"
metrics:
  duration_minutes: ~25
  tasks_completed: 2
  files_modified: 9
  completed_date: "2026-06-26"
---

# Quick 260626-jgp: KOL Scan 4-Batch Coverage Summary

KOL scan gains a `--max-accounts N` staleness-partition flag; 4 staggered systemd timers each call `--max-accounts 15` to guarantee 4×15=60 ≥ 58 accounts covered daily.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add --max-accounts staleness path + tests (TDD) | 9887e87 | batch_scan_kol.py, tests/unit/test_scan_max_accounts.py |
| 2 | Author systemd repo unit copies | 9e70da2 | 5 new + 2 modified deploy/aliyun/systemd/ files |

## What Was Built

### Task 1: `--max-accounts` flag + staleness SELECT

`batch_scan_kol.py` `run()` gains a new last keyword param `max_accounts: int | None = None`.

- **Default path (`max_accounts is None`)**: byte-behavior-identical to before — `SELECT name, fakeid FROM accounts ORDER BY name` + unconditional `random.shuffle(rows)`. Zero truncation.
- **Staleness path (`max_accounts is not None`)**: version-safe LEFT JOIN + GROUP BY with `ORDER BY (MAX(a.scanned_at) IS NULL) DESC, MAX(a.scanned_at) ASC, acc.name ASC` — NULL-first (never-scanned), then oldest-scanned, then name tiebreak. No shuffle. Truncates to `rows[:max_accounts]`.
- `argparse`: `--max-accounts` type=int default=None, backward-compatible with all existing flags.

### Task 2: Systemd units

| File | Change |
|------|--------|
| `omnigraph-kol-scan-batch@.service` | NEW template: `--daily --max-accounts 15`, RuntimeMaxSec=1800, OnFailure alert chain |
| `omnigraph-kol-scan-batch@1.timer` | NEW: OnCalendar 01:30 UTC, Persistent=true, Unit=...@1.service, no Requires= |
| `omnigraph-kol-scan-batch@2.timer` | NEW: OnCalendar 05:30 UTC, Persistent=true, Unit=...@2.service, no Requires= |
| `omnigraph-kol-scan-batch@3.timer` | NEW: OnCalendar 11:00 UTC, Persistent=true, Unit=...@3.service, no Requires= |
| `omnigraph-kol-scan-batch@4.timer` | NEW: OnCalendar 15:30 UTC, Persistent=true, Unit=...@4.service, no Requires= |
| `omnigraph-kol-classify.timer` | MODIFIED: OnCalendar 11:15→16:00 UTC, Requires= line dropped from [Unit] |
| `omnigraph-kol-scan.timer` | MODIFIED: SUPERSEDED header comment prepended, body unchanged |

## Pytest Results

**Interpreter:** `/c/Users/huxxha/Desktop/OmniGraph-Vault/venv/Scripts/python.exe` (main repo venv — worktree has no venv; run via absolute path from main repo root)

**Command used:** `cd /c/Users/huxxha/Desktop/OmniGraph-Vault && python.exe -m pytest "<absolute-path-to-test-file>" -v`

**Result:** 4/4 PASSED

- `test_staleness_selection_null_first_then_oldest` PASSED
- `test_default_path_no_truncation` PASSED
- `test_argparse_max_accounts_int` PASSED
- `test_argparse_max_accounts_absent_is_none` PASSED

**Note on worktree / pytest path:** The git worktree at `agent-afa0d2516c133639b` is sparse — only changed files are present; `kol_config.py` (imported at module level by `batch_scan_kol.py`) lives only in the main repo. Running `pytest` from the worktree root with a relative path fails with `ModuleNotFoundError: No module named 'kol_config'`. The workaround is to run pytest from the main repo root (`cd /c/.../OmniGraph-Vault`) with the absolute path to the test file — this is the correct invocation and was what the plan's `venv/Scripts/python.exe -m pytest tests/unit/test_scan_max_accounts.py -v` intended (the plan assumes the worktree has a local venv or will be run from the right context).

## Deviations from Plan

### Plan-checker advisories folded in (both NON-BLOCKING)

**1. `time.sleep` patch in tests (a) and (b)**

The plan's `<plan_checker_advisories_to_honor>` block specified patching `time.sleep` to prevent 5s × N delays accumulating in the test suite. Applied `monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)` in both `test_staleness_selection_null_first_then_oldest` and `test_default_path_no_truncation`. Suite runs in ~0.8s not ~30s.

**2. Resume-mode log imprecision (cosmetic only)**

As noted in the advisory: `total_accounts = len(rows)` on the staleness path reflects the truncated N (15), not the full account count. Left as-is per advisory — this is mutually-exclusive with batch cron usage (`--daily`, not `--resume`). No code added.

### No other deviations

All must_haves verified:
- Default path byte-behavior-identical: `SELECT name, fakeid FROM accounts ORDER BY name` + `random.shuffle(rows)` — confirmed by line 245+256 in batch_scan_kol.py and passing `test_default_path_no_truncation`
- Staleness SQL has no `NULLS FIRST` keyword (grep confirms)
- `shuffle` call is inside the `max_accounts is None` branch only (line 256)
- argparse backward-compatible (mutual-exclusion check, all existing flags unmodified)
- Template @.service: `--max-accounts 15`, `RuntimeMaxSec=1800`, `OnFailure=omnigraph-kol-scan-alert.service` all verified
- 4 batch timers: no `Requires=` in any (grep -L confirms all 4)
- classify.timer: retimed to 16:00 UTC, Requires= removed
- scan.timer: SUPERSEDED header prepended, file retained
- Scope: only the 9 named files modified (git diff HEAD~2..HEAD confirms)

## Commits

- `9887e87` feat(scan): add --max-accounts staleness-partition path to batch_scan_kol (260626-jgp)
- `9e70da2` chore(systemd): 4-batch KOL scan timers + retime classify 16:00 UTC (260626-jgp)

Both atomic, forward-only, explicit `git add <files>`, NOT pushed (orchestrator handles Aliyun rollout in Phase 2).

## Known Stubs

None. This plan has no UI components and no deferred data wiring.

## Self-Check

- [x] `batch_scan_kol.py` exists and modified
- [x] `tests/unit/test_scan_max_accounts.py` created (4 tests GREEN)
- [x] `deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service` created
- [x] `deploy/aliyun/systemd/omnigraph-kol-scan-batch@{1,2,3,4}.timer` created (4 files)
- [x] `deploy/aliyun/systemd/omnigraph-kol-classify.timer` modified (16:00, no Requires=)
- [x] `deploy/aliyun/systemd/omnigraph-kol-scan.timer` modified (SUPERSEDED header)
- [x] Commits 9887e87 and 9e70da2 verified in git log

---

## Phase 2 — Aliyun Operator Rollout + Bootstrap Validation (orchestrator, 2026-06-27 CST)

> Phase 1 above is the EXECUTOR's Phase-1-only summary. This section is the orchestrator's Phase 2 (Aliyun systemd rollout + end-to-end bootstrap) — the operator work the executor explicitly did NOT do.

### Deploy (all surgical, in-flight hot-patches untouched)

- **Code:** SCP'd `batch_scan_kol.py` (local `main` @ `9928661`) directly to Aliyun `/root/OmniGraph-Vault/` — `git fetch origin` HUNG (Aliyun→github 443 cross-border block; Aliyun is 81 commits behind with in-flight `synthesizer.py`/`qdrant_to_nanovdb.py` hot-patch mods that a `git pull` would disturb). Single-file SCP is the proven #70 fallback. Verified on Aliyun: `ast.parse` OK, `--max-accounts` flag live in `--help`, staleness SQL present, no `NULLS FIRST` keyword.
- **SQLite collation pre-check:** Aliyun SQLite **3.37.2** — `(MAX(a.scanned_at) IS NULL) DESC` boolean ordering executes cleanly (version-safe write confirmed in prod, not just assumed).
- **Backups:** `.bak-pre-scanbatch-260627` taken for all 5 touched units in `/etc/systemd/system/` before any change.
- **Units installed (SCP to `/etc/systemd/system/`):** `omnigraph-kol-scan-batch@.service` + `@{1,2,3,4}.timer` + retimed `omnigraph-kol-classify.timer` (16:00 UTC, Requires= dropped). `daemon-reload` OK; all 5 parse clean.
- **Timers armed (NO `--now`):** enabled + started the 4 batch timers. `systemctl disable --now omnigraph-kol-scan.timer` (old single-day timer off; `.service` + `-alert.service` defs retained for the template + alert chain). classify timer restarted to pick up 16:00 UTC.
- **Final schedule (CST):** scan @1=09:30, @2=13:30, @3=19:00, @4=23:30 (= 01:30/05:30/11:00/15:30 UTC); classify next-fires Sun 00:00 CST = 16:00 UTC. Old scan timer absent from `list-timers`. ✅ matches plan exactly.

### Pre-deploy coverage snapshot (binding baseline)

`58` accounts; **9 never-scanned** (`MAX(scanned_at) IS NULL`): `CV技术指南, NewBeeNLP, ShowMeAI, 夕小瑶智能体, 大猿搬砖简记, 漫士沉思录, 科学空间, 腾讯AI Lab, 陈宇明`; `47/58` stale-or-NULL within 24h.

### Bootstrap (batch@1, then batch@2) — what was PROVEN

**The `--max-accounts 15` + staleness machinery is correct and validated on real prod data:**

1. **Exact staleness selection** — batch@1's first fire selected precisely the 15 staleest in correct order: the 9 NULL-first, then the oldest-scanned tail (`和AI一起进化` 04-27 → `ArronAI` → `李rumor` → `海滨code` → `AINLP` → `折腾技术`). Matches the unit-test contract on live data.
2. **No 50/50 rate-limit** — `15 requests` per batch, exactly the cap. The batch math (15 × ~2.7 ≈ 40 < 50) holds in prod; the in-process page counter never tripped.
3. **`RuntimeMaxSec=1800` fine** (runs ~46s–110s), **`OnFailure=` alert chain preserved + fired.**
4. **Cookie self-heal chain (#56/R33) works end-to-end** — batch@1's first fire hit a DEAD cookie (every account `ret=200003`, last refresh 2026-06-23, 4 days stale) → `WECHAT_SESSION_INVALID: 15/15` → `exit(2)` → `OnFailure` fired `omnigraph-kol-scan-alert.service` → SSH'd Hermes → `refresh_wechat_cookie.py` → wrote back `kol_config.py` (mtime flipped 01:35, COOKIE len 777, TOKEN present). Re-fired batch@1 → **`15 ok, 0 failed, 15 requests`**. Then batch@2 advanced to a DIFFERENT scannable set (`DeepHub IMBA +11, AI科技评论 +11, 苍何 +8` — none touched by batch@1), proving the **staleness rotation deterministically advances**.

### HONEST FINDING — binding "58/58 daily / 0 NULL" criterion is NOT met (orthogonal pre-existing bug)

The successful re-fire exposed that the pinned root-cause theory (`random.shuffle` → 9 never picked) was **incomplete**. With a HEALTHY cookie and a deterministic staleest-first scan, the 9 "never-scanned" accounts **still produce zero attributable rows**, splitting into two orthogonal pre-existing data problems:

- **`CV技术指南`** (account `id=5767`, an anomalously high id vs the others at 9–54): API returns 5 articles but **all 5 skipped on the `articles.url` UNIQUE constraint** — its articles already exist under a *different* `account_id`. `distinct_account_ids_in_articles = 54 < 58 accounts` → article rows orphaned from their current account row (registry re-keyed / duplicate-account history).
- **8 others** (`NewBeeNLP, ShowMeAI, 夕小瑶智能体, 大猿搬砖简记, 漫士沉思录, 科学空间, 腾讯AI Lab, 陈宇明`): API returns **0 articles** even with a healthy cookie (`0 scanned`) — fakeid drift / renamed / empty-120-day window.

**Consequence for daily coverage:** because these 9 are permanently `MAX(scanned_at)=NULL`, the `(IS NULL) DESC` ordering pins them to the **top-9 of EVERY batch**. Each `--max-accounts 15` batch therefore spends 9 slots re-attempting dead accounts and scans only **6 fresh** ones. 4 batches/day = 9 dead (repeated) + ~24 distinct scannable, out of **49 scannable** (58 − 9). Full *scannable* rotation completes in ~2-3 days, not 1.

**Net assessment:** the infrastructure is a large, deterministic improvement — every *scannable* account is now guaranteed coverage within ~2-3 days (vs the old random ~18/day where 9 accounts went un-scanned for months), AND the cookie self-heal chain is proven to recover unattended. But the literal "0 NULL accounts / 58-58 daily" target is **mathematically unreachable at `--max-accounts 15` while the 9 dead accounts eat slots** — and those 9 cannot be populated by ANY scan schedule (orthogonal attribution/fakeid bug). Filed as a new ISSUES.md row (decision options: prune/fix the 9 dead accounts, or add a "skip N-consecutive-zero-yield accounts from the staleness head" guard so they stop eating slots — either restores 49/49-scannable daily within the 15-cap).

### Phase 2 verification checklist (Principle #6)

- [x] SQLite `(col IS NULL) DESC` supported on Aliyun (3.37.2) — verified, not assumed
- [x] Code deployed + syntax/flag/SQL markers confirmed on Aliyun
- [x] Unit backups taken before change (`.bak-pre-scanbatch-260627` ×5)
- [x] 4 batch timers armed at correct UTC times; old scan timer disabled; classify retimed 16:00 UTC — `list-timers` confirms
- [x] Staleness selection picks exact staleest-N in correct order (live)
- [x] No 50/50 rate-limit (15 req/batch); `RuntimeMaxSec` + `OnFailure` intact
- [x] Cookie self-heal chain fired + recovered + re-fire `15 ok/0 failed`
- [x] Rotation advances (batch@1 set ≠ batch@2 set)
- [ ] **0 NULL accounts** — NOT met; blocked by 9 structurally-unpopulatable accounts (orthogonal pre-existing bug, filed)
- [ ] **0 accounts >24h unscanned** — NOT met for the same reason (dead-9 eat slots → ~2-3 day scannable rotation, not daily)

### Deferred commit

The Phase 2 unit-file rollout used the repo copies already committed in `9e70da2` (cherry-picked to `main` @ `9928661`, pushed). No new code commit needed for Phase 2 — only this SUMMARY addendum + ISSUES/STATE doc updates.

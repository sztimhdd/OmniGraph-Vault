---
phase: quick-260629-gvl
plan: 01
subsystem: batch_scan_kol
tags: [kol-scan, sqlite, staleness, dead-accounts, issues-73]
dependency_graph:
  requires: []
  provides: [accounts.last_scanned_at, staleness-ordering-by-attempt-time]
  affects: [batch_scan_kol.py, tests/unit/test_scan_last_scanned.py]
tech_stack:
  added: []
  patterns: [sqlite-idempotent-migration, behavior-anchor-tests, tdd]
key_files:
  created: [tests/unit/test_scan_last_scanned.py]
  modified: [batch_scan_kol.py]
decisions:
  - "Order staleness queue by last_scanned_at (attempt time) not MAX(article.scanned_at); empty accounts can never advance article recency"
  - "Stamp on ok=True only — cookie-dead failures must not falsely rotate accounts to the back"
  - "Use (last_scanned_at IS NULL) DESC boolean trick instead of NULLS FIRST for SQLite portability"
metrics:
  duration_minutes: 15
  completed_at: "2026-06-29T17:19:21Z"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 2
---

# Quick 260629-gvl: KOL Dead-Account Prune and Guard — Task 1 Summary

**One-liner:** Per-account `last_scanned_at` stamp (on successful scan attempt, even 0-article) + staleness SELECT reordered by attempt time, fixing ISSUES #73 permanent head-pinning for empty accounts.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add last_scanned_at column, stamp on success, re-order staleness queue | e4fe935 | batch_scan_kol.py, tests/unit/test_scan_last_scanned.py |

## What Was Built

Three surgical changes to `batch_scan_kol.py`:

**1. Column migration (init_db):**
Added `_ensure_column(conn, "accounts", "last_scanned_at", "TEXT")` after the existing 3 `_ensure_column` calls. Idempotent (PRAGMA table_info guard), TEXT/nullable/no default. NULL = never attempted.

**2. Stamp-on-success (run() scan loop):**
Inside the `if ok:` branch, added:
```python
conn.execute(
    "UPDATE accounts SET last_scanned_at = datetime('now','localtime') WHERE name = ?",
    (name,),
)
conn.commit()
```
Stamps on every `ok=True` (including 0-article accounts). The `else:` (failure) branch is untouched — cookie-dead runs do NOT stamp.

**3. Staleness SELECT replacement:**
Replaced the LEFT JOIN/GROUP BY article-recency query with:
```sql
SELECT name, fakeid FROM accounts
ORDER BY (last_scanned_at IS NULL) DESC, last_scanned_at ASC, name ASC
```
Simpler, no join, orders by attempt time. Default path (max_accounts=None) is byte-identical.

## Test Results

```
Interpreter: C:\Users\huxxha\Desktop\OmniGraph-Vault\venv\Scripts\python.exe
Working dir: C:\Users\huxxha\Desktop\OmniGraph-Vault
PYTHONPATH: /c/Users/huxxha/Desktop/OmniGraph-Vault/.claude/worktrees/agent-a1f1ca9c4b340718b

Command:
  DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy PYTHONPATH=<worktree> \
  venv/Scripts/python.exe -m pytest \
    <worktree>/tests/unit/test_scan_last_scanned.py \
    <worktree>/tests/unit/test_scan_max_accounts.py -v

Result: 8 passed in 2.05s
```

**4 new tests (test_scan_last_scanned.py):**
- `test_stamp_on_success_even_zero_articles` — PASSED
- `test_no_stamp_on_failure` — PASSED
- `test_staleness_orders_by_last_scanned_at` — PASSED
- `test_just_scanned_rotates_to_back` — PASSED

**4 existing tests (test_scan_max_accounts.py):**
- `test_staleness_selection_null_first_then_oldest` — PASSED
- `test_default_path_no_truncation` — PASSED
- `test_argparse_max_accounts_int` — PASSED
- `test_argparse_max_accounts_absent_is_none` — PASSED

## Deviations from Plan

**Existing test `test_staleness_selection_null_first_then_oldest` — analysis and result:**

The plan flagged a potential regression risk: the existing test seeds accounts with ARTICLE `scanned_at` values and asserts ordering Alpha, Beta, Charlie. With the new SELECT ordered by `accounts.last_scanned_at` (not article recency), this test could break if it relied on article recency for ordering.

**Actual result: NO regression.** Reason: All seeded accounts in that test have `last_scanned_at = NULL` (they are inserted via `init_db()` before any stamp occurs, and none are explicitly stamped). With all accounts NULL → `(NULL IS NULL) = 1` for all → tie on DESC → `last_scanned_at ASC` = all NULL = tie → `name ASC` → Alpha, Beta, Charlie, Delta, Echo → top 3 = Alpha, Beta, Charlie. Same expected result as before.

**No test changes required.** The existing test continues to assert the correct contract (NULL-first, then name tiebreak) even though the underlying mechanism changed from article recency to attempt recency.

**No other deviations.** Plan executed exactly as specified. No architectural changes, no scope expansion, no out-of-scope fixes.

## Known Stubs

None. All changes are fully wired end-to-end.

## Self-Check

### Files exist:
- `batch_scan_kol.py` — modified (last_scanned_at column migration + stamp + new SELECT)
- `tests/unit/test_scan_last_scanned.py` — created (4 behavior-anchor tests)

### Commits exist:
- `e4fe935` — feat(quick-260629-gvl): add last_scanned_at stamp + staleness re-ordering (ISSUES #73)

## Self-Check: PASSED

Both files verified present. Commit e4fe935 confirmed in git log. 8/8 tests pass.

---

## Operator Phase 2 Note

This summary covers Task 1 (code) only. Phase 2 (Aliyun DB delete of 5 CV accounts + ~371 articles) is an operator runbook in the plan's `<operator_phase_2>` section — executed by the orchestrator via SSH after this commit is merged. NOT performed by this executor.

---

## Phase 2 — Aliyun Operator Rollout (orchestrator, 2026-06-30 CST)

### Pre-delete resurrection gate (HARD — caught a real risk)

`init_accounts()` re-inserts from `kol_config.FAKEIDS` on every `run()`. Gate check found **all 5 CV accounts WERE present in the live Aliyun `kol_config.FAKEIDS` (49 entries)** — so a bare DB delete would have been silently undone on the next scan. (They were absent from the kol_registry `list_accounts()`, consistent with their `source=None`.)

**Fix applied first:** backed up `kol_config.py` (`.bak-pre-cvdelete-260629`), removed the 5 CV lines (`CVer / CV技术指南 / OpenCV学堂 / 我爱计算机视觉 / AIWalker`). Verified fresh import: FAKEIDS **49 → 44**, no CV names remain. NOTE: `kol_config.py` is gitignored / Aliyun-local (the repo-tracked copy is a 2-entry stub with no real credentials), so this edit is correctly an Aliyun-only operator action — not a repo push.

### Transactional CV delete (kol_scan.db)

Backup `kol_scan.db.bak-pre-cvdelete-260629` taken first. Single `BEGIN/COMMIT` transaction, FK-ordered (child rows → articles → accounts):

| Table | Rows deleted |
|-------|-------------|
| classifications | 1855 |
| ingestions | 529 |
| extracted_entities | 202 |
| articles | 371 (145 under 5 live CV accounts + 226 orphan CV articles under deleted ids 16/17/18/19/49) |
| accounts | 5 |

**Totals: accounts 58 → 53, articles 2197 → 1826.** Post-delete verify: 0 CV-target articles remain, 0 CV accounts remain, `PRAGMA integrity_check = ok`. Scope honored: only `kol_scan.db` touched — LightRAG KG / Qdrant untouched (the 226 CV articles may already be in the KG; cleaning the KG is explicitly out of scope).

### Code deploy + bootstrap

- SCP'd new `batch_scan_kol.py` (main @ `4683c9a`) to Aliyun (git fetch 443-blocked per 260626-jgp). Verified: `ast.parse` OK, `last_scanned_at` markers present.
- Fired `--daily --max-accounts 5`: **migration ran cleanly** — `PRAGMA table_info(accounts)` now shows `last_scanned_at` column present on the live DB. The new staleness `ORDER BY (last_scanned_at IS NULL) DESC, last_scanned_at ASC, name ASC` executes correctly: with all 53 accounts currently NULL, it falls through to `name ASC` (alphabetical) — `AI 深度研究员, AINLP, AI产品榜, …` — the correct new-contract behavior.

### Honest limitation — stamp-on-success NOT yet proven on LIVE data

The bootstrap scan hit a **dead WeChat cookie** (`ret=200003 ×5`, ~3 days since the 2026-06-27 refresh) → all attempts failed → `if ok:` never ran → 0 accounts stamped. Correct behavior (no-stamp-on-failure), but it means the *positive* stamp path is unproven on live data this session.

Triggered the systemd batch@1 **service** (has `OnFailure=…-alert.service`) to engage the #56 cookie self-heal chain. The chain fired (breadcrumb stamped) but the Hermes hand-off failed: **`ssh: connect to host ohca.ddns.net port 49221: No route to host`** — Hermes is currently unreachable from Aliyun (home network down / IP drift). Unlike 2026-06-27 (Hermes reachable → cookie auto-recovered), the refresh could not complete this session.

**Assessment:** the stamp-on-success logic is proven by `test_stamp_on_success_even_zero_articles` (8/8 green) — a 0-article success stamps. Live confirmation is gated on a healthy cookie, which is an orthogonal environmental dependency (Hermes reachability + WeChat session). Once the cookie recovers (next time Hermes is reachable, or a manual refresh), the 4 daily batch timers will stamp accounts and the staleness rotation will advance as designed — the 8 non-CV dormant accounts will each get scanned once, stamp `last_scanned_at`, and rotate to the back instead of pinning the head.

### Phase 2 verification checklist (Principle #6)

- [x] Resurrection gate: 5 CV names removed from live `kol_config.FAKEIDS` (49→44, verified by fresh import)
- [x] Backups taken: `kol_config.py.bak-pre-cvdelete-260629` + `kol_scan.db.bak-pre-cvdelete-260629`
- [x] CV delete: 58→53 accounts, 2197→1826 articles (371 removed), child rows cascaded, `integrity_check=ok`, 0 CV remain
- [x] New code deployed (SCP) + `last_scanned_at` column physically present on live DB (migration ran)
- [x] New staleness ORDER BY runs on live DB (alphabetical fallback while all NULL — correct)
- [ ] **Live stamp-on-success** — NOT proven this session (dead cookie + Hermes unreachable for auto-refresh). Proven by unit test; live confirmation deferred to next healthy-cookie scan. Orthogonal environmental dependency, not a code defect.

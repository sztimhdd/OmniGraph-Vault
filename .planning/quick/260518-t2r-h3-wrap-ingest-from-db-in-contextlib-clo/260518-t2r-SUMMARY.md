---
phase: quick-260518-t2r
plan: 01
subsystem: ingest-pipeline
tags: [refactor, conn-leak, contextlib, ingest_from_db, h3]
requires:
  - tests/unit/test_ingest_from_db_orchestration.py (5 anchored behaviors)
provides:
  - "ingest_from_db() conn lifetime owned by contextlib.closing context manager"
  - "Any exception during init / schema migration / Layer 1 batch / get_rag(flush=True) closes conn cleanly via scope-exit"
affects:
  - "Future Hermes 2026-05-19 08:15 ADT cron exercises refactored code path on real production traffic"
tech-stack:
  added:
    - "stdlib: contextlib (used as contextlib.closing)"
  patterns:
    - "context-manager-owned resource lifetime (replaces 3 explicit conn.close() calls + 1 leak window)"
key-files:
  modified:
    - batch_ingest_from_spider.py
decisions:
  - "Reindent strategy = Option B one-shot Python script (not sed): asserted uniqueness of conn-creation anchor + sentinel close-line. AST-parse verified before commit."
  - "Removed all 3 explicit conn.close() (early-return rows, early-return candidate_rows, finally-block) — idempotent with context manager but cleaner to drop, matches plan."
metrics:
  duration_seconds: 195
  duration_minutes: 3
  tasks_total: 1
  tasks_completed: 1
  files_modified: 1
  diff_insertions: 494
  diff_deletions: 490
  diff_minus_w_lines: 58
  reindented_lines: 546
  conn_close_removed: 3
  pytest_pre: "5 passed"
  pytest_post: "5 passed"
  completed: 2026-05-19T00:03:34Z
---

# Quick 260518-t2r — H3 wrap ingest_from_db in contextlib.closing()

Pure structural refactor: wrap `batch_ingest_from_spider.ingest_from_db()` body in `with contextlib.closing(sqlite3.connect(str(DB_PATH))) as conn:` so exceptions in the L1578-L1728 init window (schema migration / fullbody column ensure / SELECT / Layer 1 batch / `get_rag(flush=True)`) close the conn cleanly via context-manager scope-exit instead of leaking.

## What Changed

| Site | Before | After |
| ---- | ------ | ----- |
| Imports (L21-L29) | `import asyncio` → `import hashlib` | `import asyncio` → `import contextlib` → `import hashlib` (alphabetical) |
| Docstring (~L1573) | ends with quick-260518 paragraph | new `quick-260519 (H3):` paragraph appended explaining the leak-window closure |
| L1583 (now L1590) | `conn = sqlite3.connect(str(DB_PATH))` | `with contextlib.closing(sqlite3.connect(str(DB_PATH))) as conn:` |
| Body (L1584..L2129 → L1591..L2136) | flat at 4-space indent | +4 spaces leading whitespace (546 lines reindented; blank lines preserved as blank) |
| Early-return on `if not rows:` (was L1624) | `conn.close(); return` | `return` (context manager owns close) |
| Early-return on `if not candidate_rows:` (was L1699) | `conn.close(); return` | `return` |
| Inner-finally tail (was L2129) | `logger.info(...); conn.close()` | `logger.info(...)` |

Result: zero `conn.close()` occurrences inside `ingest_from_db()` (verified via grep — was 3, now 0).

## Verification (PRINCIPLE #7 evidence)

| Gate | Command | Result | Evidence |
| ---- | ------- | ------ | -------- |
| Pre-change pytest | `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v` | **5 passed in 2.14s** | `.scratch/quick-260519-h3-pytest-prechange.log` |
| AST parse (post-reindent) | `python -c "import ast; ast.parse(open('batch_ingest_from_spider.py').read())"` | **AST parse OK** | inline output |
| AST parse (post-removals) | (same) | **AST parse OK** | inline output |
| Post-change pytest | `venv/Scripts/python.exe -m pytest tests/unit/test_ingest_from_db_orchestration.py -v` | **5 passed in 2.14s** | `.scratch/quick-260519-h3-pytest-postchange.log` |
| CLI smoke | `python batch_ingest_from_spider.py --help \| head -30` | exit 0; usage + all flags listed | inline output |
| Diff -w line count | `git diff HEAD -w -- batch_ingest_from_spider.py \| wc -l` | **58 lines** (close to plan's ~30-40 expectation; substance is small) | inline output |
| Diff stat | `git diff --stat HEAD -- batch_ingest_from_spider.py` | **494 insertions, 490 deletions** (reindent dominates) | inline output |
| Done-criteria grep #1 | `grep -n "import contextlib" batch_ingest_from_spider.py` | line 23 | inline output |
| Done-criteria grep #2 | `grep -n "with contextlib.closing(sqlite3.connect" batch_ingest_from_spider.py` | line 1590 (exactly one match) | inline output |
| Done-criteria grep #3 | `grep -c "conn.close()" batch_ingest_from_spider.py` | 0 | inline output |
| Done-criteria grep #4 | `grep -n "quick-260519 (H3):" batch_ingest_from_spider.py` | line 1575 | inline output |
| Commit attribution | `git show --stat HEAD` | only `batch_ingest_from_spider.py` (494/+ 490/-) — no concurrent-quick file absorption | inline output |

The 5 anchored test behaviors (T1 dual-source skip_reason_version, T2 image_count queue.append shape, T3 max_articles cap, T4 finally drain, T5 image_count_row stale-0 + post-vision body markers) are all preserved on both sides of the refactor.

## Commits

| Hash | Subject | Files | Insertions | Deletions |
| ---- | ------- | ----- | ---------- | --------- |
| `2c273dd` | refactor(quick-260519-h3): wrap ingest_from_db in contextlib.closing(conn) | batch_ingest_from_spider.py | 494 | 490 |

Pushed: `3c849c4..2c273dd  main -> main` (no rebase needed despite intervening commits — explicit-add hygiene held).

## Concurrency Safety Notes

Concurrent dirty paths in working tree at task start (kdb-2-04 + kb-v2.2 translation track):
- `databricks-deploy/app.yaml`, `databricks-deploy/_wave0_probe.py`, `databricks-deploy/app.yaml.production-backup`
- `kb/api_routers/articles.py`, `kb/templates/article.html`, `kb/services/translation.py`, `kb/data/migrations/*`
- `tests/integration/kb/conftest.py`
- `.planning/STATE-KB-v2.md`, `.planning/phases/kdb-2-databricks-app-deploy/*`

`git show --stat HEAD` confirms commit `2c273dd` contains exclusively `batch_ingest_from_spider.py` — no concurrent-quick paths absorbed. Per memory `feedback_git_add_explicit_in_parallel_quicks.md`: explicit `git add batch_ingest_from_spider.py` chained with `&& commit && push` in a single Bash invocation eliminated the absorption-window risk.

Per memory `feedback_no_amend_in_concurrent_quicks.md`: no `git commit --amend`, no `git reset --soft`, no force-push. Forward-only.

## Hermes Production Validation

Tomorrow (2026-05-19 08:15 ADT) Hermes natural daily-ingest cron will exercise the refactored code path on real production traffic. Behavior should be identical to today's pre-cron baseline; the only observable change is that any exception in the init window (which historically would leak the conn) will now close it cleanly. Cron metrics should be unchanged.

## Out of Scope (deferred)

None — the plan was a single-file structural refactor; no scope creep observed.

## Self-Check: PASSED

- Modified file `batch_ingest_from_spider.py`: present (verified via Edit tool execution + final grep at expected line numbers)
- Commit `2c273dd`: present in `git log` (verified via `git show --stat HEAD`)
- Pytest evidence files in `.scratch/`:
  - `.scratch/quick-260519-h3-pytest-prechange.log` (5 passed, 2.14s)
  - `.scratch/quick-260519-h3-pytest-postchange.log` (5 passed, 2.14s)
- Reindent helper script: `.scratch/h3_reindent.py` (audit trail; idempotent if rerun, but uniqueness asserts would fire on rerun since the original anchor no longer exists — single-use by design)

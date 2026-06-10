# Quick Task 260610-rgm — 4-Issue Surgical Cluster — SUMMARY

**Mode:** `/gsd:quick --full` (YOLO cluster, executed inline in main session)
**Date:** 2026-06-11 (CST) / 2026-06-10 (UTC evening)
**Scope:** Ship 4 independent surgical fixes (#45 #47 #48 #29) in 4 atomic
commits + 1 docs commit, forward-only `push origin/main` after each. TDD gate
per fix; each fix independent (failure of one must not block the rest).

## Objective

Close a 4-issue cluster surfaced by the 2026-06-11 Aliyun backup PHASE-0 block:
the #45 ingest post-completion hang (3rd cross-platform recurrence), its #47
atomic-write-patch fragility sibling, the #48 backup/hang interaction, and the
#29 server-side citation carry-over. Repo push only — no Aliyun SSH; Aliyun
auto-pulls on cron.

## Fix outcomes

| Fix | Title | Status | Commit(s) | Tests |
|-----|-------|--------|-----------|-------|
| #45 | os._exit(0) bypasses third-party C-thread join | ✅ PASS (RESOLVED-PENDING-ALIYUN-VERIFY) | `352dd01` | 2/2 |
| #47 | sitecustomize atomic-write survives pip reinstall | ✅ PASS | `62e49a3` | 2/2 |
| #48 | backup `--ignore-active-if-quiesced` quiesce gate | ✅ PASS | `dd845c9` + `a9c4f44` | 3/3 |
| #29 | server-side citation regex sweep | ✅ PASS | `8f5d147` | 10/10 |
| docs | ISSUES.md cluster close (R29-R32) + STATE.md | ✅ | _(this commit)_ | n/a |

**17 new tests, all green local.** Pre-existing 4 `test_synthesize_hotfix`
DB-fixture errors confirmed present on parent commit (not introduced here).

## What shipped

### #45 — `batch_ingest_from_spider.py` main()
After `asyncio.run(coro)` returns, add `sys.stdout.flush()` +
`sys.stderr.flush()` + `logging.shutdown()` + `os._exit(0)`. Bypasses
`Py_Finalize()`'s join on stateless third-party connection-pool threads (Vertex
SDK HTTP/2, google-genai, qdrant-client gRPC). KeyboardInterrupt branch
(`sys.exit(130)`) byte-identical. Repo grep confirmed 0 atexit handlers + 0
application-side `threading.Thread`, so nothing application-side is skipped.
Test: `tests/unit/test_main_hard_exit.py` — `--help` exits ≤5s + source-grep
tripwire.

### #47 — `lib/lightrag_atomic_write_patch.py` + `scripts/apply_lightrag_atomic_write_patch.sh`
`apply()` monkey-patches `NetworkXStorage.write_nx_graph` to tmp + os.fsync +
os.replace (idempotent, fail-soft). Delivered via `sitecustomize.py` written
into both Aliyun venvs (`venv-aim1` + `venv`) by the shell script — fires at
interpreter startup, survives `pip install --force-reinstall lightrag` that
would revert the 260608-e8l in-place edit. **Local venv was vanilla
(unpatched), confirming the fragility premise.** Test:
`tests/unit/test_lightrag_atomic_write_persistence.py` — atomic source markers
+ idempotency, with save/restore fixture to avoid leaking class state.

### #48 — `scripts/aliyun-backup-260610.sh` (+ working copy `.scratch/`)
PHASE 0 wait-loop gains `--ignore-active-if-quiesced` (default true). When an
ingest svc is active, deep-probe: 0 real-file fds (`/proc/$PID/fd`) + 0 `*.tmp`
in storage dir + parseable graphml; all 3 → `QUIESCED — proceeding` + break.
`__quiesce_probe` testability seam. Test:
`tests/unit/test_backup_quiesce_gate.py` — quiesced→pass, open-fd→block,
.tmp-orphan→block.

### #29 — `kb/services/synthesize.py`
`_normalize_citations(md)` applied before source resolution + return: 7 orphan
citation formats → `[hash6](articles/<hash>.html)`, plus `_dedupe_reference_sections`
keeps the link-densest References block. Mirrors qa.js Pass 1 + Pass 2 +
dedupe; qa.js retained (defense-in-depth + cached pre-fix responses). Test:
`tests/unit/test_citation_normalize.py` — 7 format cases + dual-References
dedupe + already-clean idempotency + no-double-process (10 total).

## Deviations handled (forward-only, no --amend)

1. **#48 first commit silently dropped the script.** `.scratch/` is gitignored;
   `git add .scratch/aliyun-backup-260610.sh` was refused, so `dd845c9`
   committed only the test (which referenced a path Aliyun could never receive
   via pull). Fixed forward in `a9c4f44`: relocated the deployable script to
   tracked `scripts/aliyun-backup-260610.sh` and repointed the test. The
   `.scratch/` copy stays as the local working artifact.
2. **#48 test path portability.** `str(WindowsPath)` emits backslashes that
   broke the bash glob + the embedded `python -c` graphml literal (`\U` escape).
   Fixed with `.as_posix()` — test-harness-only (Aliyun is Linux).

## Constraints honored

- NO Aliyun SSH (repo push only; Aliyun pulls on cron).
- NO `--amend`, NO `git reset --soft`, NO `--no-verify`, NO `-A` / `.` —
  explicit `git add <files>` per commit.
- Forward-only `push origin/main` after each commit (5 pushes:
  `4131c19→352dd01→62e49a3→dd845c9→a9c4f44→8f5d147→` docs).
- Did NOT touch systemd override.conf, ROADMAP.md, or CLAUDE.md.

## Aliyun verification (deferred, not this quick's scope)

Next 08:00 CST `omnigraph-daily-ingest` cron pulls main. Verify journalctl
shows clean exit ≤5s after `Metrics written` (NOT 1h27min S-state). To wire
#47 on Aliyun: `bash scripts/apply_lightrag_atomic_write_patch.sh` after deploy
(sitecustomize files are gitignored — the script is the delivery mechanism). If
#45 recurs after pull, escalate to `/gsd:plan-phase` (Vertex SDK shutdown
contract investigation).

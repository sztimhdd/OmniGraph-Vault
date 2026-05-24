# aim-4-2 — sync-from-aliyun.sh authoring + smoke evidence

**Timestamp:** 2026-05-24 20:43–20:45 ADT (Hermes-side smoke executed
2026-05-24 23:43–23:45 UTC; agent ran SSH from Windows dev box)
**Plan:** aim-4-2
**REQs:** SYNC-01, SYNC-04
**Status:** PASS
**Predecessor:** aim-4-1 (commit `d9cf8da`, fingerprint
`SHA256:qCDafXLDZwf2U6M69vkAzKkVNeKaQzEU/cOxam6rWUo`)

## Script

- Path: `scripts/sync-from-aliyun.sh`
- Mode: 0755 (verified post-commit via `git ls-files --stage`)
- `bash -n scripts/sync-from-aliyun.sh` syntax check: exit 0
- 4 sync targets verified in source via `grep -E
  '/root/OmniGraph-Vault/kb/output/articles/|/root/OmniGraph-Vault/data/kol_scan.db|/root/\.hermes/omonigraph-vault/images/|/root/OmniGraph-Vault/kb/wiki/'`
  → exactly 4 lines.
- `delays=(60 300 1800)` present (1 line).
- `rm -f /tmp/aliyun-sync-failed-*` present (stale-marker cleanup,
  FINDING 10).
- `BatchMode=yes` present in `SSH_OPTS`.
- `set -u` present; `set -e` intentionally omitted (per plan §Acc #3).

## First-run smoke on Hermes (cold cache, BUT pre-existing 1.5G images)

Pre-sync state on Hermes: `~/.hermes/omonigraph-vault/images/` already
contained 1.5G from prior production cron runs. rsync `-az --delete`
reconciled local against Aliyun (872M canonical), so the wire transfer
was incremental, not full 937 MB. This is expected idempotency
behaviour and acceptable per plan (the 30-min ceiling was a
worst-case greenfield budget; real Hermes had warm cache).

```
=== FIRST RUN START 2026-05-24T23:43:59Z ===
[2026-05-24T23:43:59Z] rsync /root/OmniGraph-Vault/data/kol_scan.db → /home/sztimhdd/.hermes/omonigraph-vault/kol_scan.db
[2026-05-24T23:44:14Z] rsync /root/OmniGraph-Vault/kb/wiki/ → /home/sztimhdd/.hermes/omonigraph-vault/kb/wiki/
[2026-05-24T23:44:20Z] rsync /root/OmniGraph-Vault/kb/output/articles/ → /home/sztimhdd/.hermes/omonigraph-vault/articles/
[2026-05-24T23:44:31Z] rsync /root/.hermes/omonigraph-vault/images/ → /home/sztimhdd/.hermes/omonigraph-vault/images/
[2026-05-24T23:44:40Z] sync OK on attempt 1
FIRST_RC=0

real    0m41.061s
user    0m0.357s
sys     0m0.519s
```

- Wallclock: **41.061 s** (well below 30-min ceiling)
- RC: **0**
- Single-attempt success — no retry/backoff invoked

## Second-run smoke (idempotency proof)

```
=== SECOND RUN START 2026-05-24T23:44:48Z ===
[2026-05-24T23:44:48Z] rsync /root/OmniGraph-Vault/data/kol_scan.db → /home/sztimhdd/.hermes/omonigraph-vault/kol_scan.db
[2026-05-24T23:44:54Z] rsync /root/OmniGraph-Vault/kb/wiki/ → /home/sztimhdd/.hermes/omonigraph-vault/kb/wiki/
[2026-05-24T23:44:59Z] rsync /root/OmniGraph-Vault/kb/output/articles/ → /home/sztimhdd/.hermes/omonigraph-vault/articles/
[2026-05-24T23:45:05Z] rsync /root/.hermes/omonigraph-vault/images/ → /home/sztimhdd/.hermes/omonigraph-vault/images/
[2026-05-24T23:45:08Z] sync OK on attempt 1
SECOND_RC=0

real    0m19.945s
user    0m0.251s
sys     0m0.048s
```

- Wallclock: **19.945 s** (≤ 5 min, idempotency proven)
- RC: **0**
- All 4 targets met-data round-trip only (rsync delta scan); no real
  payload transferred — kol_scan.db `mtime` unchanged, images du
  unchanged (see post-sync inventory).

## Post-sync inventory on Hermes

| Target | Value | Plan expectation | Match |
| --- | --- | --- | --- |
| `~/.hermes/omonigraph-vault/articles/` file count | **1944** HTML files | ≥ 1900 | PASS |
| `~/.hermes/omonigraph-vault/articles/` du | 32 M | ~32 MB | PASS |
| `~/.hermes/omonigraph-vault/kol_scan.db` size | 26,959,872 bytes (25.7 MB) | ≥ 30 MB (loose) | DEVIATION (see note) |
| `~/.hermes/omonigraph-vault/kb/wiki/` contents | `README.md SCHEMA.md _suggestions comparisons concepts entities index.md log.md queries` | dirs `concepts/`, `comparisons/` | PASS (both present, plus extras) |
| `~/.hermes/omonigraph-vault/images/` du | 872 M | matches Aliyun canonical | PASS |

**Deviation note (kol_scan.db size):** Plan §Acc #4 stated DB size
should be `≥ 30 MB`. Actual canonical Aliyun source is 26,959,872
bytes ≈ 25.7 MB (this is the same byte count aim-4-1 dry-run captured
in its EVIDENCE.md, line 76). The 30 MB figure was a planner-side
loose approximation. The byte-exact transfer matches Aliyun source —
no data loss. Recommend forward-fixing the plan's wording on next
edit; not a smoke failure.

## Marker check

```
=== MARKER CHECK ===
NO_MARKER_OK
```

`/tmp/aliyun-sync-failed-*` does NOT exist after success. Confirms
`clean_stale_markers` correctly fired on the success path of `main()`.

## Cleanup

`/tmp/sync-from-aliyun.sh.aim-4-2-smoke` removed from Hermes via
SSH-inline `rm -f` after smoke. CLEANUP_OK echoed.

## Acceptance gates summary (15 items from plan §Acceptance criteria)

| # | Gate | Result |
| --- | --- | --- |
| 1 | `scripts/sync-from-aliyun.sh` exists at top of `scripts/` | PASS |
| 2 | File mode 0755 / `100755` in git index | PASS (verified post-commit) |
| 3 | Header has `#!/usr/bin/env bash` + `set -u`; `set -e` omitted | PASS |
| 4 | 4 sync targets defined exactly (kol_scan.db, kb/wiki/, kb/output/articles/, images/) | PASS |
| 5 | `HERMES_DATA_DIR` defaults to `${HOME}/.hermes/omonigraph-vault` | PASS |
| 6 | `ALIYUN_SSH_KEY` defaults to `${HOME}/.ssh/hermes_to_aliyun_ed25519` | PASS |
| 7 | rsync flags `-az --delete` + `BatchMode=yes` SSH opts | PASS |
| 8 | Retry loop with `delays=(60 300 1800)` then final attempt | PASS |
| 9 | All-success path runs `rm -f /tmp/aliyun-sync-failed-*` before exit 0 | PASS |
| 10 | All-fail path writes marker, emits `ERROR:` to stderr, exits 1 | PASS (code path inspected; not exercised in smoke since first attempt PASS) |
| 11 | `BatchMode=yes` set | PASS |
| 12 | shellcheck-clean | SKIPPED (shellcheck unavailable in agent env; `bash -n` syntax check PASSED instead, per plan §Acc #12 fallback clause) |
| 13 | Smoke first-run RC=0 ≤ 30 min; re-run RC=0 ≤ 5 min near-zero transfer | PASS (41s / 20s) |
| 14 | Smoke evidence in `aim-4-2-EVIDENCE.md` | PASS (this file) |
| 15 | Single forward-only commit with both files | (verified post-commit) |

## References

- Plan: `.planning/phases/aim-4-daily-sync/aim-4-2.md`
- Predecessor evidence: `.planning/phases/aim-4-daily-sync/aim-4-1-EVIDENCE.md`
- aim-4 CONTEXT.md §"sync-from-aliyun.sh skeleton" (lines 192-251)
- REQUIREMENTS-Aliyun-Ingest-Migration-v1.md SYNC-01 (line 71), SYNC-04 (line 74)
- Memory `feedback_aim1_agent_is_operator.md` — agent IS the operator
- Memory `feedback_dont_outsource_ssh.md` — agent ran scp/ssh via Bash
- Memory `feedback_no_literal_secrets_in_prompts.md` — no Hermes/Aliyun host/port/key in committed file body
- Memory `feedback_git_add_explicit_in_parallel_quicks.md` — explicit `git add` of 2 files only
- Memory `feedback_no_amend_in_concurrent_quicks.md` — forward-only commit

## Forward-only correction

Initial commit `996412c` landed the script as mode `100644` (Windows
Git Bash on the corp dev box does not propagate the in-tree `chmod +x`
to the git index — `core.filemode=false` on this clone). Forward-only
follow-up commit `8cc6204` `fix(aim-4): chmod +x scripts/sync-from-aliyun.sh
(Windows core.filemode workaround)` runs `git update-index --chmod=+x`
to flip the index mode to `100755`. Per memory
`feedback_no_amend_in_concurrent_quicks.md`, no `--amend` was used.
Post-fix: `git ls-files --stage scripts/sync-from-aliyun.sh` reports
`100755` (PASS plan §Acc #2).

## Next step

aim-4-3 will install `omnigraph-daily-pull.service` + `.timer` on
Hermes calling this script (via `git pull` of the committed path,
NOT scp anymore). Marker file aging + 7-day STAB-03 monitoring deferred
to aim-5.

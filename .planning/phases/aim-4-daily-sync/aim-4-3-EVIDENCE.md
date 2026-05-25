# aim-4-3 — Hermes systemd timer install evidence

**Timestamp:** 2026-05-25T00:14Z (2026-05-24 21:14 ADT)
**Plan:** aim-4-3
**REQs:** SYNC-02, SYNC-04 (journald wiring)
**Status:** PASS (with 1 deviation, see §Deviations)
**Raw log:** `.scratch/aim-4-3-gates-20260525T001236Z.log`

## Repo files committed

- `deploy/hermes/systemd/omnigraph-daily-pull.service`
- `deploy/hermes/systemd/omnigraph-daily-pull.timer`
- `deploy/hermes/systemd/README.md`

## Hermes deployment timeline

1. Prior agent (a69fc2172415a91a2) staged `/tmp/omnigraph-daily-pull.{service,timer}` on Hermes via `scp`.
2. User granted NOPASSWD for `/bin/systemctl` and `/bin/cp` via `/etc/sudoers.d/sztimhdd-omnigraph`.
3. This agent ran `sudo cp /tmp/omnigraph-daily-pull.{service,timer} /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now omnigraph-daily-pull.timer` — Created symlink `/etc/systemd/system/timers.target.wants/omnigraph-daily-pull.timer`.
4. After G5 revealed Hermes TZ = `America/Halifax` (not UTC as plan README assumed), repo timer file fixed (`OnCalendar=*-*-* 05:00:00` → `OnCalendar=*-*-* 05:00:00 UTC`), redeployed via scp + `sudo cp` + `daemon-reload` + `restart`.

## Gate results (raw outputs in log lines noted)

| Gate | Check | Pass | Log line |
| --- | --- | --- | --- |
| G1 | service file deployed content matches repo | PASS | `.scratch/aim-4-3-gates-20260525T001236Z.log` L21-34 (G1-retry, world-readable read; sudo cat earlier blocked because `/bin/cat` not in NOPASSWD list, irrelevant — file content identical to repo) |
| G2 | timer file deployed content matches repo (post-fix `UTC` suffix) | PASS | log L35-44 (G2-retry); plus L73-89 redeploy section showing fixed file installed |
| G3 | `systemctl is-enabled omnigraph-daily-pull.timer` → `enabled` | PASS | log L7-8 |
| G4 | `systemctl is-active omnigraph-daily-pull.timer` → `active` | PASS | log L9-10 |
| G5 | next fire 05:00 UTC = 02:00 ADT | PASS | log L65-69 (final, post-UTC fix): `Mon 2026-05-25 02:00:00 ADT  4h 46min ... omnigraph-daily-pull.timer` |
| G6 | `crontab -l \| grep -cE "ingest\|kol_scan\|rss"` returns 0 | PASS | log L13-14 |
| G7 | `systemctl list-timers --all --no-pager \| grep -c omnigraph-` ≥ 1 | PASS | log L15-16 (returns `1`) |
| G8 | manual fire `Result=success` | PASS | log L77-83: `Result=success ExecMainStatus=0 ActiveState=inactive SubState=dead` |
| G9 | journalctl shows rsync log lines | PASS | log L92-104: 4 `rsync` lines + `sync OK on attempt 1`, exit `code=exited, status=0/SUCCESS` |

## REQ traceability

### SYNC-02 — Hermes-side daily-pull cron installed, schedule 02:00 ADT, output lands at `~/.hermes/omonigraph-vault/`, Hermes net cron count: 11 → 1

- ✅ Daily-pull installed as systemd timer (Hermes WSL2 has systemd, per plan FINDING 3) — G3 + G4 + G7
- ✅ Schedule 02:00 ADT — G5 next fire `Mon 2026-05-25 02:00:00 ADT` (= 05:00 UTC, explicit `UTC` suffix on `OnCalendar` value)
- ✅ Output lands at `~/.hermes/omonigraph-vault/` — G9 journal shows rsync targets `/home/sztimhdd/.hermes/omonigraph-vault/{kol_scan.db, kb/wiki/, articles/, images/}`
- ✅ Net cron count 11 → 1 — G6 returns 0 legacy ingest cron lines (aim-3 cleared them); G7 returns exactly 1 omnigraph- timer

### SYNC-04 — journald wiring captures retry attempts + ERROR lines from `scripts/sync-from-aliyun.sh`

- ✅ `StandardOutput=journal` + `StandardError=journal` set in service unit — G1 deployed file shows both directives
- ✅ `journalctl -u omnigraph-daily-pull.service -n 100` captures real script output — G9 log L92-104 shows 5 `sync-from-aliyun.sh[PID]:` log lines per fire (4 rsync + 1 success summary), confirming stdout flowed through journal

## Deviations

### Rule 1 (auto-fix bug) — timer schedule mismatch with REQ SYNC-02 due to TZ assumption

**Found during:** G5 verification.

**Issue:** Plan README claimed "Hermes WSL2 uses UTC system clock"; in reality `timedatectl` reports `Time zone: America/Halifax (ADT, -0300)` (log L52-55). With local TZ = ADT, the bare `OnCalendar=*-*-* 05:00:00` was interpreted as 05:00 ADT (= 08:00 UTC), violating REQ SYNC-02's "02:00 ADT" contract.

**Fix:** Append explicit `UTC` suffix to `OnCalendar` value — `OnCalendar=*-*-* 05:00:00 UTC`. Also updated `deploy/hermes/systemd/README.md` Schedule table + ADT/UTC narrative to document the actual host TZ (`America/Halifax`) and explain why the explicit `UTC` suffix is required regardless of host TZ drift / DST.

**Files modified:**
- `deploy/hermes/systemd/omnigraph-daily-pull.timer` (line 6: added ` UTC`)
- `deploy/hermes/systemd/README.md` (Schedule §)

**Re-deploy:** scp → `sudo cp` → `sudo systemctl daemon-reload` → `sudo systemctl restart omnigraph-daily-pull.timer`. G5 final shows next fire = `Mon 2026-05-25 02:00:00 ADT` (= 05:00 UTC), satisfying REQ SYNC-02 verbatim.

**Commit:** rolled into the single forward-only commit for this plan; no separate fix commit (fix happened pre-commit during execution).

## Manual fire smoke

- Trigger: `sudo systemctl start omnigraph-daily-pull.service` at 2026-05-25T00:13:54Z
- Completion: 2026-05-24 21:14:09 ADT (= 00:14:09 UTC) — wall-clock ~21s (warm cache, expected per aim-4-2 cold-cache benchmark)
- `systemctl show -p Result -p ExecMainStatus`: `Result=success ExecMainStatus=0`
- Exit code: 0
- journalctl tail (G9 log L93-104):
  - `rsync /root/OmniGraph-Vault/data/kol_scan.db → /home/sztimhdd/.hermes/omonigraph-vault/kol_scan.db`
  - `rsync /root/OmniGraph-Vault/kb/wiki/ → /home/sztimhdd/.hermes/omonigraph-vault/kb/wiki/`
  - `rsync /root/OmniGraph-Vault/kb/output/articles/ → /home/sztimhdd/.hermes/omonigraph-vault/articles/`
  - `rsync /root/.hermes/omonigraph-vault/images/ → /home/sztimhdd/.hermes/omonigraph-vault/images/`
  - `sync OK on attempt 1`

## Net cron count audit

- `crontab -l 2>/dev/null | grep -cE "ingest|kol_scan|rss"`: 0 (G6)
- `systemctl list-timers --all --no-pager | grep -c omnigraph-`: 1 (G7) — only `omnigraph-daily-pull.timer`
- Net Hermes-side OmniGraph scheduled jobs: **1** (per SYNC-02 "11 → 1" target)

## References

- `.planning/phases/aim-4-daily-sync/aim-4-CONTEXT.md` §Hermes systemd units
- `.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` SYNC-02, SYNC-04
- `.planning/phases/aim-4-daily-sync/aim-4-2-EVIDENCE.md` (sync-from-aliyun.sh shipped to Hermes)
- `scripts/sync-from-aliyun.sh` (called by ExecStart)
- Raw gate log: `.scratch/aim-4-3-gates-20260525T001236Z.log`

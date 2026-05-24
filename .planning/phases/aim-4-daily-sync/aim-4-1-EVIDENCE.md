# aim-4-1 — Hermes → Aliyun SSH key bootstrap evidence

**Timestamp:** 2026-05-24 20:36 ADT (Hermes-side keygen) / 2026-05-25 07:36 CST (Aliyun-side append)
**Plan:** aim-4-1
**Status:** PASS

## Key generated

- Path on Hermes: `~/.ssh/hermes_to_aliyun_ed25519` (mode 600, 419 bytes)
- Pubkey path on Hermes: `~/.ssh/hermes_to_aliyun_ed25519.pub` (mode 644, 109 bytes)
- SHA-256 fingerprint: `SHA256:qCDafXLDZwf2U6M69vkAzKkVNeKaQzEU/cOxam6rWUo`
- Algorithm: ED25519 (256-bit)
- Comment: `hermes-to-aliyun-2026-05-24`
- Status: NEW_KEY_GENERATED (no prior key existed at this path; clean greenfield)

ssh-keygen -lf output:

```
256 SHA256:qCDafXLDZwf2U6M69vkAzKkVNeKaQzEU/cOxam6rWUo hermes-to-aliyun-2026-05-24 (ED25519)
```

ls -la output:

```
-rw------- 1 sztimhdd sztimhdd 419 May 24 20:36 /home/sztimhdd/.ssh/hermes_to_aliyun_ed25519
-rw-r--r-- 1 sztimhdd sztimhdd 109 May 24 20:36 /home/sztimhdd/.ssh/hermes_to_aliyun_ed25519.pub
```

## Pubkey installed on Aliyun

- File: `/root/.ssh/authorized_keys`
- Backup: `/root/.ssh/authorized_keys.bak-pre-aim4-1-20260525-073631`
- Line delta: PRE=4 POST=5 DELTA=1
- File mode: 600 (unchanged; 550 bytes post-append)

ls -la output post-append:

```
-rw------- 1 root root 550 May 25 07:36 /root/.ssh/authorized_keys
```

Tail confirms the appended line is intact (single line, no wrap, comment preserved). The line ends with the comment `hermes-to-aliyun-2026-05-24` exactly as expected; per `feedback_no_literal_secrets_in_prompts.md` the pubkey body is NOT reproduced here. Identity is captured via the SHA-256 fingerprint above (`SHA256:qCDafXLDZwf2U6M69vkAzKkVNeKaQzEU/cOxam6rWUo`).

## Validation 1 — non-interactive SSH (BatchMode=yes)

Command (executed from Hermes via nested SSH):

```
ssh -i ~/.ssh/hermes_to_aliyun_ed25519 \
    -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    root@101.133.154.49 hostname
```

stdout: `iZuf65iclmdqtv2ol6cazcZ`
exit: 0

`BatchMode=yes` would have caused non-zero exit if any password prompt was attempted; clean exit proves pubkey auth works end-to-end.

## Validation 2 — dry-run rsync

Command (executed from Hermes via nested SSH):

```
rsync --dry-run -av \
  -e 'ssh -i ~/.ssh/hermes_to_aliyun_ed25519 -o BatchMode=yes' \
  root@101.133.154.49:/root/OmniGraph-Vault/data/kol_scan.db /tmp/ \
  && echo 'RSYNC_DRYRUN_OK'
```

stdout snippet:

```
receiving incremental file list
kol_scan.db

sent 27 bytes  received 57 bytes  15.27 bytes/sec
total size is 26,959,872  speedup is 320,950.86 (DRY RUN)
RSYNC_DRYRUN_OK
```

exit: 0

File `kol_scan.db` is reachable, total size 26,959,872 bytes (~25.7 MB). No transfer occurred (dry-run); proves rsync-over-SSH protocol negotiation + remote path access work via the new key.

## Acceptance gates summary

| # | Gate | Result |
| --- | --- | --- |
| 1 | ed25519 keypair on Hermes (600 / 644 modes) | PASS |
| 2 | Pubkey appended to Aliyun authorized_keys; line-delta = 1; mode 600 preserved; backup created | PASS |
| 3 | Non-interactive SSH (BatchMode=yes) returns hostname, exit 0 | PASS |
| 4 | Dry-run rsync exits 0, file-list mentions `kol_scan.db` | PASS |
| 5 | Evidence file exists with fingerprint (not pubkey body) | PASS (this file) |
| 6 | No literal pubkey or private key material in evidence | PASS — pre-commit grep guard |
| 7 | Single forward-only commit with explicit `git add` of evidence file only | (verified post-commit) |

## References

- Plan: `.planning/phases/aim-4-daily-sync/aim-4-1.md`
- aim-4 CONTEXT.md §"Hermes → Aliyun SSH key bootstrap (prereq plan)" (lines 290-304)
- Memory `feedback_dont_outsource_ssh.md` — agent IS the operator, ran SSH via Bash
- Memory `feedback_aim1_agent_is_operator.md` — aim-N PLAN "operator" language overridden
- Memory `feedback_no_literal_secrets_in_prompts.md` — fingerprint only, no key body
- Memory `feedback_git_add_explicit_in_parallel_quicks.md` — explicit `git add`, atomic chain
- Memory `feedback_no_amend_in_concurrent_quicks.md` — forward-only commits

## Next step

`scripts/sync-from-aliyun.sh` (aim-4-3) can now reference this key (`~/.ssh/hermes_to_aliyun_ed25519`) for non-interactive rsync from Aliyun. SYNC-01..04 are unblocked.

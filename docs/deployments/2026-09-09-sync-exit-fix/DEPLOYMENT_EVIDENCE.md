# Hermes sync exit-status fix deployment evidence

Date: 2026-09-09

Scope: only `/home/sztimhdd/OmniGraph-Vault/scripts/sync-from-aliyun.sh` on
Hermes PC. No service, timer, scheduler, runtime data, environment file, Git
commit, or push was changed.

## Preconditions

- SSH alias `OHPC` reported hostname `OH-Desktop` before every remote mutation
  and verification command.
- Remote target pre-deployment SHA-256:
  `a53a284f8a7c6990fc1ba9deaa672d9d013a2fdb320532680c40d3ad19f68451`
- `git status --short -- scripts/sync-from-aliyun.sh` on Hermes was empty.
- That SHA-256 matched `git show HEAD:scripts/sync-from-aliyun.sh` locally.
- The local reviewed candidate SHA-256:
  `ce7148702119e2cf9c30f4ac032c3d390b8eb4160bfc544db37d609ba7dd4e1d`
- Original target mode: `775`.

## Change and backup

The sole diff changes the `do_rsync_all` failure branch from `if ! command;
then code=$?` to a positive success condition plus `else`, so `$?` retains the
failing rsync status.

- Backup:
  `/home/sztimhdd/.local/share/vitax-backups/sync-exit-fix-2026-09-09/sync-from-aliyun.sh.pre-ce7148702119`
- Backup mode: `775`
- Backup SHA-256:
  `a53a284f8a7c6990fc1ba9deaa672d9d013a2fdb320532680c40d3ad19f68451`
- Install method: staged `install -m 775` in the target directory, then same-
  directory `mv -f`.

## Verification

- Local: `.venv/bin/python -m pytest tests/unit/test_sync_from_aliyun_exit_status.py -q`
  returned `4 passed in 0.34s`.
- Remote candidate: `bash -n` returned zero; the diff contained only the
  failure-status branch described above.
- Remote offline stub harness ran the candidate from `/tmp` with fake `rsync`,
  `ssh`, `sleep`, `rm`, and `touch`; it never called the fake `ssh`.
  - Persistent fake rsync failures: exit `1`, 16 fake rsync calls.
  - Immediate fake rsync success: exit `0`, 4 fake rsync calls.
- Installed target: `bash -n` returned zero; mode is `775`; SHA-256 is
  `ce7148702119e2cf9c30f4ac032c3d390b8eb4160bfc544db37d609ba7dd4e1d`.

## Reproducible rollback

```bash
ssh OHPC 'set -eu
test "$(hostname)" = OH-Desktop
target=/home/sztimhdd/OmniGraph-Vault/scripts/sync-from-aliyun.sh
backup=/home/sztimhdd/.local/share/vitax-backups/sync-exit-fix-2026-09-09/sync-from-aliyun.sh.pre-ce7148702119
staged="${target}.rollback-sync-exit-fix.$$"
trap "rm -f \"$staged\"" EXIT
backup_hash=$(sha256sum "$backup" | cut -d " " -f1)
test "$backup_hash" = a53a284f8a7c6990fc1ba9deaa672d9d013a2fdb320532680c40d3ad19f68451
install -m 775 "$backup" "$staged"
mv -f "$staged" "$target"
trap - EXIT
bash -n "$target"
sha256sum "$target"'
```

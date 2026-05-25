---
plan_id: aim-4-1
phase: aim-4
wave: 1
depends_on: []
requirements_addressed: []
files_modified:
  - .planning/phases/aim-4-daily-sync/aim-4-1-EVIDENCE.md
autonomous: true
t_shirt: S
---

# aim-4-1 — Hermes → Aliyun SSH key bootstrap (prereq for SYNC-01)

## Goal

Establish a non-interactive SSH connection from Hermes (`ohca.ddns.net`, user
`sztimhdd`) to Aliyun (`101.133.154.49`, user `root`) using a dedicated
ed25519 key pair generated on Hermes. Without this, the systemd-driven
`scripts/sync-from-aliyun.sh` (aim-4-3) will silently fail on first fire
because rsync-over-SSH will hit the password prompt and return non-zero.

This is a prereq plan with NO REQ coverage (it gates SYNC-01..04 but
implements none of them directly). It produces no repo files except an
evidence markdown documenting the bootstrap. The actual key pair lives
ONLY on Hermes (private) and Aliyun `/root/.ssh/authorized_keys` (public).

This plan is executor-driven (agent IS the operator per
`feedback_aim1_agent_is_operator.md`). The agent runs the SSH commands
directly via the Bash tool. NO operator-channel prompts.

## Acceptance criteria

1. New ed25519 key pair exists on Hermes: `~/.ssh/hermes_to_aliyun_ed25519`
   (private) + `~/.ssh/hermes_to_aliyun_ed25519.pub` (public).
2. The pubkey contents have been appended to Aliyun
   `/root/.ssh/authorized_keys`. Existing keys in that file are NOT touched.
3. From Hermes, `ssh -i ~/.ssh/hermes_to_aliyun_ed25519
   -o BatchMode=yes -o StrictHostKeyChecking=accept-new
   root@101.133.154.49 'hostname'` returns Aliyun's hostname WITHOUT
   prompting for password and WITHOUT non-zero exit.
4. From Hermes, a smoke rsync `rsync --dry-run -az
   -e 'ssh -i ~/.ssh/hermes_to_aliyun_ed25519 -o BatchMode=yes'
   root@101.133.154.49:/root/OmniGraph-Vault/data/kol_scan.db /tmp/`
   exits 0 and reports the file-list line for `kol_scan.db`.
5. Evidence markdown
   `.planning/phases/aim-4-daily-sync/aim-4-1-EVIDENCE.md`
   exists in repo recording: timestamp, Hermes pubkey fingerprint
   (`ssh-keygen -lf` output — fingerprint only, never the pubkey
   itself), Aliyun smoke `hostname` output, smoke rsync exit code.
6. No literal pubkey or private key material is committed to the repo.
   Only the SHA-256 fingerprint string from `ssh-keygen -lf` is allowed
   (not sensitive — fingerprints are public-safe identifiers).
7. Single forward-only commit on `main` containing the evidence file
   only. No `-A` git add. Commit message in conventional commits
   format: `docs(aim-4): SSH key bootstrap evidence (aim-4-1)`.

## Task list

### Task 1 — Generate ed25519 key pair on Hermes

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md` lines 290-304 (SSH key bootstrap recipe)
- Memory `hermes_ssh.md` (Hermes SSH connection: port 49221, user sztimhdd)
- Memory `feedback_dont_outsource_ssh.md` (run SSH yourself via Bash, don't hand commands to user)

**`<acceptance_criteria>`**
- `~/.ssh/hermes_to_aliyun_ed25519` exists on Hermes with mode 600.
- `~/.ssh/hermes_to_aliyun_ed25519.pub` exists on Hermes with mode 644.
- The pubkey starts with `ssh-ed25519 AAAA` and ends with a comment
  containing `hermes-to-aliyun` (use `-C "hermes-to-aliyun-$(date +%Y-%m-%d)"`).
- If a key file already exists at that path (rare but possible from a
  prior aborted attempt), STOP — do NOT overwrite. Manually inspect on
  Hermes via `ssh-keygen -lf <path>` and decide whether to reuse or
  remove + regenerate. Write the decision into the evidence file.

**`<action>`**

Run via Bash tool (replace nothing; the SSH alias `-p 49221 sztimhdd@ohca.ddns.net` is per memory):

```bash
ssh -p 49221 sztimhdd@ohca.ddns.net 'set -e; \
  if [ -f ~/.ssh/hermes_to_aliyun_ed25519 ]; then \
    echo "EXISTING_KEY"; ssh-keygen -lf ~/.ssh/hermes_to_aliyun_ed25519; \
  else \
    ssh-keygen -t ed25519 -f ~/.ssh/hermes_to_aliyun_ed25519 -N "" \
      -C "hermes-to-aliyun-$(date +%Y-%m-%d)"; \
    chmod 600 ~/.ssh/hermes_to_aliyun_ed25519; \
    chmod 644 ~/.ssh/hermes_to_aliyun_ed25519.pub; \
    echo "NEW_KEY_GENERATED"; \
    ssh-keygen -lf ~/.ssh/hermes_to_aliyun_ed25519; \
  fi'
```

Capture the SHA-256 fingerprint line for the evidence file. If output
is `EXISTING_KEY`, decide whether the existing key is acceptable
(likely yes — reuse) or needs regeneration (only if compromised or
corrupted; document the reason in evidence).

### Task 2 — Install pubkey on Aliyun authorized_keys

**`<read_first>`**
- Memory `aliyun_vitaclaw_ssh.md` (Aliyun host 101.133.154.49 root, key
  `~/.ssh/aliyun_orchestrator_ed25519` on dev box, alias `aliyun-vitaclaw`)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md` line 298-300 (`echo "<pubkey>" >> /root/.ssh/authorized_keys` pattern)

**`<acceptance_criteria>`**
- The pubkey (full single-line ed25519 string) appears as a NEW line in
  `/root/.ssh/authorized_keys` on Aliyun.
- Pre-existing lines in `/root/.ssh/authorized_keys` are byte-identical
  before and after the append (verified by `wc -l` delta = 1, and
  `head -n -1` byte-compare).
- File mode of `/root/.ssh/authorized_keys` remains 600 (not modified).
- A backup of the file pre-append exists at
  `/root/.ssh/authorized_keys.bak-pre-aim4-1-$(date +%Y%m%d-%H%M%S)`.

**`<action>`**

Step 1 — capture pubkey from Hermes:

```bash
PUBKEY=$(ssh -p 49221 sztimhdd@ohca.ddns.net 'cat ~/.ssh/hermes_to_aliyun_ed25519.pub')
echo "$PUBKEY" | head -c 80   # sanity: starts with "ssh-ed25519 AAAA..."
```

Step 2 — backup + append on Aliyun (single connection to keep operations atomic):

```bash
ssh aliyun-vitaclaw "set -e; \
  cp /root/.ssh/authorized_keys /root/.ssh/authorized_keys.bak-pre-aim4-1-\$(date +%Y%m%d-%H%M%S); \
  PRE_LINES=\$(wc -l < /root/.ssh/authorized_keys); \
  echo '$PUBKEY' >> /root/.ssh/authorized_keys; \
  POST_LINES=\$(wc -l < /root/.ssh/authorized_keys); \
  echo \"PRE=\$PRE_LINES POST=\$POST_LINES DELTA=\$((POST_LINES - PRE_LINES))\"; \
  test \$((POST_LINES - PRE_LINES)) -eq 1 || { echo 'ERROR: line delta != 1'; exit 1; }; \
  ls -la /root/.ssh/authorized_keys"
```

Capture the `PRE/POST/DELTA` line and `ls -la` output for evidence.

If DELTA != 1, abort and inspect on Aliyun manually before retrying.

### Task 3 — Validate non-interactive SSH + dry-run rsync

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-4-daily-sync\aim-4-CONTEXT.md` line 302-304 (validation pattern)

**`<acceptance_criteria>`**
- `ssh -i ~/.ssh/hermes_to_aliyun_ed25519 -o BatchMode=yes
  -o StrictHostKeyChecking=accept-new root@101.133.154.49 'hostname'`
  exits 0 from Hermes and prints Aliyun's hostname.
- `BatchMode=yes` ensures the test fails (non-zero) if password is
  prompted — this is the critical correctness check. A pass here proves
  pubkey auth works.
- Dry-run rsync from Hermes for `kol_scan.db` exits 0 and the file-list
  output mentions `kol_scan.db`.

**`<action>`**

Run from Hermes (via Bash tool nested SSH):

```bash
# Validation 1: non-interactive ssh
ssh -p 49221 sztimhdd@ohca.ddns.net \
  'ssh -i ~/.ssh/hermes_to_aliyun_ed25519 \
     -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
     root@101.133.154.49 hostname'
# Expected stdout: Aliyun hostname (e.g., iZ8vbf...)
# Expected exit: 0

# Validation 2: dry-run rsync proves rsync-over-ssh works
ssh -p 49221 sztimhdd@ohca.ddns.net \
  "rsync --dry-run -az \
     -e 'ssh -i ~/.ssh/hermes_to_aliyun_ed25519 -o BatchMode=yes' \
     root@101.133.154.49:/root/OmniGraph-Vault/data/kol_scan.db /tmp/ \
     && echo 'RSYNC_DRYRUN_OK'"
# Expected stdout: contains "kol_scan.db" and "RSYNC_DRYRUN_OK"
# Expected exit: 0
```

If Validation 1 fails with "Permission denied (publickey)": pubkey
append in Task 2 either didn't land or has a copy-paste artifact (line
break / trailing whitespace). On Aliyun, `tail -1
/root/.ssh/authorized_keys` should show the exact ed25519 line; if it
is split across 2 lines or has trailing chars, fix manually + re-test.

If Validation 1 fails with "Host key verification failed": rare; rerun
with `StrictHostKeyChecking=accept-new` (already in command above) which
adds Aliyun host key to Hermes's `~/.ssh/known_hosts` on first
connection.

Capture both outputs into the evidence file.

### Task 4 — Author evidence markdown + commit

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\CLAUDE.md` Lessons Learned 2026-05-06 #5 + 2026-05-15 #1 (forward-only commits, explicit `git add`, never `-A`)
- Memory `feedback_git_add_explicit_in_parallel_quicks.md`
- Memory `feedback_no_literal_secrets_in_prompts.md` (no pubkey body in
  the evidence file — fingerprint only)

**`<acceptance_criteria>`**
- `.planning/phases/aim-4-daily-sync/aim-4-1-EVIDENCE.md` exists.
- File contains: timestamp, key fingerprint (SHA-256 from
  `ssh-keygen -lf`), authorized_keys line-delta result, smoke
  `hostname` stdout, smoke rsync stdout snippet.
- File does NOT contain: full pubkey, private key, password.
- `grep -E "ssh-ed25519 AAAA|BEGIN.*PRIVATE KEY" .planning/phases/aim-4-daily-sync/aim-4-1-EVIDENCE.md`
  returns 0 matches.
- Single forward-only commit on `main` with explicit `git add` of just
  the evidence file. Commit message:
  `docs(aim-4): SSH key bootstrap evidence (aim-4-1)`.
- `git status` clean post-commit.

**`<action>`**

Use the Write tool to author the evidence file with this skeleton:

```markdown
# aim-4-1 — Hermes → Aliyun SSH key bootstrap evidence

**Timestamp:** <YYYY-MM-DD HH:MM:SS ADT>
**Plan:** aim-4-1
**Status:** PASS

## Key generated

- Path on Hermes: `~/.ssh/hermes_to_aliyun_ed25519` (mode 600)
- Pubkey path on Hermes: `~/.ssh/hermes_to_aliyun_ed25519.pub` (mode 644)
- SHA-256 fingerprint: <output of ssh-keygen -lf>
- Comment: `hermes-to-aliyun-<date>`

## Pubkey installed on Aliyun

- File: `/root/.ssh/authorized_keys`
- Backup: `/root/.ssh/authorized_keys.bak-pre-aim4-1-<ts>`
- Line delta: PRE=<n> POST=<n+1> DELTA=1
- File mode: 600 (unchanged)

## Validation 1 — non-interactive ssh

Command: `ssh -i hermes_to_aliyun_ed25519 -o BatchMode=yes
-o StrictHostKeyChecking=accept-new root@101.133.154.49 hostname`
stdout: <Aliyun hostname>
exit: 0

## Validation 2 — dry-run rsync

Command: `rsync --dry-run -az -e 'ssh -i hermes_to_aliyun_ed25519
-o BatchMode=yes' root@101.133.154.49:/root/OmniGraph-Vault/data/kol_scan.db /tmp/`
stdout snippet: kol_scan.db
exit: 0

## References

- aim-4 CONTEXT.md §"Hermes → Aliyun SSH key bootstrap (prereq plan)"
- Memory `feedback_dont_outsource_ssh.md`
```

Then commit:

```bash
# Sanity guards
grep -E "ssh-ed25519 AAAA|BEGIN.*PRIVATE KEY" .planning/phases/aim-4-daily-sync/aim-4-1-EVIDENCE.md
# Expect: NO matches (exit 1)
test $? -eq 1 || { echo "ERROR: secret material in evidence"; exit 1; }

git add .planning/phases/aim-4-daily-sync/aim-4-1-EVIDENCE.md
git status   # confirm only the evidence file staged
git commit -m "docs(aim-4): SSH key bootstrap evidence (aim-4-1)"
git log -1 --name-only
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| Existing key at `~/.ssh/hermes_to_aliyun_ed25519` from prior attempt | Reuse if fingerprint reasonable (matches a recent timestamp). Do NOT overwrite blindly — record decision in evidence. |
| `authorized_keys` line delta != 1 after append | Restore from backup `cp /root/.ssh/authorized_keys.bak-pre-aim4-1-<ts> /root/.ssh/authorized_keys`. Reattempt with single-line echo. |
| Validation 1 returns "Permission denied (publickey)" | Inspect `tail -1 /root/.ssh/authorized_keys` on Aliyun — likely line wrap or trailing whitespace. Fix manually, re-test. |
| Pubkey or private material accidentally typed into evidence file | DO NOT COMMIT. Re-edit the file to remove. Re-run grep guard. Only commit after grep returns 0 matches. |
| Forward-only correction needed post-commit | New commit with `docs(aim-4): correction — <reason>`. Do NOT amend (per `feedback_no_amend_in_concurrent_quicks.md`). |

## Evidence to capture

- `~/.ssh/hermes_to_aliyun_ed25519.pub` fingerprint (SHA-256)
- Aliyun authorized_keys line-delta = 1
- Validation 1 + 2 stdout + exit codes
- Single commit hash on `main` with the evidence file

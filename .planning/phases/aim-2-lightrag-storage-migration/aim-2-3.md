---
plan_id: aim-2-3
phase: aim-2
wave: 3
depends_on:
  - aim-2-2
requirements_addressed:
  - STORAGE-03
files_modified:
  - .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-03-transfer-evidence.md
autonomous: false
t_shirt: M
---

# aim-2-3 — scp transfer + Aliyun re-hash + extract to holding dir (STORAGE-03)

## Goal

Transfer the Hermes-side tar (from STORAGE-02) to Aliyun via `scp` (NOT rsync `--delete`, NOT resume), re-compute sha256 on Aliyun, byte-compare to Hermes-side hash. **Hard fail on mismatch — abort, do NOT extract, retry transfer.** On hash match, extract the tar into the **holding directory** `/tmp/aim2-extract/lightrag_storage/` on Aliyun (NOT into the production path; production path stays empty until aim-2-5 mv).

This plan introduces the rollback breakpoint of the phase: between STORAGE-03 (extract to holding) and STORAGE-05 (mv to production), the production path stays empty, and a count-mismatch failure at STORAGE-04 means `rm -rf /tmp/aim2-extract/` and retry — production path is never touched on retry.

This plan is the FIRST plan in the phase where the agent SSHes Aliyun directly (per memory `feedback_aim1_agent_is_operator.md` — agent IS the operator on Aliyun side). Hermes-side scp source must still come from the operator (Hermes mutating ops stay operator-channel). The transfer itself is initiated from the Aliyun side as a `scp pull`: the agent on Aliyun runs `scp <hermes-alias>:/tmp/<tar> /tmp/<tar>` — but this requires Aliyun → Hermes SSH access which is NOT a given. The fallback (and recommended path) is operator-driven `scp` push from Hermes, with Aliyun-side hash re-compute by the agent.

## Acceptance criteria

1. `/tmp/lightrag_storage_aim2_<TS>.tar.gz` exists on Aliyun.
2. `/tmp/lightrag_storage_aim2_<TS>.tar.gz.sha256` (the Hermes-side companion) exists on Aliyun, identical bytes to Hermes-side file.
3. Aliyun-side `sha256sum -c /tmp/lightrag_storage_aim2_<TS>.tar.gz.sha256` returns `OK` exit 0.
4. Aliyun-side `sha256sum /tmp/lightrag_storage_aim2_<TS>.tar.gz | awk '{print $1}'` literal hex value matches the Hermes-side hex from STORAGE-02-tar-evidence.md byte-for-byte.
5. Holding directory `/tmp/aim2-extract/lightrag_storage/` exists on Aliyun and contains the extracted tree (verify via `ls /tmp/aim2-extract/lightrag_storage/ | wc -l` ≥ 1).
6. Aliyun production path `/root/.hermes/omonigraph-vault/lightrag_storage/` is **empty** at end of plan (`ls /root/.hermes/omonigraph-vault/lightrag_storage/ 2>/dev/null | wc -l` returns 0; or path does not exist yet — both acceptable).
7. `EVIDENCE/STORAGE-03-transfer-evidence.md` exists, committed, contains both hashes, transfer wallclock duration, holding-dir contents listing.

## Task list

### Task 1 — Operator pushes tar from Hermes to Aliyun via scp

**`<read_first>`**
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 53 (STORAGE-03 wording — scp not rsync, hash compare, abort on mismatch, holding-dir not production path)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-02-tar-evidence.md` (source of TS suffix and Hermes-side hash hex — used for byte-compare)

**`<acceptance_criteria>`**
- Hermes-side `scp` exits 0.
- Aliyun-side: `ls -la /tmp/lightrag_storage_aim2_<TS>.tar.gz /tmp/lightrag_storage_aim2_<TS>.tar.gz.sha256` shows both files with sizes matching Hermes-side.
- Network transfer wallclock recorded (for evidence + future aim-4 sync planning baseline).

**`<action>`**

Agent writes the following operator prompt and asks user to forward to Hermes verbatim. Note: this prompt assumes the Aliyun host is reachable from Hermes via an SSH alias `aliyun-vitaclaw` configured on Hermes (or the operator configures one). If not reachable, see Abort/rollback protocol — alternative is operator-driven multi-hop or Aliyun-side pull.

```hermes-operator-prompt
You are operating the Hermes production host. The aim-2-2 tar.gz + sha256 from a few minutes ago must still exist at /tmp/lightrag_storage_aim2_<TS>.tar.gz. Do NOT delete it after this transfer — it is the 30-day cold backup.

Step 1 — confirm source files still exist:

```bash
TS=$(cat /tmp/aim2-tar-ts.txt | sed 's/^TS=//')
echo "TS=$TS"
TAR=/tmp/lightrag_storage_aim2_${TS}.tar.gz
SHA=/tmp/lightrag_storage_aim2_${TS}.tar.gz.sha256
ls -la "$TAR" "$SHA"
sha256sum -c "$SHA"
```

Step 2 — push BOTH files to Aliyun via scp. The Aliyun host has SSH alias `aliyun-vitaclaw` from operator's local machine; on Hermes you may need to set up the equivalent alias OR use literal user@host. Connection details for Aliyun are in your local Hermes notes — do NOT paste them into the response below.

```bash
echo "=== scp tar (this is the long step — 1.6 GB tar over your link) ==="
time scp "$TAR" aliyun-vitaclaw:/tmp/
echo "scp_tar_exit=$?"

echo "=== scp sha256 companion ==="
time scp "$SHA" aliyun-vitaclaw:/tmp/
echo "scp_sha256_exit=$?"
```

If your Hermes ssh config does not have an `aliyun-vitaclaw` alias, replace with `<user>@<aliyun-host>:/tmp/` using credentials from your Aliyun notes — but do NOT paste the literal user@host into the response.

Step 3 — confirm source files still on Hermes (cold backup retention):

```bash
ls -la "$TAR" "$SHA"
```

Paste FULL output of all 3 steps back, including the `time` reports for each scp (wallclock measurement). Replace any literal user@host values in your output with `<aliyun>` before pasting back if you used a literal instead of the alias.
```

After receiving operator output, the agent moves to Task 2.

### Task 2 — Agent SSHes Aliyun, verifies hash, extracts to holding dir

**`<read_first>`**
- The operator response from Task 1 (in chat) — extracts the literal `TS` value.
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-02-tar-evidence.md` — extracts the literal Hermes-side sha256 hex for byte-compare.
- Memory `aliyun_vitaclaw_ssh.md` (loaded at session start) — provides the `aliyun-vitaclaw` SSH alias.

**`<acceptance_criteria>`**
- Aliyun: `sha256sum -c /tmp/lightrag_storage_aim2_<TS>.tar.gz.sha256` returns `OK` exit 0.
- Aliyun-recomputed hex equals Hermes-side hex byte-for-byte (tested via `diff <(echo $aliyun_hex) <(echo $hermes_hex)` returning empty).
- Aliyun: `/tmp/aim2-extract/lightrag_storage/` exists and contains files (`ls -la /tmp/aim2-extract/lightrag_storage/ | head -10` shows entries).
- Aliyun: `/root/.hermes/omonigraph-vault/lightrag_storage/` either does not exist OR is empty (`ls /root/.hermes/omonigraph-vault/lightrag_storage/ 2>/dev/null | wc -l` returns 0).
- Aliyun: free disk under `/tmp` ≥ tar size + extracted size (~3.2 GB headroom; verify via `df -h /tmp` before extract).

**`<action>`**

Agent runs the following directly via Bash (agent IS operator on Aliyun side per `feedback_aim1_agent_is_operator.md`):

```bash
# Extract TS from operator response (agent reads from chat and substitutes literal value)
TS="<literal value from operator response Step 1>"
HERMES_HEX="<literal sha256 hex value from STORAGE-02-tar-evidence.md>"

ssh aliyun-vitaclaw bash -c "'
TAR=/tmp/lightrag_storage_aim2_${TS}.tar.gz
SHA=/tmp/lightrag_storage_aim2_${TS}.tar.gz.sha256

echo \"=== verify tar + sha256 landed on Aliyun ===\"
ls -la \$TAR \$SHA

echo \"=== free disk under /tmp BEFORE extract (must be > 3 GB headroom) ===\"
df -h /tmp

echo \"=== aliyun-side sha256 recompute ===\"
sha256sum \$TAR

echo \"=== self-consistency check via -c ===\"
sha256sum -c \$SHA

echo \"=== extract to HOLDING dir (NOT production path) ===\"
rm -rf /tmp/aim2-extract
mkdir -p /tmp/aim2-extract
time tar -xzf \$TAR -C /tmp/aim2-extract/
echo \"extract_exit=\$?\"

echo \"=== verify holding-dir layout ===\"
ls -la /tmp/aim2-extract/lightrag_storage/ | head -20
du -sh /tmp/aim2-extract/lightrag_storage/

echo \"=== verify production path is STILL EMPTY (rollback breakpoint) ===\"
ls /root/.hermes/omonigraph-vault/lightrag_storage/ 2>&1 | head -5 || echo \"(path does not exist yet — expected and acceptable)\"
ls /root/.hermes/omonigraph-vault/lightrag_storage/ 2>/dev/null | wc -l
'"
```

Then the agent does the byte-compare locally:

```bash
# Agent extracts ALIYUN_HEX from the ssh output above and compares
ALIYUN_HEX="<literal hex from `sha256sum $TAR` line in ssh output>"
echo "Hermes hex:  $HERMES_HEX"
echo "Aliyun hex:  $ALIYUN_HEX"
[ "$HERMES_HEX" = "$ALIYUN_HEX" ] && echo "MATCH" || echo "MISMATCH — abort per Abort/rollback"
```

If MISMATCH, follow Abort/rollback protocol below — do NOT proceed to Task 3.

### Task 3 — Agent writes STORAGE-03 evidence and commits

**`<read_first>`**
- All output from Task 1 (operator) + Task 2 (agent ssh).

**`<acceptance_criteria>`**
- File `EVIDENCE/STORAGE-03-transfer-evidence.md` exists with: TS literal, Hermes-side hex, Aliyun-side hex, MATCH verdict, transfer wallclock, holding-dir size + ls -la head, production-path-empty proof.
- File committed locally.

**`<action>`**

Use the Write tool to create `.planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-03-transfer-evidence.md`:

```markdown
# STORAGE-03 — scp transfer + Aliyun re-hash + extract evidence

Phase: aim-2 (LightRAG storage full migration)
REQ: STORAGE-03

## Tar identity

- TS suffix: `[literal]`
- Hermes path: `/tmp/lightrag_storage_aim2_[TS].tar.gz`
- Aliyun path (post-scp): `/tmp/lightrag_storage_aim2_[TS].tar.gz`

## Sha256 byte-compare (the integrity gate)

- Hermes-side hex (from STORAGE-02-tar-evidence.md): `[64-char hex]`
- Aliyun-side hex (Aliyun-recomputed): `[64-char hex]`
- Verdict: **MATCH** / MISMATCH

## Aliyun-side `sha256sum -c` self-verify

```
[paste verbatim Aliyun output of `sha256sum -c $SHA`]
```

Expected: ends with `OK`.

## Transfer wallclock

- scp tar duration: `[time output, e.g. "real 4m22s"]`
- scp sha256 companion duration: `[time output]`
- Total: `[sum]`

## Holding directory contents (Aliyun)

```
[paste verbatim ls -la /tmp/aim2-extract/lightrag_storage/ head -20]
```

- du -sh /tmp/aim2-extract/lightrag_storage/: `[literal size]`

## Production path empty check (ROLLBACK BREAKPOINT)

```
[paste verbatim ls /root/.hermes/omonigraph-vault/lightrag_storage/ 2>&1]
```

- Production path entry count: `[N]` (REQUIRED == 0 — the production path MUST still be empty here. STORAGE-05 is the only plan that writes to it.)

## Cold backup retention reminder

Hermes-side `/tmp/lightrag_storage_aim2_[TS].tar.gz` + `.sha256` retained ≥ 30 days (per STORAGE-02-tar-evidence.md retention deadline). Aliyun-side `/tmp/lightrag_storage_aim2_[TS].tar.gz` may be `rm`'d any time after STORAGE-05 succeeds (per CLAUDE.md cleanup discipline — but is OUT of scope for this milestone).
```

Then commit:

```bash
git add .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-03-transfer-evidence.md
git commit -m "docs(aim-2): record STORAGE-03 scp + sha256 match + extract evidence"
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| `scp` exits non-zero on Hermes | Investigate (network / disk / auth). Retry from Task 1. Do NOT proceed to Task 2 until both files transferred. Hermes pause stays in effect. |
| Aliyun `sha256sum -c` returns FAILED | Transfer corrupted in flight. `rm -f /tmp/lightrag_storage_aim2_<TS>.tar.gz /tmp/lightrag_storage_aim2_<TS>.tar.gz.sha256` on Aliyun via `ssh aliyun-vitaclaw rm -f /tmp/lightrag_storage_aim2_<TS>.tar.gz*`. Retry Task 1 from Hermes side. |
| Hermes hex ≠ Aliyun hex (MISMATCH at Task 2) | Same as above — `rm` Aliyun copies and retry from Task 1. Do NOT extract. Do NOT proceed to Task 3. |
| `tar -xzf` exits non-zero | Tar archive corrupted (would have been caught by sha256 already, but handle anyway). `rm -rf /tmp/aim2-extract/` and retry from Task 1. |
| `df -h /tmp` shows < 3 GB free before extract | Stop. Free disk on Aliyun first (e.g., remove old `/tmp/aim2-extract` from prior aborts, remove old aim-0 readiness scratch). Then proceed. |
| Production path NOT empty at end of Task 2 (`/root/.hermes/omonigraph-vault/lightrag_storage/` has files) | UNEXPECTED. The production path was confirmed empty per aim-1 SUMMARYs. Do NOT proceed to STORAGE-04. Investigate via separate quick — content there could be from aim-1 smoke contamination, kb-api leftover, or another agent. Aim-2-5 mv would overwrite, but the audit trail must be clean first. |

If any abort happens, Hermes pause stays in effect (do NOT resume Hermes during retries — operational liveness is owned only by aim-2-1 acceptance and aim-2-5 final cutover). The retry budget is operator's call; suggested ≤ 3 attempts before declaring infrastructure issue and triggering operator review.

## Evidence to capture

- `EVIDENCE/STORAGE-03-transfer-evidence.md` — committed locally.
- Aliyun `/tmp/aim2-extract/lightrag_storage/` exists, owned by root, contents byte-identical to source (proved by sha256 round-trip).
- Hermes `/tmp/lightrag_storage_aim2_<TS>.tar.gz` + `.sha256` retained for cold backup.

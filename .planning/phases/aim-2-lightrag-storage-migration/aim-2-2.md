---
plan_id: aim-2-2
phase: aim-2
wave: 2
depends_on:
  - aim-2-1
requirements_addressed:
  - STORAGE-02
files_modified:
  - .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-02-tar-evidence.md
autonomous: false
t_shirt: S
---

# aim-2-2 — Tar archive on Hermes (STORAGE-02)

## Goal

Create a single `tar.gz` archive of `~/.hermes/omonigraph-vault/lightrag_storage/` on Hermes plus a companion `.sha256` file. The tar lives at `/tmp/lightrag_storage_aim2_<ts>.tar.gz` and is the **only** vehicle for STORAGE-03's scp transfer. Both files (tar + .sha256) are retained on Hermes ≥ 30 days post-cutover as the cold backup of record.

The pause from aim-2-1 MUST still be in effect during this plan; the storage on disk MUST be quiescent or the byte-identical guarantee at STORAGE-04 fails.

## Acceptance criteria

1. Operator-reported `ls -la /tmp/lightrag_storage_aim2_<ts>.tar.gz` shows file with size ≥ 1 GB (sanity floor; current storage ~1.6 GB at 2026-05-20 baseline).
2. Operator-reported `ls -la /tmp/lightrag_storage_aim2_<ts>.tar.gz.sha256` shows the companion sha256 file exists.
3. Operator-reported `sha256sum -c /tmp/lightrag_storage_aim2_<ts>.tar.gz.sha256` returns `OK`.
4. Operator-reported `tar -tzf /tmp/lightrag_storage_aim2_<ts>.tar.gz | head -5` shows top-level entry beginning with `lightrag_storage/`.
5. `EVIDENCE/STORAGE-02-tar-evidence.md` exists, committed locally, contains tar filename, byte size, sha256 hex, top-5 tar entries, retention deadline (ISO date `tar_creation_date + 30 days`).
6. Hermes pause from aim-2-1 still in effect (re-checked at end of plan): `pgrep -f batch_ingest_from_spider` exit 1.

## Task list

### Task 1 — Operator creates tar.gz and sha256 on Hermes

**`<read_first>`**

- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 52 (STORAGE-02 wording — exact tar command, sha256 method, retention requirement)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-01-pause-evidence.md` (confirms pause is in effect — do not proceed if pause not confirmed)

**`<acceptance_criteria>`**

- File `/tmp/lightrag_storage_aim2_<ts>.tar.gz` exists on Hermes with `stat -c %s` ≥ 1073741824 (1 GiB).
- File `/tmp/lightrag_storage_aim2_<ts>.tar.gz.sha256` exists with content matching `<sha256hex>  /tmp/lightrag_storage_aim2_<ts>.tar.gz` shape.
- `sha256sum -c /tmp/lightrag_storage_aim2_<ts>.tar.gz.sha256` returns `OK` exit 0.
- `tar -tzf /tmp/lightrag_storage_aim2_<ts>.tar.gz | head -5` first line starts with `lightrag_storage/`.
- `pgrep -f batch_ingest_from_spider` returns exit 1 (pause still in effect).

**`<action>`**

Agent writes the following operator prompt and asks the user to forward it to Hermes verbatim:

```hermes-operator-prompt
You are operating the Hermes production host. The aim-2-1 pause MUST still be in effect — do not proceed if `crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)"` returns any rows.

Step 1 — re-confirm pause is active:

```bash
echo "=== uncommented ingest lines (expect 0) ==="
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l
echo "=== running ingest workers (expect ALL exit 1) ==="
pgrep -f batch_ingest_from_spider; echo "exit=$?"
pgrep -f batch_scan_kol; echo "exit=$?"
pgrep -f rss_ingest; echo "exit=$?"
```

If any of those FAILS the expected output, STOP and report back; do NOT continue.

Step 2 — capture timestamp and create tar.gz. Use the SAME timestamp suffix for both the tar and its sha256 file:

```bash
TS=$(date -u +"%Y%m%dT%H%M%SZ")
echo "TS=$TS" | tee /tmp/aim2-tar-ts.txt
TAR=/tmp/lightrag_storage_aim2_${TS}.tar.gz
SHA=/tmp/lightrag_storage_aim2_${TS}.tar.gz.sha256

echo "=== source size BEFORE tar ==="
du -sh ~/.hermes/omonigraph-vault/lightrag_storage/

echo "=== creating tar — this may take 1-3 min depending on disk speed ==="
time tar -czf "$TAR" -C ~/.hermes/omonigraph-vault lightrag_storage/

echo "=== tar size ==="
ls -la "$TAR"
stat -c "size=%s bytes (%s / 1073741824 GiB threshold)" "$TAR"
SIZE=$(stat -c %s "$TAR")
if [ "$SIZE" -lt 1073741824 ]; then
  echo "FAIL: tar size $SIZE < 1 GiB sanity floor"
  exit 1
fi

echo "=== computing sha256 ==="
sha256sum "$TAR" > "$SHA"
cat "$SHA"

echo "=== verifying sha256 self-consistency ==="
sha256sum -c "$SHA"

echo "=== top-5 tar entries (must start with lightrag_storage/) ==="
tar -tzf "$TAR" | head -5

echo "=== final ls ==="
ls -la "$TAR" "$SHA"
```

Step 3 — re-confirm pause is STILL in effect after the tar work (defense against operator accidentally restarting cron during the work):

```bash
echo "=== final pause re-check ==="
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l
pgrep -f batch_ingest_from_spider; echo "exit=$?"
```

Paste FULL output of all 3 steps back. Include the `TS=` line literally — the local agent needs the timestamp suffix to write the next plan's scp command.

```

After receiving operator output, the agent moves to Task 2.

### Task 2 — Agent writes STORAGE-02 evidence and commits

**`<read_first>`**
- The operator response from Task 1 (in chat).
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\CLAUDE.md` lessons 2026-05-08 — "no fabricated data in commit messages" — every value pasted MUST come from operator output verbatim.

**`<acceptance_criteria>`**
- File `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-02-tar-evidence.md` exists.
- File records: tar filename literal, byte size literal, full sha256 hex, top-5 tar entries verbatim.
- File records ISO retention deadline = tar_creation_date + 30 days, computed from the `TS=` line.
- `git log -1 --name-only EVIDENCE/STORAGE-02-tar-evidence.md` returns a commit.

**`<action>`**

Use the Write tool to create `.planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-02-tar-evidence.md`:

```markdown
# STORAGE-02 — Hermes tar archive evidence

Phase: aim-2 (LightRAG storage full migration)
REQ: STORAGE-02

## Tar metadata

- Timestamp suffix (TS): `[paste literal from /tmp/aim2-tar-ts.txt]`
- Tar path on Hermes: `/tmp/lightrag_storage_aim2_[TS].tar.gz`
- Sha256 path on Hermes: `/tmp/lightrag_storage_aim2_[TS].tar.gz.sha256`
- Tar byte size: `[paste literal from `stat -c %s`]`
- Tar size human: `[paste literal from `ls -la`]`

## Sha256 (Hermes-side, source of truth for STORAGE-03)

```

[paste verbatim contents of `cat $SHA`]

```

## Sha256 self-verify

```

[paste verbatim output of `sha256sum -c $SHA`]

```

Expected: ends with `OK`.

## Source size before tar

```

[paste verbatim output of `du -sh ~/.hermes/omonigraph-vault/lightrag_storage/`]

```

## Top-5 tar entries

```

[paste verbatim output of `tar -tzf "$TAR" | head -5`]

```

Expected: first line begins with `lightrag_storage/`.

## Pause re-check (post-tar)

- Uncommented ingest lines: `[N]` (required == 0)
- pgrep batch_ingest_from_spider exit: `[N]` (required == 1)

## 30-day retention deadline

- Tar creation date (UTC): `[YYYY-MM-DD from TS]`
- Retention deadline (UTC): `[YYYY-MM-DD = creation + 30 days]`
- Both `tar.gz` and `.sha256` files MUST remain on Hermes at /tmp/ until at least the retention deadline above. Do NOT `rm` them. Cleanup is OUT of scope per PROJECT §5 Out of Scope.
```

Then commit:

```bash
git add .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-02-tar-evidence.md
git commit -m "docs(aim-2): record STORAGE-02 Hermes tar.gz + sha256 evidence"
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| Step 1 pause re-check fails (uncommented ingest lines > 0) | STOP. Do not tar. Re-run aim-2-1 pause sequence. |
| Tar command exits non-zero | STOP. Capture stderr; investigate as separate quick before retry. Hermes resume is OPTIONAL here (operator's call) — tar is read-only on the storage. |
| Tar size < 1 GiB sanity floor | FAIL. The source storage may have been corrupted or partial. Do NOT proceed. Investigate via `du -sh ~/.hermes/omonigraph-vault/lightrag_storage/` and historical baseline. |
| `sha256sum -c` returns FAILED | Disk corruption suspected. Re-run tar from Step 2 with new TS; do NOT trust the first tar. |
| Step 3 final pause re-check fails | The pause was broken during tar (cron restarted somehow). The tar may include partially-mutated state. DISCARD the tar (`rm $TAR $SHA`); re-pause via aim-2-1; re-tar. |

If any condition aborts and Hermes operator wants to resume cron temporarily (e.g., to fix something else), they may — but aim-2-3 cannot proceed until aim-2-1 + aim-2-2 are re-verified clean.

## Evidence to capture

- `EVIDENCE/STORAGE-02-tar-evidence.md` — committed locally.
- Hermes-side `/tmp/lightrag_storage_aim2_<TS>.tar.gz` + `.sha256` retained ≥ 30 days (operator-side persistence; no agent action).

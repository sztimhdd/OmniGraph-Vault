---
plan_id: aim-2-4
phase: aim-2
wave: 4
depends_on:
  - aim-2-3
requirements_addressed:
  - STORAGE-04
files_modified:
  - scripts/lightrag_count.py
  - .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-04-count-evidence.md
autonomous: false
t_shirt: M
---

# aim-2-4 — Entity / relation / chunk / kv_keys count ±0% verify (STORAGE-04)

## Goal

Verify that the Aliyun-extracted holding-dir storage from STORAGE-03 has IDENTICAL entity / relation / chunk / kv_keys counts as the Hermes-source storage, byte-for-byte (not "approximately equal"). On match, the storage is proved byte-identical and aim-2-5 may proceed. On mismatch, the cutover ABORTS — Hermes resumes via aim-2-1 reverse, and the operator decides whether to retry from STORAGE-02 or investigate.

This plan introduces `scripts/lightrag_count.py` (which does NOT exist in repo today — confirmed via `Glob: scripts/lightrag*.py` returning zero files). The script is checked into the repo because it is reused at aim-3 (post-cutover smoke), aim-5 (7-day stability), and any future migration.

## Acceptance criteria

1. `scripts/lightrag_count.py` exists in the repo, committed to main.
2. `python scripts/lightrag_count.py --help` returns usage text exit 0.
3. `python scripts/lightrag_count.py /path/to/lightrag_storage/` outputs JSON with keys `entities`, `relations`, `chunks`, `kv_keys` — all integers ≥ 0.
4. Operator-side Hermes count run produces JSON A.
5. Agent-side Aliyun count run produces JSON B.
6. `diff <(echo $A_json) <(echo $B_json)` returns empty (byte-identical JSON, modulo run timestamp comments — see script spec).
7. All four counts (entities / relations / chunks / kv_keys) are equal between A and B.
8. `EVIDENCE/STORAGE-04-count-evidence.md` exists, committed locally, contains both JSONs verbatim and the verdict line.

## Task list

### Task 1 — Agent writes `scripts/lightrag_count.py`

**`<read_first>`**

- `c:\Users\huxxha\Desktop\OmniGraph-Vault\list_entities.py` (existing pattern for reading the GraphML — same `graph_chunk_entity_relation.graphml` filename used by LightRAG; `nx.read_graphml` enumerates nodes for entities)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\config.py` lines 20-30 (RAG_WORKING_DIR derivation — confirms the storage path layout under `{BASE_DIR}/lightrag_storage/`)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 54 (STORAGE-04 wording — required outputs `entities`, `relations`, `chunks`, `kv_keys`; ±0% byte-identical)

**`<acceptance_criteria>`**

- File `scripts/lightrag_count.py` exists.
- `python scripts/lightrag_count.py --help` exits 0 with usage text.
- `python scripts/lightrag_count.py <empty-dir>` exits non-zero with clear error message (does NOT silently return zeros).
- `python scripts/lightrag_count.py <real-storage>` exits 0 with valid JSON on stdout.
- JSON keys: `entities` (int), `relations` (int), `chunks` (int), `kv_keys` (int), `storage_path` (string), `script_version` (string `"1.0"`).
- The `--help` output documents that the script does NOT mutate the storage (read-only).
- Type annotations on all function signatures (per project Python coding-style rule).
- Uses `logging` for diagnostic output, NOT `print` for non-result lines (per project hooks rule). The JSON result IS printed to stdout via `print(json.dumps(result))` because that is the script's CLI contract.

**`<action>`**

Use the Write tool to create `c:\Users\huxxha\Desktop\OmniGraph-Vault\scripts\lightrag_count.py`:

```python
"""Count LightRAG storage entities / relations / chunks / kv_keys.

Read-only diagnostic. Used by aim-2-4 (STORAGE-04) to prove byte-identical
storage between Hermes source and Aliyun extracted copy. Output is JSON on
stdout; diagnostic logging goes to stderr.

Usage:
    python scripts/lightrag_count.py /path/to/lightrag_storage/
    python scripts/lightrag_count.py --help

Exit 0 = success (JSON printed). Exit 1 = path missing / unreadable.
Exit 2 = required LightRAG storage files missing under the path.

Counts:
    entities  : nodes in graph_chunk_entity_relation.graphml
    relations : edges in graph_chunk_entity_relation.graphml
    chunks    : keys in kv_store_text_chunks.json (LightRAG v1+)
    kv_keys   : total keys across all kv_store_*.json files
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import networkx as nx

SCRIPT_VERSION = "1.0"

logger = logging.getLogger("lightrag_count")
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")


def count_graph(storage: Path) -> tuple[int, int]:
    """Return (entity_count, relation_count) from the GraphML file."""
    graphml = storage / "graph_chunk_entity_relation.graphml"
    if not graphml.exists():
        raise FileNotFoundError(f"GraphML not found: {graphml}")
    g = nx.read_graphml(str(graphml))
    return g.number_of_nodes(), g.number_of_edges()


def count_chunks(storage: Path) -> int:
    """Return chunk count from kv_store_text_chunks.json."""
    chunks_file = storage / "kv_store_text_chunks.json"
    if not chunks_file.exists():
        # LightRAG variants may name it differently; treat as 0 with warning.
        logger.warning("kv_store_text_chunks.json not present under %s", storage)
        return 0
    with chunks_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"kv_store_text_chunks.json root is not a dict: {type(data)}")
    return len(data)


def count_kv_keys(storage: Path) -> int:
    """Return total key count summed across all kv_store_*.json files."""
    total = 0
    for kv in sorted(storage.glob("kv_store_*.json")):
        with kv.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            total += len(data)
        else:
            logger.warning("kv_store file %s root is not a dict — skipping", kv.name)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count LightRAG storage entities / relations / chunks / kv_keys (read-only).",
    )
    parser.add_argument(
        "storage",
        type=Path,
        help="Path to a LightRAG storage directory (containing graph_chunk_entity_relation.graphml + kv_store_*.json).",
    )
    args = parser.parse_args()

    storage: Path = args.storage
    if not storage.exists():
        logger.error("storage path does not exist: %s", storage)
        return 1
    if not storage.is_dir():
        logger.error("storage path is not a directory: %s", storage)
        return 1

    try:
        entities, relations = count_graph(storage)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 2
    chunks = count_chunks(storage)
    kv_keys = count_kv_keys(storage)

    result = {
        "script_version": SCRIPT_VERSION,
        "storage_path": str(storage.resolve()),
        "entities": entities,
        "relations": relations,
        "chunks": chunks,
        "kv_keys": kv_keys,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Then commit:

```bash
git add scripts/lightrag_count.py
git commit -m "feat(aim-2): add scripts/lightrag_count.py for STORAGE-04 byte-identical verify"
```

### Task 2 — Operator runs count on Hermes source storage

**`<read_first>`**

- The committed `scripts/lightrag_count.py` (just created in Task 1)
- `c:\Users\huxxha\Desktop\OmniGraph-Vault\.planning\phases\aim-2-lightrag-storage-migration\EVIDENCE\STORAGE-01-pause-evidence.md` (re-confirm Hermes pause is still active)

**`<acceptance_criteria>`**

- Hermes-side Python venv has `networkx` available (likely yes — already a LightRAG dependency).
- Hermes count run exits 0 and emits valid JSON.
- Hermes pause re-confirmed still active before AND after the count run.

**`<action>`**

Agent writes the operator prompt:

```hermes-operator-prompt
You are operating the Hermes production host. The aim-2-1 pause MUST still be in effect. Run:

Step 1 — pull latest scripts/lightrag_count.py from main:

```bash
cd ~/OmniGraph-Vault
git pull --ff-only origin main
ls -la scripts/lightrag_count.py
python -c "import networkx; print(networkx.__version__)"
```

Step 2 — run the count on Hermes-source storage:

```bash
echo "=== Hermes-source storage size ==="
du -sh ~/.hermes/omonigraph-vault/lightrag_storage/

echo "=== running count ==="
source venv/bin/activate
python scripts/lightrag_count.py ~/.hermes/omonigraph-vault/lightrag_storage/ | tee /tmp/aim2-count-hermes.json
```

Step 3 — re-confirm pause still active:

```bash
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l
pgrep -f batch_ingest_from_spider; echo "exit=$?"
```

Paste FULL output of all 3 steps. The JSON line from /tmp/aim2-count-hermes.json is the source-of-truth for byte-compare in Task 3.

```

### Task 3 — Agent runs count on Aliyun holding-dir and byte-compares

**`<read_first>`**
- The operator response from Task 2 (extracts Hermes JSON literal).
- Memory `aliyun_vitaclaw_ssh.md` (SSH alias).

**`<acceptance_criteria>`**
- Aliyun count run exits 0, emits valid JSON.
- The two JSON `entities` / `relations` / `chunks` / `kv_keys` values match byte-for-byte.
- The `storage_path` field WILL differ (Hermes vs Aliyun paths) — that's expected; only the four count fields matter for the integrity gate.

**`<action>`**

Agent runs:

```bash
HERMES_JSON='<paste literal JSON line from operator response Step 2>'

ssh aliyun-vitaclaw bash -c "'
cd /root/OmniGraph-Vault
echo \"=== sync repo to get scripts/lightrag_count.py ===\"
git fetch origin main
git pull --ff-only origin main
ls -la scripts/lightrag_count.py

echo \"=== running count on holding-dir ===\"
source venv/bin/activate 2>/dev/null || source venv-aim1/bin/activate
python scripts/lightrag_count.py /tmp/aim2-extract/lightrag_storage/ | tee /tmp/aim2-count-aliyun.json
'"

ALIYUN_JSON=$(ssh aliyun-vitaclaw cat /tmp/aim2-count-aliyun.json)

echo "Hermes JSON: $HERMES_JSON"
echo "Aliyun JSON: $ALIYUN_JSON"

# Byte-compare on the four count fields ONLY (storage_path will differ)
HERMES_COUNTS=$(echo "$HERMES_JSON" | python -c "import sys, json; d=json.load(sys.stdin); print(json.dumps({k:d[k] for k in ['entities','relations','chunks','kv_keys']}, sort_keys=True))")
ALIYUN_COUNTS=$(echo "$ALIYUN_JSON" | python -c "import sys, json; d=json.load(sys.stdin); print(json.dumps({k:d[k] for k in ['entities','relations','chunks','kv_keys']}, sort_keys=True))")

echo "Hermes counts: $HERMES_COUNTS"
echo "Aliyun counts: $ALIYUN_COUNTS"

if [ "$HERMES_COUNTS" = "$ALIYUN_COUNTS" ]; then
  echo "VERDICT: MATCH — STORAGE-04 PASS"
else
  echo "VERDICT: MISMATCH — STORAGE-04 FAIL — abort per Abort/rollback"
fi
```

If MISMATCH, follow Abort/rollback below — do NOT proceed to Task 4 or aim-2-5.

### Task 4 — Agent writes STORAGE-04 evidence and commits

**`<read_first>`**

- All output from Tasks 2 + 3.

**`<acceptance_criteria>`**

- File `EVIDENCE/STORAGE-04-count-evidence.md` exists.
- File contains both JSON literals (Hermes-source, Aliyun-holding).
- File contains explicit MATCH / MISMATCH verdict per-field table.
- File committed locally.

**`<action>`**

Use Write to create `.planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-04-count-evidence.md`:

```markdown
# STORAGE-04 — Entity / relation / chunk / kv_keys count verify

Phase: aim-2 (LightRAG storage full migration)
REQ: STORAGE-04
Tool: `scripts/lightrag_count.py` v1.0 (committed in Task 1)

## Hermes-source storage count

Path: `~/.hermes/omonigraph-vault/lightrag_storage/`

```json
[paste verbatim contents of /tmp/aim2-count-hermes.json from operator response]
```

## Aliyun-holding storage count

Path: `/tmp/aim2-extract/lightrag_storage/`

```json
[paste verbatim contents of /tmp/aim2-count-aliyun.json from agent ssh]
```

## Per-field verdict table

| Field | Hermes-source | Aliyun-holding | Match? |
|-------|---------------|----------------|--------|
| entities  | [N] | [N] | YES / NO |
| relations | [N] | [N] | YES / NO |
| chunks    | [N] | [N] | YES / NO |
| kv_keys   | [N] | [N] | YES / NO |

**Overall verdict:** **PASS** (all four match) / FAIL (any mismatch)

## Pause re-check

- Hermes uncommented ingest lines: `[N]` (required == 0)
- Hermes pgrep batch_ingest_from_spider exit: `[N]` (required == 1)

## Decision

- If PASS: aim-2-5 proceeds (mv holding-dir to production path, set Hermes read-only, resume Hermes cron AFTER mv).
- If FAIL: see aim-2-4 Abort/rollback. Hermes resumes via aim-2-1 reverse BEFORE retrying from STORAGE-02. Aliyun holding-dir cleaned via `rm -rf /tmp/aim2-extract/`.

```

Then commit:

```bash
git add .planning/phases/aim-2-lightrag-storage-migration/EVIDENCE/STORAGE-04-count-evidence.md
git commit -m "docs(aim-2): record STORAGE-04 byte-identical count verify"
```

## Abort/rollback protocol

| Condition | Action |
| --- | --- |
| Task 1: `python scripts/lightrag_count.py --help` fails | Fix the script, re-commit, retry. Do NOT proceed to Task 2. |
| Task 1: Hermes-side `import networkx` fails | The Hermes venv is missing networkx — operator runs `pip install networkx` in Hermes venv. Retry. |
| Task 2: Hermes count exits non-zero | Investigate via stderr in operator output. Common causes: GraphML file path differs from default, kv_store_*.json schema differs. Patch script, re-commit, retry. |
| Task 3: Aliyun count exits non-zero | Same as above on Aliyun side. Confirm `/tmp/aim2-extract/lightrag_storage/` actually has the files (re-run aim-2-3 verify). |
| Task 3: MISMATCH on any field | **CRITICAL**. Abort cutover. (a) `ssh aliyun-vitaclaw rm -rf /tmp/aim2-extract` — drop the holding dir; (b) Send operator the "resume Hermes cron" prompt (uncomment 11 crontab lines per aim-2-1 evidence resume protocol) — Hermes goes back online; (c) Investigate root cause: tar corruption (already ruled out by sha256 in STORAGE-03 — but possible if hash compute itself was buggy), filesystem bit-rot during scp, LightRAG storage actively-changing during tar (suggests aim-2-1 pause was incomplete). (d) Once root cause is fixed, restart phase from aim-2-1. **Do NOT chain retries while Hermes is still paused — operational liveness > migration speed.** |
| Pause re-check at end of Task 2 or Task 3 fails (uncommented ingest lines > 0) | The Hermes pause was broken. The count comparison is invalid (Hermes storage may have advanced during count). Resume Hermes formally, drop Aliyun holding-dir, restart from aim-2-1. |

## Resume Hermes operator prompt (for use ONLY on STORAGE-04 abort)

If STORAGE-04 fails and the abort protocol calls for Hermes to resume BEFORE retrying, agent writes this prompt and asks user to forward to Hermes:

```hermes-operator-prompt
ABORT recovery from aim-2-4 STORAGE-04 fail. Resume Hermes ingest crontab to operational state. Run:

```bash
echo "=== current commented ingest lines ==="
crontab -l | grep -E "^#.*(ingest|kol_scan|rss)" | wc -l

# Edit crontab and remove the leading `#` from every commented ingest/kol_scan/rss line
crontab -e

echo "=== verify uncommented count == previous commented count (~11) ==="
crontab -l | grep -vE "^#" | grep -E "(ingest|kol_scan|rss)" | wc -l

echo "=== resume timestamp ==="
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee /tmp/aim2-pause-resumed.iso
```

Paste output back. After this, Hermes is back to authoritative ingest. The aim-2 retry begins from aim-2-1 (re-pause) when operator + agent are ready.

```

## Evidence to capture

- `scripts/lightrag_count.py` (the new tool — reused at aim-3 / aim-5).
- `EVIDENCE/STORAGE-04-count-evidence.md` (per-field verdict table).
- Hermes `/tmp/aim2-count-hermes.json` (operator-side artifact, may be cleaned post-cutover).
- Aliyun `/tmp/aim2-count-aliyun.json` (agent-side artifact, may be cleaned post-cutover).

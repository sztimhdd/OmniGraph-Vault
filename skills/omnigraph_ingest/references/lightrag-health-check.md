# LightRAG Pipeline Health Check

Quick check for stuck docs, graph health, and storage hygiene.

## When to Use

- After a hung/killed ingest batch ("清理积压", "管线有无积压")
- Before running a new ingest batch (pre-flight)
- After mystery row cleanup (verify graph is intact)

## Check 1: Doc Status (Stuck Docs)

```bash
cd ~/OmniGraph-Vault && venv/bin/python << 'PYEOF'
import json
from pathlib import Path
ds = json.loads((Path.home() / '.hermes' / 'omonigraph-vault' / 'lightrag_storage' / 'kv_store_doc_status.json').read_text(encoding='utf-8'))
by_status = {}
for doc_id, info in ds.items():
    s = info.get('status', 'unknown')
    by_status[s] = by_status.get(s, 0) + 1
print(f"Total docs: {len(ds)}")
print(f"By status: {by_status}")
pending = [d for d, i in ds.items() if i.get('status') == 'processing']
if pending:
    print(f"⚠️ STUCK in 'processing': {len(pending)}")
    for d in pending[:10]:
        print(f"  {d}")
else:
    print("✅ All docs processed")
PYEOF
```

**Expected:** All docs `processed`, zero in `processing`. If any stuck, run `clean_lightrag_zombies.py`.

## Check 2: Graph Health

```bash
python3 -c "
import json
with open('$HOME/.hermes/omonigraph-vault/lightrag_storage/graph_chunk_entity_relation.graphml') as f:
    content = f.read()
nodes = content.count('<node ')
edges = content.count('<edge ')
print(f'graphml: {len(content):,} bytes, ~{nodes} nodes, ~{edges} edges')
"
```

**Expected:** 8000+ nodes, 10000+ edges, file 8-10MB. If file is 0 bytes or nodes < 100, graph is corrupted.

## Check 3: Temp/Lock Files

```bash
find ~/.hermes/omonigraph-vault/lightrag_storage/ -name '*.tmp' -o -name '*.lock' 2>/dev/null
```

**Expected:** empty. Any .tmp/.lock files indicate an interrupted write that may block future ingests.

## Check 4: Old Backup Files

```bash
ls -lhS ~/.hermes/omonigraph-vault/lightrag_storage/*.bak-* 2>/dev/null
```

**Cleanup rule:** Remove .bak files older than today. Keep today's for audit trail.

```bash
# Remove May 5-8, keep May 9
rm -v ~/.hermes/omonigraph-vault/lightrag_storage/*.bak-2026050[5-8]* 2>/dev/null
```

## Check 5: Vector DB Presence

```bash
ls -lh ~/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json
```

**Expected:** `vdb_entities.json`, `vdb_relationships.json`, `vdb_chunks.json` all present and non-zero.

## What NOT to Do

- ❌ Don't vacuum or rebuild LightRAG storage
- ❌ Don't delete graph_chunk_entity_relation.graphml
- ❌ Don't touch kv_store_full_*.json (production data)

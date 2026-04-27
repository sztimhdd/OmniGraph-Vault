# Phase 2 — Entity Layer Migration to SQLite

## Context

Phase 1 completed: `batch_scan_kol.py`, `batch_classify_kol.py`, and `--from-db`
mode are live. `data/kol_scan.db` exists with `accounts`, `articles`,
`classifications`, `ingestions` tables populated.

Phase 2 migrates the **entity layer** from fragmented file storage to the same
SQLite database. The tables (`extracted_entities`, `entity_canonical`) already
exist in the schema from Phase 1 — they are defined but currently **empty**
(no code reads or writes them yet).

## Current State

| Data | Storage | Format |
|------|---------|--------|
| Extracted entities | `entity_buffer/{hash}_entities.json` | 1 file per article |
| Canonical entity map | `~/.hermes/omonigraph-vault/canonical_map.json` | Single JSON dict |
| Processed markers | `entity_buffer/{hash}.processed` | Empty marker files |

## Target State

All entity data lives in `data/kol_scan.db`. File-based storage becomes
fallback-only (if DB doesn't exist), then removed entirely after transition.

## DB Schema (already exists, no changes needed)

```sql
CREATE TABLE IF NOT EXISTS extracted_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    entity_name TEXT NOT NULL,
    entity_type TEXT,
    extracted_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS entity_canonical (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_name TEXT NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL,
    entity_type TEXT,
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_extracted_entities_article ON extracted_entities(article_id);
CREATE INDEX IF NOT EXISTS idx_extracted_entities_name ON extracted_entities(entity_name);
```

## Files to Modify

### 1. `ingest_wechat.py` — Add entity SQLite write (~20 lines)

After entity extraction finishes (two locations: `ingest_one()` ~line 459
and `ingest_article()` ~line 564), add a post-processing call.

**Implementation:**

```python
def _persist_entities_to_sqlite(url: str, entities: list[str]) -> None:
    """Write extracted entities to kol_scan.db if it exists. No-op if not."""
    db_path = PROJECT_ROOT / "data" / "kol_scan.db"
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path))
        article = conn.execute(
            "SELECT id FROM articles WHERE url = ?", (url,)
        ).fetchone()
        if article:
            article_id = article[0]
            for entity in entities:
                conn.execute(
                    "INSERT OR IGNORE INTO extracted_entities(article_id, entity_name) VALUES (?, ?)",
                    (article_id, entity.strip())
                )
            conn.commit()
    except Exception:
        pass  # Non-critical — entity_buffer files are still the primary path
    finally:
        conn.close()
```

**Key decisions:**
- **Additive only** — still writes `entity_buffer/*.json` files. SQLite is a
  secondary persistence path. This gives a safety net during transition.
- **No-op if DB doesn't exist** — backward compatible with direct
  `ingest_wechat.py` calls outside the batch pipeline.
- **Silent failure** — if SQLite write fails (e.g. DB locked), don't crash
  the ingestion. Entity buffer files are still the source of truth.

**Change to `cognee_batch_processor.py`'s `discover_files()`:**
The existing `entity_buffer/*.json` + `*.processed` pattern already works.
No change needed to the file discovery logic at this stage — the batch
processor will pick up entity files regardless of whether they were also
written to SQLite.

### 2. `cognee_batch_processor.py` — Add DB-first entity reading (~30 lines changed)

The batch processor currently:
1. Lists `entity_buffer/*.json` → reads entities
2. Calls Gemini for disambiguation → builds `canonical_map.json`
3. Writes `canonical_map.json` atomically (tmp → rename)
4. Writes `*.processed` marker files

**Change:** Add a **DB-first code path** that reads from `extracted_entities`
and writes to `entity_canonical`, with file-based fallback.

### 2a. Replace `discover_files()` with dual-path discovery

```python
def discover_entities(db_path: Path) -> list[dict]:
    """
    Discover unprocessed entities.
    DB-first: query extracted_entities not yet in entity_canonical.
    Fallback: list entity_buffer/*.json files without .processed marker.
    """
    if db_path and db_path.exists():
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("""
            SELECT e.id, e.entity_name, e.article_id, a.url
            FROM extracted_entities e
            JOIN articles a ON e.article_id = a.id
            WHERE e.entity_name NOT IN (
                SELECT raw_name FROM entity_canonical
            )
        """).fetchall()
        conn.close()
        if rows:
            return [
                {"id": r[0], "name": r[1], "article_id": r[2], "url": r[3]}
                for r in rows
            ]
    
    # Fallback: file-based
    buffer_dir = PROJECT_ROOT / "entity_buffer"
    if not buffer_dir.exists():
        return []
    
    results = []
    for f in sorted(buffer_dir.glob("*_entities.json")):
        marker = f.with_name(f.stem.replace("_entities", "") + ".processed")
        if marker.exists():
            continue
        data = json.loads(f.read_text())
        results.append({
            "id": f.stem,
            "name": data.get("entity", data.get("name", "unknown")),
            "source_file": str(f),
        })
    return results
```

### 2b. Add DB canonical map read/write

Replace `load_canonical_map()`:
```python
def load_canonical_map(db_path: Path) -> dict[str, str]:
    """Load canonical map. DB-first, JSON fallback."""
    if db_path and db_path.exists():
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT raw_name, canonical_name FROM entity_canonical"
        ).fetchall()
        conn.close()
        if rows:
            return dict(rows)
    # Fallback
    path = PROJECT_ROOT.parent / ".hermes" / "omonigraph-vault" / "canonical_map.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}
```

Replace `save_canonical_map()`:
```python
def save_canonical_entry(db_path: Path, raw: str, canonical: str,
                          entity_type: str = "") -> None:
    """Write one canonical mapping. DB-first, JSON fallback."""
    if db_path and db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """INSERT OR REPLACE INTO entity_canonical
               (raw_name, canonical_name, entity_type)
               VALUES (?, ?, ?)""",
            (raw, canonical, entity_type)
        )
        conn.commit()
        conn.close()
    else:
        # Legacy atomic JSON write
        path = PROJECT_ROOT.parent / ".hermes" / "omonigraph-vault" / "canonical_map.json"
        canonical_map = json.loads(path.read_text()) if path.exists() else {}
        canonical_map[raw] = canonical
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(canonical_map, ensure_ascii=False, indent=2))
        tmp.rename(path)
```

### 2c. Remove `.processed` marker file creation in DB mode

When running in DB mode (DB exists), skip creating `*.processed` marker files.
The processed status is implicit — once a `raw_name` appears in `entity_canonical`,
it won't be re-fetched.

When running in fallback (file) mode, continue creating `*.processed` markers
as before.

```python
if db_path and db_path.exists():
    # Processed status tracked via entity_canonical table — no marker file needed
    pass
else:
    # Legacy: write .processed marker
    marker = source_path.with_name(source_path.stem.replace("_entities", "") + ".processed")
    marker.write_text("")
```

### 3. `kg_synthesize.py` — DB-first canonical map read (~10 lines changed)

Replace the current JSON file read:

```python
# Before:
canonical_map_path = RAG_WORKING_DIR / "canonical_map.json"
canonical_map = {}
if canonical_map_path.exists():
    canonical_map = json.loads(canonical_map_path.read_text())

# After:
DB_PATH = PROJECT_ROOT / "data" / "kol_scan.db"
canonical_map = {}
if DB_PATH.exists():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT raw_name, canonical_name FROM entity_canonical"
    ).fetchall()
    conn.close()
    canonical_map = dict(rows)
if not canonical_map:
    # Fallback to JSON
    canonical_map_path = RAG_WORKING_DIR / "canonical_map.json"
    if canonical_map_path.exists():
        import json
        canonical_map = json.loads(canonical_map_path.read_text())
```

### 4. `run_uat_ingest.py` — DB-first entity queries (~10 lines changed)

Replace entity_buffer directory listing with DB query, file fallback:

```python
def get_entities_for_article(url: str) -> list[dict]:
    """Get entities for an article. DB-first, file fallback."""
    db_path = PROJECT_ROOT / "data" / "kol_scan.db"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("""
            SELECT e.entity_name, e.entity_type
            FROM extracted_entities e
            JOIN articles a ON e.article_id = a.id
            WHERE a.url = ?
        """, (url,)).fetchall()
        conn.close()
        if rows:
            return [{"name": r[0], "type": r[1]} for r in rows]
    
    # Fallback: list entity_buffer
    buffer_dir = PROJECT_ROOT / "entity_buffer"
    if not buffer_dir.exists():
        return []
    # ... existing file-based logic ...
```

## Migration Path

This phase uses a **dual-write, DB-first read** strategy:

| Operation | DB exists | DB doesn't exist |
|-----------|-----------|------------------|
| Write entities | SQLite + file | File only (unchanged) |
| Read entities | SQLite | File fallback |
| Write canonical | SQLite | JSON atomic write |
| Read canonical | SQLite | JSON fallback |

**No migration script needed.** Old files (`*.json`, `*.processed`) remain on disk
and are simply no longer read once the DB path is active. They can be cleaned up
manually after verifying the DB has all data.

## Dependency Map

```
ingest_wechat.py ──writes──┐
                           ▼
                 extracted_entities (SQLite)
                           │
                    cognee_batch_processor.py
                           │
                           ▼
                   entity_canonical (SQLite)
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
      kg_synthesize.py  run_uat_ingest.py  (future consumer)
```

No circular dependencies. `ingest_wechat.py` only writes; batch processor reads
and writes canonical; synthesizer only reads canonical.

## What NOT to Change

- `kol_config.py` — untouched
- `spiders/wechat_spider.py` — untouched
- `batch_scan_kol.py` — untouched (Phase 1)
- `batch_classify_kol.py` — untouched (Phase 1)
- `batch_ingest_from_spider.py` — untouched (Phase 1)
- Any skill files — untouched (Hermes territory)
- `entity_buffer/` directory deletion — NOT part of this phase (cleanup later)

## Verification

```bash
# 1. Ingest an article (non-DB path still works)
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."

# 2. Entities now in SQLite too
sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM extracted_entities"

# 3. Batch processor reads from DB
python cognee_batch_processor.py
sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM entity_canonical"

# 4. Synthesis reads canonical from DB
python kg_synthesize.py "What is OpenClaw?" hybrid

# 5. File fallback: rename DB and test
mv data/kol_scan.db data/kol_scan.db.bak
python cognee_batch_processor.py
python kg_synthesize.py "What is OpenClaw?" hybrid
mv data/kol_scan.db.bak data/kol_scan.db

# 6. No entity_buffer files were deleted
ls entity_buffer/*_entities.json | head -3
```

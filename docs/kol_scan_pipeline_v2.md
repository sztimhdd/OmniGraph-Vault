# KOL Article Scanning Pipeline v2 — SQLite Backend Refactor

## Overview

Replace the fragmented file-based intermediate storage (`coldstart_run_*.json`,
`entity_buffer/*.json`, `canonical_map.json`) with a single unified SQLite
database (`data/kol_scan.db`). Implemented in two phases.

**Goal:** One scan, classify many times, entities queryable.

---

## Phase 1 — Scan + Classify + Ingest Pipeline (Current)

### Scope

| File | Action |
|------|--------|
| `batch_scan_kol.py` | **New** — scan-only, writes to DB |
| `batch_classify_kol.py` | **New** — classify-only, reads/writes DB |
| `batch_ingest_from_spider.py` | **Modify** — add `--from-db` mode |
| `data/kol_scan.db` | **Auto-created** |

### Out of Scope (Phase 1)

- ❌ `ingest_wechat.py` — untouched
- ❌ `cognee_batch_processor.py` — untouched
- ❌ `kg_synthesize.py` — untouched
- ❌ `run_uat_ingest.py` — untouched
- ❌ Entity buffer / canonical map migration

### DB Schema

```sql
-- Phase 1 tables (REQUIRED)
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    wechat_id TEXT,
    fakeid TEXT NOT NULL UNIQUE,
    tags TEXT,        -- JSON array: ["RAG", "Agent", ...]
    source TEXT,      -- "searchbiz_API", "KOL_List", etc.
    category TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    digest TEXT,
    update_time INTEGER,  -- WeChat MP publish timestamp (unix epoch)
    scanned_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    topic TEXT NOT NULL,
    depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
    relevant INTEGER DEFAULT 0,
    excluded INTEGER DEFAULT 0,
    reason TEXT,
    classified_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(article_id, topic)
);

CREATE TABLE IF NOT EXISTS ingestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped')),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(article_id)
);

-- Phase 2 tables (DEFINED but not read/written in Phase 1)
-- These tables exist in the schema so no ALTER TABLE needed later.
-- Phase 1 code does NOT read from or write to these tables.

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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_articles_account ON articles(account_id);
CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
CREATE INDEX IF NOT EXISTS idx_classifications_topic ON classifications(topic);
CREATE INDEX IF NOT EXISTS idx_classifications_article ON classifications(article_id);
CREATE INDEX IF NOT EXISTS idx_extracted_entities_article ON extracted_entities(article_id);
CREATE INDEX IF NOT EXISTS idx_extracted_entities_name ON extracted_entities(entity_name);
```

### New File: `batch_scan_kol.py`

**Purpose:** Scan-only. No classify, no ingest. Creates DB on first run.

**Reuses:**
- `spiders/wechat_spider.py` — `list_articles_with_digest()`, rate limit constants
- `kol_config.py` — `TOKEN`, `COOKIE`, `FAKEIDS`
- `batch_ingest_from_spider.py` — `_load_hermes_env()` (copy inline)

**Account initialization:**
On first run, merge `kol_registry.list_accounts()` (from `docs/wechat_kol_registry.json`)
+ `kol_config.FAKEIDS` → `INSERT OR REPLACE INTO accounts`.
This makes the DB the source of truth, no need to maintain parallel lists.

**Scan loop:**
1. Query accounts from DB (not `kol_config.FAKEIDS` directly)
2. For each account, call `list_articles_with_digest(token, cookie, fakeid, days_back, max_articles)`
3. `INSERT OR IGNORE INTO articles(...)` — dedup by url UNIQUE constraint
4. Log: `[3/54] [叶小钗] 已扫描 17 篇 (新增 12, 跳过 5)`

**Session management:**
- Global request counter, auto-stop at 45 requests
- `--resume` flag: skip accounts that already have articles in DB
- ret=200013: handled by `list_articles_with_digest()` (60s cooldown, 3 retries)
- At 45 requests, print message:
  ```
  ⏸️ 已扫描 45 个账号，接近 session 上限（50次）。
     请在浏览器中刷新 mp.weixin.qq.com 页面恢复 session，
     然后运行: python batch_scan_kol.py --resume
  ```

**CLI:**
```
python batch_scan_kol.py --days-back 120 --max-articles 20
python batch_scan_kol.py --days-back 120 --max-articles 20 --account "叶小钗"
python batch_scan_kol.py --days-back 120 --max-articles 20 --resume
python batch_scan_kol.py --help
```

### New File: `batch_classify_kol.py`

**Purpose:** Classification-only. Reads unclassified articles from DB,
calls LLM, writes classifications back.

**Reuses** (copy inline from `batch_ingest_from_spider.py`):
- `_build_filter_prompt()` — builds the LLM classification prompt
- `_call_deepseek()` — DeepSeek API call
- `_call_gemini()` — Gemini API call
- `get_deepseek_api_key()`, `get_gemini_api_key()` — key resolution

**Data flow:**
1. Query articles that have not been classified for the given topic:
   ```sql
   SELECT a.* FROM articles a
   WHERE a.id NOT IN (
       SELECT article_id FROM classifications WHERE topic = ?
   )
   ```
2. Batch 200 articles at a time, send to LLM
3. Parse results → `INSERT INTO classifications(article_id, topic, depth_score, relevant, excluded, reason)`
4. Print summary: `Pass: 12 | Filtered out: 6 (depth too low: 3, off-topic: 2, excluded: 1)`

**CLI:**
```
python batch_classify_kol.py --topic "OpenClaw" --min-depth 2
python batch_classify_kol.py --topic "Agent" --classifier gemini
python batch_classify_kol.py --topic "RAG" --dry-run
python batch_classify_kol.py --list-topics  # Show which topics have been classified
```

### Modified: `batch_ingest_from_spider.py` — `--from-db` mode

**Add new function:** `ingest_from_db(topic, dry_run, min_depth, ...)`

1. Query DB for passed articles:
   ```sql
   SELECT a.* FROM articles a
   JOIN classifications c ON a.id = c.article_id
   WHERE c.topic = ? AND c.relevant = 1 AND c.depth_score >= ?
     AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
   ```
2. Call existing `ingest_article(url, dry_run)` subprocess
3. On success: `INSERT INTO ingestions(article_id, status)`
4. Log: `[5/12] [叶小钗] AI Coding实战... → ok`

**New CLI flags:**
```
python batch_ingest_from_spider.py --from-db --topic "OpenClaw" --dry-run
python batch_ingest_from_spider.py --from-db --topic "OpenClaw"
```

**Backward compatibility:**
Existing flow (without `--from-db`) = 100% unchanged. All existing flags work.

### Verification — Phase 1

```bash
# 1. Scan a single account first
python batch_scan_kol.py --days-back 7 --max-articles 3 --account "叶小钗"

# 2. Check DB
sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM articles"
sqlite3 data/kol_scan.db "SELECT a.name, COUNT(*) FROM accounts a JOIN articles ar ON a.id=ar.account_id GROUP BY a.name"

# 3. Classify
python batch_classify_kol.py --topic "AI agents" --min-depth 2 --dry-run

# 4. Ingest from DB (dry run)
python batch_ingest_from_spider.py --from-db --topic "AI agents" --dry-run

# 5. Re-scan dedup
python batch_scan_kol.py --days-back 7 --max-articles 3 --account "叶小钗"
# Log shows: "跳过 N 篇已存在"

# 6. Full scan
python batch_scan_kol.py --days-back 120 --max-articles 20
```

---

## Phase 2 — Entity Layer Migration (Deferred)

### Trigger

Phase 2 starts after Phase 1 is verified working in production for at least
one full scan→classify→ingest cycle.

### Scope

| File | Action |
|------|--------|
| `ingest_wechat.py` | **Modify** — add entity SQLite write after extraction |
| `cognee_batch_processor.py` | **Modify** — read `extracted_entities` table + write `entity_canonical` table |
| `kg_synthesize.py` | **Modify** — read `entity_canonical` from DB instead of JSON |
| `run_uat_ingest.py` | **Modify** — read entities from DB instead of directory |

### Design Principles

1. **DB-first, file-fallback** — if `data/kol_scan.db` exists, read/write DB;
   if not, fall back to existing file-based behavior. No migration needed.
2. **Additive writes** — Phase 2 code writes to both DB AND existing file paths
   for a transition period. Removal of file paths happens in a cleanup round.
3. **No schema changes** — `extracted_entities` and `entity_canonical` tables
   already exist from Phase 1 schema creation. No ALTER TABLE needed.

### Changes

#### `ingest_wechat.py` — Add SQLite write (~15 lines)

After entity extraction in `ingest_one()` and `ingest_article()`, add:

```python
def _persist_entities_to_db(url: str, entities: list[str]) -> None:
    """Write extracted entities to kol_scan.db if it exists. No-op if not."""
    db_path = PROJECT_ROOT / "data" / "kol_scan.db"
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        article = conn.execute(
            "SELECT id FROM articles WHERE url = ?", (url,)
        ).fetchone()
        if article:
            article_id = article[0]
            for entity in entities:
                conn.execute(
                    "INSERT OR IGNORE INTO extracted_entities(article_id, entity_name) VALUES (?, ?)",
                    (article_id, entity)
                )
            conn.commit()
    finally:
        conn.close()
```

Still writes `entity_buffer/` files (backward compatible). SQLite is additive.

#### `cognee_batch_processor.py` — DB-first entity processing (~80 lines changed)

Replace `discover_files()` (lists `entity_buffer/*.json`):
```python
def discover_unprocessed_entities(db_path: Path) -> list[dict]:
    """Get entities not yet canonicalized from DB."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("""
        SELECT e.id, e.entity_name, e.article_id, a.url
        FROM extracted_entities e
        JOIN articles a ON e.id = a.id
        WHERE e.id NOT IN (SELECT id FROM entity_processed)
    """).fetchall()
    conn.close()
    return rows
```

Replace `load_canonical_map()` (reads `canonical_map.json`):
```python
def load_canonical_map(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT raw_name, canonical_name FROM entity_canonical"
    ).fetchall()
    conn.close()
    return dict(rows)
```

Replace `save_canonical_map()` (atomic tmp→rename JSON write):
```python
def save_canonical_entry(db_path: Path, raw: str, canonical: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR REPLACE INTO entity_canonical(raw_name, canonical_name) VALUES (?, ?)",
        (raw, canonical)
    )
    conn.commit()
    conn.close()
```

#### `kg_synthesize.py` — DB-first canonical map read (~5 lines)

```python
db_path = PROJECT_ROOT / "data" / "kol_scan.db"
canonical_map = {}
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT raw_name, canonical_name FROM entity_canonical"
    ).fetchall()
    conn.close()
    canonical_map = dict(rows)
else:
    # fallback to JSON
    import json
    canonical_map_path = RAG_WORKING_DIR / "canonical_map.json"
    if canonical_map_path.exists():
        canonical_map = json.loads(canonical_map_path.read_text())
```

#### `run_uat_ingest.py` — DB query (~10 lines)

Replace `Path(entity_buffer).glob("*.json")` listing with:

```python
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT e.entity_name, e.entity_type, a.url "
        "FROM extracted_entities e JOIN articles a ON e.article_id = a.id"
    ).fetchall()
    conn.close()
```

### Verification — Phase 2

```bash
# Existing file-based entity processing still works (no DB)
python cognee_batch_processor.py

# DB-based entity processing (DB exists)
sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM extracted_entities"
sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM entity_canonical"

# Full pipeline with DB
python ingest_wechat.py "https://mp.weixin.qq.com/s/..."
python cognee_batch_processor.py
python kg_synthesize.py "What is OpenClaw?" hybrid
```

---

## Phase 3 (Future — Optional)

Potential improvements not yet scoped:

1. **LLM Response Cache** — SQLite cache for `_call_deepseek()` and `_call_gemini()`
   to avoid re-classifying identical prompts, saving tokens.
2. **Ingestion Queue** — A `pending_ingestions` table that `batch_ingest_from_spider.py`
   polls, enabling cronjob-driven async ingestion.
3. **Account Sync** — A script that re-reads `docs/wechat_kol_registry.json` and
   syncs the `accounts` table, adding new KOLs automatically.

---

## Non-Changes (Both Phases)

- `spiders/wechat_spider.py` — untouched (rate limiting stays)
- `kol_config.py` — untouched (credentials stay)
- All skill files under `skills/` — untouched (Hermes territory)
- Image files — filesystem only (binary, no DB)
- `synthesis_output.md` — filesystem only (human-readable reports)
- `cognee_wrapper.py` — no direct file I/O, gets data from batch processor

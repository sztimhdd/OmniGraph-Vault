# ir-4 W1 — Migration 008 + dual-source candidate SQL (LF-4.4 structural)

**Commit:** `5d943f8`
**Files:** 9 changed, +1062 / -176

## Goal

Add `source TEXT` column to `ingestions` and rewrite the
`--from-db` candidate SELECT as a UNION ALL across `articles` (KOL) +
`rss_articles` (RSS), with source-aware anti-join on the same source-tagged
ingestions table. Wire ingest_from_db's consumer-side to unpack the new
7-col tuple shape so the dispatch is self-runnable end-to-end after W1
(no broken-state-on-main between W1 and W2).

## Deliverables

### Migration 008 ingestions dual-source rebuild

`migrations/008_ingestions_dual_source.sql` + `.py` runner.

SQLite table-rebuild dance (ALTER cannot DROP CONSTRAINT or modify UNIQUE):

- **Adds**: `source TEXT NOT NULL DEFAULT 'wechat' CHECK (source IN ('wechat','rss'))`.
- **Replaces**: `UNIQUE(article_id)` → `UNIQUE(article_id, source)`.
- **Drops**: FK to `articles(id)` — dual-source semantics enforced at the
  application layer (one FK cannot represent both `articles.id` and
  `rss_articles.id`; SQLite triggers for conditional FK = over-engineering).
- **Preserves**: status CHECK (6 values), `enrichment_id TEXT` column,
  `ingested_at` DEFAULT clause.
- Idempotent via `PRAGMA table_info(ingestions)` source-col guard.
- Verifies post-rebuild: row count preserved, all migrated rows source='wechat',
  `PRAGMA integrity_check` returns `ok`, `PRAGMA foreign_key_check` returns empty.
- `--dry-run` flag prints rebuild SQL without mutating.

### `_build_topic_filter_query` UNION ALL refactor

`batch_ingest_from_spider.py:_build_topic_filter_query`:

- Returns 7-col rows: `(id, source, title, url, source_name, body, summary)`.
- KOL branch: `SELECT a.id AS id, 'wechat' AS source, ..., a.digest AS summary FROM articles a JOIN accounts acc ON a.account_id = acc.id WHERE a.id NOT IN (SELECT article_id FROM ingestions WHERE source='wechat' AND status='ok') AND (a.layer1_verdict IS NULL OR a.layer1_prompt_version IS NOT ? OR a.layer1_verdict='candidate')`.
- RSS branch: `SELECT r.id, 'rss', r.title, r.url, f.name, r.body, r.summary FROM rss_articles r JOIN rss_feeds f ON r.feed_id = f.id WHERE r.id NOT IN (SELECT article_id FROM ingestions WHERE source='rss' AND status='ok') AND (r.layer1_verdict IS NULL OR r.layer1_prompt_version IS NOT ? OR r.layer1_verdict='candidate')`.
- `ORDER BY source DESC, id` — KOL ('wechat' DESC > 'rss') first, FIFO within each source.
- Source-aware anti-join: KOL id=42 + RSS id=42 do NOT cross-exclude.
- params changed from 1-tuple `(PROMPT_VERSION_LAYER1,)` to 2-tuple
  (one binding per UNION branch).

### ingest_from_db consumer-side updates

- Inline `CREATE TABLE IF NOT EXISTS ingestions` rewritten to match migration 008.
- Layer 1 batch loop: `ArticleMeta.source = row[1]`, `ArticleMeta.summary = row[6]`.
- Layer 1 reject INSERT: includes `source` column.
- Layer 2 batch (`_drain_layer2_queue`): `ArticleWithBody.source = row[1]`,
  `ArticleWithBody.title = row[2]`. Per-row INSERT INTO ingestions (reject + ok)
  includes `source` column. `url_d = row[3]` (was `row[2]`).
- Per-article ingest loop: 7-col unpack `(art_id, source, title, url, account, body, summary)`.
- All 7 INSERT INTO ingestions sites in `--from-db` path now include source.
- Pre-Layer-2 scrape gated `if not body and source == "wechat"` (W1 KOL-only;
  W2 will lift the gate and add RSS body skip-scrape via `_needs_scrape`).
- variable rename `digest → summary` in graded-classify branch.

### batch_classify_kol.py + batch_scan_kol.py inline DDL alignment

Both files have a defensive `CREATE TABLE IF NOT EXISTS ingestions` (fresh-DB
bootstrap). Rewritten to match the migration 008 schema. Cosmetic — neither
file writes to ingestions (verified via grep).

### Tests

- `tests/unit/test_batch_ingest_topic_filter.py` (rewritten): 24 tests.
- `tests/unit/test_migration_008_idempotent.py` (new): 13 tests.
- `tests/unit/test_article_filter.py`: fixture for layer1_prompt_version_bump
  test extended with rss_feeds + rss_articles + dual-source ingestions DDL.
- `tests/unit/test_vision_worker.py`: fixture for
  test_ingest_from_db_drains_pending_vision_tasks extended with rss_feeds +
  rss_articles. Test was pre-existing flake (verified via `git stash` on
  pre-W1 main).

## Local validation gate (G1-G4) — all PASS

| Gate | Result | Evidence |
|---|---|---|
| G1 migration 008 idempotency | 1st run: 577 rows migrated all source='wechat', integrity:[(ok,)], fk:[]; 2nd run: SKIP all 5 ops | `.scratch/ir-4-w1-mig008-1st.log`, `.scratch/ir-4-w1-mig008-2nd.log`, `.scratch/ir-4-w1-integrity.log` |
| G2 dual-source SQL | KOL=149, RSS=1600, total 1749 candidates; cursor.description = 7 columns; transition row 149; anti-join 0 false positives | `.scratch/ir-4-w1-dualsql.log` |
| G3 pytest | 37/37 PASS (24 SQL + 13 migration); 3 pre-existing failures verified pre-existing on main pre-W1 via git stash | `.scratch/ir-4-w1-pytest-w1tests.log` |
| G4 harness smoke | `KOL_SCAN_DB_PATH=.test-008.copy bash scripts/local_e2e.sh kol --max-articles 1 --dry-run`: EXIT=0, total inputs=1749 | `.scratch/ir-4-w1-kol-dryrun.log` |

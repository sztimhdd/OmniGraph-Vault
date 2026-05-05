-- Migration: expand ingestions.status CHECK constraint
-- PR:     batch_ingest_from_spider.py 66e9c03 (2026-05-04)
-- 
-- Problem: 'skipped_ingested' and 'dry_run' not in CHECK whitelist
-- Fix:     recreate table with expanded constraint
--
-- Run:     python3 migrations/002_expand_ingestions_check.py <path/to/kol_scan.db>
--
-- Or manual via sqlite3:
--   sqlite3 kol_scan.db
--   > .read migrations/002_expand_ingestions_check.sql

-- Idempotency check
SELECT CASE
    WHEN sql LIKE '%skipped_ingested%' THEN 'SKIP: already migrated'
    ELSE 'OK: proceeding with migration'
END AS migration_status
FROM sqlite_master
WHERE type='table' AND name='ingestions';

-- ============================================================
-- STOP HERE if the SELECT above returned 'SKIP: already migrated'
-- ============================================================

BEGIN TRANSACTION;

CREATE TABLE ingestions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped', 'skipped_ingested', 'dry_run')),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    enrichment_id TEXT,
    UNIQUE(article_id)
);

INSERT INTO ingestions_new SELECT * FROM ingestions;

DROP TABLE ingestions;

ALTER TABLE ingestions_new RENAME TO ingestions;

COMMIT;

-- Verification
SELECT sql FROM sqlite_master WHERE type='table' AND name='ingestions';

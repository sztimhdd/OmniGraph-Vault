-- Migration: add 'skipped_graded' to ingestions.status CHECK constraint
-- PR:     batch_ingest_from_spider.py (graded classification MVP, 2026-05-05)
--
-- Adds 'skipped_graded' status for articles that fail the graded
-- classification probe (OMNIGRAPH_GRADED_CLASSIFY=1).
--
-- Run:     python3 migrations/003_expand_ingestions_status_graded.py <path/to/kol_scan.db>
-- Or manual via sqlite3:
--   sqlite3 kol_scan.db
--   > .read migrations/003_expand_ingestions_status_graded.sql

SELECT CASE
    WHEN sql LIKE '%skipped_graded%' THEN 'SKIP: already migrated'
    ELSE 'OK: proceeding with migration'
END AS migration_status
FROM sqlite_master
WHERE type='table' AND name='ingestions';

BEGIN TRANSACTION;

CREATE TABLE ingestions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    status TEXT NOT NULL CHECK(status IN (
        'ok', 'failed', 'skipped', 'skipped_ingested',
        'dry_run', 'skipped_graded'
    )),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    enrichment_id TEXT,
    UNIQUE(article_id)
);

INSERT INTO ingestions_new SELECT * FROM ingestions;

DROP TABLE ingestions;

ALTER TABLE ingestions_new RENAME TO ingestions;

COMMIT;

SELECT sql FROM sqlite_master WHERE type='table' AND name='ingestions';

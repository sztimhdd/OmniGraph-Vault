-- Migration: collapse classifications to one row per article_id + UNIQUE index
-- Quick:   260506-se5 (2026-05-06)
--
-- Problem: classifications.UNIQUE(article_id, topic) allowed multiple rows per
--          article_id (one per topic). Production code already coalesces
--          duplicates via the MAX(classified_at) subquery in
--          batch_ingest_from_spider.py:1304-1315 — so the multi-row state
--          buys nothing operationally and grows silently every time
--          batch_classify_kol.py:445 and batch_ingest_from_spider.py:1025
--          run side-by-side.
-- Fix:     dedup keeping MAX(rowid) per article_id (matches cron query
--          MAX(classified_at) semantics — newer row wins), then add
--          UNIQUE(article_id) so future bare INSERTs raise IntegrityError
--          and ON CONFLICT(article_id) DO UPDATE upserts cleanly.
--
-- ============================================================
-- OPERATOR: BACKUP THE DB FILE BEFORE RUNNING THIS MIGRATION
--   cp data/kol_scan.db data/kol_scan.db.backup-pre-mig004-$(date +%Y%m%d-%H%M%S)
-- (Per CLAUDE.md Lessons 2026-05-06 #2 — backup file before any DELETE.)
-- ============================================================
--
-- Run:     sqlite3 <path/to/kol_scan.db> < migrations/004_classifications_unique_article_id.sql
--
-- Idempotent: dedup DELETE on already-deduped table is a no-op (0 rows
-- affected); CREATE UNIQUE INDEX IF NOT EXISTS is a no-op if the index
-- already exists.

DELETE FROM classifications
WHERE rowid NOT IN (
    SELECT MAX(rowid) FROM classifications GROUP BY article_id
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_classifications_article_id
    ON classifications(article_id);

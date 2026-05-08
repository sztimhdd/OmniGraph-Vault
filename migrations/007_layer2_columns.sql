-- Migration 007: Layer 2 verdict columns (v3.5 Ingest Refactor)
-- Phase:   ir-2 (Real Layer 2 + full-body scoring)
-- REQ:     LF-2.5
-- Date:    2026-05-07
--
-- Adds 4 columns × 2 tables = 8 total columns. All additive, no data touched.
-- Existing rows have all four layer2_* columns NULL (re-evaluated by next ingest).
--
-- ============================================================
-- OPERATOR: BACKUP THE DB FILE BEFORE RUNNING THIS MIGRATION
--   cp data/kol_scan.db data/kol_scan.db.backup-pre-mig007-$(date +%Y%m%d-%H%M%S)
-- (Per CLAUDE.md Lessons 2026-05-06 #2.)
-- ============================================================
--
-- This .sql file is NOT idempotent: re-running raises "duplicate column name".
-- For idempotent runs use the .py twin:
--   python migrations/007_layer2_columns.py [path/to/kol_scan.db]

ALTER TABLE articles      ADD COLUMN layer2_verdict        TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer2_reason         TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer2_at             TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer2_prompt_version TEXT NULL;

ALTER TABLE rss_articles  ADD COLUMN layer2_verdict        TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer2_reason         TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer2_at             TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer2_prompt_version TEXT NULL;

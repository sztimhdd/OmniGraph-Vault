-- Migration 006: Layer 1 verdict columns (v3.5 Ingest Refactor)
-- Phase:   ir-1 (Real Layer 1 + KOL ingest wiring)
-- REQ:     LF-1.6
-- Date:    2026-05-07
--
-- Adds 4 columns × 2 tables = 8 total columns. All additive, no data touched.
-- Existing rows have all four layer1_* columns NULL (re-evaluated on next ingest).
--
-- ============================================================
-- OPERATOR: BACKUP THE DB FILE BEFORE RUNNING THIS MIGRATION
--   cp data/kol_scan.db data/kol_scan.db.backup-pre-mig006-$(date +%Y%m%d-%H%M%S)
-- (Per CLAUDE.md Lessons 2026-05-06 #2 — backup file before any schema change.)
-- ============================================================
--
-- This .sql file is NOT idempotent: re-running raises "duplicate column name".
-- For idempotent runs (e.g. CI / local dev re-applies), use the .py twin:
--   python migrations/006_layer1_columns.py [path/to/kol_scan.db]

ALTER TABLE articles      ADD COLUMN layer1_verdict        TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_reason         TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_at             TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_prompt_version TEXT NULL;

ALTER TABLE rss_articles  ADD COLUMN layer1_verdict        TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_reason         TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_at             TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_prompt_version TEXT NULL;

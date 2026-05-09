-- Migration 008: ingestions table dual-source rebuild (v3.5 ir-4)
-- Phase:   ir-4 (RSS integration into batch ingest pipeline)
-- REQ:     LF-4.4
-- Date:    2026-05-08
--
-- Rebuilds the `ingestions` table to support a dual-source identity space:
--   * (article_id, source) is the new primary identity (was just article_id)
--   * source ∈ {'wechat', 'rss'} indicates which source-table the
--     article_id refers to: source='wechat' → articles(id);
--     source='rss' → rss_articles(id)
--
-- Why a rebuild (not ALTER): SQLite ALTER TABLE cannot DROP CONSTRAINT or
-- modify an existing UNIQUE/CHECK. Need to:
--   * Replace UNIQUE(article_id) with UNIQUE(article_id, source)
--   * Drop the FK to articles(id) (a single FK can't represent dual-source)
--   * Add CHECK on source enumerator
-- The dual-source semantics are enforced at the application layer
-- (lib.article_filter.persist_layer1/2_verdicts already source-aware,
-- batch_ingest_from_spider INSERT sites pass source explicitly).
--
-- Existing 'wechat'-source rows: all 577 production ingestions are KOL
-- articles, so the INSERT SELECT below stamps source='wechat' for all of
-- them.
--
-- ============================================================
-- OPERATOR: BACKUP THE DB FILE BEFORE RUNNING THIS MIGRATION
--   cp data/kol_scan.db data/kol_scan.db.backup-pre-mig008-$(date +%Y%m%d-%H%M%S)
-- (Per CLAUDE.md Lessons 2026-05-06 #2.)
-- ============================================================
--
-- This .sql file is NOT idempotent: re-running on a post-008 DB raises
-- "table ingestions_new already exists" or similar. For idempotent runs
-- (e.g. CI / local dev re-applies) use the .py twin:
--   python migrations/008_ingestions_dual_source.py [path/to/kol_scan.db] [--dry-run]

CREATE TABLE ingestions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'wechat'
        CHECK (source IN ('wechat', 'rss')),
    status TEXT NOT NULL CHECK (status IN (
        'ok', 'failed', 'skipped', 'skipped_ingested',
        'dry_run', 'skipped_graded'
    )),
    ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
    enrichment_id TEXT,
    UNIQUE (article_id, source)
);

INSERT INTO ingestions_new (id, article_id, source, status, ingested_at, enrichment_id)
    SELECT id, article_id, 'wechat', status, ingested_at, enrichment_id
    FROM ingestions;

DROP TABLE ingestions;

ALTER TABLE ingestions_new RENAME TO ingestions;

CREATE INDEX idx_ingestions_article_source ON ingestions(article_id, source);

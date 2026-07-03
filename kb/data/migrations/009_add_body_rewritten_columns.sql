-- 009: Add body_rewritten column for kb-v2.3 display-only LLM rewrite.
-- Additive, non-breaking, idempotent (run_migrations.py guards via PRAGMA table_info).
--
-- rewrite_body_cron.py writes clean bodies here. The INPUT to the rewrite is the
-- D-14-resolved DISPLAY content (final_content.enriched.md then final_content.md
-- then body_cleaned then body) -- NOT raw DB body. DB body carries WeChat CDN URLs,
-- not the localhost:8765 URLs the display content carries.
--
-- get_article_body() D-14 chain checks body_rewritten FIRST, above the filesystem
-- final_content.md sources. body_rewritten is display-only -- KG (LightRAG) always
-- reads the original body, never this column.
--
-- body_cleaned is NOT reused as the slot -- it is 0-populated and shadowed by
-- final_content.md for ~70 percent of the corpus.
-- See decision_rewrite_display_only_kg_uses_original.md (incl. CRITICAL CORRECTION).
--
-- No backfill required (NULL is correct until the plan-03 cron runs).
-- Rollback: ALTER TABLE <t> DROP COLUMN body_rewritten (SQLite >= 3.35).

ALTER TABLE articles ADD COLUMN body_rewritten TEXT;
ALTER TABLE articles ADD COLUMN rewritten_at DATETIME;
ALTER TABLE rss_articles ADD COLUMN body_rewritten TEXT;
ALTER TABLE rss_articles ADD COLUMN rewritten_at DATETIME;

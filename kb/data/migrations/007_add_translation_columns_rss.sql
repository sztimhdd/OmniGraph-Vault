-- 007: Mirror migration 006 onto rss_articles (kb-v2.2-7 bilingual-by-site-language)
-- Additive, non-breaking (C3 contract preserved).
-- Applied by run_migrations.py which guards idempotency via PRAGMA table_info.
--
-- Rollback: ALTER TABLE rss_articles DROP COLUMN <col> for each (SQLite >= 3.35).
ALTER TABLE rss_articles ADD COLUMN body_translated TEXT;
ALTER TABLE rss_articles ADD COLUMN title_translated TEXT;
ALTER TABLE rss_articles ADD COLUMN translated_lang VARCHAR(5);
ALTER TABLE rss_articles ADD COLUMN translated_at DATETIME;

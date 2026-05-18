-- 006: Add translation columns to articles table (kb-v2.2-2 F1')
-- Additive, non-breaking (C3 contract preserved).
-- Applied by run_migrations.py which guards idempotency via PRAGMA table_info.
ALTER TABLE articles ADD COLUMN body_translated TEXT;
ALTER TABLE articles ADD COLUMN title_translated TEXT;
ALTER TABLE articles ADD COLUMN translated_lang VARCHAR(5);
ALTER TABLE articles ADD COLUMN translated_at DATETIME;

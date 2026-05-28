-- 008: Backfill body_cleaned + body_repositioned columns missed by ef4367a (2026-05-22).
-- Additive, non-breaking, idempotent (run_migrations.py guards via PRAGMA table_info).
--
-- Context: ef4367a added unconditional SELECTs of body_cleaned (KOL+RSS) and
-- body_repositioned (KOL only) to kb/data/article_query.py without shipping the
-- corresponding ALTER TABLE migrations. databricks-deploy/_kdb_images_fix_VERIFICATION.md
-- L1357 declared the columns "Hermes prod 不需要" — that was wrong: any prod DB
-- without these columns crashes list_articles() with sqlite3.OperationalError.
--
-- Verified failure mode (Aliyun 2026-05-28):
--   sqlite3.OperationalError: no such column: body_cleaned
--
-- No backfill required (NULL is correct semantics). get_article_body()
-- already falls back via body_cleaned OR body OR empty (article_query.py).
--
-- Rollback: ALTER TABLE <t> DROP COLUMN <col> (SQLite >= 3.35).

ALTER TABLE articles ADD COLUMN body_cleaned TEXT;
ALTER TABLE articles ADD COLUMN body_repositioned TEXT;
ALTER TABLE rss_articles ADD COLUMN body_cleaned TEXT;

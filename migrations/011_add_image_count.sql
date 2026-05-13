-- Migration 011: image_count column for fresh-article budget
-- Phase:   quick-260513-q15 (D2 from Hermes 2026-05-13 design review)
-- REQ:     IMC-01 (issue #2 follow-up; T1-b1 d767580 fixed re-ingestion only)
-- Date:    2026-05-13
--
-- Background: T1-b1 disk fallback (_count_images_on_disk) saves re-ingestion
-- but fresh daily-cron path runs BEFORE scrape, when images/{hash}/ does not
-- yet exist. _compute_article_budget_s sees image_count=0, returns 900s floor,
-- vision-heavy articles (51 images = ~1500s real need) timeout.
--
-- Fix: persist image_count at scrape time (ingest_wechat.py post manifest
-- write); pass through SELECT -> tuple -> budget call. T1-b1 fallback retained
-- as defense-in-depth.
--
-- Schema: INTEGER DEFAULT 0 with NO CHECK constraint (Hermes review § 5.a --
-- zero silent-drop risk; non-int values would have been caught by application
-- layer at INSERT time anyway).

ALTER TABLE articles     ADD COLUMN image_count INTEGER DEFAULT 0;
ALTER TABLE rss_articles ADD COLUMN image_count INTEGER DEFAULT 0;

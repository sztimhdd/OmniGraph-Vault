"""Quick 260511-b4k: rescrape missing bodies for candidate RSS articles.

SELECT rss_articles WHERE layer1_verdict='candidate' AND body IS NULL,
re-scrape via b4k-fixed lib.scraper.scrape_url(), write body back.

Intended: daily cron after rss-fetch (06:00), before classify/ingest.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import sys
from pathlib import Path

# Defensive sys.path insert: cron Script-type delivery (no_agent=true) does NOT
# pre-set PYTHONPATH, so `from lib.scraper import scrape_url` would ImportError.
# Inserting project-root makes the script work under all invocation forms
# (manual `python enrichment/rss_rescrape_bodies.py`, Hermes Script-type cron,
# `cd ~/OmniGraph-Vault && python enrichment/rss_rescrape_bodies.py` bash form).
# Discovered 2026-05-11 17:55 ADT during manual fire (21/21 ImportError → 20/21
# OK after `PYTHONPATH=. python ...`).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DB_PATH = _PROJECT_ROOT / "data" / "kol_scan.db"
DELAY_S = 1.5   # polite delay between scrapes

logger = logging.getLogger(__name__)


async def rescrape_one(url: str) -> str | None:
    from lib.scraper import scrape_url

    result = await scrape_url(url)
    if result and not result.summary_only:
        body = (result.markdown or "").strip() or (result.content_html or "").strip()
        if body:
            return body
    return None


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT id, url FROM rss_articles "
        "WHERE layer1_verdict = 'candidate' AND body IS NULL"
    ).fetchall()

    if not rows:
        logger.info("No candidate articles with missing body — nothing to do.")
        conn.close()
        return 0

    logger.info("Found %d candidate(s) with NULL body", len(rows))
    rescued = 0

    for art_id, url in rows:
        try:
            body = await rescrape_one(url)
            if body:
                conn.execute(
                    "UPDATE rss_articles SET body = ? WHERE id = ?",
                    (body, art_id),
                )
                conn.commit()
                rescued += 1
                logger.info("OK  id=%d  len=%d  %s", art_id, len(body), url[:80])
            else:
                logger.info("SKIP id=%d  (empty/scrape-failed) %s", art_id, url[:80])
        except Exception:
            logger.exception("ERR id=%d  %s", art_id, url[:80])

        await asyncio.sleep(DELAY_S)

    conn.close()
    logger.info("Done: rescued %d/%d", rescued, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

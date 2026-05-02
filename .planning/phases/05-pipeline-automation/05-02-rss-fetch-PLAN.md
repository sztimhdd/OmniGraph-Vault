---
phase: 05-pipeline-automation
plan: 02
type: execute
wave: 1
depends_on: [05-01]
files_modified:
  - enrichment/rss_fetch.py
  - tests/unit/test_rss_fetch.py
autonomous: true
requirements: [D-15]
must_haves:
  truths:
    - "`enrichment/rss_fetch.py` fetches all 92 feeds, deduplicates by URL, inserts into `rss_articles`"
    - "Each feed has independent try/except — one feed's 404 does not abort the full run"
    - "Pre-filter skips articles < 500 chars and non-English/non-Chinese (langdetect)"
    - "2s delay between feeds (PRD §3.1.3); per-feed timeout 15s"
    - "Supports `--max-feeds N` and `--dry-run` CLI flags"
    - "Idempotent — re-running produces no duplicates (URL UNIQUE constraint)"
  artifacts:
    - path: "enrichment/rss_fetch.py"
      provides: "OPML parse + feedparser fetch + dedup + SQLite insert"
      min_lines: 120
    - path: "tests/unit/test_rss_fetch.py"
      provides: "Mock feedparser + SQLite tests for pre-filter, dedup, feed-level fault tolerance"
      min_lines: 60
  key_links:
    - from: "enrichment/rss_fetch.py"
      to: "rss_feeds table (query active feeds)"
      via: "sqlite3 SELECT xml_url FROM rss_feeds WHERE active=1"
      pattern: "FROM rss_feeds"
    - from: "enrichment/rss_fetch.py"
      to: "rss_articles table (INSERT OR IGNORE)"
      via: "INSERT OR IGNORE INTO rss_articles"
      pattern: "INSERT OR IGNORE INTO rss_articles"
---

<objective>
Build `enrichment/rss_fetch.py`: an RSS/Atom fetcher that iterates over active rows in `rss_feeds`, parses each feed with `feedparser`, applies length + language pre-filter, and writes new articles to `rss_articles` with URL-based dedup. Feed-level fault tolerance is mandatory per PRD §3.1.3.

Purpose: This is the data source for Plan 05-03 (classify) and Plan 05-04 (orchestrate). Without dedup and fault tolerance, the daily cron would crash on the first 404 feed.

Output: runnable fetcher + unit tests for dedup, pre-filter, and fault tolerance.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-RESEARCH.md
@.planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md
@enrichment/rss_schema.py
@batch_scan_kol.py

<interfaces>
From `batch_scan_kol.py` (existing pattern for SQLite writes):
```python
# Usually _persist_* helpers with failure-tolerant logging
try:
    conn.execute("INSERT OR IGNORE INTO ...", (...))
    conn.commit()
except Exception as e:
    logger.warning(f"DB write failed: {e}")
```

Expected rss_articles row shape (from PRD §3.1.4):
- feed_id (FK)
- title
- url (UNIQUE)
- author
- summary
- content_hash
- published_at
- content_length

feedparser API:
```python
import feedparser
parsed = feedparser.parse(url)
# parsed.entries -> list of entries
# entry.title, entry.link, entry.author, entry.summary, entry.published
# entry.content -> list of {value: html, ...} (Atom); often same as entry.summary for RSS 2.0
```

langdetect:
```python
from langdetect import detect
lang = detect(text)  # 'en', 'zh-cn', 'zh-tw', etc.
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 2.1: Build `enrichment/rss_fetch.py` with pre-filter, dedup, fault tolerance</name>
  <files>enrichment/rss_fetch.py, tests/unit/test_rss_fetch.py</files>
  <behavior>
    - Test 1: A feed with 3 entries inserts 3 rows into `rss_articles`.
    - Test 2: Running the same fetch twice produces the same final row count (URL dedup works).
    - Test 3: An entry with body < 500 chars is skipped (pre-filter) and NOT inserted.
    - Test 4: An entry whose body is detected as a non-supported language (e.g., Russian) is skipped.
    - Test 5: When one feed raises (simulate `feedparser.parse` returning `bozo=1` with no entries, OR raise HTTPError), the run continues to the next feed and increments `rss_feeds.error_count` for the failing feed.
    - Test 6: After a successful fetch, `rss_feeds.last_fetched_at` is set to a recent timestamp.
  </behavior>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-PRD.md §3.1.3 (fetcher responsibilities, 2s delay, fault tolerance)
    - .planning/phases/05-pipeline-automation/05-PRD.md §3.1.4 (rss_articles column list)
    - .planning/phases/05-pipeline-automation/05-RESEARCH.md Pitfall 6 (RSS timeout strategy)
    - enrichment/rss_schema.py (column names)
    - batch_scan_kol.py (existing logging + SQLite patterns)
  </read_first>
  <action>
    Create `enrichment/rss_fetch.py`:

    ```python
    """RSS fetcher — iterates over active rss_feeds, writes new rows to rss_articles.

    Pre-filter (PRD §3.1.3):
      - skip entries < 500 chars
      - skip entries whose detected language is not in {'en', 'zh-cn', 'zh-tw', 'zh'}

    Fault tolerance (PRD §3.1.3):
      - per-feed try/except
      - timeout per feed = 15s (feedparser supports timeout via socket.setdefaulttimeout)
      - 2s delay between feeds
      - increment rss_feeds.error_count on failure
    """
    from __future__ import annotations

    import argparse
    import hashlib
    import logging
    import socket
    import sqlite3
    import sys
    import time
    from pathlib import Path
    from typing import Any, Iterator

    import feedparser
    from langdetect import DetectorFactory, LangDetectException, detect

    DetectorFactory.seed = 0  # deterministic language detection
    DB = Path("data/kol_scan.db")
    FEED_DELAY_SECONDS = 2.0
    FEED_TIMEOUT_SECONDS = 15
    MIN_CONTENT_CHARS = 500
    SUPPORTED_LANGS = {"en", "zh-cn", "zh-tw", "zh"}
    USER_AGENT = "OmniGraph-Vault/1.0 (+https://github.com/sztimhdd/OmniGraph-Vault)"

    logger = logging.getLogger("rss_fetch")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    def _content_text(entry: Any) -> str:
        """Extract largest text body from a feedparser entry."""
        if getattr(entry, "content", None):
            bodies = [c.get("value", "") for c in entry.content]
            return max(bodies, key=len, default="")
        return getattr(entry, "summary", "") or getattr(entry, "description", "") or ""

    def _should_keep(text: str) -> tuple[bool, str]:
        """Return (keep, reason)."""
        if len(text) < MIN_CONTENT_CHARS:
            return False, "too_short"
        try:
            lang = detect(text[:2000])
        except LangDetectException:
            return False, "langdetect_failed"
        if lang not in SUPPORTED_LANGS:
            return False, f"unsupported_lang:{lang}"
        return True, ""

    def _fetch_feed(xml_url: str) -> list[dict]:
        """Fetch one feed; return list of article dicts ready for INSERT."""
        socket.setdefaulttimeout(FEED_TIMEOUT_SECONDS)
        parsed = feedparser.parse(xml_url, agent=USER_AGENT)
        # feedparser sets bozo=1 and bozo_exception on fetch/parse error
        if parsed.bozo and not parsed.entries:
            raise RuntimeError(f"feed unreachable or malformed: {parsed.bozo_exception!r}")
        articles = []
        for e in parsed.entries:
            text = _content_text(e)
            keep, reason = _should_keep(text)
            if not keep:
                logger.debug(f"skip {getattr(e, 'link', '?')}: {reason}")
                continue
            articles.append({
                "title": getattr(e, "title", "") or "",
                "url": getattr(e, "link", "") or "",
                "author": getattr(e, "author", None),
                "summary": getattr(e, "summary", "") or "",
                "content_hash": hashlib.md5(text.encode("utf-8")).hexdigest(),
                "published_at": getattr(e, "published", None),
                "content_length": len(text),
            })
        return [a for a in articles if a["url"]]

    def run(max_feeds: int | None, dry_run: bool) -> dict:
        conn = sqlite3.connect(DB)
        feeds = conn.execute(
            "SELECT id, xml_url, name FROM rss_feeds WHERE active=1 ORDER BY id"
        ).fetchall()
        if max_feeds is not None:
            feeds = feeds[:max_feeds]
        stats = {"feeds_ok": 0, "feeds_fail": 0, "articles_inserted": 0}
        for feed_id, xml_url, name in feeds:
            try:
                articles = _fetch_feed(xml_url)
                if not dry_run:
                    for a in articles:
                        try:
                            cur = conn.execute(
                                """INSERT OR IGNORE INTO rss_articles
                                   (feed_id, title, url, author, summary, content_hash,
                                    published_at, content_length)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                (feed_id, a["title"], a["url"], a["author"], a["summary"],
                                 a["content_hash"], a["published_at"], a["content_length"]),
                            )
                            # L-21 fix: cursor.rowcount == 1 is the correct per-row metric
                            # (conn.total_changes is cumulative across the connection lifetime)
                            if cur.rowcount == 1:
                                stats["articles_inserted"] += 1
                        except Exception as ex:
                            logger.warning(f"insert failed for {a['url']}: {ex}")
                    conn.execute(
                        "UPDATE rss_feeds SET last_fetched_at=datetime('now','localtime'), error_count=0 WHERE id=?",
                        (feed_id,),
                    )
                    conn.commit()
                stats["feeds_ok"] += 1
                logger.info(f"OK {name}: {len(articles)} candidates")
            except Exception as ex:
                stats["feeds_fail"] += 1
                logger.warning(f"FAIL {name} ({xml_url}): {ex}")
                if not dry_run:
                    conn.execute("UPDATE rss_feeds SET error_count=error_count+1 WHERE id=?", (feed_id,))
                    conn.commit()
            time.sleep(FEED_DELAY_SECONDS)
        conn.close()
        return stats

    def main() -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--max-feeds", type=int, default=None)
        p.add_argument("--dry-run", action="store_true")
        args = p.parse_args()
        stats = run(args.max_feeds, args.dry_run)
        logger.info(f"stats: {stats}")
        print(f'{{"status": "ok", "feeds_ok": {stats["feeds_ok"]}, "feeds_fail": {stats["feeds_fail"]}, "articles_inserted": {stats["articles_inserted"]}}}')

    if __name__ == "__main__":
        main()
    ```

    Create `tests/unit/test_rss_fetch.py` exercising the 6 behaviors using `unittest.mock.patch("feedparser.parse", ...)` with a minimal fake parsed object (`SimpleNamespace(bozo=0, entries=[...], bozo_exception=None)`). Use `:memory:` SQLite with `init_rss_schema` seeded.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_rss_fetch.py -v &amp;&amp; venv/bin/python enrichment/rss_fetch.py --max-feeds 5 --dry-run"</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/rss_fetch.py` exists; ≥ 120 lines.
    - `grep -q "INSERT OR IGNORE INTO rss_articles" enrichment/rss_fetch.py` returns 0.
    - `grep -q "FEED_DELAY_SECONDS = 2.0" enrichment/rss_fetch.py` returns 0.
    - `grep -q "MIN_CONTENT_CHARS = 500" enrichment/rss_fetch.py` returns 0.
    - All 6 pytest tests pass.
    - `--dry-run --max-feeds 5` exits 0 on remote with no SQLite writes (`SELECT COUNT(*) FROM rss_articles` unchanged).
    - Non-dry run inserts ≥ 10 articles on first pass (reality check; feeds produce content).
    - Re-running non-dry produces 0 (or near-0) new inserts — dedup works.
  </acceptance_criteria>
  <done>RSS fetcher operational; feeds data flowing into `rss_articles`.</done>
</task>

</tasks>

<verification>
- `enrichment/rss_fetch.py` runs end-to-end on remote with `--dry-run --max-feeds 5`.
- Unit tests pass (6 scenarios).
- Non-dry-run ingest inserts new rows; re-run ingests 0 (dedup).
</verification>

<success_criteria>
- All 92 feeds iterated with per-feed fault tolerance.
- Pre-filter drops short/non-supported-language entries.
- URL-based dedup idempotent across runs.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-02-SUMMARY.md` with: first-run article count, feeds_ok/feeds_fail split, example pre-filter drops, and the idempotency re-run count.
</output>

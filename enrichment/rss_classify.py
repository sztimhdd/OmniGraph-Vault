"""RSS article classifier — full-body multi-topic classify via DeepSeek.

Phase 20 RCL-01..03 (D-20.01..04):
  - Reads `rss_articles.body` (Phase 19 column) for full-text classify; falls
    back to `summary` when body is NULL.
  - Single LLM call per article covering ALL topics together (not one call per
    topic). Imports `_build_fullbody_prompt` + `_call_fullbody_llm` directly
    from `batch_classify_kol` (D-20.01 single source of truth — no copy).
  - Writes 5 columns on `rss_articles` after each successful classify:
    body, body_scraped_at, depth, topics (JSON), classify_rationale.
  - 4.5s throttle between articles for DeepSeek 15 RPM safety (D-20.03).

Usage:
    venv/bin/python enrichment/rss_classify.py
    venv/bin/python enrichment/rss_classify.py --article-id 1 --dry-run
    venv/bin/python enrichment/rss_classify.py --max-articles 20
    venv/bin/python enrichment/rss_classify.py --topic Agent --topic LLM
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# D-20.01: import from batch_classify_kol — single source of truth.
# FULLBODY_TRUNCATION_CHARS + prompt builder + LLM caller all live there;
# future KOL prompt tweaks propagate to RSS for free.
import batch_classify_kol
from batch_classify_kol import (
    get_deepseek_api_key,
    _build_fullbody_prompt,
    _call_fullbody_llm,
    FULLBODY_TRUNCATION_CHARS,
)

DB = Path(os.environ.get("KOL_SCAN_DB_PATH", "data/kol_scan.db"))
DEFAULT_TOPICS: tuple[str, ...] = ("Agent", "LLM", "RAG", "NLP", "CV")
# D-20.03: DeepSeek 15 RPM ceiling — 60s / 15 = 4.0s + 12.5% safety margin.
FULLBODY_THROTTLE_SECONDS = 4.5

logger = logging.getLogger("rss_classify")


def _call_deepseek(prompt: str, api_key: str) -> dict:
    """Legacy per-topic DeepSeek caller — kept as stub for test monkeypatching.

    Phase 20 no longer calls this function; all classify calls go through
    `batch_classify_kol._call_fullbody_llm` instead.  Tests that monkeypatch
    this name (to assert it is never called) need the attribute to exist on the
    module; removing it would raise AttributeError inside monkeypatch.setattr.
    """
    raise NotImplementedError(
        "_call_deepseek must not be called after Phase 20 RCL upgrade; "
        "use batch_classify_kol._call_fullbody_llm instead"
    )


def _eligible_articles(
    conn: sqlite3.Connection,
    topics: tuple[str, ...],
    article_id: int | None,
    max_articles: int | None,
) -> list[tuple[int, str, str, str, str]]:
    """Return rows eligible for full-body classify.

    Returns tuples of (id, title, url, body, summary).  Callers use
    body if non-empty, summary as fallback (D-20.04 inline-scrape is a
    future enhancement; for now summary is the fallback when body is NULL).

    Eligibility: `depth IS NULL` (not yet classified in Phase-20 schema).
    When article_id is given: bypass eligibility — supports re-classify.
    """
    if article_id is not None:
        rows = conn.execute(
            "SELECT id, title, url, COALESCE(body, '') AS body, COALESCE(summary, '') AS summary"
            " FROM rss_articles WHERE id=?",
            (article_id,),
        ).fetchall()
        return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]

    # CLI --max-articles wins; otherwise fall back to env cap (default 500).
    # Parse failures are silent: bad env value -> fallback 500, never raise.
    if max_articles is None:
        try:
            max_articles = int(os.environ.get("OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP", "500"))
        except ValueError:
            max_articles = 500

    sql = (
        "SELECT id, title, url, COALESCE(body, '') AS body, COALESCE(summary, '') AS summary"
        " FROM rss_articles"
        " WHERE depth IS NULL"
        " ORDER BY fetched_at DESC"
        " LIMIT ?"
    )
    rows = conn.execute(sql, (max_articles,)).fetchall()
    return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]


def run(
    topics: tuple[str, ...],
    article_id: int | None,
    max_articles: int | None,
    dry_run: bool,
    db_path: Path = DB,
) -> dict:
    """Full-body multi-topic classify (D-20.01..04, RCL-01..03).

    For each eligible row:
      1. Pick body source: row.body preferred, row.summary fallback.
      2. Build prompt via batch_classify_kol._build_fullbody_prompt(title, body,
         topic_filter=list(topics)) — single call, all topics together.
      3. Call batch_classify_kol._call_fullbody_llm(prompt) — returns
         {depth, topics, rationale} or None on any error.
      4. Parse result; UPDATE rss_articles with 5 Phase-19 columns.
      5. time.sleep(FULLBODY_THROTTLE_SECONDS) between articles.
    """
    conn = sqlite3.connect(db_path)
    rows = _eligible_articles(conn, topics, article_id, max_articles)
    api_key: str | None = None
    if not dry_run:
        api_key = get_deepseek_api_key()
        if not api_key:
            conn.close()
            raise RuntimeError(
                "DEEPSEEK_API_KEY not found in env / ~/.hermes/.env / config.yaml"
            )

    stats = {"classified": 0, "failed": 0, "dry_run_planned": 0}
    for aid, title, url, body, summary in rows:
        text = body or summary
        if not text:
            logger.warning("a=%s skipped: empty body and summary", aid)
            stats["failed"] += 1
            continue

        if dry_run:
            logger.info("DRY: a=%s topics=%s", aid, topics)
            stats["dry_run_planned"] += 1
            continue

        # D-20.01 / D-20.02: single prompt covers all topics together.
        # Call via module reference so monkeypatch on batch_classify_kol module
        # attributes takes effect during tests.
        prompt = batch_classify_kol._build_fullbody_prompt(
            title, text, topic_filter=list(topics)
        )
        result = batch_classify_kol._call_fullbody_llm(prompt)
        if result is None:
            logger.warning("classify failed a=%s (LLM returned None)", aid)
            stats["failed"] += 1
            time.sleep(FULLBODY_THROTTLE_SECONDS)
            continue

        try:
            depth = int(result["depth"])
            if not 1 <= depth <= 3:
                raise ValueError(f"depth out of range: {depth}")
            topics_json = json.dumps(result.get("topics", []))
            rationale = str(result.get("rationale", ""))[:1000]
        except (KeyError, ValueError, TypeError) as ex:
            logger.warning("classify parse failed a=%s: %s", aid, ex)
            stats["failed"] += 1
            time.sleep(FULLBODY_THROTTLE_SECONDS)
            continue

        body_scraped_at = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                """UPDATE rss_articles
                   SET body = COALESCE(body, ?),
                       body_scraped_at = COALESCE(body_scraped_at, ?),
                       depth = ?,
                       topics = ?,
                       classify_rationale = ?
                   WHERE id = ?""",
                (text, body_scraped_at, depth, topics_json, rationale, aid),
            )
            conn.commit()
            stats["classified"] += 1
            logger.info("a=%s depth=%s topics=%s", aid, depth, result.get("topics"))
        except sqlite3.Error as ex:
            logger.warning("UPDATE failed a=%s: %s", aid, ex)
            stats["failed"] += 1

        time.sleep(FULLBODY_THROTTLE_SECONDS)

    conn.close()
    return stats


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument(
        "--topic",
        action="append",
        default=None,
        help="Topic(s) to classify against (default: Agent,LLM,RAG,NLP,CV)",
    )
    p.add_argument("--article-id", type=int, default=None)
    p.add_argument("--max-articles", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    topics = tuple(args.topic) if args.topic else DEFAULT_TOPICS
    stats = run(topics, args.article_id, args.max_articles, args.dry_run)
    print(
        json.dumps(
            {
                "status": "ok",
                "classified": stats["classified"],
                "failed": stats["failed"],
                "dry_run_planned": stats["dry_run_planned"],
            }
        )
    )


if __name__ == "__main__":
    main()

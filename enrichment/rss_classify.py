"""RSS article classifier — DeepSeek tags each article with depth_score per topic.

Mirrors batch_classify_kol.py's DeepSeek pattern (raw HTTP to api.deepseek.com).
Adapted for RSS:
  - reads from rss_articles (not articles)
  - writes to rss_classifications
  - prompt asks LLM to output in Chinese regardless of source-article language
    (D-08: EN->CN handled inside the classifier prompt, no separate translation)

Topic taxonomy shared with KOL: Agent, LLM, RAG, NLP, CV (PRD §3.1.5).

LLM routing (Phase 7 D-09 supersession 2026-05-02):
  LLM calls use DeepSeek via raw HTTP. Gemini is Vision + Embedding only.

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
from pathlib import Path

import requests

# Reuse the production key resolver from batch_classify_kol.py (env ->
# ~/.hermes/.env -> config.yaml).
from batch_classify_kol import get_deepseek_api_key

DB = Path("data/kol_scan.db")
DEFAULT_TOPICS: tuple[str, ...] = ("Agent", "LLM", "RAG", "NLP", "CV")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = os.environ.get("CLASSIFIER_MODEL", "deepseek-chat")
THROTTLE_SECONDS = 0.3

CLASSIFY_PROMPT = """你是技术文章分类器。给定一篇文章的标题和正文(可能是英文或中文),请对它在主题 "{topic}" 上做分类。

**规则**:
- 必须用中文回答 reason(无论原文语言)。
- depth_score: 1=资讯/快讯, 2=技术教程/分析, 3=深度研究/架构拆解。
- relevant: 0 或 1(是否与主题相关)。
- excluded: 0 或 1(是否应被剔除,例如广告/招聘/纯转载)。
- 只输出 JSON,不要任何其他文字。不要代码块围栏,不要解释。

输入:
title: {title}
content: {content}

输出 JSON 格式:
{{"topic": "{topic}", "depth_score": 1|2|3, "relevant": 0|1, "excluded": 0|1, "reason": "<中文简要说明>"}}
"""

logger = logging.getLogger("rss_classify")


def _call_deepseek(prompt: str, api_key: str) -> dict:
    """Raw HTTP call to DeepSeek chat completions. Returns parsed JSON dict.

    Raises on HTTP failure or JSON parse failure — callers catch and skip.
    """
    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip optional ``` fences (DeepSeek sometimes wraps JSON in code blocks
    # even when told not to).
    if content.startswith("```"):
        start = content.find("\n") + 1
        end = content.rfind("```")
        if end > start:
            content = content[start:end].strip()
    return json.loads(content)


def _classify(api_key: str, title: str, content: str, topic: str) -> dict:
    prompt = CLASSIFY_PROMPT.format(
        topic=topic, title=title[:200], content=content[:4000]
    )
    data = _call_deepseek(prompt, api_key)
    depth = int(data["depth_score"])
    if not 1 <= depth <= 3:
        raise ValueError(f"depth_score out of range: {depth}")
    return {
        "topic": topic,
        "depth_score": depth,
        "relevant": int(bool(data.get("relevant", 0))),
        "excluded": int(bool(data.get("excluded", 0))),
        "reason": str(data.get("reason", ""))[:500],
    }


def _eligible_articles(
    conn: sqlite3.Connection,
    topics: tuple[str, ...],
    article_id: int | None,
    max_articles: int | None,
) -> list[tuple[int, str, str]]:
    if article_id is not None:
        rows = conn.execute(
            "SELECT id, title, COALESCE(summary, '') FROM rss_articles WHERE id=?",
            (article_id,),
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    placeholders = ",".join("?" for _ in topics)
    sql = (
        f"SELECT a.id, a.title, COALESCE(a.summary, '') "
        f"FROM rss_articles a "
        f"WHERE (SELECT COUNT(*) FROM rss_classifications c "
        f"       WHERE c.article_id = a.id AND c.topic IN ({placeholders})) < ? "
        f"ORDER BY a.fetched_at DESC "
        f"LIMIT ?"
    )
    rows = conn.execute(sql, (*topics, len(topics), max_articles or 1000)).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def run(
    topics: tuple[str, ...],
    article_id: int | None,
    max_articles: int | None,
    dry_run: bool,
    db_path: Path = DB,
) -> dict:
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
    for aid, title, content in rows:
        for topic in topics:
            if dry_run:
                logger.info("DRY: a=%s t=%s", aid, topic)
                stats["dry_run_planned"] += 1
                continue
            try:
                assert api_key is not None
                result = _classify(api_key, title, content, topic)
                logger.info(
                    "a=%s t=%s depth=%s exc=%s",
                    aid,
                    topic,
                    result["depth_score"],
                    result["excluded"],
                )
                try:
                    conn.execute(
                        """INSERT INTO rss_classifications
                           (article_id, topic, depth_score, relevant, excluded, reason)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            aid,
                            topic,
                            result["depth_score"],
                            result["relevant"],
                            result["excluded"],
                            result["reason"],
                        ),
                    )
                    conn.commit()
                    stats["classified"] += 1
                except sqlite3.IntegrityError:
                    # UNIQUE(article_id, topic) — re-classify is a no-op.
                    pass
            except Exception as ex:
                logger.warning("classify failed a=%s t=%s: %s", aid, topic, ex)
                stats["failed"] += 1
            time.sleep(THROTTLE_SECONDS)
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

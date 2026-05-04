"""RSS ingest: translate English body to Chinese (D-09), then ingest into LightRAG.
Updates rss_articles.enriched to 2 on success (post-ainsert verification).

Pipeline per article (D-07 REVISED 2026-05-02 + D-19 — NO enrichment):
  1. Fetch body + metadata (title, url, summary) from rss_articles joined with
     rss_classifications (depth_score >= 2 gate).
  2. langdetect on body:
       - 'en'                 -> DeepSeek translate to Chinese (one HTTP call)
       - 'zh-cn'/'zh-tw'/'zh' -> skip translation (body already Chinese)
       - anything else        -> log + skip (rss_fetch prefilter catches in
                                 practice; this is defence in depth)
  3. Atomic write original.md (English source) + final_content.md (Chinese)
     to ~/.hermes/omonigraph-vault/rss_content/<article_hash>/.
  4. lightrag.ainsert(final_content) with doc id f"rss-{article_id}".
  5. Task 4.2 verification hook (MANDATORY per D-19): aget_docs_by_ids([doc_id])
     must return status == 'PROCESSED' before the enriched=2 write. On any
     other outcome (absent / FAILED / exception) we return False and leave
     rss_articles.enriched at its prior value so the next batch retries.
  6. UPDATE rss_articles SET enriched = 2 only on a PROCESSED confirmation.

Explicitly NOT here: no enrich_article invocation, no child-process spawn,
no Zhihu 好问 layer (D-07 REVISED). The KOL-only enrichment bridge
(invoked by 05-04 step_6) guards against the `--source rss` branch
and no-ops for RSS; this module does not call it.

LLM routing (Phase 7 D-09 supersession 2026-05-02):
  Translation uses DeepSeek via raw HTTP. Gemini is Vision + Embedding only.

Usage:
    venv/bin/python enrichment/rss_ingest.py                   # ingest all eligible
    venv/bin/python enrichment/rss_ingest.py --dry-run         # preview
    venv/bin/python enrichment/rss_ingest.py --article-id 17   # single article
    venv/bin/python enrichment/rss_ingest.py --max-articles 5
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sqlite3
from pathlib import Path

import requests
from langdetect import DetectorFactory, LangDetectException, detect

from batch_classify_kol import get_deepseek_api_key
from config import BASE_DIR, RAG_WORKING_DIR

DetectorFactory.seed = 0  # deterministic language detection

DB = Path(os.environ.get("KOL_SCAN_DB_PATH", "data/kol_scan.db"))
RSS_CONTENT_DIR = BASE_DIR / "rss_content"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = os.environ.get("TRANSLATE_MODEL", "deepseek-chat")
CHINESE_LANGS = {"zh-cn", "zh-tw", "zh"}
TRANSLATE_TIMEOUT_SECONDS = 300
# Task 4.2 status gate — anything other than this leaves enriched unchanged.
PROCESSED_STATUS = "PROCESSED"

logger = logging.getLogger("rss_ingest")


_TRANSLATE_PROMPT = """请将下面的英文技术文章翻译为中文。保持技术术语的准确性;代码块、URL、Markdown 语法原样保留。不要添加解释性文字,只输出翻译后的中文 Markdown。

英文原文:
{body}
"""


def _atomic_write(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` via .tmp + os.replace (POSIX rename)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def _detect_lang(text: str) -> str:
    try:
        return detect(text[:2000])
    except LangDetectException:
        return "unknown"


def _translate_to_chinese(api_key: str, body: str) -> str:
    """Translate English body to Chinese via DeepSeek chat completions."""
    prompt = _TRANSLATE_PROMPT.format(body=body)
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
        timeout=TRANSLATE_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _eligible_articles(
    conn: sqlite3.Connection,
    article_id: int | None,
    max_articles: int | None,
) -> list[dict]:
    if article_id is not None:
        sql = (
            "SELECT ra.id, ra.title, ra.url, COALESCE(ra.summary,'') AS summary, "
            "       MAX(rc.depth_score) AS depth_score, ra.enriched "
            "FROM rss_articles ra "
            "LEFT JOIN rss_classifications rc ON rc.article_id = ra.id "
            "WHERE ra.id = ? "
            "GROUP BY ra.id"
        )
        rows = conn.execute(sql, (article_id,)).fetchall()
    else:
        sql = (
            "SELECT ra.id, ra.title, ra.url, COALESCE(ra.summary,'') AS summary, "
            "       MAX(rc.depth_score) AS depth_score, ra.enriched "
            "FROM rss_articles ra "
            "JOIN rss_classifications rc ON rc.article_id = ra.id "
            "WHERE rc.depth_score >= 2 AND COALESCE(ra.enriched, 0) = 0 "
            "GROUP BY ra.id "
            "ORDER BY ra.fetched_at DESC "
            "LIMIT ?"
        )
        rows = conn.execute(sql, (max_articles or 1000,)).fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "url": r[2],
            "summary": r[3],
            "depth_score": r[4],
            "enriched": r[5],
        }
        for r in rows
    ]


async def _ingest_lightrag(final_md: str, rss_article_id: int) -> bool:
    """Ingest final_content.md into LightRAG and verify via aget_docs_by_ids.

    Returns True ONLY if both:
      (a) ainsert completes without raising
      (b) aget_docs_by_ids confirms doc.status == 'PROCESSED'

    On any other outcome returns False. Caller leaves
    rss_articles.enriched untouched so the next batch retries. Pattern
    ported verbatim from ingest_wechat.py:1086-1120 (commit 585aa3b).
    """
    from lightrag import LightRAG  # noqa: WPS433 — lazy import keeps unit tests hermetic

    from lib import deepseek_model_complete
    from lib.lightrag_embedding import embedding_func

    doc_id = f"rss-{rss_article_id}"
    rag = LightRAG(
        working_dir=str(RAG_WORKING_DIR),
        llm_model_func=deepseek_model_complete,
        embedding_func=embedding_func,
        llm_model_name="deepseek-chat",
        embedding_func_max_async=1,
        embedding_batch_num=20,
        llm_model_max_async=2,
    )
    await rag.initialize_storages()

    try:
        await rag.ainsert(final_md, ids=[doc_id])
    except Exception as ex:
        logger.error(
            "LightRAG ainsert failed rss_id=%s: %s", rss_article_id, ex
        )
        return False

    try:
        statuses = await rag.aget_docs_by_ids([doc_id])
    except Exception as ex:
        logger.warning(
            "aget_docs_by_ids failed rss_id=%s: %s", rss_article_id, ex
        )
        return False

    entry = (statuses or {}).get(doc_id)
    status_val: str | None = None
    if entry is not None:
        status_val = getattr(entry, "status", None)
        if status_val is None and isinstance(entry, dict):
            status_val = entry.get("status")
    if str(status_val).upper() != PROCESSED_STATUS:
        logger.warning(
            "rss_id=%s post-ingest status=%r (expected %s) — "
            "leaving rss_articles.enriched unchanged; next batch will retry",
            rss_article_id,
            status_val,
            PROCESSED_STATUS,
        )
        return False
    return True


def run(
    article_id: int | None,
    max_articles: int | None,
    dry_run: bool,
    db_path: Path | None = None,
) -> dict:
    # Resolve DB path at call time so tests can monkeypatch module-level DB.
    conn = sqlite3.connect(db_path if db_path is not None else DB)
    rows = _eligible_articles(conn, article_id, max_articles)
    logger.info("Eligible: %d RSS articles", len(rows))

    api_key: str | None = None
    if not dry_run:
        api_key = get_deepseek_api_key()
        if not api_key:
            conn.close()
            raise RuntimeError(
                "DEEPSEEK_API_KEY not found in env / ~/.hermes/.env / config.yaml"
            )

    # Per D-07 REVISED + D-19: no enrich_article invocation; no enrich_ok /
    # enrich_fail stats. Only terminal state is enriched=2 (success).
    stats = {
        "translated": 0,
        "ingested": 0,
        "errors": 0,
        "dry_run_planned": 0,
        "skipped_lang": 0,
    }

    for row in rows:
        aid = row["id"]
        url = row["url"]
        body = row["summary"]
        article_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
        hash_dir = RSS_CONTENT_DIR / article_hash

        if dry_run:
            print(
                f"DRY: rss id={aid} hash={article_hash} -> {hash_dir}/final_content.md"
            )
            stats["dry_run_planned"] += 1
            continue

        try:
            _atomic_write(hash_dir / "original.md", body)

            lang = _detect_lang(body)
            if lang == "en":
                assert api_key is not None
                chinese_body = _translate_to_chinese(api_key, body)
                stats["translated"] += 1
            elif lang in CHINESE_LANGS:
                chinese_body = body
            else:
                logger.warning("skip rss id=%s: unsupported lang=%s", aid, lang)
                stats["skipped_lang"] += 1
                continue

            final_md = (
                f"# {row['title']}\n\n{chinese_body}\n\n<!-- source: {url} -->\n"
            )
            _atomic_write(hash_dir / "final_content.md", final_md)

            # Direct LightRAG path — NO enrich_article child-process (D-07
            # REVISED + D-19). _ingest_lightrag returns True only if ainsert
            # succeeded AND aget_docs_by_ids confirmed status == 'PROCESSED'.
            ingest_ok = asyncio.run(_ingest_lightrag(final_md, aid))
            if ingest_ok:
                stats["ingested"] += 1
                cur = conn.cursor()
                cur.execute(
                    "UPDATE rss_articles SET enriched = 2 WHERE id = ?",
                    (aid,),
                )
                conn.commit()
                if cur.rowcount != 1:
                    logger.warning(
                        "enriched update affected %d rows for rss id=%s",
                        cur.rowcount,
                        aid,
                    )
            else:
                # ainsert raised OR post-ingest status was not PROCESSED.
                # Leave rss_articles.enriched at its prior value (0 or -2) so
                # the next batch retries. Mirrors Task 4.2 anti-ghost semantics.
                logger.warning(
                    "rss id=%s: ingest_ok=False, enriched left unchanged for retry",
                    aid,
                )
                stats["errors"] += 1

        except Exception as ex:
            logger.exception("rss id=%s failed: %s", aid, ex)
            stats["errors"] += 1

    conn.close()
    return stats


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--article-id", type=int, default=None)
    p.add_argument("--max-articles", type=int, default=None)
    args = p.parse_args()
    stats = run(args.article_id, args.max_articles, args.dry_run)
    print(f"rss_ingest done: {json.dumps(stats)}")


if __name__ == "__main__":
    main()

"""RSS ingest: 5-stage multimodal pipeline for RSS articles.

Phase 20 RIN-01..06 (D-20.05..12, D-20.16):
  Pipeline per article — 5 ordered checkpoint stages:
    scrape -> classify -> image_download -> text_ingest -> vision_worker

  Doc IDs: f"rss-{article_id}" primary, f"rss-{article_id}_images" sub-doc (D-20.05).
  Checkpoint keys: lib.checkpoint short stage keys — scrape, classify,
    image_download, text_ingest, vision_worker (D-20.16).
  Per-module tracker: _pending_doc_ids (D-20.11) — distinct from
    ingest_wechat._PENDING_DOC_IDS.
  Timeout formula: max(120 + 30 * chunk_count, 900) (D-20.10).
  Rollback: adelete_by_doc_id for BOTH primary AND sub-doc on TimeoutError (D-20.06).
    enriched is left unchanged so next batch retries (D-20.12).
  PROCESSED gate (RIN-06): enriched=2 written ONLY after aget_docs_by_ids confirms
    status == 'PROCESSED'. Logic preserved verbatim from old impl lines 184-207.
  Translation removed entirely: out of v3.4 scope per REQUIREMENTS.md.
  Article hash: lib.checkpoint.get_article_hash(url) — SHA-256[:16] (NOT MD5).
  Image server: http://localhost:8765/{article_hash}/{filename}.

Usage:
    venv/bin/python enrichment/rss_ingest.py                   # ingest all eligible
    venv/bin/python enrichment/rss_ingest.py --dry-run         # preview
    venv/bin/python enrichment/rss_ingest.py --article-id 17   # single article
    venv/bin/python enrichment/rss_ingest.py --max-articles 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

import image_pipeline
from config import BASE_DIR, RAG_WORKING_DIR
from lib import deepseek_model_complete
from lib.checkpoint import (
    get_article_hash,
    get_checkpoint_dir,
    has_stage,
    read_stage,
    write_stage,
    write_vision_description,
)
from lib.lightrag_embedding import embedding_func
from lib.scraper import scrape_url

DB = Path(os.environ.get("KOL_SCAN_DB_PATH", "data/kol_scan.db"))
RSS_CONTENT_DIR = BASE_DIR / "rss_content"
BASE_IMAGE_DIR = BASE_DIR / "images"
# Task 4.2 status gate — anything other than this leaves enriched unchanged.
PROCESSED_STATUS = "PROCESSED"
VISION_DRAIN_CAP_SECONDS = 120.0  # D-20.12 cap
MIN_DEPTH_GATE = 2  # D-19 ingest depth gate

_IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")

logger = logging.getLogger("rss_ingest")

# D-20.11 — per-module tracker, distinct from ingest_wechat._PENDING_DOC_IDS
_pending_doc_ids: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atomic_write(target: Path, content: str) -> None:
    """Atomic write via .tmp + os.replace — preserved from old impl."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def _extract_image_urls(markdown: str) -> list[str]:
    """Extract image URLs from markdown: ![alt](URL) matches, deduped, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for url in _IMAGE_MD_RE.findall(markdown or ""):
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


async def _drain_rss_vision_tasks(cap_seconds: float = VISION_DRAIN_CAP_SECONDS) -> None:
    """D-20.12 / Pattern 5 — local drain helper, NOT imported from batch_ingest_from_spider.

    Drains all currently-running tasks (excluding the caller) up to cap_seconds.
    On cap timeout, cancel still-pending tasks and gather their cancellations.
    """
    pending = [
        t for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and not t.done()
    ]
    if not pending:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=cap_seconds,
        )
    except asyncio.TimeoutError:
        for t in pending:
            if not t.done():
                t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


def _compute_article_budget_s(content: str) -> float:
    """D-20.10 — identical to KOL Phase 9 formula. Inline (NOT imported from
    batch_ingest_from_spider) to avoid module-level side effects per Research Q1.
    """
    chunk_count = max(1, len(content) // 1000)
    return float(max(120 + 30 * chunk_count, 900))


# ---------------------------------------------------------------------------
# Vision worker
# ---------------------------------------------------------------------------


async def _rss_vision_worker(
    *,
    rag,
    article_id: int,
    article_hash: str,
    url_to_path: dict,
    title: str,
) -> None:
    """Async sub-doc inserter — never raises (D-10.08 contract preserved).

    Output sub-doc lines mirror ingest_wechat._vision_worker_impl format.
    Sub-doc id: f"rss-{article_id}_images" per D-20.05.
    """
    sub_doc_id = f"rss-{article_id}_images"
    try:
        paths_list = list(url_to_path.values())
        descriptions = image_pipeline.describe_images(paths_list) if paths_list else {}

        lines = [f"# Images for {title}", ""]
        successful = 0
        for i, (url_img, path) in enumerate(url_to_path.items()):
            desc = descriptions.get(path, "") or ""
            stripped = desc.strip()
            if stripped and not stripped.startswith("Error describing image:"):
                local_url = f"http://localhost:8765/{article_hash}/{path.name}"
                lines.append(f"- [image {i}]: {desc}  ({local_url})")
                successful += 1
                try:
                    write_vision_description(article_hash, Path(path).stem, {
                        "provider": "cascade",
                        "description": desc,
                        "latency_ms": None,
                        "timestamp": time.time(),
                    })
                except Exception as e:
                    logger.warning("vision checkpoint write failed for image %d: %s", i, e)

        if successful == 0:
            logger.info("rss vision sub-doc skipped (no successful descriptions) id=%s", article_id)
            return

        sub_doc_content = "\n".join(lines) + "\n"
        await rag.ainsert(sub_doc_content, ids=[sub_doc_id])
        # Track sub-doc for rollback completeness (D-20.06)
        _pending_doc_ids[f"{article_hash}_images"] = sub_doc_id
        logger.info("rss vision sub-doc inserted id=%s images=%d", sub_doc_id, successful)
    except Exception as exc:
        logger.warning("rss vision worker failed id=%s: %s", article_id, exc)
    finally:
        # Best-effort cleanup of sub-doc tracker on success (rollback path also pops)
        _pending_doc_ids.pop(f"{article_hash}_images", None)


# ---------------------------------------------------------------------------
# Single-article 5-stage ingest
# ---------------------------------------------------------------------------


async def _ingest_one_article(rag, conn: sqlite3.Connection, row: dict) -> bool:
    """5-stage pipeline for one RSS article. Returns True on PROCESSED-confirmed success."""
    aid = row["id"]
    url = row["url"]
    title = row["title"] or url
    article_hash = get_article_hash(url)  # D-20.16 + Pitfall 3
    doc_id = f"rss-{aid}"

    # ----- Stage 01: scrape (Lesson 2026-05-05 #2: persist body atomically) -----
    body: str | None = row.get("body") or None
    if not has_stage(article_hash, "scrape"):
        if not body:
            try:
                result = await scrape_url(url, site_hint="generic")
                body = result.markdown or ""
            except Exception as ex:
                logger.warning("scrape failed id=%s: %s", aid, ex)
                return False
        # Persist body to DB BEFORE any downstream gate, even if classify/ingest later fails
        if body:
            try:
                conn.execute(
                    "UPDATE rss_articles SET body = COALESCE(body, ?) WHERE id = ?",
                    (body, aid),
                )
                conn.commit()
            except sqlite3.Error as ex:
                logger.warning("body persist failed id=%s: %s", aid, ex)
        write_stage(article_hash, "scrape", body or "")

    if not body:
        body = row.get("body") or ""
        if not body:
            logger.warning("id=%s: no body after scrape; skipping", aid)
            return False

    # ----- Stage 02: classify gate (depth set by rss_classify; we just gate) -----
    if not has_stage(article_hash, "classify"):
        depth = row.get("depth")
        if depth is None:
            logger.info("id=%s: depth NULL — rss_classify must run first; skipping", aid)
            return False
        if int(depth) < MIN_DEPTH_GATE:
            logger.info("id=%s: depth=%s < %s gate; skipping", aid, depth, MIN_DEPTH_GATE)
            return False
        write_stage(article_hash, "classify", {"depth": int(depth), "topics": row.get("topics", "[]")})

    # ----- Stage 03: image download -----
    url_to_path: dict[str, Path] = {}
    if not has_stage(article_hash, "image_download"):
        image_urls = _extract_image_urls(body)
        parsed = urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
        dest_dir = BASE_IMAGE_DIR / article_hash
        url_to_path = image_pipeline.download_images(image_urls, dest_dir, referer=referer)
        manifest = {u: str(p) for u, p in url_to_path.items()}
        write_stage(article_hash, "image_download", manifest)
    else:
        # Resume: rebuild url_to_path from manifest
        manifest = read_stage(article_hash, "image_download") or {}
        url_to_path = {u: Path(p) for u, p in manifest.items()}

    # ----- Stage 04: text ingest -----
    if not has_stage(article_hash, "text_ingest"):
        localized = image_pipeline.localize_markdown(
            body, url_to_path, base_url="http://localhost:8765", article_hash=article_hash
        )
        budget_s = _compute_article_budget_s(localized)
        _pending_doc_ids[article_hash] = doc_id  # D-20.11 register BEFORE await
        try:
            await asyncio.wait_for(rag.ainsert(localized, ids=[doc_id]), timeout=budget_s)
        except asyncio.TimeoutError:
            logger.warning("id=%s: ainsert TimeoutError after %ss; rolling back", aid, budget_s)
            await _drain_rss_vision_tasks(cap_seconds=VISION_DRAIN_CAP_SECONDS)
            for delete_id in (doc_id, f"{doc_id}_images"):  # D-20.06
                try:
                    await rag.adelete_by_doc_id(delete_id)
                except Exception as del_exc:
                    logger.warning("adelete_by_doc_id(%s) failed: %s", delete_id, del_exc)
            _pending_doc_ids.pop(article_hash, None)
            _pending_doc_ids.pop(f"{article_hash}_images", None)
            # D-20.12 — leave enriched unchanged so next batch retries
            return False
        except Exception as ex:
            logger.error("id=%s: ainsert raised: %s", aid, ex)
            _pending_doc_ids.pop(article_hash, None)
            return False
        write_stage(article_hash, "text_ingest")
        _pending_doc_ids.pop(article_hash, None)

    # ----- Stage 05: vision worker (fire-and-forget) -----
    if not has_stage(article_hash, "vision_worker"):
        # Create 05_vision/ directory now so the checkpoint exists even if
        # the fire-and-forget task has not yet written any .json files.
        vision_dir = get_checkpoint_dir(article_hash) / "05_vision"
        vision_dir.mkdir(parents=True, exist_ok=True)
        if url_to_path:
            asyncio.create_task(
                _rss_vision_worker(
                    rag=rag,
                    article_id=aid,
                    article_hash=article_hash,
                    url_to_path=url_to_path,
                    title=title,
                )
            )
            # Yield to event loop so the vision task can start before PROCESSED gate.
            await asyncio.sleep(0)

    # ----- PROCESSED gate (RIN-06 preserved from old impl lines 184-207) -----
    try:
        statuses = await rag.aget_docs_by_ids([doc_id])
    except Exception as ex:
        logger.warning("id=%s: aget_docs_by_ids failed: %s", aid, ex)
        return False

    entry = (statuses or {}).get(doc_id)
    status_val: str | None = None
    if entry is not None:
        status_val = getattr(entry, "status", None)
        if status_val is None and isinstance(entry, dict):
            status_val = entry.get("status")
    if str(status_val).upper() != PROCESSED_STATUS:
        logger.warning(
            "id=%s post-ingest status=%r (expected %s); enriched left unchanged",
            aid, status_val, PROCESSED_STATUS,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Eligible articles query
# ---------------------------------------------------------------------------


def _eligible_articles(
    conn: sqlite3.Connection,
    article_id: int | None,
    max_articles: int | None,
) -> list:
    """Returns rows with id, title, url, body, depth, topics, enriched.

    Preserves PROCESSED idempotency gate from old impl: skip if already enriched=2.
    Half-fix audit (CLAUDE.md Lesson 2026-05-05 #1):
      Plan 20-01 writes: body, body_scraped_at, depth, topics, classify_rationale
      This SELECT reads: body, depth, topics, enriched — column names match.
    """
    if article_id is not None:
        sql = (
            "SELECT id, title, url, body, depth, topics, enriched "
            "FROM rss_articles WHERE id = ? AND COALESCE(enriched, 0) <> 2"
        )
        return conn.execute(sql, (article_id,)).fetchall()
    sql = (
        "SELECT id, title, url, body, depth, topics, enriched "
        "FROM rss_articles "
        "WHERE depth IS NOT NULL AND depth >= ? AND COALESCE(enriched, 0) = 0 "
        "ORDER BY fetched_at DESC LIMIT ?"
    )
    return conn.execute(sql, (MIN_DEPTH_GATE, max_articles or 1000)).fetchall()


# ---------------------------------------------------------------------------
# Async run loop
# ---------------------------------------------------------------------------


async def _run_async(
    article_id: int | None,
    max_articles: int | None,
    dry_run: bool,
    db_path: Path,
) -> dict:
    from lightrag import LightRAG  # noqa: WPS433 — lazy import keeps unit tests hermetic

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

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = _eligible_articles(conn, article_id, max_articles)
    logger.info("Eligible: %d RSS articles", len(rows))

    stats = {"ingested": 0, "errors": 0, "dry_run_planned": 0, "skipped": 0}
    for row_obj in rows:
        row = dict(row_obj)
        if dry_run:
            print(f"DRY: rss id={row['id']} url={row['url']}")
            stats["dry_run_planned"] += 1
            continue
        try:
            ok = await _ingest_one_article(rag, conn, row)
            if ok:
                conn.execute("UPDATE rss_articles SET enriched = 2 WHERE id = ?", (row["id"],))
                conn.commit()
                stats["ingested"] += 1
            else:
                stats["skipped"] += 1
        except Exception as ex:
            logger.exception("rss id=%s failed: %s", row["id"], ex)
            stats["errors"] += 1

    conn.close()
    return stats


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    article_id: int | None,
    max_articles: int | None,
    dry_run: bool,
    db_path: Path | None = None,
) -> dict:
    """Entry point — orchestrate_daily.step_7 calls this. Signature preserved."""
    actual_db = db_path if db_path is not None else DB
    return asyncio.run(_run_async(article_id, max_articles, dry_run, actual_db))


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

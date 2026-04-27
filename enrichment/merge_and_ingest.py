"""Merge enrichment artifacts and ingest into LightRAG + SQLite.

Called by the Hermes ``enrich_article`` skill as the final step of per-article
enrichment. Reads disk artifacts produced by:
  - enrichment/extract_questions.py  -> questions.json
  - /zhihu-haowen-enrich skill        -> <q>/haowen.json  (per question)
  - enrichment/fetch_zhihu.py         -> <q>/final_content.md  (per question)

Writes:
  - LightRAG: 1 enriched WeChat doc + 0-3 Zhihu docs (D-08 metadata)
  - SQLite:   articles.enriched = 2 | -2, ingestions.enrichment_id = <id>

D-07 enriched state machine:
  0  = pending (initial)
  1  = in progress (optional; not set here)
  2  = partial or full success (>= 1 question succeeded)
  -1 = skipped (too-short; set by extract_questions, not here)
  -2 = all questions failed

CLI:
    python -m enrichment.merge_and_ingest <wechat_hash> \\
        --article-path <path to wechat MD> \\
        --article-url <url>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from enrichment.merge_md import merge_wechat_with_haowen

# Hermes env has GOOGLE_GENAI_USE_VERTEXAI=true globally which forces
# genai.Client to Vertex AI (rejects API keys). Unset at import time so
# any downstream genai.Client (via LightRAG's gemini wrappers) routes to
# the Gemini API. Defensive redundancy vs config.py's pop. See test report 04-06.
os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)

logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path(os.environ.get(
    "ENRICHMENT_DIR",
    str(Path.home() / ".hermes" / "omonigraph-vault" / "enrichment"),
))
DEFAULT_DB_PATH = Path(os.environ.get(
    "KOL_SCAN_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "kol_scan.db"),
))


# ─────────────────────────── Artifact readers ────────────────────────────


def _load_haowen_list(hash_dir: Path, question_count: int) -> list[Optional[dict]]:
    """Return list of haowen dicts (or None for missing) for q_idx 0..question_count-1."""
    result: list[Optional[dict]] = []
    for i in range(question_count):
        haowen_path = hash_dir / str(i) / "haowen.json"
        if haowen_path.is_file():
            try:
                result.append(json.loads(haowen_path.read_text(encoding="utf-8")))
            except Exception as e:
                logger.warning("haowen.json for q%d unreadable: %s", i, e)
                result.append(None)
        else:
            result.append(None)
    return result


def _load_zhihu_mds(hash_dir: Path, question_count: int) -> dict[int, str]:
    """Return {q_idx: markdown} for questions that have a final_content.md."""
    result: dict[int, str] = {}
    for i in range(question_count):
        md_path = hash_dir / str(i) / "final_content.md"
        if md_path.is_file():
            result[i] = md_path.read_text(encoding="utf-8")
    return result


# ──────────────────────────── SQLite ─────────────────────────────────────


def _update_sqlite_status(
    db_path: Path,
    article_url: str,
    enriched: int,
    enrichment_id: Optional[str],
) -> None:
    """Write enriched state + enrichment_id. Failure-tolerant (logs + continues).

    Pattern follows _persist_entities_to_sqlite from ingest_wechat.py (D-11).
    """
    if not db_path.exists():
        logger.warning("SQLite DB not found at %s — skipping status update", db_path)
        return
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE articles SET enriched = ? WHERE url = ?",
            (enriched, article_url),
        )
        if enrichment_id:
            row = conn.execute(
                "SELECT id FROM articles WHERE url = ?", (article_url,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE ingestions SET enrichment_id = ? WHERE article_id = ?",
                    (enrichment_id, row[0]),
                )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("SQLite status update failed: %s", e)


# ────────────────────────── LightRAG ingest ──────────────────────────────


async def _ingest_to_lightrag(
    wechat_md: str,
    zhihu_docs: dict[int, str],
    wechat_hash: str,
) -> None:
    """Call rag.ainsert for the enriched WeChat MD + each Zhihu doc with D-08 metadata."""
    # Late import so tests can monkeypatch ingest_wechat.get_rag without importing lightrag
    from ingest_wechat import get_rag
    rag = await get_rag()

    # Parent WeChat doc — let LightRAG auto-assign the document ID
    await rag.ainsert(wechat_md)

    # Zhihu child docs — deterministic IDs + enriches-backlink (D-08)
    for q_idx, md in zhihu_docs.items():
        await rag.ainsert(
            md,
            ids=[f"zhihu_{wechat_hash}_{q_idx}"],
            file_paths=[f"enriches:{wechat_hash}"],
        )


# ──────────────────────────── Main entry ─────────────────────────────────


async def merge_and_ingest(
    wechat_hash: str,
    article_path: Path,
    article_url: str,
    base_dir: Path = DEFAULT_BASE_DIR,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict:
    """Merge enrichment artifacts and ingest everything into LightRAG + SQLite.

    Returns a summary dict (D-03 contract) suitable for JSON-serialisation on stdout.
    """
    hash_dir = base_dir / wechat_hash
    questions_path = hash_dir / "questions.json"
    if not questions_path.is_file():
        raise FileNotFoundError(f"questions.json missing at {questions_path}")

    questions_data = json.loads(questions_path.read_text(encoding="utf-8"))
    questions = questions_data.get("questions", [])
    question_count = len(questions)

    haowen_list = _load_haowen_list(hash_dir, question_count)
    zhihu_mds = _load_zhihu_mds(hash_dir, question_count)

    success_count = sum(1 for h in haowen_list if h is not None)

    # Merge WeChat MD with 好问 summaries inline (D-09)
    wechat_text = article_path.read_text(encoding="utf-8")
    enriched_md = merge_wechat_with_haowen(wechat_text, haowen_list)

    # Ingest enriched WeChat MD + Zhihu docs into LightRAG
    await _ingest_to_lightrag(enriched_md, zhihu_mds, wechat_hash)

    # D-07 / D-11: partial success (>= 1 q ok) → 2; all-fail → -2
    enriched_state = 2 if success_count >= 1 else -2
    enrichment_id = f"enrich_{wechat_hash}"
    _update_sqlite_status(db_path, article_url, enriched_state, enrichment_id)

    return {
        "hash": wechat_hash,
        "status": "ok",
        "enriched": enriched_state,
        "question_count": question_count,
        "success_count": success_count,
        "zhihu_docs_ingested": len(zhihu_mds),
        "enrichment_id": enrichment_id,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Emits single-line JSON on stdout (D-03 contract)."""
    parser = argparse.ArgumentParser(
        description="Merge enrichment artifacts and ingest into LightRAG + SQLite."
    )
    parser.add_argument("wechat_hash", help="MD5 hash prefix of the WeChat article")
    parser.add_argument("--article-path", required=True, help="Path to the WeChat article markdown")
    parser.add_argument("--article-url", required=True, help="WeChat article URL (SQLite key)")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR),
                        help="Base enrichment directory (default: $ENRICHMENT_DIR)")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH),
                        help="Path to kol_scan.db")
    args = parser.parse_args(argv)

    try:
        summary = asyncio.run(merge_and_ingest(
            args.wechat_hash,
            Path(args.article_path),
            args.article_url,
            base_dir=Path(args.base_dir),
            db_path=Path(args.db_path),
        ))
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"hash": args.wechat_hash, "status": "error", "error": str(e)}))
        return 1

    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())

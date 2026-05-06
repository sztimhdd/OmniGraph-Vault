import os
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from config import RAG_WORKING_DIR, load_env, CANONICAL_MAP_FILE
load_env()
DB_PATH = Path(os.environ.get("KOL_SCAN_DB_PATH", str(Path(__file__).parent / "data" / "kol_scan.db")))

import asyncio
import time

from lightrag.lightrag import LightRAG, QueryParam
from lib.llm_deepseek import deepseek_model_complete
from lib.lightrag_embedding import embedding_func

# Phase 5 Wave 0 fix (2026-05-03): SYNTHESIS_LLM was gemini-2.5-flash-lite but
# the routing rule is "ALL LLM → DeepSeek, Gemini ONLY for Vision+Embedding".
# Also: Cognee import was triggering async pipelines at module level (Vertex AI
# 404 cascade), blocking the event loop. Cognee is now lazy-imported only when
# recall/remember succeeds — which it never does on free-tier Vertex AI anyway.

# HYG-04 (Phase 18-03): single source of truth for the image-URL-preservation
# directive. Captured from Wave 0 commit 0109c02. Any future synthesis-layer
# prompt (omnigraph_synthesize, scripts/bench_ingest_fixture, or any skill)
# that pipes a query to an LLM over image-containing LightRAG context MUST
# include this directive, or inline image URLs are dropped by the model
# (observed 2026-05-02 in P2 of Wave 0 gate).
IMAGE_URL_DIRECTIVE = (
    "CRITICAL: when the context below contains image URLs like "
    "http://localhost:8765/..., you MUST include them as "
    "![description](url) INLINE in your answer near the relevant text. "
    "Do NOT skip images. Do NOT drop URLs."
)

# HYG-03 (Phase 18-02): replacement for removed Cognee recall/remember flow.
# Past-query memory is persisted as append-only JSONL. Never blocks synthesis —
# read failures return empty list; write failures log a warning only.
# Note: the parent dir name `omonigraph-vault` is the canonical typo (CLAUDE.md).
QUERY_HISTORY_FILE = Path.home() / ".hermes" / "omonigraph-vault" / "query_history.jsonl"


def _archive_filename(query_text: str, ts: datetime | None = None) -> str:
    """Build a unique archive filename for a synthesis answer.

    Format: ``YYYY-MM-DD_HHMMSS_<slug>.md``. The slug keeps alphanumerics,
    underscore, hyphen, and CJK characters; everything else collapses to a
    single hyphen. Truncated to 40 chars to keep filenames manageable.
    Empty queries fall back to ``"untitled"`` so the filename always parses.
    """
    import re
    ts = ts or datetime.now()
    stamp = ts.strftime("%Y-%m-%d_%H%M%S")
    slug = re.sub(r"[^\w一-鿿-]+", "-", (query_text or "").strip())
    slug = re.sub(r"-+", "-", slug).strip("-")[:40] or "untitled"
    return f"{stamp}_{slug}.md"


def _read_recent_query_history(limit: int = 10) -> list[str]:
    """Return the most-recent N queries, newest first. Empty list on any failure."""
    try:
        if not QUERY_HISTORY_FILE.exists():
            return []
        with QUERY_HISTORY_FILE.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        out: list[str] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            q = entry.get("query") if isinstance(entry, dict) else None
            if isinstance(q, str) and q:
                out.append(q)
                if len(out) >= limit:
                    break
        return out
    except Exception:
        return []


def _append_query_history(query: str, mode: str, response_len: int) -> None:
    """Atomic-per-line append to the query-history JSONL. Silent on failure."""
    try:
        QUERY_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "query": query,
            "mode": mode,
            "response_len": response_len,
        }
        with QUERY_HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Warning: query history append failed: {e}")


async def synthesize_response(query_text: str, mode: str = "hybrid"):
    rag = LightRAG(working_dir=RAG_WORKING_DIR, llm_model_func=deepseek_model_complete, embedding_func=embedding_func)
    if hasattr(rag, "initialize_storages"): await rag.initialize_storages()
        
    await asyncio.sleep(2)
    # Apply canonical mapping if exists (DB-first, JSON fallback)
    canonical_map = {}
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute("SELECT raw_name, canonical_name FROM entity_canonical").fetchall()
            conn.close()
            canonical_map = dict(rows)
        except Exception as e:
            print(f"Warning: Failed to load canonical map from DB: {e}")
    if not canonical_map:
        map_file = str(CANONICAL_MAP_FILE)
        if os.path.exists(map_file):
            try:
                with open(map_file, "r") as f:
                    canonical_map = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load canonical map: {e}")
    for raw, canonical in canonical_map.items():
        if raw in query_text:
            query_text = query_text.replace(raw, canonical)

    # HYG-03: inject past-query history for context-aware synthesis.
    history = _read_recent_query_history(limit=10)
    history_block = ""
    if history:
        history_block = (
            "Previous queries for context (most recent first):\n"
            + "\n".join(f"- {q}" for q in history)
            + "\n\n"
        )

    # Instruction placed FIRST (before query) so LightRAG's internal template
    # does not overshadow it. IMAGE_URL_DIRECTIVE is the module-level constant
    # (HYG-04) — do NOT duplicate the directive text in-line.
    custom_prompt = (
        "You are a knowledge synthesizer. "
        + IMAGE_URL_DIRECTIVE
        + "\n\n"
        + history_block
        + f"Query: {query_text}"
    )

    param = QueryParam(mode=mode)

    response = None
    for i in range(3):
        try:
            response = await rag.aquery(custom_prompt, param=param)
            break
        except Exception as e:
            print(f"Query attempt {i+1} failed: {e}")
            if i < 2: await asyncio.sleep(5)
            else: raise e

    # HYG-03: record this query in history after successful synthesis.
    # Never raises — _append_query_history handles its own errors.
    if response:
        _append_query_history(query_text, mode, len(response) if isinstance(response, str) else 0)

    return response


async def main():
    if len(sys.argv) < 2:
        print("Usage: python kg_synthesize.py \"<your query>\" [mode]")
        sys.exit(1)
    query, mode = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "hybrid"
    from config import SYNTHESIS_OUTPUT
    try:
        response = await synthesize_response(query, mode=mode)
        if response:
            # Dual-write: unique archive file (never overwritten) +
            # synthesis_output.md (back-compat: Telegram skill / other consumers
            # that hardcode the canonical filename).
            archive_dir = SYNTHESIS_OUTPUT.parent / "synthesis_archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_file = archive_dir / _archive_filename(query)
            with open(archive_file, "w", encoding="utf-8") as f: f.write(response)
            with open(SYNTHESIS_OUTPUT, "w", encoding="utf-8") as f: f.write(response)
            print(f"Response saved ({len(response)} chars):")
            print(f"  archive: {archive_file}")
            print(f"  latest:  {SYNTHESIS_OUTPUT}")
        else:
            print("ERROR: empty response from LightRAG")
    except Exception as e:
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

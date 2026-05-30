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
import logging
import time

from lightrag.lightrag import LightRAG, QueryParam
from lib.llm_complete import get_llm_func  # quick-260509-s29 W3: dispatcher

_log = logging.getLogger(__name__)


def _get_embedding_func():
    """Return the LightRAG embedding function (Vertex Gemini, 3072-dim).

    arx-2 (2026-05-25): collapsed dispatcher — Aliyun storage is canonical
    3072-dim Vertex; Databricks UC volume mirrors it. LLM provider routing
    (databricks_serving / deepseek / vertex_gemini) stays separate via
    lib.llm_complete.get_llm_func; embedding is unconditionally Vertex.
    """
    from lib.lightrag_embedding import embedding_func
    return embedding_func

# Phase 5 Wave 0 fix (2026-05-03): SYNTHESIS_LLM was gemini-2.5-flash-lite but
# the routing rule is "ALL LLM → DeepSeek, Gemini ONLY for Vision+Embedding".
# Cognee was removed from kg_synthesize on 2026-05-03 (commit 0109c02) and
# fully retired from the repo on 2026-05-10 (quick 260510-gfg, Path A).

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

# HYG-03 (Phase 18-02): JSONL past-query memory (replaces the legacy memory
# layer that was retired in quick 260510-gfg). Append-only file; never blocks
# synthesis — read failures return empty list; write failures log a warning only.
# Note: the parent dir name `omonigraph-vault` is the canonical typo (CLAUDE.md).
QUERY_HISTORY_FILE = Path.home() / ".hermes" / "omonigraph-vault" / "query_history.jsonl"


# 260524-tk5: inner per-attempt timeout for rag.aquery(). The outer wrapper at
# kb/services/synthesize.py uses KB_SYNTHESIZE_TIMEOUT=60 (default) — but
# long_form requests bump this to 240. Without an inner bound, a hung
# Databricks SDK HTTP call inside the retry loop blocks the entire 240s
# wrapper budget on attempt 1 alone. 150s < 240s lets attempt 1 raise
# TimeoutError into the existing 3-attempt retry, giving attempt 2/3 a chance
# to succeed once the worker queue clears.
KB_LIGHTRAG_INNER_TIMEOUT: int = int(os.environ.get("KB_LIGHTRAG_INNER_TIMEOUT", "150"))


def _embedding_timeout_default() -> int:
    """Return embedding timeout in seconds (env override or 90s default).

    Cross-border Aliyun→GCP-Singapore embedding via WireGuard takes 15-25s
    per Vertex call; LightRAG hybrid query batches 3 sequential Vertex calls
    inside one worker (lib/lightrag_embedding.py:207 ``for text in texts``).
    90s Func → 180s Worker (LightRAG utils.py:680-685 auto-derives
    Worker = Func × 2) accommodates 3 × 25s + jitter. Default 30/60/75 was
    sized for same-region deploys and is too tight cross-border.
    """
    raw = os.environ.get("LIGHTRAG_EMBEDDING_TIMEOUT", "90")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 90


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


async def synthesize_response(
    query_text: str,
    mode: str = "mix",  # v1.1.P2-3: paired with BGE reranker per upstream LightRAG guidance
    rag: LightRAG | None = None,
    lightrag_lock: asyncio.Lock | None = None,
) -> str:
    if rag is None:
        # CLI fallback path: build a one-shot LightRAG. Production callers
        # (kb-api routers) pass the lifespan-pinned app.state.lightrag.
        rag = LightRAG(
            working_dir=RAG_WORKING_DIR,
            llm_model_func=get_llm_func(),
            embedding_func=_get_embedding_func(),
            default_embedding_timeout=_embedding_timeout_default(),
        )
        if hasattr(rag, "initialize_storages"):
            await rag.initialize_storages()
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
            _log.info(
                "kg_before_aquery: attempt=%d mode=%s prompt_chars=%d",
                i + 1, mode, len(custom_prompt),
            )
            t_attempt = time.monotonic()
            # 260524-tk5: bound inner aquery so a hung SDK call surfaces as
            # asyncio.TimeoutError (caught below by `except Exception`) instead
            # of stalling the entire outer KB_SYNTHESIZE_TIMEOUT budget.
            # v1.1.P5: lock acquired strictly INSIDE wait_for so a hung holder
            # is cancelable; CLI path (lock=None) skips acquisition entirely.
            if lightrag_lock is not None:
                async with lightrag_lock:
                    response = await asyncio.wait_for(
                        rag.aquery(custom_prompt, param=param),
                        timeout=KB_LIGHTRAG_INNER_TIMEOUT,
                    )
            else:
                response = await asyncio.wait_for(
                    rag.aquery(custom_prompt, param=param),
                    timeout=KB_LIGHTRAG_INNER_TIMEOUT,
                )
            _log.info(
                "kg_after_aquery: attempt=%d wall_s=%.2f response_chars=%d",
                i + 1, time.monotonic() - t_attempt,
                len(response) if isinstance(response, str) else 0,
            )
            break
        except Exception as e:
            _log.warning("Query attempt %d failed: %s", i + 1, e)
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
    # Note: CLI default stays "hybrid" (v1.1.P2-3 scope A+) — pass `mix` explicitly to use reranker path
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

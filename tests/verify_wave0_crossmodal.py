"""Wave 0 cross-modal verifier: text query -> image chunk retrieval.

Loads ``tests/fixtures/wave0_golden_queries.json`` and runs queries with
``type == "cross_modal"`` against LightRAG in hybrid mode. Passes if >= 1 of
the cross-modal queries returns at least one chunk whose content contains an
image URL matching ``http://localhost:8765/\\S+\\.(jpg|jpeg|png)`` in the top-K.

Order of operations:
    1. WAVE0_MODE=baseline python tests/verify_wave0_benchmark.py   # captures baseline
    2. python scripts/wave0_reembed.py --i-understand               # re-embed 22 docs
    3. python tests/verify_wave0_benchmark.py                        # post-check
    4. python tests/verify_wave0_crossmodal.py                       # this script

Exit codes:
    0 - >= 1 of 2 cross-modal queries retrieved an image-URL chunk
    1 - 0 cross-modal queries retrieved an image-URL chunk
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import RAG_WORKING_DIR, load_env  # noqa: E402

load_env()

from lightrag.lightrag import LightRAG, QueryParam  # noqa: E402
from lightrag.llm.gemini import gemini_model_complete  # noqa: E402

from lightrag_embedding import embedding_func  # noqa: E402


GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "wave0_golden_queries.json"
IMAGE_URL_RE = re.compile(r"http://localhost:8765/\S+?\.(?:jpg|jpeg|png)", re.IGNORECASE)
TOP_K = 5
MIN_HIT_QUERIES = 1  # >= 1 of the 2 cross-modal queries must hit an image URL


async def _llm_stub(prompt, system_prompt=None, history_messages=None, **kwargs):
    return await gemini_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages or [],
        api_key=os.environ.get("GEMINI_API_KEY"),
        model_name="gemini-2.5-flash-lite",
        **kwargs,
    )


async def _build_rag() -> LightRAG:
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=_llm_stub,
        embedding_func=embedding_func,
        llm_model_name="gemini-2.5-flash-lite",
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return rag


async def _retrieve_top_chunks(rag: LightRAG, query_text: str) -> list[dict[str, Any]]:
    param = QueryParam(mode="hybrid", only_need_context=True, top_k=TOP_K)
    data = await rag.aquery_data(query_text, param=param)
    if not isinstance(data, dict) or data.get("status") != "success":
        return []
    return data.get("data", {}).get("chunks", [])[:TOP_K] or []


async def main() -> int:
    queries = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["queries"]
    cross_modal = [q for q in queries if q["type"] == "cross_modal"]
    if not cross_modal:
        print("ERROR: no cross-modal queries found in golden fixture.", file=sys.stderr)
        return 1

    rag = await _build_rag()

    hits = 0
    print(f"query_id | image-URL hits in top-{TOP_K}")
    print(f"---------|------------------------------")
    for q in cross_modal:
        chunks = await _retrieve_top_chunks(rag, q["text"])
        with_image = [c for c in chunks if IMAGE_URL_RE.search(c.get("content", "") or "")]
        if with_image:
            hits += 1
        print(f"{q['id']} | {len(with_image)}/{len(chunks)}")
        for c in with_image[:2]:
            match = IMAGE_URL_RE.search(c.get("content", "") or "")
            if match:
                print(f"    - {c.get('chunk_id', '?')}: {match.group(0)}")

    print(f"\nCross-modal queries hitting >=1 image chunk: {hits}/{len(cross_modal)}")
    return 0 if hits >= MIN_HIT_QUERIES else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

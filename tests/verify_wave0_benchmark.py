"""Wave 0 benchmark: top-5 overlap verifier for Chinese + English golden queries.

Two modes (controlled by env var WAVE0_MODE):
    baseline  - run queries, capture top-5 chunk IDs to tests/fixtures/wave0_baseline.json
    compare   - (default) run queries, compare top-5 against baseline, assert >= 60%

Cross-modal queries are skipped here (handled by verify_wave0_crossmodal.py).

Order of operations:
    1. WAVE0_MODE=baseline python tests/verify_wave0_benchmark.py   # captures baseline
    2. python scripts/wave0_reembed.py --i-understand               # re-embed 22 docs
    3. python tests/verify_wave0_benchmark.py                        # post-check (compare)
    4. python tests/verify_wave0_crossmodal.py                       # cross-modal check

Exit codes:
    0 - baseline mode OK, OR compare-mode: every non-cross-modal query hit >= 60% overlap
    1 - compare-mode: at least one query < 60% overlap, OR fatal error
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Repo root on sys.path so ``from config import ...`` works.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import RAG_WORKING_DIR, load_env  # noqa: E402

load_env()

from lightrag.lightrag import LightRAG, QueryParam  # noqa: E402
from lightrag.llm.gemini import gemini_model_complete  # noqa: E402

from lightrag_embedding import embedding_func  # noqa: E402


GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "wave0_golden_queries.json"
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "wave0_baseline.json"
OVERLAP_THRESHOLD = 0.6  # >= 3 of 5 chunks must overlap
TOP_K = 5


async def _llm_stub(prompt, system_prompt=None, history_messages=None, **kwargs):
    # Only called if only_need_context=False; we never need it here.
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


async def _retrieve_top_chunks(rag: LightRAG, query_text: str) -> list[str]:
    """Run a hybrid retrieval-only query and return the top-K chunk IDs."""
    param = QueryParam(mode="hybrid", only_need_context=True, top_k=TOP_K)
    data = await rag.aquery_data(query_text, param=param)
    if not isinstance(data, dict) or data.get("status") != "success":
        return []
    chunks = data.get("data", {}).get("chunks", []) or []
    ids: list[str] = []
    for ch in chunks[:TOP_K]:
        # chunk_id is the stable identifier; fall back to reference_id if missing
        cid = ch.get("chunk_id") or ch.get("reference_id")
        if cid:
            ids.append(cid)
    return ids


def _load_queries() -> list[dict[str, Any]]:
    payload = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return payload["queries"]


def _overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    return len(set(a) & set(b)) / float(TOP_K)


async def run_baseline(queries: list[dict]) -> int:
    rag = await _build_rag()
    out: dict[str, list[str]] = {}
    for q in queries:
        if q["type"] == "cross_modal":
            continue
        ids = await _retrieve_top_chunks(rag, q["text"])
        out[q["id"]] = ids
        print(f"[baseline] {q['id']}: top-{TOP_K} = {ids}")
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nBaseline written to {BASELINE_PATH}")
    return 0


async def run_compare(queries: list[dict]) -> int:
    if not BASELINE_PATH.exists():
        print(f"ERROR: missing {BASELINE_PATH}. Run WAVE0_MODE=baseline first.", file=sys.stderr)
        return 1

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    rag = await _build_rag()

    all_pass = True
    print(f"query_id | overlap | pass/fail")
    print(f"---------|---------|----------")
    for q in queries:
        if q["type"] == "cross_modal":
            continue
        qid = q["id"]
        if qid not in baseline:
            print(f"{qid} | N/A (no baseline) | SKIP")
            continue
        new_ids = await _retrieve_top_chunks(rag, q["text"])
        ov = _overlap(new_ids, baseline[qid])
        passed = ov >= OVERLAP_THRESHOLD
        all_pass = all_pass and passed
        status = "PASS" if passed else "FAIL"
        print(f"{qid} | {ov:.2f} | {status}")
        if not passed:
            print(f"  baseline top-{TOP_K}: {baseline[qid]}")
            print(f"  current  top-{TOP_K}: {new_ids}")

    return 0 if all_pass else 1


async def main() -> int:
    mode = os.environ.get("WAVE0_MODE", "compare").lower()
    queries = _load_queries()
    if mode == "baseline":
        return await run_baseline(queries)
    return await run_compare(queries)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

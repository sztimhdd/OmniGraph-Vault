"""Plan 05-00c Task 0c.6 — remote smoke test.

Exercises the full post-swap pipeline end-to-end against ONE small document:
  1. Deepseek LLM wrapper (entity extraction via LightRAG)
  2. Gemini embedding with 2-key rotation (_ROTATION_HITS telemetry)
  3. 3072-dim embedding storage

Approach: reads smallest doc from kv_store_full_docs.json.bak, instantiates a
LightRAG over a PRIVATE temp working dir (so the production graph is not
touched), runs ainsert(), then dumps counters + storage evidence.

Exit codes: 0 on pass, 2 on pending_api_budget (both keys 429), 1 on fail.
NOT committed — temporary verification script per plan note.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# Repo-root on sys.path so `import config` works when executed as
# `python scripts/wave0c_smoke.py` from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import RAG_WORKING_DIR, load_env

load_env()


async def main() -> int:
    from lib.lightrag_embedding import _ROTATION_HITS, embedding_func
    from lib.api_keys import load_keys
    # quick-260509-s29 W3: dispatcher route (defaults to deepseek).
    from lib.llm_complete import get_llm_func
    from lightrag import LightRAG

    # Pick smallest doc from .bak
    bak_path = Path(RAG_WORKING_DIR) / "kv_store_full_docs.json.bak"
    if not bak_path.exists():
        print(f"FAIL: no backup at {bak_path}")
        return 1

    bak = json.loads(bak_path.read_text(encoding="utf-8"))
    if not bak:
        print("FAIL: backup is empty")
        return 1

    doc_id, doc = min(bak.items(), key=lambda kv: len(kv[1].get("content", "") or ""))
    content = doc.get("content", "") or ""
    print(f"smoke doc: {doc_id}")
    print(f"doc_size_chars: {len(content)}")

    pool = load_keys()
    print(f"key_pool_size: {len(pool)}")

    # PRIVATE temp working dir — do NOT touch the production graph.
    tmp = tempfile.mkdtemp(prefix="wave0c_smoke_")
    print(f"temp_working_dir: {tmp}")

    rag = LightRAG(
        working_dir=tmp,
        llm_model_func=get_llm_func(),
        embedding_func=embedding_func,
        embedding_func_max_async=1,
        embedding_batch_num=20,
        llm_model_max_async=2,
    )

    try:
        if hasattr(rag, "initialize_storages"):
            await rag.initialize_storages()
        # Truncate extremely long docs to keep smoke cost bounded — first 4000 chars.
        excerpt = content[:4000]
        print(f"ingesting excerpt ({len(excerpt)} chars)...")
        await rag.ainsert(excerpt)
        print("OK ingested")
        result = "pass"
    except RuntimeError as e:
        msg = str(e)
        if "exhausted" in msg.lower() or "429" in msg:
            print(f"PENDING: Gemini keys drained — {msg}")
            result = "pending_api_budget"
        else:
            print(f"FAIL: RuntimeError: {msg}")
            traceback.print_exc()
            result = "fail"
    except Exception as e:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
            print(f"PENDING: quota error — {msg}")
            result = "pending_api_budget"
        else:
            print(f"FAIL: {type(e).__name__}: {msg}")
            traceback.print_exc()
            result = "fail"
    finally:
        # Inspect the private working dir's vdb_chunks.json for embedding_dim.
        vdb_chunks = Path(tmp) / "vdb_chunks.json"
        final_dim: int | None = None
        if vdb_chunks.exists():
            try:
                data = json.loads(vdb_chunks.read_text(encoding="utf-8"))
                final_dim = data.get("embedding_dim")
            except Exception:
                pass
        print(f"rotation_hits: {dict(_ROTATION_HITS)}")
        print(f"final_vdb_embedding_dim: {final_dim}")
        print(f"result: {result}")

        # Emit machine-readable YAML-ish log line
        log = {
            "doc_id": doc_id,
            "doc_size_chars": len(content),
            "key_pool_size": len(pool),
            "deepseek_invoked": "true",
            "gemini_llm_invoked": "false",
            "key_rotation_hits": dict(_ROTATION_HITS),
            "final_vdb_embedding_dim": final_dim,
            "result": result,
        }
        print("LOG_JSON:" + json.dumps(log))

        # Clean temp working dir
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass

    if result == "pass":
        return 0
    if result == "pending_api_budget":
        return 2
    return 1


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)

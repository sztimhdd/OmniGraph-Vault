"""
Benchmark: LightRAG merge speed before/after config tuning.
Measures rag.ainsert() wall-clock time for the same article.
"""
import asyncio, time, sys, os
os.environ["RAG_WORKING_DIR"] = os.path.expanduser("~/.hermes/omonigraph-vault/lightrag_storage")

# Must be before any OmniGraph imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import RAG_WORKING_DIR
from lib import embedding_func
from lib.llm_deepseek import deepseek_model_complete
from lightrag import LightRAG
from pathlib import Path

ARTICLE_HASH = "f799dcd732"
ARTICLE_PATH = Path.home() / ".hermes/omonigraph-vault/images" / ARTICLE_HASH / "final_content.md"

CONTROL = {
    "embedding_func_max_async": 1,
    "embedding_batch_num": 20,
    "llm_model_max_async": 2,
}

EXPERIMENT = {
    "embedding_func_max_async": 4,
    "embedding_batch_num": 64,
    "llm_model_max_async": 4,
    "max_parallel_insert": 3,
    "addon_params": {"insert_batch_size": 100},
}


async def run(label: str, config: dict) -> float:
    doc_id = f"bench-{label.replace(' ', '-')}"
    text = ARTICLE_PATH.read_text()
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Doc: {ARTICLE_HASH}  ({len(text)//1024}KB)")
    print(f"  Config: {config}")

    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=deepseek_model_complete,
        embedding_func=embedding_func,
        llm_model_name="deepseek-v4-flash",
        **config,
    )
    await rag.initialize_storages()

    t0 = time.monotonic()
    await rag.ainsert(text, ids=[doc_id])
    elapsed = time.monotonic() - t0

    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    print(f"  ⏱️  {mins}m{secs}s")
    return elapsed


async def main():
    if not ARTICLE_PATH.exists():
        print(f"Article not found: {ARTICLE_PATH}")
        return

    # Warm-up: load graph
    print("Loading graph...")
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=deepseek_model_complete,
        embedding_func=embedding_func,
        llm_model_name="deepseek-v4-flash",
    )
    await rag.initialize_storages()
    del rag

    control_t = await run("CONTROL (old config)", CONTROL)
    exper_t = await run("EXPERIMENT (new config)", EXPERIMENT)

    ratio = control_t / exper_t
    print(f"\n{'='*60}")
    print(f"  Speedup: {ratio:.1f}×")
    print(f"  Old: {control_t:.0f}s  →  New: {exper_t:.0f}s")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())

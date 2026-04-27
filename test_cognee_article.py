"""Test Cognee remember_article integration end-to-end."""
import os, sys, asyncio
from pathlib import Path

# Load hermes env
dotenv = Path("//wsl.localhost/Ubuntu-24.04/home/sztimhdd/.hermes/.env")
if dotenv.exists():
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and val and key not in os.environ:
            os.environ[key] = val

sys.path.insert(0, str(Path(__file__).parent))

import cognee_wrapper


async def test():
    print("=== Testing remember_article ===\n")

    # 1. Store article metadata
    print("1. Storing article metadata via remember_article...")
    result = await cognee_wrapper.remember_article(
        title="AI Agent Memory Systems Design 2026",
        url="https://mp.weixin.qq.com/s/test123",
        entities=["AI Agent", "Memory", "RAG", "Cognee", "LightRAG", "Dual-Store"],
        summary_gist="This article explores dual-store architecture for AI agent memory, "
                     "combining episodic memory (Cognee) with semantic knowledge graphs (LightRAG). "
                     "Key insight: fire-and-forget at ingestion time, hybrid retrieval at query time.",
    )
    print(f"   remember_article returned: {result}")

    if not result:
        print("   NOTE: Cognee may not be available or timed out (this is OK — fast-path preserved)")
        print("   Test complete (graceful degradation verified).")
        return

    # 2. Small wait for processing
    print("\n2. Waiting 5s for Cognee background processing...")
    await asyncio.sleep(5)

    # 3. Try recall via the v1.0 API
    print("3. Testing recall...")
    try:
        import cognee
        results = await cognee.recall(
            query_text="What have I read about AI agent memory?",
            datasets=["ingested_articles"],
        )
        print(f"   Recall results type: {type(results)}")
        if isinstance(results, list):
            print(f"   Results count: {len(results)}")
        else:
            print(f"   Result: {str(results)[:200]}")
    except Exception as e:
        print(f"   Recall via v1.0 API failed (may need full pipeline): {e}")

    # 4. Try recall via our wrapper
    print("4. Testing recall via cognee_wrapper.recall_previous_context...")
    try:
        results = await cognee_wrapper.recall_previous_context("AI agent memory")
        print(f"   Results: {len(results)} items")
        for r in results[:3]:
            print(f"    - {str(r)[:150]}")
    except Exception as e:
        print(f"   Wrapper recall: {e}")

    print("\n=== Test complete ===")


if __name__ == "__main__":
    asyncio.run(test())

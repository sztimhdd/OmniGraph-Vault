"""Single-article timing benchmark for ingest_wechat.py.
Usage: cd /home/sztimhdd/OmniGraph-Vault && venv/bin/python scripts/time_single_ingest.py "<url>"
"""
import asyncio, sys, time, os

os.environ.setdefault("VISION_PROVIDER", "siliconflow")
os.environ.setdefault("LLM_TIMEOUT", "600")

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "http://mp.weixin.qq.com/s?__biz=MjM5ODkzMzMwMQ==&mid=2650451632&idx=1"
    "&sn=38a328ba354614403d8190f299fc37da"
    "&chksm=becd28ea89baa1fcf565b0e8defa154bf49db85600ad487bdf10bf606db80894cee8370f55f1#rd"
)

t0 = time.monotonic()
stages = {}

def mark(stage: str):
    elapsed = time.monotonic() - t0
    stages[stage] = elapsed
    print(f"\n⏱ [{stage}] +{elapsed - list(stages.values())[-1]:.1f}s (total: {elapsed:.1f}s)", flush=True)

async def main():
    mark("start")
    
    import ingest_wechat
    # Pre-init LightRAG once (like the batch orchestrator does)
    from pathlib import Path
    mark("imports")
    
    rag = await ingest_wechat.get_rag()
    mark("rag_init")
    
    await ingest_wechat.ingest_article(URL, rag=rag)
    mark("done")
    
    # Print summary
    total = stages["done"] - stages["start"]
    print(f"\n{'='*60}")
    print(f"Stage breakdown:")
    prev_t = 0
    prev_name = None
    for name, t in stages.items():
        if prev_name:
            print(f"  {prev_name:20s} → {name:20s}   {t - prev_t:8.1f}s")
        prev_t, prev_name = t, name
    print(f"  {'TOTAL':>43s}   {total:8.1f}s")
    print(f"{'='*60}")

asyncio.run(main())

"""
run_uat_ingest.py — Ingest 5 WeChat articles with rate limiting and detailed logging.
Respects Gemini API RPM limits by adding delays between articles.
"""
import sys
import os
import sqlite3
import time
import asyncio
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "kol_scan.db"

sys.stdout.reconfigure(encoding="utf-8")

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
os.environ.setdefault("SSL_CERT_FILE", os.path.expanduser("~/.claude/certs/combined-ca-bundle.pem"))
os.environ.setdefault("REQUESTS_CA_BUNDLE", os.path.expanduser("~/.claude/certs/combined-ca-bundle.pem"))
os.environ.setdefault("TIKTOKEN_CACHE_DIR", os.path.expanduser("~/.tiktoken_cache"))

ARTICLES = [
    "https://mp.weixin.qq.com/s/Y_uRMYBmdLWUPnz_ac7jWA",
    "https://mp.weixin.qq.com/s/8SGRMIyspvUcLMcmeDa2Mw",
    "https://mp.weixin.qq.com/s/4bE4AZPAAYVdtQIlf9hP9A",
    "https://mp.weixin.qq.com/s/qzacaj9XHfq9etTOBt8r5Q",
    "https://mp.weixin.qq.com/s/oGXo8psXgP6A24mmKbTGIw",
]

DELAY_BETWEEN_ARTICLES = 30  # seconds — respect Gemini RPM limits


async def ingest_one(url, index):
    from ingest_wechat import ingest_article
    print(f"\n{'='*60}")
    print(f"ARTICLE {index+1}/5: {url}")
    print(f"{'='*60}")
    start = time.time()
    try:
        await ingest_article(url)
        elapsed = time.time() - start
        print(f"\nArticle {index+1} completed in {elapsed:.0f}s")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\nArticle {index+1} FAILED after {elapsed:.0f}s: {e}")
        return False


async def main():
    results = []

    # Check which articles are already ingested (DB-first, entity buffer fallback)
    from config import ENTITY_BUFFER_DIR
    existing: set[str] = set()
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute("SELECT url FROM articles WHERE id IN (SELECT article_id FROM ingestions WHERE status='ok')").fetchall()
            conn.close()
            for (url,) in rows:
                import hashlib
                existing.add(hashlib.md5(url.encode()).hexdigest()[:10])
        except Exception:
            pass
    if not existing and os.path.exists(ENTITY_BUFFER_DIR):
        for f in os.listdir(ENTITY_BUFFER_DIR):
            if f.endswith("_entities.json"):
                existing.add(f.split("_")[0])

    print(f"Entity buffer already has {len(existing)} articles: {existing}")
    print(f"Delay between articles: {DELAY_BETWEEN_ARTICLES}s (Gemini RPM limit)")

    for i, url in enumerate(ARTICLES):
        # Check if already ingested by computing hash
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        if url_hash in existing:
            print(f"\nArticle {i+1} ({url_hash}) already ingested, skipping")
            results.append(("SKIP", url_hash))
            continue

        success = await ingest_one(url, i)
        results.append(("OK" if success else "FAIL", url))

        if i < len(ARTICLES) - 1:
            print(f"\nWaiting {DELAY_BETWEEN_ARTICLES}s before next article (RPM limit)...")
            time.sleep(DELAY_BETWEEN_ARTICLES)

    # Summary
    print(f"\n{'='*60}")
    print("INGESTION SUMMARY")
    print(f"{'='*60}")
    for i, (status, info) in enumerate(results):
        print(f"  Article {i+1}: {status} — {info[:60]}")

    # Check runtime data
    from config import ENTITY_BUFFER_DIR, RAG_WORKING_DIR, BASE_IMAGE_DIR
    eb_files = os.listdir(ENTITY_BUFFER_DIR) if os.path.exists(ENTITY_BUFFER_DIR) else []
    rag_files = os.listdir(RAG_WORKING_DIR) if os.path.exists(RAG_WORKING_DIR) else []
    img_dirs = os.listdir(BASE_IMAGE_DIR) if os.path.exists(BASE_IMAGE_DIR) else []
    print(f"\nEntity buffer: {len([f for f in eb_files if f.endswith('_entities.json')])} files")
    print(f"LightRAG storage: {len(rag_files)} files")
    print(f"Image directories: {len(img_dirs)}")

    # Show entity buffer contents
    for f in sorted(eb_files):
        if f.endswith("_entities.json"):
            path = os.path.join(ENTITY_BUFFER_DIR, f)
            try:
                with open(path, encoding="utf-8") as fp:
                    data = json.load(fp)
                entities = data if isinstance(data, list) else data.get("entities", [])
                print(f"  {f}: {len(entities)} entities")
            except Exception as e:
                print(f"  {f}: error reading — {e}")


if __name__ == "__main__":
    asyncio.run(main())

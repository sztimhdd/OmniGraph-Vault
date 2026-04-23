import asyncio
import base64
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import subprocess
import numpy as np
import nest_asyncio

try:
    from lightrag.lightrag import LightRAG, QueryParam
    from lightrag.llm.gemini import gemini_model_complete, gemini_embed
    from lightrag.utils import wrap_embedding_func_with_attrs
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

nest_asyncio.apply()

from config import RAG_WORKING_DIR, load_env
load_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_github")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
os.makedirs(RAG_WORKING_DIR, exist_ok=True)

ENTITY_REGISTRY_FILE = Path(__file__).parent / "entity_registry.json"


# --- LightRAG setup (matches ingest_wechat.py exactly) ---

async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    return await gemini_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=GEMINI_API_KEY,
        model_name="gemini-3.1-flash-lite-preview",
        **kwargs,
    )

@wrap_embedding_func_with_attrs(
    embedding_dim=768,
    send_dimensions=True,
    max_token_size=2048,
    model_name="gemini-embedding-001",
)
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    return await gemini_embed.func(
        texts, api_key=GEMINI_API_KEY, model="gemini-embedding-001",
        embedding_dim=768,
    )

async def get_rag() -> LightRAG:
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=llm_model_func,
        embedding_func=embedding_func,
        llm_model_name="gemini-3.1-flash-lite-preview",
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return rag


# --- GitHub API via gh CLI (bypasses corporate SSL proxy) ---

def _gh_api(endpoint: str) -> dict | None:
    """Call GitHub API via gh CLI. Go binary bypasses Python SSL proxy issues."""
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            logger.warning(f"gh api {endpoint}: {result.stderr.strip()}")
            return None
    except FileNotFoundError:
        print("Error: gh CLI not found. Install from https://cli.github.com/")
        sys.exit(1)
    except Exception as e:
        logger.error(f"gh api call failed: {e}")
        return None

def fetch_repo_content(org: str, repo: str) -> str | None:
    """Fetch repo metadata + README + file tree and return as a single markdown document."""
    slug = f"repos/{org}/{repo}"

    meta = _gh_api(slug)
    if not meta:
        return None

    readme_data = _gh_api(f"{slug}/readme")
    readme_text = ""
    if readme_data and readme_data.get("content"):
        try:
            readme_text = base64.b64decode(readme_data["content"]).decode("utf-8", errors="replace")
        except Exception:
            pass

    tree_data = _gh_api(f"{slug}/git/trees/HEAD")
    top_files: list[str] = []
    if tree_data and tree_data.get("tree"):
        top_files = [item["path"] for item in tree_data["tree"] if item["type"] in ("blob", "tree")][:30]

    topics = meta.get("topics", [])
    doc = f"""# {meta['full_name']}

## Repository Metadata
- **Description**: {meta.get('description') or 'N/A'}
- **Stars**: {meta.get('stargazers_count', 0)}
- **Language**: {meta.get('language') or 'N/A'}
- **Topics**: {', '.join(topics) if topics else 'N/A'}
- **License**: {(meta.get('license') or {}).get('name', 'N/A')}
- **URL**: {meta['html_url']}
- **Default branch**: {meta.get('default_branch', 'main')}

## Top-Level Structure
{chr(10).join(f'- {f}' for f in top_files) if top_files else 'N/A'}

## README

{readme_text}
"""
    return doc


# --- entity_registry.json (atomic read/write) ---

def _load_registry() -> dict:
    if ENTITY_REGISTRY_FILE.exists():
        with open(ENTITY_REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_registry(registry: dict) -> None:
    tmp = ENTITY_REGISTRY_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    tmp.replace(ENTITY_REGISTRY_FILE)


# --- Main ingestion ---

async def ingest_github(url: str) -> None:
    url = url.rstrip("/")
    slug = url.replace("https://github.com/", "").replace("http://github.com/", "")
    parts = slug.split("/")
    if len(parts) < 2:
        print(f"Error: Cannot parse GitHub URL: {url}")
        sys.exit(1)
    org, repo = parts[0], parts[1]

    print(f"--- Starting GitHub Ingestion: {org}/{repo} ---")

    registry = _load_registry()
    if url in registry:
        print(f"Already ingested: {url} (at {registry[url]['ingested_at']}). Skipping.")
        return

    print("Fetching from GitHub API...")
    content = fetch_repo_content(org, repo)
    if not content:
        print(f"Error: Could not fetch content for {org}/{repo}")
        sys.exit(1)

    content_hash = hashlib.md5(content.encode()).hexdigest()[:10]
    print(f"Content fetched ({len(content)} chars, hash {content_hash})")

    print("Ingesting into LightRAG...")
    rag = await get_rag()
    await rag.ainsert(content)

    registry[url] = {
        "url": url,
        "org": org,
        "repo": repo,
        "content_hash": content_hash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_registry(registry)

    print(f"--- Successfully Ingested! ---")
    print(f"Repo:     {org}/{repo}")
    print(f"Hash:     {content_hash}")
    print(f"Registry: {ENTITY_REGISTRY_FILE}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_github.py <github_url>")
        print("Example: python ingest_github.py https://github.com/NousResearch/hermes-agent")
        sys.exit(1)

    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not set. Add it to ~/.hermes/.env")
        sys.exit(1)

    asyncio.run(ingest_github(sys.argv[1]))

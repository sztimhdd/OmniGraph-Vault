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
            capture_output=True, text=True, encoding="utf-8", timeout=15,
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

def _fetch_identity(org: str, repo: str) -> str | None:
    """Fetch repo metadata + README + file tree as the identity card segment."""
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
    doc = f"""# {org}/{repo} — Identity

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


def _fetch_docs(org: str, repo: str) -> str | None:
    """Fetch .md and .rst files from the docs/ directory."""
    listing = _gh_api(f"repos/{org}/{repo}/contents/docs")
    if not isinstance(listing, list):
        return None

    md_files = [f for f in listing if f["name"].endswith((".md", ".rst"))]
    if not md_files:
        return None

    doc = f"# {org}/{repo} — Documentation\n\n"
    for file_entry in md_files[:10]:
        file_data = _gh_api(file_entry["url"])
        if not file_data or not file_data.get("content"):
            continue
        try:
            content = base64.b64decode(file_data["content"]).decode("utf-8", errors="replace")
        except Exception:
            continue
        doc += f"## {file_entry['name']}\n\n{content}\n\n"

    return doc if len(doc) > len(f"# {org}/{repo} — Documentation\n\n") else None


def _fetch_releases(org: str, repo: str) -> str | None:
    """Fetch the last 5 releases."""
    releases = _gh_api(f"repos/{org}/{repo}/releases?per_page=5")
    if not isinstance(releases, list) or not releases:
        return None

    doc = f"# {org}/{repo} — Releases\n\n"
    for r in releases:
        tag = r.get("tag_name", "")
        name = r.get("name", "")
        published = r.get("published_at", "")
        body = r.get("body") or ""
        doc += f"## {tag} — {name}\nPublished: {published}\n\n{body}\n\n"

    return doc


def _fetch_deps(org: str, repo: str) -> str | None:
    """Fetch the first available dependency manifest file."""
    for filename in ("requirements.txt", "pyproject.toml", "package.json"):
        result = _gh_api(f"repos/{org}/{repo}/contents/{filename}")
        if result and result.get("content"):
            try:
                content = base64.b64decode(result["content"]).decode("utf-8", errors="replace")
                return f"# {org}/{repo} — Dependencies\n\n## {filename}\n\n{content}\n"
            except Exception:
                continue
    return None


def _fetch_top_issues(org: str, repo: str) -> str | None:
    """Fetch top 10 issues sorted by reactions."""
    items = _gh_api(f"repos/{org}/{repo}/issues?state=all&sort=reactions&per_page=10&direction=desc")
    if not isinstance(items, list) or not items:
        return None

    issues = [item for item in items if not item.get("pull_request")]
    if not issues:
        return None

    doc = f"# {org}/{repo} — Top Issues (by reactions)\n\n"
    for issue in issues:
        number = issue.get("number", "")
        title = issue.get("title", "")
        state = issue.get("state", "")
        labels = ", ".join(lbl["name"] for lbl in issue.get("labels", []))
        body = (issue.get("body") or "")[:500]
        reactions = (issue.get("reactions") or {}).get("total_count", 0)
        doc += f"## #{number}: {title}\nState: {state} | Reactions: {reactions} | Labels: {labels}\n\n{body}\n\n"

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

    # Fetch all segments
    segments: list[tuple[str, str | None]] = [
        ("identity", _fetch_identity(org, repo)),
        ("docs", _fetch_docs(org, repo)),
        ("releases", _fetch_releases(org, repo)),
        ("deps", _fetch_deps(org, repo)),
        ("issues", _fetch_top_issues(org, repo)),
    ]

    # Must have at least identity
    if segments[0][1] is None:
        print(f"Error: Could not fetch identity for {org}/{repo}")
        sys.exit(1)

    # Compute dedup hash on ALL segment content combined
    combined_for_hash = "".join(content for _, content in segments if content)
    content_hash = hashlib.md5(combined_for_hash.encode()).hexdigest()[:10]
    print(f"Segments fetched: {[name for name, c in segments if c]} (combined hash {content_hash})")

    # Insert each segment separately
    rag = await get_rag()
    for seg_name, seg_content in segments:
        if seg_content:
            print(f"  Inserting segment: {seg_name} ({len(seg_content)} chars)")
            await rag.ainsert(seg_content)

    registry[url] = {
        "url": url,
        "org": org,
        "repo": repo,
        "content_hash": content_hash,
        "segments": [name for name, c in segments if c],
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

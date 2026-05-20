"""Generate wiki entity pages from THREE sources:

  1. LightRAG corpus (multi-hop hybrid retrieval — `only_need_context=True`,
     intermediate Vertex AI calls allowed per user 2026-05-20)
  2. Tavily web search (advanced depth, top results)
  3. Databricks Claude Opus 4.7 training knowledge

Synthesis is performed by Databricks Claude Opus 4.7 (1M context). Output
follows the SCHEMA-2026-05-20 format: GFM `[^N]` footnotes + multi-type
sources list in YAML frontmatter.

Per llm-wiki-02-entity-content-PLAN.md Task 3 spec — this script is the W1 T3
deliverable. Cost-gate prerequisite: `llm-wiki-02-COST-ESTIMATE.md` must have
`approved: yes` in frontmatter.

CLI:
    python scripts/wiki_generate_pages.py \\
      --entities <selection.md> \\
      --cost-gate <cost-estimate.md> \\
      --output-dir kb/wiki/entities/ \\
      [--smoke ENTITY_NAME] \\
      [--dry-run]

Required env vars:
    TAVILY_API_KEY                — Tavily web search auth
    DATABRICKS_CONFIG_PROFILE=dev — Databricks SDK profile
    GOOGLE_APPLICATION_CREDENTIALS — Vertex AI SA key (for LightRAG embeddings)
    OMNIGRAPH_BASE_DIR             — LightRAG storage root
    KOL_SCAN_DB_PATH               — articles SQLite path
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter
import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger("wiki_generate_pages")

OPUS_MODEL_ENDPOINT = os.environ.get("WIKI_LLM_ENDPOINT", "databricks-claude-opus-4-7")
TAVILY_API_URL = "https://api.tavily.com/search"
TAVILY_MAX_RESULTS = int(os.environ.get("WIKI_TAVILY_MAX_RESULTS", "8"))

CHUNK_ID_RE = re.compile(r"chunk-[a-f0-9]{8,}")
WIKI_LEGACY_CITATION_RE = re.compile(r"\^\[article:([a-f0-9]{10})\]")


# ----------------------------------------------------------------------------- helpers


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return s or "untitled"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as f:
        f.write(content)
        tmp_path = Path(f.name)
    os.replace(tmp_path, path)


def _verify_cost_gate(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"FATAL: cost gate file missing: {path}")
    post = frontmatter.load(path)
    approved = post.get("approved")
    if approved is True or (isinstance(approved, str) and approved.strip().lower() == "yes"):
        logger.info("cost gate OK: %s approved=%s", path, approved)
        return
    raise SystemExit(f"FATAL: cost gate {path} has approved={approved!r}; expected `yes`.")


def _parse_selection(path: Path) -> list[str]:
    """Parse entity names from the FIRST fenced code block in the selection file.

    Subsequent code blocks (e.g. the resume command shell snippet) are ignored.
    """
    text = path.read_text(encoding="utf-8")
    in_block = False
    seen_block = False
    names: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if not seen_block:
                in_block = not in_block
                if not in_block:
                    seen_block = True
            continue
        if in_block:
            n = line.strip()
            # Skip blank, comment, and lines that don't look like entity names
            # (defensive even though we only read first block now)
            if n and not n.startswith("#") and "/" not in n and "\\" not in n:
                names.append(n)
    if not names:
        raise SystemExit(f"FATAL: no entities parsed from {path}")
    return names


def _resolve_db_path() -> Path:
    env = os.environ.get("KOL_SCAN_DB_PATH")
    if env:
        return Path(env).expanduser()
    try:
        import config  # type: ignore[import-not-found]
        cand = Path(config.BASE_DIR) / "data" / "kol_scan.db"
        if cand.exists():
            return cand
    except Exception:
        pass
    return _REPO_ROOT / ".dev-runtime" / "data" / "kol_scan.db"


def _resolve_lightrag_dir() -> Path:
    try:
        import config  # type: ignore[import-not-found]
        return Path(config.RAG_WORKING_DIR)
    except Exception:
        base = os.environ.get("OMNIGRAPH_BASE_DIR")
        if base:
            return Path(base).expanduser() / "lightrag_storage"
    return _REPO_ROOT / ".dev-runtime" / "lightrag_storage"


# ----------------------------------------------------------------------------- chunk-id → article catalog


def _build_chunk_article_map(lightrag_dir: Path, db_path: Path) -> dict[str, dict[str, str]]:
    """Pre-compute {chunk_id: {hash: '...', title: '...', url: '...'}}."""
    chunks_path = lightrag_dir / "kv_store_text_chunks.json"
    docs_path = lightrag_dir / "kv_store_full_docs.json"
    if not chunks_path.exists() or not docs_path.exists():
        logger.warning("chunk/doc kv store missing; chunk→article map will be empty")
        return {}

    chunks = json.load(chunks_path.open(encoding="utf-8"))
    docs = json.load(docs_path.open(encoding="utf-8"))

    # Build URL → (hash, title) from SQLite (only when DB exists)
    url_map: dict[str, tuple[str, str]] = {}
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            for url, h, title in conn.execute(
                "SELECT url, content_hash, title FROM articles "
                "WHERE url IS NOT NULL AND content_hash IS NOT NULL"
            ):
                if not url or not h:
                    continue
                url_map[url] = (h, title or "")
                # Normalize http⇆https for lookup robustness
                if url.startswith("http://"):
                    url_map.setdefault("https://" + url[7:], (h, title or ""))
                elif url.startswith("https://"):
                    url_map.setdefault("http://" + url[8:], (h, title or ""))
        finally:
            conn.close()

    url_re = re.compile(r"URL:\s*(\S+)")
    result: dict[str, dict[str, str]] = {}
    for chunk_id, chunk_data in chunks.items():
        if not isinstance(chunk_data, dict):
            continue
        doc_id = chunk_data.get("full_doc_id")
        if not doc_id:
            continue
        doc_data = docs.get(doc_id)
        if not isinstance(doc_data, dict):
            continue
        content = doc_data.get("content", "")
        m = url_re.search(content)
        if not m:
            continue
        url = m.group(1).strip()
        info = url_map.get(url)
        if info:
            result[chunk_id] = {"hash": info[0], "title": info[1], "url": url}
        else:
            # Article exists in LightRAG but not in local SQLite — record URL
            # without hash so we can still cite the URL as a web source.
            result[chunk_id] = {"hash": "", "title": "", "url": url}
    return result


def _entity_chunks_from_vdb(
    entity_name: str, lightrag_dir: Path
) -> tuple[str, list[str]]:
    """Return (entity_description, chunk_ids) for an entity using vdb_entities.json.

    Used as fallback when LightRAG aquery context parsing yields zero chunks.
    """
    vdb_path = lightrag_dir / "vdb_entities.json"
    if not vdb_path.exists():
        return ("", [])
    data = json.load(vdb_path.open(encoding="utf-8"))
    rows = data.get("data", data) if isinstance(data, dict) else data
    desc = ""
    chunk_ids: set[str] = set()
    for ent in rows:
        if (ent.get("entity_name") or "") == entity_name:
            desc = ent.get("content", "") or desc
            sid = ent.get("source_id") or ""
            for c in re.split(r"[<>|\s]+", sid):
                c = c.strip()
                if c.startswith("chunk-"):
                    chunk_ids.add(c)
    return (desc, sorted(chunk_ids))


# ----------------------------------------------------------------------------- source builders


_RAG_INSTANCE = None


async def _get_rag():
    """Construct LightRAG instance once (cache for batch run).

    Mirrors `kg_synthesize.synthesize_response` setup but skips the final
    synthesis path. Vertex AI is used for keyword extraction + embedding
    (allowed per user 2026-05-20).
    """
    global _RAG_INSTANCE
    if _RAG_INSTANCE is not None:
        return _RAG_INSTANCE
    from lightrag.lightrag import LightRAG  # type: ignore[import-not-found]
    from config import RAG_WORKING_DIR  # type: ignore[import-not-found]
    from lib.llm_complete import get_llm_func  # type: ignore[import-not-found]
    from lib.lightrag_embedding import embedding_func  # type: ignore[import-not-found]
    from kg_synthesize import _embedding_timeout_default  # type: ignore[import-not-found]

    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=get_llm_func(),
        embedding_func=embedding_func,
        default_embedding_timeout=_embedding_timeout_default(),
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    await asyncio.sleep(1)
    _RAG_INSTANCE = rag
    return rag


async def fetch_lightrag_context(entity_name: str) -> str:
    """Call LightRAG aquery with only_need_context=True, mode=hybrid.

    Returns raw context text (multi-hop entities + relations + chunks). Does
    NOT do final LLM synthesis — Opus 4.7 will do that.

    Image URL rewrite: chunks often contain legacy `http://localhost:8765/...`
    image markdown from the v1 image_server pipeline. We rewrite to
    `/static/img/<hash>/<n>.jpg` (kb canonical) before stuffing into the prompt
    so Opus emits the corrected form straight through.
    """
    from lightrag.lightrag import QueryParam  # type: ignore[import-not-found]

    rag = await _get_rag()
    query = (
        f"Provide all available knowledge about `{entity_name}`: definition, "
        f"architecture, history, related entities, and notable use cases."
    )
    param = QueryParam(mode="hybrid", only_need_context=True)
    ctx = await rag.aquery(query, param=param)
    if not isinstance(ctx, str):
        return ""
    # Rewrite legacy image URLs to kb canonical form
    try:
        from kb.services.synthesize import _rewrite_image_urls  # type: ignore[import-not-found]
        ctx = _rewrite_image_urls(ctx)
    except Exception as e:
        logger.warning("image-url rewrite skipped (%s)", e)
    return ctx


def fetch_tavily_results(entity_name: str, api_key: str) -> list[dict[str, Any]]:
    """Tavily advanced search — top results with URL, title, content snippet."""
    body = {
        "api_key": api_key,
        "query": f"{entity_name} AI agent framework",
        "search_depth": "advanced",
        "max_results": TAVILY_MAX_RESULTS,
        "include_raw_content": False,
    }
    try:
        r = requests.post(TAVILY_API_URL, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("results", []) or []
    except Exception as e:
        logger.warning("Tavily search failed for %s: %s", entity_name, e)
        return []


# ----------------------------------------------------------------------------- catalog + prompt


def build_source_catalog(
    *,
    chunk_ids: list[str],
    chunk_article_map: dict[str, dict[str, str]],
    tavily_results: list[dict[str, Any]],
    include_builtin: bool = True,
) -> list[dict[str, Any]]:
    """Build a deduplicated, ordered source catalog for the Opus prompt.

    Returns: list of dicts with: id (1-indexed int), type, ref, title, content
    """
    catalog: list[dict[str, Any]] = []
    seen_article_hashes: set[str] = set()
    seen_urls: set[str] = set()

    # Article sources (dedup by content_hash)
    for cid in chunk_ids:
        info = chunk_article_map.get(cid)
        if not info:
            continue
        h = info.get("hash") or ""
        url = info.get("url") or ""
        title = info.get("title") or ""
        if h and h not in seen_article_hashes:
            seen_article_hashes.add(h)
            catalog.append({
                "id": len(catalog) + 1,
                "type": "article",
                "ref": h,
                "title": title or f"corpus article {h}",
                "url": url,
            })
        elif not h and url and url not in seen_urls:
            # Article in LightRAG but not in local SQL — surface as web source
            seen_urls.add(url)
            catalog.append({
                "id": len(catalog) + 1,
                "type": "web",
                "ref": url,
                "title": title or url,
            })

    # Tavily web sources
    for r in tavily_results:
        url = (r.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        catalog.append({
            "id": len(catalog) + 1,
            "type": "web",
            "ref": url,
            "title": (r.get("title") or url)[:200],
            "content": (r.get("content") or "")[:2000],
        })

    if include_builtin:
        catalog.append({
            "id": len(catalog) + 1,
            "type": "builtin",
            "ref": None,
            "title": "Databricks Claude Opus 4.7 training knowledge",
        })

    return catalog


def build_opus_prompt(
    *,
    entity_name: str,
    lightrag_context: str,
    tavily_results: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    today: date,
) -> str:
    """Build the synthesis prompt for Opus 4.7.

    Output format follows kb/wiki/SCHEMA.md (legacy single-type citation):
    - Inline citations are `^[article:<10-char-hex>]` ONLY (article corpus only)
    - Frontmatter `sources:` is a list of strings `article:<hex>` (legacy)
    - Web sources surface in body as narrative `According to [Title]:` references
      and aggregated in a `## Further Reading` section listing URLs
    - Built-in knowledge supplements but is NOT inline-cited
    """
    article_lines = []
    web_lines = []
    builtin_lines = []
    for s in catalog:
        if s["type"] == "article":
            article_lines.append(f"  - article:{s['ref']} — {s['title']!r}")
        elif s["type"] == "web":
            web_lines.append(
                f"  - {s['ref']} — {s['title']!r}"
            )
        else:
            builtin_lines.append(f"  - {s['title']}")

    article_block = "\n".join(article_lines) if article_lines else "  (no article sources)"
    web_block = "\n".join(web_lines) if web_lines else "  (no web sources)"
    builtin_block = "\n".join(builtin_lines) if builtin_lines else "  (no builtin)"

    tavily_content_block = ""
    if tavily_results:
        tavily_lines = []
        for s in catalog:
            if s["type"] != "web" or "content" not in s:
                continue
            tavily_lines.append(
                f"--- {s['ref']} ---\n"
                f"Title: {s['title']}\n"
                f"Content: {s['content']}\n"
            )
        if tavily_lines:
            tavily_content_block = "## Tavily Web Search Results\n\n" + "\n".join(tavily_lines)

    # Articles list for frontmatter (legacy SCHEMA: list of strings)
    article_yaml_lines = [f"  - article:{s['ref']}" for s in catalog if s["type"] == "article"]
    article_yaml = "\n".join(article_yaml_lines) if article_yaml_lines else "  []"

    return f"""You are a knowledge synthesizer building a wiki entry for `{entity_name}`.

# YOUR TASK

Write a comprehensive wiki page about `{entity_name}` integrating THREE source types:
1. LightRAG corpus context (curated articles in our knowledge base) — formally cited inline
2. Tavily web search results (current web information) — referenced in body, listed in Further Reading
3. Your own training knowledge (Claude Opus 4.7) — supplements the body, not inline-cited

# CRITICAL OUTPUT FORMAT

Output a single complete markdown document with YAML frontmatter, EXACTLY this shape:

```
---
title: {entity_name}
created: '{today.isoformat()}'
last_updated: '{today.isoformat()}'
sources:
{article_yaml}
confidence_level: high | medium | low
---

# {entity_name}

<body with `^[article:<hash>]` inline citations on article-derived claims>

## Further Reading

- [Title](URL) — short note
- [Title](URL) — short note

```

# CITATION RULES (MUST FOLLOW)

Inline citations:
- Format is exactly `^[article:<10-char-hex>]` — note the `^` caret prefix and the 10-char article hash.
- Cite article-derived claims using ONLY hashes from the AVAILABLE ARTICLES list below.
- DO NOT invent hashes. DO NOT cite web URLs or builtin knowledge inline.
- Multiple citations stack: `^[article:abc1234567]^[article:def9876543]`.
- For claims that come from web search or your own training knowledge, write the claim narratively (e.g. "According to the Hermes GitHub README, ...") and ensure the URL appears in `## Further Reading`.

Frontmatter `sources:` list:
- MUST equal the AVAILABLE ARTICLES list below (same hashes, same order, format `article:<hex>`).
- DO NOT add web URLs or builtin to `sources:` — that field is for article corpus only.

`## Further Reading` section (append at end of body):
- One bullet per web URL used.
- Format: `- [Source title](URL) — one-sentence note`.
- Omit this section entirely if no web URL was actually used.

`confidence_level`:
- `high` if ≥3 article citations spanning ≥2 distinct hashes
- `medium` if 1-2 article citations
- `low` if 0 article citations (pure web/builtin pages)

Required body sections (use `## Heading` for each, in this order):
1. Definition / Overview
2. Architecture / Design (when applicable)
3. History / Origin
4. Key Concepts / Components
5. Notable Use Cases / Examples
6. Cross-references — list `[[entity-slug]]` mentions
7. Further Reading — web URLs (omit if none used)

# AVAILABLE ARTICLES (cite hashes from this list ONLY)

{article_block}

# AVAILABLE WEB SOURCES (use as narrative reference, list in Further Reading)

{web_block}

# AVAILABLE BUILTIN KNOWLEDGE

{builtin_block}

DO NOT:
- Output anything before the opening `---` of frontmatter
- Use `[^N]` GFM-footnote form (NOT this SCHEMA's format)
- Cite an article hash not in AVAILABLE ARTICLES above
- Output empty/placeholder pages — if zero articles available, still produce a page sourced from web + builtin (will land at confidence_level: low)

# IMAGES (CRITICAL — preserve from LightRAG context)

The LIGHTRAG CORPUS CONTEXT below may contain inline markdown images such as
`![alt](/static/img/<hash>/<n>.jpg)`. You MUST:
- Preserve EVERY relevant image markdown from the context — copy it verbatim into your output near the relevant text
- Pick the most informative 3-8 images for the page (e.g. architecture diagrams, screenshots) — do NOT skip them all
- Place each image inline immediately AFTER the paragraph it illustrates, on its own line
- Do NOT alter the URL path or filename
- Do NOT invent image URLs that don't appear in context
- If the context has zero images, that's fine — output none

Image format example (use this verbatim shape):
`![Architecture diagram](/static/img/abc1234567/3.jpg)`

# LIGHTRAG CORPUS CONTEXT

{lightrag_context if lightrag_context else "(LightRAG returned no context — page must rely on web + builtin only.)"}

{tavily_content_block}

# WRITE THE WIKI PAGE NOW
"""


# ----------------------------------------------------------------------------- Databricks Opus call


def _databricks_credentials() -> tuple[str, str]:
    """Resolve (workspace_url, token) from ~/.databrickscfg [profile] or env.

    Bypasses Databricks SDK to avoid its reported timeout issue (2026-05-20)
    where `serving_endpoints.list()` and `query()` hang for 5+ min via SDK
    while direct REST is fast. Reads PAT from configfile profile section.
    """
    host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if host and token:
        return host, token

    cfg_path = Path(os.environ.get("DATABRICKS_CONFIG_FILE", "")).expanduser() \
        if os.environ.get("DATABRICKS_CONFIG_FILE") else Path.home() / ".databrickscfg"
    profile_name = os.environ.get("DATABRICKS_CONFIG_PROFILE", "dev")
    if not cfg_path.exists():
        raise RuntimeError(f"Databricks config file missing: {cfg_path}")

    import configparser
    parser = configparser.ConfigParser()
    parser.read(cfg_path)
    if profile_name not in parser:
        raise RuntimeError(f"profile [{profile_name}] not in {cfg_path}")
    section = parser[profile_name]
    host = host or (section.get("host") or "").rstrip("/")
    token = token or section.get("token") or ""
    if not host:
        raise RuntimeError(f"profile [{profile_name}] has no host")
    if not token:
        raise RuntimeError(
            f"profile [{profile_name}] has no token; auth_type={section.get('auth_type')}"
        )
    return host, token


def call_opus(prompt: str, *, max_tokens: int = 8000, timeout_s: int = 180) -> str:
    """Call Databricks Claude Opus 4.7 serving endpoint via direct REST.

    Uses OpenAI-compatible chat completions schema at
    `<host>/serving-endpoints/<name>/invocations`.
    """
    host, token = _databricks_credentials()
    url = f"{host}/serving-endpoints/{OPUS_MODEL_ENDPOINT}/invocations"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    # SSL note: corp Cisco Umbrella proxy intercepts HTTPS; the local
    # certifi/REQUESTS_CA_BUNDLE doesn't include the Databricks cert chain
    # in this network. Direct curl works (already verified). Since we know
    # the workspace URL is fixed + auth uses bearer PAT, accept the small
    # MITM-on-known-host residual risk and disable verify here. Production
    # Hermes / Aliyun deploys hit Databricks via different network paths
    # without the proxy interception.
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    r = requests.post(url, headers=headers, json=body, timeout=timeout_s, verify=False)
    if r.status_code != 200:
        raise RuntimeError(
            f"Opus call failed: HTTP {r.status_code} {r.text[:300]}"
        )
    data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Opus returned no choices: {str(data)[:300]}")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        # Some endpoints return content as list of blocks; join text blocks
        content = "\n".join(
            (b.get("text") or "") for b in content if isinstance(b, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"Opus content invalid: {type(content)} {str(content)[:200]}")
    return content


# ----------------------------------------------------------------------------- validation


def _strip_code_fences(text: str) -> str:
    """If Opus wrapped output in ```markdown ... ``` fence, strip it."""
    text = text.strip()
    if text.startswith("```"):
        # Find first newline after fence and last fence
        first_nl = text.find("\n")
        if first_nl > 0:
            inner = text[first_nl + 1 :]
            if inner.rstrip().endswith("```"):
                inner = inner.rstrip()[:-3]
            return inner.strip()
    return text


def validate_and_parse(
    opus_output: str, catalog: list[dict[str, Any]]
) -> dict[str, Any]:
    """Validate Opus output against legacy kb/wiki/SCHEMA.md citation contract.

    Contract:
    - Must start with `---` YAML frontmatter
    - Frontmatter has 5 required fields
    - `sources:` is a list of strings `article:<10-char-hex>`
    - Body has at least one `^[article:<hex>]` inline citation
    - Every body citation hash is in the catalog's article entries
    - (Web/builtin go in `## Further Reading` body section, not validated here)

    Returns: {"post": Post|None, "errors": [...], "hashes_cited": [...]}
    """
    errors: list[str] = []
    text = _strip_code_fences(opus_output)

    if not text.startswith("---"):
        errors.append("output does not start with YAML frontmatter `---`")
        return {"post": None, "errors": errors, "hashes_cited": []}

    try:
        post = frontmatter.loads(text)
    except Exception as e:
        errors.append(f"frontmatter parse failed: {type(e).__name__}: {e}")
        return {"post": None, "errors": errors, "hashes_cited": []}

    required = {"title", "created", "last_updated", "sources", "confidence_level"}
    missing = required - set(post.metadata.keys())
    if missing:
        errors.append(f"missing frontmatter fields: {sorted(missing)}")

    # Frontmatter sources must be list of strings 'article:<hex>'
    fm_sources = post.metadata.get("sources") or []
    fm_hashes: set[str] = set()
    for s in fm_sources:
        if isinstance(s, str) and s.startswith("article:"):
            fm_hashes.add(s.split(":", 1)[1])

    # Catalog article hashes (the trusted list — Opus must not exceed it)
    catalog_article_hashes = {s["ref"] for s in catalog if s["type"] == "article"}

    # Body citations
    body = post.content
    body_hashes_list = WIKI_LEGACY_CITATION_RE.findall(body)
    body_hashes = sorted(set(body_hashes_list))

    if not catalog_article_hashes:
        # Edge case: no article sources available — page is web/builtin only.
        # Allow zero inline citations but require confidence_level=low.
        if body_hashes:
            errors.append(
                f"body cites article hashes but no articles in catalog: {body_hashes[:5]}"
            )
        if str(post.metadata.get("confidence_level", "")).lower() != "low":
            errors.append("zero-article page must declare confidence_level: low")
    else:
        if not body_hashes:
            errors.append("no ^[article:<hash>] citations in body")
        # Every body hash must be in catalog (Opus didn't hallucinate)
        for h in body_hashes:
            if h not in catalog_article_hashes:
                errors.append(f"^[article:{h}]: hash not in available catalog")

    # Frontmatter sources must include every body-cited hash
    orphans = [h for h in body_hashes if h not in fm_hashes]
    if orphans:
        errors.append(
            f"body cites hashes not declared in frontmatter sources: {orphans[:5]}"
        )

    return {
        "post": post if not errors else None,
        "errors": errors,
        "hashes_cited": body_hashes,
    }


# ----------------------------------------------------------------------------- per-entity


async def generate_one_entity(
    *,
    entity_name: str,
    output_dir: Path,
    log_path: Path,
    chunk_article_map: dict[str, dict[str, str]],
    lightrag_dir: Path,
    tavily_api_key: str,
    today: date,
    dry_run: bool,
    max_retries: int = 2,
) -> dict[str, Any]:
    slug = _slugify(entity_name)
    out_path = output_dir / f"{slug}.md"
    t0 = time.monotonic()

    if dry_run:
        return {
            "status": "ok",
            "slug": slug,
            "path": str(out_path),
            "sources": 0,
            "confidence": "dry-run",
            "errors": [],
            "wallclock_s": 0.0,
        }

    # === Source 1: LightRAG corpus context ===
    try:
        lightrag_ctx = await fetch_lightrag_context(entity_name)
    except Exception as e:
        logger.warning(
            "[%s] LightRAG aquery failed: %s: %r; using vdb fallback",
            slug, type(e).__name__, str(e) or "<empty msg>",
        )
        lightrag_ctx = ""

    chunk_ids = sorted(set(CHUNK_ID_RE.findall(lightrag_ctx)))
    if not chunk_ids:
        # Fallback: pull entity's source chunks directly from vdb_entities.json
        _, chunk_ids = _entity_chunks_from_vdb(entity_name, lightrag_dir)
        logger.info("[%s] LightRAG ctx had no chunk-ids; vdb fallback found %d", slug, len(chunk_ids))

    # === Source 2: Tavily web search ===
    tavily_results = fetch_tavily_results(entity_name, tavily_api_key) if tavily_api_key else []
    logger.info("[%s] LightRAG ctx %d chars / %d chunks · Tavily %d hits",
                slug, len(lightrag_ctx), len(chunk_ids), len(tavily_results))

    # === Build source catalog ===
    catalog = build_source_catalog(
        chunk_ids=chunk_ids,
        chunk_article_map=chunk_article_map,
        tavily_results=tavily_results,
    )
    if not catalog:
        return {
            "status": "failed",
            "slug": slug,
            "path": None,
            "sources": 0,
            "confidence": "n/a",
            "errors": ["empty source catalog (no LightRAG chunks resolved + no Tavily results)"],
            "wallclock_s": round(time.monotonic() - t0, 1),
        }

    prompt = build_opus_prompt(
        entity_name=entity_name,
        lightrag_context=lightrag_ctx,
        tavily_results=tavily_results,
        catalog=catalog,
        today=today,
    )

    # === Source 3 + synthesizer: Opus 4.7 ===
    debug_path = output_dir.parent / "_debug" / f"{slug}-opus.md"
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    (output_dir.parent / "_debug" / f"{slug}-prompt.txt").write_text(prompt, encoding="utf-8")

    last_errors: list[str] = []
    final_post = None
    for attempt in range(1, max_retries + 2):
        try:
            opus_output = call_opus(prompt)
        except Exception as e:
            last_errors = [f"Opus call raised: {type(e).__name__}: {e}"]
            logger.warning("[%s] attempt %d Opus call failed: %s", slug, attempt, last_errors[0])
            if attempt > max_retries:
                break
            await asyncio.sleep(3)
            continue

        try:
            debug_path.write_text(opus_output, encoding="utf-8")
        except Exception:
            pass

        result = validate_and_parse(opus_output, catalog)
        if not result["errors"]:
            final_post = result["post"]
            last_errors = []
            break

        last_errors = result["errors"]
        logger.warning("[%s] attempt %d validation failed: %s", slug, attempt, last_errors[:3])
        if attempt > max_retries:
            break
        await asyncio.sleep(2)

    if final_post is None:
        return {
            "status": "failed",
            "slug": slug,
            "path": None,
            "sources": 0,
            "confidence": "n/a",
            "errors": last_errors,
            "wallclock_s": round(time.monotonic() - t0, 1),
        }

    # Write atomically
    page_text = frontmatter.dumps(final_post)
    _atomic_write(out_path, page_text)

    n_sources = len(final_post.metadata.get("sources") or [])
    confidence = final_post.metadata.get("confidence_level", "medium")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(
            f"- {today.isoformat()} — generated entities/{slug}.md "
            f"(sources: {n_sources}, confidence: {confidence})\n"
        )

    return {
        "status": "ok",
        "slug": slug,
        "path": str(out_path),
        "sources": n_sources,
        "confidence": confidence,
        "errors": [],
        "wallclock_s": round(time.monotonic() - t0, 1),
    }


# ----------------------------------------------------------------------------- main


def _rebuild_index(wiki_root: Path) -> None:
    index_path = wiki_root / "index.md"
    sections: list[str] = ["# Wiki Index", ""]
    sections.append(
        "Auto-generated. Re-run `scripts/wiki_generate_pages.py` to refresh."
    )
    sections.append("")
    for subdir in ("entities", "concepts", "comparisons", "queries"):
        d = wiki_root / subdir
        if not d.exists():
            continue
        files = sorted(d.glob("*.md"))
        if not files:
            continue
        sections.append(f"## {subdir.title()}")
        sections.append("")
        for f in files:
            try:
                post = frontmatter.load(f)
                title = post.get("title") or f.stem
            except Exception:
                title = f.stem
            sections.append(f"- [{title}]({subdir}/{f.name})")
        sections.append("")
    _atomic_write(index_path, "\n".join(sections).rstrip() + "\n")


async def run(args: argparse.Namespace) -> int:
    cost_gate_path = Path(args.cost_gate).resolve()
    selection_path = Path(args.entities).resolve()
    output_dir = Path(args.output_dir).resolve()
    wiki_root = output_dir.parent
    log_path = wiki_root / "log.md"

    _verify_cost_gate(cost_gate_path)
    all_entities = _parse_selection(selection_path)
    entities_to_run = [args.smoke] if args.smoke else all_entities

    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not tavily_key and not args.dry_run:
        logger.warning("TAVILY_API_KEY unset — proceeding with corpus + builtin only")

    db_path = _resolve_db_path()
    lightrag_dir = _resolve_lightrag_dir()
    logger.info("LightRAG dir: %s · SQLite: %s", lightrag_dir, db_path)

    chunk_article_map = _build_chunk_article_map(lightrag_dir, db_path)
    logger.info("chunk→article map size: %d", len(chunk_article_map))

    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today()

    results: list[dict[str, Any]] = []
    for ent in entities_to_run:
        slug = _slugify(ent)
        target = output_dir / f"{slug}.md"
        if args.skip_existing and target.exists():
            # Treat as already-done: still parse for the summary tally
            try:
                post = frontmatter.load(target)
                results.append({
                    "status": "ok",
                    "slug": slug,
                    "path": str(target),
                    "sources": len(post.metadata.get("sources") or []),
                    "confidence": post.metadata.get("confidence_level", "?"),
                    "errors": [],
                    "wallclock_s": 0.0,
                })
                logger.info("[%s] skip-existing (page already present)", slug)
                continue
            except Exception:
                pass  # fall through to regen on parse failure
        logger.info("=== generating: %s ===", ent)
        res = await generate_one_entity(
            entity_name=ent,
            output_dir=output_dir,
            log_path=log_path,
            chunk_article_map=chunk_article_map,
            lightrag_dir=lightrag_dir,
            tavily_api_key=tavily_key,
            today=today,
            dry_run=args.dry_run,
        )
        results.append(res)
        logger.info(
            "[%s] status=%s sources=%d confidence=%s wallclock=%ss",
            res["slug"], res["status"], res["sources"], res["confidence"], res["wallclock_s"],
        )

    if not args.dry_run and not args.smoke:
        _rebuild_index(wiki_root)
        logger.info("rebuilt %s", wiki_root / "index.md")

    written = sum(1 for r in results if r["status"] == "ok")
    failed = sum(1 for r in results if r["status"] == "failed")
    print()
    print("=" * 70)
    print(f"SUMMARY: {written} written / {failed} failed / {len(results)} total")
    for r in results:
        marker = "✓" if r["status"] == "ok" else "✗"
        print(
            f"  {marker} {r['slug']:30s} src={r['sources']:>3} "
            f"conf={r['confidence']:<6} t={r['wallclock_s']}s"
        )
    print("=" * 70)
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(description="Generate wiki pages from LightRAG + Tavily + Opus 4.7")
    p.add_argument("--entities", required=True, help="Path to selection .md file")
    p.add_argument("--cost-gate", required=True, help="Cost-estimate .md (must have approved: yes)")
    p.add_argument("--output-dir", default="kb/wiki/entities/", help="Output dir")
    p.add_argument("--smoke", default=None, help="Run only this one entity")
    p.add_argument("--dry-run", action="store_true", help="No real LLM/network calls")
    p.add_argument(
        "--skip-existing", action="store_true",
        help="Skip entities whose page already exists (default: regenerate)"
    )
    args = p.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

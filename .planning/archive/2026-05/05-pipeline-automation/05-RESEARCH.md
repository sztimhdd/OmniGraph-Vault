# Phase 5: pipeline-automation - Research

**Researched:** 2026-04-28
**Domain:** LightRAG embedding migration, Gemini embedding-2 multimodal, Gemini Batch API, RSS pipeline
**Confidence:** HIGH (core stack, code paths, OPML source); MEDIUM (rate limits — ai.google.dev unreachable from this machine)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** A new shared module owns `embedding_func` as single source of truth. Planner picks exact path (`config/embedding.py` or `lightrag_embedding.py`). All 6 duplicate files import from it.
- **D-02:** Model name configured via env var `EMBEDDING_MODEL` in `~/.hermes/.env`. Rollback = one-line change.
- **D-03:** Consolidation is in-scope for Wave 0. Migration and dedup happen together.
- **D-04:** In-band multimodal. New `embedding_func` fetches image bytes when a chunk contains `http://localhost:8765/...` URL. Text + `inline_data` sent as one `embed_content` call. LightRAG contract `(texts: list[str]) -> np.ndarray` unchanged.
- **D-05:** Gemini-2 task prefix formatting lives inside the wrapper. Documents get `title: none | text: {chunk}`, queries get `task: search result | query: {content}`. Wrapper distinguishes query vs document paths.
- **D-06:** Wave 0b catch-up uses Gemini Batch API (50% cheaper, ~24hr). Wave 0 18-doc re-embed uses sync API.
- **D-07:** Uniform enrichment contract (depth_score >= 2) for all RSS articles regardless of language.
- **D-08:** EN→CN translation inside `extract_questions` prompt — one-step LLM call.
- **D-09:** English RSS body fully translated to Chinese before LightRAG ingest. Reconsiderable post-Wave-0 benchmark if cross-language retrieval proves strong enough.
- **D-10:** Ingestion filter = keyword match AND `depth_score >= 2`. Keywords: `{openclaw, hermes, agent, harness}`.
- **D-11:** Catch-up re-runnable as keyword scope grows. `batch_ingest_from_spider.py` extended for multi-keyword.
- **D-12:** Classification runs first over all 302 articles, populates `classifications` table before filtering.
- **D-13:** Wave 0b fires immediately after 18-doc re-embed passes Wave 0 success criteria.
- **D-14:** Single Gemini Batch API submission for filtered subset. Re-run with `--from-db` for failure recovery.
- **D-15 (= Phase 4 D-04/05/06):** All Phase 5 code on remote WSL host. Dev box edit-only.
- **D-16 (= Phase 4 D-01):** Cron follows "Hermes drives" — cron invokes Hermes skills which shell to Python helpers.
- **D-17 (= Phase 4 D-14):** LightRAG delete-by-id + re-ainsert path proven in Phase 4. Reused verbatim for 18-doc re-embed.
- **D-18 (= Phase 4 D-13):** Telegram delivery path proven. Daily digest + cron failure alerts reuse it.

### Claude's Discretion

- Exact path and name of the shared embedding module.
- Whether query-side embedding uses `embed_query` function or `is_query=True` kwarg.
- Exact CLI shape for multi-keyword filtering in `batch_ingest_from_spider.py`.
- Daily digest empty-state behavior on light days.
- OPML source strategy (bundle in-repo vs fetch-from-gist with local cache).
- Cron failure alerting threshold.
- Embedding benchmark golden-query set design.
- Sync fallback path if Batch API submission is rejected.
- Chunked vs single-batch fallback if batch request exceeds API limit.

### Deferred Ideas (OUT OF SCOPE)

- Image-as-query cross-modal (text-query → image chunks is in scope; image-as-query is NOT).
- Image-to-image similarity.
- Cross-language retrieval benchmark elimination of D-09 (reconsider in follow-up phase).
- `kg_synthesize` refactor for Agentic RAG.
- Additional RSS sources beyond Karpathy's 92.
- Per-question retry state for RSS enrichment.
- Vertex AI `multimodalembedding@001`.
- Streaming/realtime RSS ingest.
- Web digest UI.
- Sources beyond Zhihu for enrichment.
</user_constraints>

---

## Summary

Phase 5 delivers an unattended daily pipeline atop a mandatory embedding migration. The research closes three critical unknowns from CONTEXT.md and resolves seven supporting questions. The most important findings are:

**LightRAG embedding call shape:** LightRAG uses a single `embedding_func(texts: list[str]) -> np.ndarray` for BOTH document upserts and query-time retrievals. There is no `is_query` flag, no two-function variant, and no kwargs differentiation. The distinction must be implemented as a detection heuristic inside the wrapper. The most reliable heuristic available is tracking call-site context via a module-level flag set before each LightRAG call type, or using input count/length heuristics. The planner MUST choose one approach (see Pattern 1 below).

**Gemini Batch API:** Fully available in `google-genai` v1.73.1 (already installed) via `client.batches.create_embeddings()`. Marked experimental; works with file-based JSONL input via `EmbeddingsBatchJobSource(file_name=...)` or inline `EmbedContentBatch` requests. Standard poll → retrieve pattern. Available only on Gemini Developer API (not Vertex AI). Tier requirement for batch is UNKNOWN (ai.google.dev rate-limits page unreachable from this machine); two official cookbook notebooks explicitly note "requires paid tier rate limits to run properly."

**OPML source:** Confirmed accessible. Exactly 92 RSS feeds (all `type="rss"`). OPML 2.0 format, 2-level nesting (one `<outline text="Blogs">` container wrapping all 92 feeds). All five PRD-listed representative feeds confirmed present. Recommended strategy: bundle versioned snapshot in-repo at `data/karpathy_hn_2025.opml` (already referenced in PRD gate 2 test).

**NanoVectorDB dim binding:** Changing `embedding_dim` from 768 to any new value (1536, 3072) triggers an `AssertionError` on startup if existing JSON storage files are present. The storage files MUST be deleted before changing dims. This means Wave 0 cannot use delete-by-id + re-ainsert for a dim change — it must wipe `lightrag_storage/vdb_*.json` files, then re-insert all 18 docs fresh. For same-dim (768 → 768 with new model), delete-by-id + re-ainsert remains valid per Phase 4 D-17.

**Recommendation:** Use `embedding_dim=768` for gemini-embedding-2 (same as current -001 value) to preserve the Phase 4-proven delete-by-id + re-ainsert path. The quality gain from 1536/3072 is unverified and migration complexity increases significantly with a dim change. Re-evaluate at Wave 0 benchmark time if Chinese retrieval regresses.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| google-genai | 1.73.1 (installed) | Gemini embedding + batch API | Project standard; already installed; has `batches.create_embeddings()` |
| lightrag | (installed) | Knowledge graph engine | Phase 1-4 foundation |
| feedparser | 6.0.12 (PyPI latest) | RSS/Atom feed parsing | Project-chosen (PRD §3.1.2); stdlib-grade maturity |
| langdetect | 1.0.x (PyPI) | Language detection for RSS pre-filter | Project-chosen (PRD §6 new deps) |
| sqlite3 | stdlib | RSS schema + KOL schema | Already used throughout; no new dep |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| xml.etree.ElementTree | stdlib | OPML parsing | No extra dep; OPML is simple XML |
| requests | (installed) | RSS HTTP fetch + image download | Already in requirements.txt |
| numpy | (installed) | Embedding array ops | Already used in embedding_func |
| asyncio | stdlib | Async embedding calls | Used throughout |

### Not Needed (Clarification)

- `lancedb` — not used by current LightRAG installation. Vector storage is `NanoVectorDB` (JSON files). No lancedb interaction required.
- `sentence-transformers` — out of scope; local embedding was a deferred alternative for quota issues.

**Installation (new deps only):**
```bash
# Remote WSL host:
venv/bin/pip install feedparser langdetect
```

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
enrichment/
├── rss_fetch.py          # OPML parse + feed fetch + dedup → rss_articles
├── rss_classify.py       # LLM depth classification → rss_classifications
├── rss_ingest.py         # depth>=2 RSS → enrich pipeline → LightRAG
├── orchestrate_daily.py  # step-by-step state machine for full daily run
└── daily_digest.py       # TOP-N selector + Telegram Markdown formatter

lightrag_embedding.py     # NEW: shared embedding module (D-01)
                          # or config/embedding.py — planner picks

data/
└── karpathy_hn_2025.opml # OPML snapshot (bundle in-repo, D-02 discretion)

docs/spikes/
└── embedding-002-contract.md  # Wave 0 spike output (go/no-go)
```

### Pattern 1: LightRAG Query vs Document Call Discrimination

**What:** LightRAG calls `embedding_func(texts: list[str])` identically for both document upsert and query-time search. There is NO `is_query` kwarg, NO separate function registration, and NO call signature variation (confirmed by inspecting `nano_vector_db_impl.py:123` for upsert and `operate.py:3639` for query).

**The distinction that exists in LightRAG:** Query calls pass `_priority=5` kwarg (higher priority for queue management). Document upsert calls do NOT pass `_priority`. This is the only detectable difference at the function call level.

**Recommended approach (Claude's discretion):** Use a `_priority` kwarg detection heuristic. When `_priority=5` is present in `**kwargs`, apply the query prefix; otherwise apply the document prefix. This is stable and non-intrusive.

**Alternative:** Module-level context flag (`_current_embed_mode: Literal["document", "query"] = "document"`). Safe for single-process use (which this is) but requires two module-level helpers (`set_embed_mode_query()`, `set_embed_mode_document()`) called before each LightRAG init.

**When to use:** Always, for gemini-embedding-2 only. The prefix is required for optimal RAG performance per official docs.

**Code example (verified from official cookbook and code inspection):**
```python
# Source: lightrag/kg/nano_vector_db_impl.py:152-153 (query path uses _priority=5)
#         lightrag/kg/nano_vector_db_impl.py:123 (upsert path has no _priority)

@wrap_embedding_func_with_attrs(
    embedding_dim=768,          # Keep 768 to avoid NanoVectorDB dim mismatch
    send_dimensions=True,
    max_token_size=8192,        # gemini-embedding-2 supports up to 8192 tokens
    model_name="gemini-embedding-2",
)
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    is_query = kwargs.get("_priority") == 5  # LightRAG query path signals priority=5
    model = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-2")
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    processed_texts = []
    image_parts_map = {}  # index → Part for inline_data

    for i, text in enumerate(texts):
        # In-band multimodal: detect image URL, fetch bytes, build Part
        image_url_match = re.search(r'http://localhost:8765/\S+\.(?:jpg|jpeg|png)', text)
        if image_url_match:
            img_url = image_url_match.group(0)
            try:
                resp = requests.get(img_url, timeout=5)
                image_parts_map[i] = types.Part.from_bytes(
                    data=resp.content, mime_type="image/jpeg"
                )
                text = text.replace(img_url, "")  # strip URL from text part
            except Exception:
                pass  # degrade gracefully to text-only

        # Apply task prefix per D-05
        if is_query:
            prefix = f"task: search result | query: "
            processed_texts.append(prefix + text)
        else:
            prefix = f"title: none | text: "
            processed_texts.append(prefix + text)

    # Build contents: if image present for item i, aggregate text+image into one Part list
    # Otherwise send as plain string batch
    # ... (see Code Examples section for full shape)
    response = await client.aio.models.embed_content(
        model=model,
        contents=processed_texts,  # simplified; see multimodal shape below
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
    embeddings = np.array([np.array(e.values, dtype=np.float32)
                           for e in response.embeddings])
    # L2 normalize (required for dim < 3072, per LightRAG gemini.py:579-584)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return embeddings / norms
```

### Pattern 2: Gemini Batch API for Wave 0b

**What:** Submit a single embedding batch job for the filtered KOL articles. Uses `client.batches.create_embeddings()` (available in v1.73.1, marked experimental). Polls every 30s; results in output JSONL file via Files API.

**When to use:** Wave 0b only (50% cost savings, async overnight). Live RSS ingestion in Waves 1+ uses sync API.

**Code shape (verified from local SDK source + official cookbook):**
```python
# Source: venv/Lib/site-packages/google/genai/batches.py + Batch_mode.ipynb

from google import genai
from google.genai import types
import json, time

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Option A: inline (for smaller batches, e.g., 18-doc re-embed dry run)
src = types.EmbeddingsBatchJobSource(
    inlined_requests=types.EmbedContentBatch(
        contents=["text chunk 1", "text chunk 2", ...],
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
)

# Option B: file-based JSONL (recommended for Wave 0b ≥ 50 articles)
# JSONL format: each line = {"key": "req_N", "request": {"output_dimensionality": 768, "content": {"parts": [{"text": "..."}]}}}
# Upload via client.files.upload(file="batch_input.jsonl", config=types.UploadFileConfig(mime_type="jsonl"))
src = types.EmbeddingsBatchJobSource(
    file_name=uploaded_file.name  # e.g., "files/abc123"
)

batch_job = client.batches.create_embeddings(
    model="gemini-embedding-2",
    src=src,
    config=types.CreateEmbeddingsBatchJobConfig(display_name="wave0b-kol-catchup"),
)

# Polling loop (max 24h per SLO)
while True:
    batch_job = client.batches.get(name=batch_job.name)
    if batch_job.state.name in ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
        break
    time.sleep(30)

# Result retrieval
if batch_job.state.name == "JOB_STATE_SUCCEEDED":
    file_bytes = client.files.download(file=batch_job.dest.file_name)
    for line in file_bytes.decode("utf-8").splitlines():
        result = json.loads(line)
        # result["key"] → correlates to input; result["response"]["embeddings"][0]["values"]
```

**CRITICAL WARNING:** `batches.create_embeddings()` is marked `ExperimentalWarning` in the SDK. Test on the remote WSL host with a 1-item batch before committing to Wave 0b. If it fails with 403/permission error, fall back to sync API with per-article rate limiting.

### Pattern 3: NanoVectorDB Dim Change Requires Storage Wipe

**What:** NanoVectorDB (`nano_vectordb/dbs.py:72-74`) asserts `storage["embedding_dim"] == self.embedding_dim` on startup. Changing `embedding_dim` without deleting storage files triggers `AssertionError`.

**When to use:** Only relevant if planner chooses to change embedding_dim (e.g., 768 → 1536).

**If staying at 768 (recommended):** Phase 4 delete-by-id + re-ainsert path (D-17) remains fully valid. Delete the 18 docs by ID, change the model env var, re-ainsert. The JSON files remain intact.

**If changing dim (NOT recommended for Wave 0):**
1. Stop Hermes.
2. Delete `~/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json` (3 files: entities, relationships, chunks).
3. Keep `~/.hermes/omonigraph-vault/lightrag_storage/*.graphml` and KV JSON files (they are unaffected by dim change).
4. Re-ingest all 18 docs.

### Pattern 4: In-Band Multimodal Embedding (D-04)

**What:** When a text chunk contains `http://localhost:8765/<hash>/<i>.jpg`, the embedding function fetches the image bytes and sends text + image as a single aggregated embedding via `embed_content`. A single `contents` array with multiple parts (text string + `types.Part.from_bytes(...)`) produces ONE aggregated embedding per the official cookbook (Cell 21-22: "Submitting multiple parts within a single content entry produces one aggregated embedding").

**Code shape (verified from cookbook Cell 22):**
```python
# Source: google-gemini/cookbook Embeddings.ipynb Cell 22
result = client.models.embed_content(
    model="gemini-embedding-2",
    contents=[
        "The system architecture diagram shows...",  # text with URL stripped
        types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/jpeg",
        ),
    ]
)
# result.embeddings has ONE embedding (aggregated text + image)
```

**Constraint:** Up to 6 images per request, 8192 total input tokens. The wrapper must iterate texts in batches and handle the multimodal aggregation per item.

**Impact on `describe_images`:** `image_pipeline.describe_images()` generates HUMAN-READABLE text descriptions of images (for appending to `final_content.md`). It is NOT replaced by multimodal embedding. After Phase 5, `describe_images` still runs for the WeChat ingest path to produce the Markdown description that gets stored to disk. The embedding function uses image bytes INDEPENDENTLY for graph indexing. Both paths continue to exist.

### Pattern 5: OPML Parsing

**What:** `karpathy_hn_2025.opml` is OPML 2.0 with exactly 92 `type="rss"` feeds in 2-level nesting (root `<body>` → one `<outline text="Blogs">` → 92 `<outline type="rss" ...>`). Standard `xml.etree.ElementTree` parses it; no OPML library needed.

```python
# Verified OPML structure (confirmed 2026-04-28 via GitHub Gist API)
import xml.etree.ElementTree as ET

def parse_opml(path: str) -> list[dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    feeds = []
    for outline in root.findall(".//outline[@type='rss']"):
        feeds.append({
            "name": outline.get("text"),
            "xml_url": outline.get("xmlUrl"),
            "html_url": outline.get("htmlUrl"),
        })
    return feeds
# Returns 92 feeds (confirmed)
```

### Anti-Patterns to Avoid

- **Changing embedding_dim without wiping vdb_*.json:** Triggers AssertionError at LightRAG startup. Check dim first, wipe files if needed.
- **Using task_type param for gemini-embedding-2:** The `task_type` parameter in `EmbedContentConfig` is NOT supported for gemini-embedding-2 (confirmed by official cookbook Cell 44 and Cell 48 comment). Use prompt prefixes only.
- **Passing `_priority` kwarg to gemini API:** `_priority` is LightRAG-internal queue management. It must be consumed by the wrapper and NOT forwarded to `embed_content`.
- **Single-function batch mixing query and document texts:** LightRAG batches multiple texts in a single `embedding_func` call (batch_num=20). All texts in one call have the same call-site context (all query OR all document). Do not apply mixed prefixes within one batch.
- **Running batch ingest without classifying first:** `classifications` table is currently empty (STATE.md). Wave 0b depends on D-12: run `batch_classify_kol.py` first.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RSS/Atom parsing | Custom XML parser | `feedparser` 6.0.12 | Handles RSS 0.9x/1.0/2.0/Atom 0.3/1.0, edge cases, malformed feeds |
| OPML parsing | Custom OPML lib | `xml.etree.ElementTree` (stdlib) | OPML is simple XML; no extra dep needed |
| Language detection | Charset/heuristic | `langdetect` 1.0 | Statistical model, 55+ languages, works offline |
| Embedding batch job | Custom REST calls | `client.batches.create_embeddings()` | Already in installed google-genai v1.73.1 |
| Vector storage dim check | Manual assertion | NanoVectorDB startup assertion | Already enforced; just handle the pre-conditions |

**Key insight:** The RSS stack is almost entirely expressible with existing `requests` + `feedparser` + stdlib. No new HTTP clients needed.

---

## Runtime State Inventory

> Included because Wave 0 involves changing the embedding model, which affects persisted vector data.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | NanoVectorDB JSON files: `~/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json`, `vdb_entities.json`, `vdb_relationships.json` — each stores `embedding_dim: 768` and all 18-doc vectors | If dim stays 768: delete-by-id + re-ainsert (D-17). If dim changes: wipe all 3 vdb_*.json files, re-ingest 18 docs. |
| Stored data | `classifications` table in `data/kol_scan.db` — currently empty (STATE.md). Must be populated before Wave 0b filter can run. | Run `batch_classify_kol.py` in Wave 0b Step 1 (D-12). |
| Stored data | `ingestions` table — contains dedup records for the 18 already-ingested docs. | These records must be cleared or the re-ainsert will be skipped as "already ingested". Check `ingest_from_db` dedup logic before running re-embed. |
| Live service config | Hermes cron jobs `rss-fetch`, `rss-classify`, `daily-classify-kol`, `daily-enrich`, `daily-ingest`, `daily-digest` — don't exist yet; created in Wave 3. | Register via `hermes cronjob add` in Wave 3 plan. |
| Live service config | Existing Hermes cron jobs `scan_kol` (df7dc3fa0390), `health_check` (e7afccd9931b) — already registered on remote. | No action; carry forward unchanged. |
| OS-registered state | None found. | None — verified by code inspection. |
| Secrets/env vars | `EMBEDDING_MODEL` env var — NEW, does not exist yet in `~/.hermes/.env`. Must be added before Wave 0 runs. `cognee_wrapper.py:27` sets `os.environ["EMBEDDING_MODEL"] = "gemini-embedding-001"` — must update in lockstep (D-03). | Add `EMBEDDING_MODEL=gemini-embedding-2` to `~/.hermes/.env`. Update `cognee_wrapper.py:27`. |
| Build artifacts | `venv/` on remote WSL — must have `feedparser` and `langdetect` installed (not currently in requirements.txt for these). | `venv/bin/pip install feedparser langdetect` during Wave 1 setup. |

---

## Common Pitfalls

### Pitfall 1: NanoVectorDB Embedding Dim Assertion Failure
**What goes wrong:** Changing `embedding_dim` in `wrap_embedding_func_with_attrs` while existing `vdb_*.json` files have `embedding_dim: 768` causes `AssertionError: Embedding dim mismatch, expected: 1536, but loaded: 768` at LightRAG startup.
**Why it happens:** `nano_vectordb/dbs.py:72-74` asserts dim equality on every init.
**How to avoid:** Keep `embedding_dim=768` for Wave 0 (recommended). If a higher dim is chosen, delete all three `vdb_*.json` files before first run with new dim.
**Warning signs:** `AssertionError` during LightRAG `__post_init__`. Usually surfaces in the first `await rag.ainsert()` or `await rag.aquery()` call.

### Pitfall 2: Gemini Batch API Paid-Tier Requirement
**What goes wrong:** `client.batches.create_embeddings()` returns 403 or quota error on a free-tier API key.
**Why it happens:** Multiple official cookbook notebooks (Embeddings_REST.ipynb Cell 3, haystack cross-modal notebook Cell 4) explicitly note "requires paid tier rate limits to run properly."
**How to avoid:** Test with a 1-item inline batch BEFORE building the full Wave 0b pipeline. If 403: fall back to sync API with per-embedding `asyncio.sleep(1.0)` rate limiting (same pattern as Phase 4's 100-RPM guard on -001).
**Warning signs:** HTTP 403 or `google.api_core.exceptions.PermissionDenied` on `batches.create_embeddings()`.

### Pitfall 3: task_type Parameter Not Supported for gemini-embedding-2
**What goes wrong:** Passing `config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")` to `embed_content` with `model="gemini-embedding-2"` may silently ignore or error.
**Why it happens:** Official cookbook Cell 44 explicitly states "With gemini-embedding-2, the task_type parameter is not supported. Instead, you should include task instructions directly in the prompt." The Haystack integration notebook appears to pass `task_type` in config but that may be a Haystack abstraction that converts it to a prompt prefix internally.
**How to avoid:** Use prompt prefixes (`"task: search result | query: {text}"`) not `task_type` param. Never forward `task_type` to `embed_content` for `-2`.
**Warning signs:** Embeddings appear to work but retrieval quality is degraded (no cross-modal benefit); or API returns error about unsupported parameter.

### Pitfall 4: Ingestion Dedup Blocking Re-Embed
**What goes wrong:** After Wave 0 re-embed, `ingest_from_db` skips all 18 docs because `ingestions` table already has `status=ok` for them.
**Why it happens:** `ingest_from_db:562` excludes `article_id IN (SELECT article_id FROM ingestions WHERE status = 'ok')`.
**How to avoid:** Wave 0 re-embed script must use `rag.adelete_by_doc_id()` + `rag.ainsert()` directly (not `ingest_from_db`). The ingestion record stays intact (no need to wipe it) — only the LightRAG vector storage needs refreshing.
**Warning signs:** "No passed articles found" message during re-embed run.

### Pitfall 5: `_priority` Kwarg Forwarded to Gemini API
**What goes wrong:** LightRAG wraps the embedding function with `priority_limit_async_func_call` which injects `_priority` kwarg. If the wrapper naively forwards `**kwargs` to `embed_content`, the Gemini SDK throws `TypeError: unexpected keyword argument _priority`.
**Why it happens:** LightRAG's queue mechanism passes `_priority=5` to signal higher priority for query calls. It's an internal kwarg, not a Gemini API parameter.
**How to avoid:** Pop `_priority` from kwargs before calling `embed_content`: `is_query = kwargs.pop("_priority", None) == 5`.
**Warning signs:** `TypeError` on first `rag.aquery()` call.

### Pitfall 6: RSS Feed Timeout Blocking Full Fetch
**What goes wrong:** One slow feed (30s timeout) blocks subsequent feeds if run synchronously.
**Why it happens:** `feedparser.parse()` is synchronous; 92 feeds × potential 30s = up to ~46 min.
**How to avoid:** Run feeds in thread pool with `asyncio.get_event_loop().run_in_executor()`, cap each at 10-15s timeout. PRD §7 specifies "feedparser 超时 30s/feed" — confirm this is per-feed (not total).
**Warning signs:** `rss_fetch.py` run takes > 10 minutes for 92 feeds.

### Pitfall 7: cognee_wrapper EMBEDDING_MODEL Env Var Conflict
**What goes wrong:** `cognee_wrapper.py:27` sets `os.environ["EMBEDDING_MODEL"] = "gemini-embedding-001"` at import time, overwriting the `EMBEDDING_MODEL=gemini-embedding-2` set in `~/.hermes/.env`.
**Why it happens:** cognee_wrapper hardcodes the old model name as an environment override.
**How to avoid:** D-03 requires updating `cognee_wrapper.py:27` in lockstep with the migration.
**Warning signs:** Cognee uses embedding-001 while LightRAG uses embedding-2, causing dual incompatible embedding spaces.

---

## Code Examples

### Verified: gemini-embedding-2 Basic Embed Call

```python
# Source: google-gemini/cookbook quickstarts/Embeddings.ipynb (Cell 15-16)
# Requires google-genai>=1.73.0 (project has 1.73.1)

from google import genai
from google.genai import types

client = genai.Client(api_key=GEMINI_API_KEY)

result = client.models.embed_content(
    model="gemini-embedding-2",
    contents=["text to embed"],
    config=types.EmbedContentConfig(output_dimensionality=768),
)
# result.embeddings[0].values → list of 768 floats
# Default dim is 3072; use output_dimensionality to reduce
```

### Verified: gemini-embedding-2 Multimodal (Text + Image)

```python
# Source: google-gemini/cookbook quickstarts/Embeddings.ipynb (Cell 22)
# One aggregated embedding for text + image

result = client.models.embed_content(
    model="gemini-embedding-2",
    contents=[
        "Description text here",
        types.Part.from_bytes(
            data=image_bytes,   # bytes from file or requests.get()
            mime_type="image/jpeg",  # or "image/png"
        ),
    ],
    config=types.EmbedContentConfig(output_dimensionality=768),
)
# result.embeddings has exactly ONE aggregated embedding
```

### Verified: Batch API for Embeddings

```python
# Source: google-gemini/cookbook quickstarts/Batch_mode.ipynb (Cells 37-45)
# + venv/Lib/site-packages/google/genai/batches.py

import json, time
from google import genai
from google.genai import types

client = genai.Client(api_key=GEMINI_API_KEY)

# Build JSONL file
batch_requests = [
    {"key": f"req_{i}", "request": {
        "output_dimensionality": 768,
        "content": {"parts": [{"text": chunk_text}]}
    }}
    for i, chunk_text in enumerate(text_chunks)
]
with open("batch_embed_input.jsonl", "w") as f:
    for req in batch_requests:
        f.write(json.dumps(req) + "\n")

# Upload
uploaded = client.files.upload(
    file="batch_embed_input.jsonl",
    config=types.UploadFileConfig(mime_type="jsonl"),
)

# Submit
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    batch_job = client.batches.create_embeddings(
        model="gemini-embedding-2",
        src=types.EmbeddingsBatchJobSource(file_name=uploaded.name),
        config=types.CreateEmbeddingsBatchJobConfig(display_name="wave0b-kol"),
    )

# Poll
while True:
    batch_job = client.batches.get(name=batch_job.name)
    if batch_job.state.name in ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
        break
    time.sleep(30)

# Retrieve
if batch_job.state.name == "JOB_STATE_SUCCEEDED":
    file_bytes = client.files.download(file=batch_job.dest.file_name)
    results = [json.loads(line) for line in file_bytes.decode("utf-8").splitlines() if line]
    # results[i]["key"] → "req_N"
    # results[i]["response"]["embeddings"][0]["values"] → list[float]
```

### Verified: `batch_ingest_from_spider.py` Multi-Keyword Extension

Current signature (lines 598-616):
```python
# Current: single --topic-filter string, required with --from-db
parser.add_argument("--topic-filter", type=str, default=None)
# ingest_from_db(args.topic_filter, args.min_depth, args.dry_run)
# SQL: WHERE c.topic = ? AND c.relevant = 1 AND c.depth_score >= ?
```

Extension for multi-keyword (D-11). **Recommended CLI shape:** multi-flag (consistent with existing `batch_classify_kol.py --topic Agent --topic LLM` pattern):
```python
# Extended: multiple --topic-filter flags (match any)
parser.add_argument("--topic-filter", type=str, action="append", dest="topic_filters",
                    metavar="TOPIC", help="Topic to include (repeatable)")
# ingest_from_db(args.topic_filters, args.min_depth, args.dry_run)
# SQL: WHERE c.topic IN ({placeholders}) AND c.relevant = 1 AND c.depth_score >= ?
#      AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `gemini-embedding-001` with `task_type` param | `gemini-embedding-2` with prompt prefixes | 2026 (Gemini API) | No backward compat; embedding spaces incompatible; re-embed required |
| Text-only embeddings | Multimodal (text+image+audio+video+PDF) | 2026 (gemini-embedding-2 launch) | Cross-modal retrieval now possible without Vision pre-processing |
| `task_type="RETRIEVAL_DOCUMENT"` in config | `"title: none | text: {chunk}"` prefix in content | gemini-embedding-2 | Must prefix inside embedding wrapper, not API config |
| LightRAG single `gemini_embed.func` | New custom wrapper (calls SDK directly) | Wave 0 | `gemini_embed` uses `task_type` param, incompatible with -2 |
| 6 duplicated `embedding_func` copies | Single shared module (D-01) | Wave 0 | Easier model swaps; one change point |

**Deprecated/outdated:**
- `gemini_embed.func` from `lightrag.llm.gemini`: Uses `task_type` parameter, incompatible with `-2`. Must be replaced in the new shared module with a direct SDK call. (The function remains in the package but cannot be used for `-2`.)
- `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` task_type values: Still valid for `gemini-embedding-001`; unsupported for `gemini-embedding-2`.

---

## Open Questions

1. **gemini-embedding-2 free-tier RPM/RPD quotas**
   - What we know: Phase 4 blocked on gemini-embedding-001's 100 RPM limit. CONTEXT.md presumes -2 is "more generous." Two official cookbook notebooks note "requires paid tier rate limits to run properly" — suggesting the free tier MAY be more restrictive for batch operations.
   - What's unclear: Exact free-tier RPM for gemini-embedding-2 sync API (could be 100 RPM like -001, or higher). The `ai.google.dev/gemini-api/docs/rate-limits` page was unreachable during research.
   - Recommendation: Wave 0 spike MUST include a quota probe. If free-tier is still 100 RPM, the `-001` throttle code (1.0s min interval) must be preserved in the new wrapper. If higher, relax to 0.2s or remove.
   - **This question must be answered on the remote WSL host during Wave 0 spike before committing to any RPM assumptions.**

2. **Gemini Batch API tier requirement (BLOCKING for D-06/D-14)**
   - What we know: SDK `batches.create_embeddings()` raises `ExperimentalWarning`. Two official cookbook notebooks explicitly say "requires paid tier rate limits." The Batch API in general is documented as available on the Gemini Developer API (non-Vertex).
   - What's unclear: Is batch embeddings specifically blocked for free tier, or just "works best with paid tier"?
   - Recommendation: Test `client.batches.create_embeddings(model="gemini-embedding-2", src=types.EmbeddingsBatchJobSource(inlined_requests=types.EmbedContentBatch(contents=["test"])))` on the remote WSL host immediately. If 403: D-06 and D-14 must fall back to sync API with rate limiting. The planner MUST include this spike as Wave 0 task 0.
   - **CRITICAL: If batch API is unavailable on free tier, D-06 and D-14 need a sync fallback plan.**

3. **`ingest_from_db` dedup interaction with re-embed**
   - What we know: `ingest_from_db` skips articles with existing `status='ok'` ingestion record. The 18 docs re-embedded in Wave 0 have `status='ok'` already.
   - What's unclear: Does the re-embed script bypass `ingest_from_db` entirely (using direct LightRAG API), or does it need to clear the `ingestions` records first?
   - Recommendation: Wave 0 re-embed uses `rag.adelete_by_doc_id()` + `rag.ainsert()` directly via a dedicated script (not `ingest_from_db`). The ingestion records are NOT cleared — they represent "this doc has been ingested" which remains true after re-embed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| google-genai | Embedding + Batch API | Local: yes (test on remote) | 1.73.1 | — |
| feedparser | rss_fetch.py | NOT yet installed (remote venv) | 6.0.12 (PyPI) | Install step in Wave 1 |
| langdetect | rss_fetch.py pre-filter | NOT yet installed (remote venv) | 1.0.x (PyPI) | Install step in Wave 1 |
| GEMINI_API_KEY | All embedding calls | Present in ~/.hermes/.env | — | BLOCKED if absent |
| EMBEDDING_MODEL env var | Shared embedding module | NOT yet in ~/.hermes/.env | — | Add in Wave 0 setup |
| Karpathy OPML gist | rss_fetch.py first run | Accessible (confirmed 2026-04-28) | 92 feeds | Bundle in-repo (recommended) |
| Edge CDP port 9223 | KOL scan (existing) | Present on remote (Phase 4 confirmed) | — | N/A |
| Telegram bot | daily_digest.py | Proven in Phase 4 | — | — |
| `batch_classify_kol.py` | Wave 0b pre-classification | Present in repo | — | — |

**Missing dependencies requiring install steps:**
- `feedparser` + `langdetect`: Wave 1 plan must include `venv/bin/pip install feedparser langdetect && pip freeze > requirements.txt`.

**Blocking unknowns (must be resolved in Wave 0 spike):**
- Gemini Batch API tier availability — test before building Wave 0b pipeline.
- gemini-embedding-2 free-tier RPM — probe before setting throttle interval.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Manual verification scripts (project pattern) — `tests/verify_*.py` |
| Config file | None (no pytest.ini) |
| Quick run command | `ssh remote "cd ~/OmniGraph-Vault && venv/bin/python tests/verify_gate_N.py"` |
| Full suite command | `ssh remote "cd ~/OmniGraph-Vault && venv/bin/python -m pytest tests/ -v"` (if pytest is installed; else run each verify_*.py) |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | Automated Command | Notes |
|-----|----------|-----------|-------------------|-------|
| Wave 0 gate | 18-doc re-embed completes without error | smoke | `venv/bin/python scripts/wave0_reembed.py --dry-run` | New script |
| Wave 0 gate | Chinese retrieval not degraded (5-10 golden queries) | benchmark | `venv/bin/python tests/verify_wave0_benchmark.py` | New; compare top-5 overlap before/after |
| Wave 0 gate | Cross-modal: text query → image chunk | smoke | `venv/bin/python tests/verify_wave0_crossmodal.py` | 1 query "某架构图" → top-5 has ≥1 chunk with image URL |
| Wave 0 gate | `omnigraph_query` / `kg_synthesize.py` / `enrich_article` still function | smoke | existing Phase 4 verify scripts | Run all verify_gate_*.py |
| Wave 0b | Filter correctness: all ingested articles pass keyword+depth | SQL assertion | `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM ingestions i JOIN classifications c..."` | Inline SQL check |
| Wave 1 | OPML parse ≥ 90 feeds | unit | `ssh ... "venv/bin/python -c 'from enrichment.rss_fetch import parse_opml; feeds=parse_opml(\"data/karpathy_hn_2025.opml\"); assert len(feeds)>=90'"` | PRD Gate 1 |
| Wave 1 | RSS fetch first 5 feeds, no crash | smoke | `ssh ... "venv/bin/python enrichment/rss_fetch.py --max-feeds 5 --dry-run"` | PRD Gate 2 |
| Wave 1 | SQLite schema migration idempotent | unit | `ssh ... "venv/bin/python -c 'import sqlite3; c=sqlite3.connect(\"data/kol_scan.db\"); assert \"rss_feeds\" in ...'"` | PRD Gate 3 |
| Wave 2 | Orchestrator dry-run completes all 9 steps | smoke | `ssh ... "venv/bin/python enrichment/orchestrate_daily.py --dry-run --skip-scan"` | PRD Gate 5 |
| Wave 2 | Daily digest generates valid Markdown | unit | `ssh ... "venv/bin/python enrichment/daily_digest.py --date <date> --dry-run"` | PRD Gate 4 |
| Wave 3 | Cron jobs registered on remote Hermes | manual | `hermes cronjob list | grep -E "rss|kol|digest"` | Manual verification |
| Wave 3 | 3-day observation: Telegram digest delivered | manual/observation | Monitor Telegram | 3-day window |

### Benchmark Design (Wave 0 Deliverable)

**Golden-query set:** 5-10 queries covering key topics already in the graph (Phase 4-validated). Minimum design:
- 2 Chinese technical queries (e.g., "Hermes Agent 架构", "OpenClaw 技术栈")
- 2 cross-modal queries (e.g., "LightRAG 架构图", queries expected to surface image chunks)
- 1 English query if any English content exists in graph

**Scoring method:** Top-5 overlap rate. For each query: record top-5 doc IDs before migration, record top-5 after. Pass threshold: ≥ 3 of 5 overlap (60% retention). Cross-modal: at least 1 of top-5 contains an image URL reference.

**Timing:** Run benchmark BEFORE wipe/re-embed (baseline), then AFTER re-embed (comparison). Include benchmark results in `docs/spikes/embedding-002-contract.md`.

### Wave 0 Gaps (New Test Infrastructure Required)

- [ ] `tests/verify_wave0_benchmark.py` — golden-query benchmark; covers Wave 0 retrieval gate
- [ ] `tests/verify_wave0_crossmodal.py` — cross-modal smoke test; covers Wave 0 cross-modal gate
- [ ] `scripts/wave0_reembed.py` — re-embed 18 docs via delete-by-id + re-ainsert; smoke-tested with `--dry-run`
- [ ] `scripts/wave0b_classify_and_ingest.py` (or extend `batch_classify_kol.py`) — Wave 0b classification + filtered ingest

---

## Sources

### Primary (HIGH confidence)
- `venv/Lib/site-packages/lightrag/kg/nano_vector_db_impl.py` — LightRAG upsert path: `embedding_func(batch)` at line 123; query path: `embedding_func([query], _priority=5)` at line 152
- `venv/Lib/site-packages/lightrag/operate.py:3639` — LightRAG query batching: `await actual_embedding_func(texts_to_embed, _priority=5)`
- `venv/Lib/site-packages/nano_vectordb/dbs.py:72-74` — Dim mismatch assert: confirmed hard fail on dim change with existing storage
- `venv/Lib/site-packages/lightrag/llm/gemini.py:464-603` — `gemini_embed` function: confirmed uses `task_type` param, incompatible with gemini-embedding-2
- `venv/Lib/site-packages/google/genai/batches.py` — `create_embeddings()` method: confirmed available, experimental, Gemini Developer API only
- `venv/Lib/site-packages/google/genai/types.py:16731-16760` — `EmbeddingsBatchJobSource`, `EmbedContentBatch` type definitions
- GitHub Gist `emschwartz/e6d2bf860ccc367fe37ff953ba6de66b` (accessed 2026-04-28 via GitHub API) — OPML confirmed: 92 feeds, OPML 2.0, 2-level nesting, all representative feeds present

### Secondary (MEDIUM confidence — verified via official Google cookbook)
- `google-gemini/cookbook quickstarts/Embeddings.ipynb` (accessed 2026-04-28 via GitHub API) — Confirmed: gemini-embedding-2 model name correct; `task_type` unsupported for -2; multimodal via `types.Part.from_bytes()`; aggregated embedding for text+image in single `contents` list; default dim 3072; `output_dimensionality` config supported
- `google-gemini/cookbook quickstarts/Batch_mode.ipynb` (accessed 2026-04-28 via GitHub API) — Confirmed: `client.batches.create_embeddings()` API shape; JSONL format for file-based batches; `EmbeddingsBatchJobSource(file_name=...)` or `inlined_requests`; poll/retrieve pattern; 24hr SLO
- `google-gemini/cookbook quickstarts/rest/Embeddings_REST.ipynb` Cell 3 + `examples/haystack/Gemini_Embedding_Haystack_Crossmodal_Retrieval.ipynb` Cell 4 — Both note "requires paid tier rate limits" for cross-modal/batch embedding

### Tertiary (LOW confidence — needs on-host validation)
- `google-genai` v1.73.1 PyPI metadata — confirmed version installed in project venv
- feedparser 6.0.12 from PyPI — confirmed latest version; not yet installed on remote

---

## Project Constraints (from CLAUDE.md)

- Preserve typo'd runtime dir `~/.hermes/omonigraph-vault/` (not `omnigraph`). All new paths under this dir must use the typo'd name.
- Atomic writes for all new state files: `.tmp` then `os.rename()`. Applies to `canonical_map.json`, digest archives, cron run logs.
- `cognee_wrapper.py` must have Cognee ops non-blocking on ingestion fast-path. Wave 0 embedding changes must not add blocking Cognee calls.
- LLM output never goes directly into the graph. Applies to RSS enrichment output too.
- Entity buffer idempotency: `.processed` marker pattern must be used for any new batch processor (RSS batch classify).
- GSD workflow enforcement: all code changes go through GSD commands, not direct edits.
- Python 3.11+ (remote WSL host). `venv/bin/python` path (Linux), not `venv/Scripts/python`.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions confirmed from PyPI + local venv
- LightRAG embedding call shape: HIGH — directly inspected installed source
- NanoVectorDB dim binding: HIGH — directly inspected installed source
- Batch API shape: HIGH — directly inspected installed SDK + official cookbook
- Gemini task prefix format: HIGH — official cookbook Cell 44 is definitive
- OPML source: HIGH — confirmed via GitHub Gist API 2026-04-28
- Free-tier rate limits: LOW — ai.google.dev unreachable; cookbook hints at paid-tier requirement
- Batch API tier requirement: LOW — cookbook notes suggest paid tier; needs on-host test

**Research date:** 2026-04-28
**Valid until:** 2026-05-28 (LightRAG internals stable; Gemini API may change faster)

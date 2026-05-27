---
phase: 05-pipeline-automation
plan: 00
type: execute
wave: 0
depends_on: []
files_modified:
  - scripts/phase5_wave0_spike.py
  - docs/spikes/embedding-002-contract.md
  - lightrag_embedding.py
  - ingest_wechat.py
  - ingest_github.py
  - kg_synthesize.py
  - multimodal_ingest.py
  - query_lightrag.py
  - cognee_wrapper.py
  - scripts/wave0_reembed.py
  - tests/verify_wave0_benchmark.py
  - tests/verify_wave0_crossmodal.py
  - tests/fixtures/wave0_baseline.json
  - .planning/phases/05-pipeline-automation/05-PRD.md
autonomous: true
requirements: [D-01, D-02, D-03, D-04, D-05, D-06, D-15, D-17]
user_setup:
  - service: gemini
    why: "Verify gemini-embedding-2 multimodal availability on the remote WSL's free-tier key"
    env_vars:
      - name: EMBEDDING_MODEL
        source: "~/.hermes/.env — new var, value 'gemini-embedding-2'"
must_haves:
  truths:
    - "Spike script runs on remote WSL and produces a go/no-go report at docs/spikes/embedding-002-contract.md"
    - "Spike report records Batch API availability (boolean), measured free-tier RPM ceiling, and multimodal smoke test result"
    - "A single shared module lightrag_embedding.py exports embedding_func with in-band multimodal handling at 3072 dim"
    - "All 6 sites that previously defined their own embedding_func now import from lightrag_embedding"
    - "cognee_wrapper.py:27 sets EMBEDDING_MODEL=gemini-embedding-2 in lockstep"
    - "18 existing LightRAG docs are re-embedded via NanoVectorDB wipe + re-ingest from full_docs.json backup (required for 768→3072 dim change)"
    - "Post-migration vdb_chunks.json embedding_dim is 3072"
    - "Wave 0 benchmark passes: ≥60% top-5 overlap on Chinese queries vs baseline, ≥1/5 cross-modal image hit"
    - "PRD §2.4 model name corrected from 'embedding-002' to 'gemini-embedding-2'"
  artifacts:
    - path: "scripts/phase5_wave0_spike.py"
      provides: "Remote-runnable Batch API + RPM + multimodal spike"
      min_lines: 80
    - path: "docs/spikes/embedding-002-contract.md"
      provides: "Go/no-go decision record"
      contains: "batch_api_available:"
    - path: "lightrag_embedding.py"
      provides: "Shared embedding_func with _priority=5 detection and multimodal in-band handling"
      contains: "def embedding_func"
    - path: "scripts/wave0_reembed.py"
      provides: "vdb wipe + re-ingest from full_docs.json backup for all 18 docs (3072-dim migration) with --dry-run, --one-doc, and --i-understand safety gate"
      contains: "vdb_chunks.json"
    - path: "tests/verify_wave0_benchmark.py"
      provides: "Chinese retrieval top-5 overlap assertion (≥60%) for golden queries"
      contains: "top-5 overlap"
    - path: "tests/verify_wave0_crossmodal.py"
      provides: "Cross-modal text→image retrieval assertion (≥1/5 hit)"
      contains: "image"
    - path: "tests/fixtures/wave0_baseline.json"
      provides: "Pre-re-embed top-5 snapshot per golden query"
  key_links:
    - from: "ingest_wechat.py, ingest_github.py, kg_synthesize.py, multimodal_ingest.py, query_lightrag.py"
      to: "lightrag_embedding.py"
      via: "from lightrag_embedding import embedding_func"
      pattern: "from lightrag_embedding import embedding_func"
    - from: "lightrag_embedding.embedding_func"
      to: "google-genai embed_content with output_dimensionality=3072"
      via: "client.aio.models.embed_content"
      pattern: "embed_content"
    - from: "scripts/wave0_reembed.py"
      to: "NanoVectorDB storage wipe + LightRAG ainsert of backup-recovered doc text"
      via: "RESEARCH.md Pattern 3 (dim change requires wipe)"
      pattern: "ainsert"
---

<objective>
Wave 0 gate for Phase 5. Migrate LightRAG embeddings from `gemini-embedding-001` to `gemini-embedding-2` (multimodal) by: (1) running a remote spike to confirm Batch API availability and measured free-tier RPM, (2) consolidating 6 duplicated `embedding_func` sites into a single shared module `lightrag_embedding.py` with in-band multimodal handling and task-prefix routing per D-05, (3) re-embedding the 18 existing LightRAG docs via delete-by-id + re-ainsert, (4) benchmarking Chinese retrieval and cross-modal hits against baseline, (5) fixing PRD §2.4 model name typo.

Purpose: Phase 4 criterion 11/12 are blocked by `-001`'s 100-RPM quota. Every downstream Phase 5 wave assumes the new embedding base is in place and the 18-doc re-embed preserves retrieval quality. The spike's go/no-go controls whether Wave 0b uses Batch API or falls back to throttled sync.

Output: `docs/spikes/embedding-002-contract.md` go/no-go; `lightrag_embedding.py` as single source of truth; 6 files importing from it; re-embedded 18-doc graph; benchmark-green fixtures; PRD typo fix.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-RESEARCH.md
@.planning/phases/05-pipeline-automation/05-VALIDATION.md
@CLAUDE.md
@config.py
@ingest_wechat.py
@ingest_github.py
@kg_synthesize.py
@multimodal_ingest.py
@query_lightrag.py
@cognee_wrapper.py

<interfaces>
From `venv/Lib/site-packages/lightrag/` on the remote (per RESEARCH.md Pattern 1):

```python
# LightRAG calls embedding_func identically for upsert AND query.
# ONLY discriminator: query path injects _priority=5 kwarg; upsert does not.
# Source: lightrag/kg/nano_vector_db_impl.py:152 (query, priority=5)
#         lightrag/kg/nano_vector_db_impl.py:123 (upsert, no priority)

# Target signature for new shared module:
@wrap_embedding_func_with_attrs(
    embedding_dim=3072,        # gemini-embedding-2 native full dim (NanoVectorDB requires storage wipe for any change)
    send_dimensions=True,
    max_token_size=8192,       # gemini-embedding-2 limit
    model_name="gemini-embedding-2",
)
async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
    is_query = kwargs.pop("_priority", None) == 5  # pop so it is NOT forwarded to Gemini
    ...
```

From google-genai v1.73.1 (installed):
```python
# Multimodal embed: contents can be a list of mixed text + Part.from_bytes for ONE aggregated vector
response = await client.aio.models.embed_content(
    model="gemini-embedding-2",
    contents=[...],  # list[str] OR list[list[str|Part]] per request
    config=types.EmbedContentConfig(output_dimensionality=3072),
)
# response.embeddings -> list; each .values is list[float]

# Batch API (experimental on free tier — spike must confirm):
client.batches.create_embeddings(model=..., src=types.EmbeddingsBatchJobSource(...), config=...)
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 0.1: Wave 0 Spike — Batch API + RPM + Multimodal smoke</name>
  <files>scripts/phase5_wave0_spike.py, docs/spikes/embedding-002-contract.md</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-RESEARCH.md (Pattern 2 Batch API code shape; Pitfall 2 paid-tier warning)
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md (D-06, D-14, D-15 — remote WSL only)
    - ingest_wechat.py lines 127-154 (current sync embed pattern and 100-RPM throttle)
    - CLAUDE.md (remote SSH workflow section)
  </read_first>
  <action>
    Create `scripts/phase5_wave0_spike.py`. It MUST be runnable on the remote WSL host via `ssh <host> "cd ~/OmniGraph-Vault && venv/bin/python scripts/phase5_wave0_spike.py > docs/spikes/embedding-002-contract.md"`.

    The script performs three probes and writes a single Markdown report to stdout (redirected to `docs/spikes/embedding-002-contract.md`):

    **All probes use `output_dimensionality=3072` (the target production dim — see Task 0.2 `_OUTPUT_DIM`).**

    **Probe 1 — Batch API availability:**
    ```python
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    try:
        src = types.EmbeddingsBatchJobSource(
            inlined_requests=types.EmbedContentBatch(
                contents=["hello", "world"],
                config=types.EmbedContentConfig(output_dimensionality=3072),
            )
        )
        job = client.batches.create_embeddings(
            model="gemini-embedding-2",
            src=src,
            config=types.CreateEmbeddingsBatchJobConfig(display_name="wave0-spike"),
        )
        batch_api_available = True
        batch_job_name = job.name
    except Exception as e:
        batch_api_available = False
        batch_error = str(e)
    ```

    **Probe 2 — Free-tier RPM measurement:**
    Fire 120 sync `embed_content` calls in a 60-second window; count 200s and 429s. Record `rpm_ceiling = count_200_within_60s`. Use a fresh synchronous loop with `time.time()` bookkeeping. Each call: `client.models.embed_content(model="gemini-embedding-2", contents="ping", config=types.EmbedContentConfig(output_dimensionality=3072))`.

    **Probe 3 — Multimodal smoke:**
    Fetch one image from `~/.hermes/omonigraph-vault/images/` (glob for `*.jpg`; pick first; read bytes). Send one aggregated call:
    ```python
    resp = client.models.embed_content(
        model="gemini-embedding-2",
        contents=[
            "title: none | text: a diagram of system architecture",
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
        ],
        config=types.EmbedContentConfig(output_dimensionality=3072),
    )
    multimodal_works = (len(resp.embeddings) >= 1 and len(resp.embeddings[0].values) == 3072)
    ```

    **Report format (Markdown, machine-greppable):**
    ```
    # Wave 0 Embedding Spike Report
    date: 2026-04-28
    host: <gethostname>
    model: gemini-embedding-2

    batch_api_available: <true|false>
    batch_error: "<err or empty>"
    rpm_ceiling: <int>
    multimodal_works: <true|false>
    recommendation: <proceed|block>
    ```

    `recommendation = "proceed"` iff `multimodal_works=true` AND `rpm_ceiling>=30`. If Batch API is unavailable, still recommend proceed (Wave 0b falls back to chunked sync); record the fallback requirement.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python scripts/phase5_wave0_spike.py" | tee docs/spikes/embedding-002-contract.md &amp;&amp; grep -E "^(batch_api_available|rpm_ceiling|multimodal_works|recommendation):" docs/spikes/embedding-002-contract.md | wc -l | grep -q "^4$"</automated>
  </verify>
  <acceptance_criteria>
    - File `scripts/phase5_wave0_spike.py` exists and has at least 80 lines.
    - File `docs/spikes/embedding-002-contract.md` exists and contains exactly these four keys on separate lines: `batch_api_available:`, `rpm_ceiling:`, `multimodal_works:`, `recommendation:`.
    - `grep -E "^recommendation: (proceed|block)$" docs/spikes/embedding-002-contract.md` returns non-empty.
    - If `recommendation: block` → STOP and escalate to user; do not proceed to Task 0.2.
  </acceptance_criteria>
  <done>Spike report committed; downstream tasks read its values to configure Batch-vs-sync path in Wave 0b.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 0.2: Create shared `lightrag_embedding.py` with in-band multimodal and task-prefix routing</name>
  <files>lightrag_embedding.py, tests/unit/test_lightrag_embedding.py</files>
  <behavior>
    - Test 1: `embedding_func(["hello"])` with NO `_priority` kwarg returns `(1, 3072)` np.ndarray of float32.
    - Test 2: `embedding_func(["hello"], _priority=5)` applies query prefix and still returns `(1, 3072)` shape.
    - Test 3: `_priority` is popped from kwargs and never forwarded to the Gemini client (mock client, assert `embed_content` receives no `_priority` in config).
    - Test 4: A text containing `http://localhost:8765/abc/0.jpg` is detected; the function calls `requests.get(img_url)` once and constructs a `types.Part.from_bytes` in the `contents` list (can be verified with a `requests` mock).
    - Test 5: Output is L2-normalized (row norm ≈ 1.0 within 1e-5).
  </behavior>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-RESEARCH.md (Pattern 1 full code shape; Pitfall 5 `_priority` forwarding; Pattern 4 in-band multimodal; Pitfall 3 no `task_type` param)
    - ingest_wechat.py lines 127-154 (existing wrapper, throttle, decorator usage)
    - kg_synthesize.py lines 53-58 (read-path duplicate)
    - multimodal_ingest.py lines 60-76 (vision-augmented duplicate)
    - CLAUDE.md (simplicity first — one function, not two)
  </read_first>
  <action>
    Create `lightrag_embedding.py` at repo root (chosen over `config/embedding.py` because `config.py` already exists at root and adjacent module name is consistent with `query_lightrag.py` / `kg_synthesize.py` naming).

    File MUST contain:
    ```python
    """Shared embedding function for LightRAG.

    Single source of truth for Phase 5 D-01/D-03/D-04/D-05.
    All ingestion and query scripts import `embedding_func` from this module.
    """
    from __future__ import annotations

    import os
    import re
    from typing import Any

    import numpy as np
    import requests
    from google import genai
    from google.genai import types
    from lightrag.utils import wrap_embedding_func_with_attrs

    _IMAGE_URL_PATTERN = re.compile(r"http://localhost:8765/\S+?\.(?:jpg|jpeg|png)", re.IGNORECASE)
    _DOC_PREFIX = "title: none | text: "
    _QUERY_PREFIX = "task: search result | query: "
    _DEFAULT_MODEL = "gemini-embedding-2"
    _OUTPUT_DIM = 3072  # native full-capacity dim; any change requires NanoVectorDB wipe (see Task 0.4)
    _MAX_IMAGES_PER_REQUEST = 6  # Gemini hard cap

    def _fetch_image_part(url: str, timeout: float = 5.0) -> types.Part | None:
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
            return types.Part.from_bytes(data=resp.content, mime_type=mime)
        except Exception:
            return None

    def _build_contents(text: str, is_query: bool) -> list:
        """Build contents payload — ALL image URLs in the chunk are fetched and sent as Parts.

        Phase 5 corr (2026-05-03): the original design only fetched the FIRST
        image URL (re.search). When LightRAG chunks multiple [Image N Reference]
        lines into one chunk, images 2+ were stripped from text but never
        embedded. Fixed to findall → fetch all → send all as Parts, capped at
        ``_MAX_IMAGES_PER_REQUEST = 6`` (Gemini hard limit).
        """
        prefix = _QUERY_PREFIX if is_query else _DOC_PREFIX
        urls = _IMAGE_URL_PATTERN.findall(text)
        if not urls:
            return [prefix + text]

        clean_text = _IMAGE_URL_PATTERN.sub("", text).strip()
        parts: list = []
        for url in urls[:_MAX_IMAGES_PER_REQUEST]:
            part = _fetch_image_part(url)
            if part is not None:
                parts.append(part)

        if not parts:
            # All fetches failed — fall through to text-only
            return [prefix + clean_text]
        return [prefix + clean_text] + parts

    @wrap_embedding_func_with_attrs(
        embedding_dim=_OUTPUT_DIM,
        send_dimensions=True,
        max_token_size=8192,
        model_name=_DEFAULT_MODEL,
    )
    async def embedding_func(texts: list[str], **kwargs: Any) -> np.ndarray:
        is_query = kwargs.pop("_priority", None) == 5
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        model = os.environ.get("EMBEDDING_MODEL", _DEFAULT_MODEL)
        client = genai.Client(api_key=api_key)
        vectors: list[np.ndarray] = []
        for text in texts:
            contents = _build_contents(text, is_query)
            response = await client.aio.models.embed_content(
                model=model,
                contents=contents,
                config=types.EmbedContentConfig(output_dimensionality=_OUTPUT_DIM),
            )
            # One aggregated embedding per `contents` (text+image or text-only)
            vec = np.asarray(response.embeddings[0].values, dtype=np.float32)
            vectors.append(vec)
        out = np.vstack(vectors)
        # At 3072 (native), Gemini returns unit-norm vectors already; manual L2 norm is idempotent and safe.
        # Keep it so the function is correct across any _OUTPUT_DIM choice.
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return out / norms
    ```

    Create `tests/unit/test_lightrag_embedding.py` with the 5 behavioral tests listed above using `pytest` + `unittest.mock.patch` on `google.genai.Client` and `requests.get`. Tests run LOCALLY (no network) via mocks.

    Tests use `pytest.mark.asyncio` (asyncio_mode=auto is configured per Phase 4's pyproject.toml).
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_lightrag_embedding.py -v"</automated>
  </verify>
  <acceptance_criteria>
    - File `lightrag_embedding.py` exists at repo root.
    - `grep -q "def embedding_func" lightrag_embedding.py` returns 0.
    - `grep -q "kwargs.pop(\"_priority\", None) == 5" lightrag_embedding.py` returns 0.
    - `grep -q "_OUTPUT_DIM = 3072" lightrag_embedding.py` returns 0.
    - `grep -q "output_dimensionality=_OUTPUT_DIM" lightrag_embedding.py` returns 0.
    - `! grep -q "task_type" lightrag_embedding.py` (task_type is forbidden for -2 per Pitfall 3; grep MUST return non-zero = pattern not present).
    - `pytest tests/unit/test_lightrag_embedding.py -v` — 5 tests pass; shape assertions use `(1, 3072)`.
  </acceptance_criteria>
  <done>Shared module ready for import by all 6 duplicate sites.</done>
</task>

<task type="auto">
  <name>Task 0.3: Consolidate 6 duplicate embedding_func sites; add EMBEDDING_MODEL env var</name>
  <files>ingest_wechat.py, ingest_github.py, kg_synthesize.py, multimodal_ingest.py, query_lightrag.py, cognee_wrapper.py</files>
  <read_first>
    - lightrag_embedding.py (Task 0.2 output — the new import target)
    - ingest_wechat.py lines 127-170 (current duplicate + rag construction context)
    - ingest_github.py lines 51-67 (duplicate)
    - kg_synthesize.py lines 53-58 (read path duplicate)
    - multimodal_ingest.py lines 60-76 (duplicate)
    - query_lightrag.py lines 30-34 (duplicate)
    - cognee_wrapper.py lines 25-30 (hardcoded model name)
    - CLAUDE.md (Surgical Changes — touch only what you must; clean up your own orphans)
  </read_first>
  <action>
    For each of the 6 files, replace the local `embedding_func` definition with a single import from the shared module. DO NOT touch unrelated code in these files (CLAUDE.md §3 surgical changes).

    **1. ingest_wechat.py:**
    - Remove lines 127-154 (the `_embed_lock`, `_last_embed_time`, `_EMBED_MIN_INTERVAL`, and the `embedding_func` definition decorated with `@wrap_embedding_func_with_attrs(...model_name="gemini-embedding-001")`).
    - Remove the old throttle doc-comment block starting with `# --- Embedding Rate Limiting ---`.
    - Add near the other third-party imports: `from lightrag_embedding import embedding_func`.
    - Remove any now-orphaned imports that the deleted block needed: `asyncio` import stays (used elsewhere), `time` stays if used elsewhere — run `grep -n "^import time\|^from.*gemini_embed" ingest_wechat.py` after edit and remove unused.

    **2. ingest_github.py:**
    - Remove lines 51-67 (local `embedding_func`).
    - Add `from lightrag_embedding import embedding_func`.

    **3. kg_synthesize.py:**
    - Remove lines 53-58.
    - Add `from lightrag_embedding import embedding_func`.

    **4. multimodal_ingest.py:**
    - Remove lines 60-76.
    - Add `from lightrag_embedding import embedding_func`.

    **5. query_lightrag.py:**
    - Remove lines 30-34.
    - Add `from lightrag_embedding import embedding_func`.

    **6. cognee_wrapper.py line 27:**
    - Change `os.environ["EMBEDDING_MODEL"] = "gemini-embedding-001"` to `os.environ["EMBEDDING_MODEL"] = "gemini-embedding-2"`.
    - Leave all other lines in `cognee_wrapper.py` unchanged.

    **Env var step (remote only, documented in plan SUMMARY):**
    On the remote WSL host, append to `~/.hermes/.env`:
    ```
    EMBEDDING_MODEL=gemini-embedding-2
    ```
    The plan SUMMARY must record this was done and paste the one-line diff for auditability.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; grep -c '^from lightrag_embedding import embedding_func' ingest_wechat.py ingest_github.py kg_synthesize.py multimodal_ingest.py query_lightrag.py | awk -F: '{s+=\$2} END {print s}'" | grep -q "^5$" &amp;&amp; ssh remote "cd ~/OmniGraph-Vault &amp;&amp; grep -c 'gemini-embedding-2' cognee_wrapper.py" | grep -q "^1$" &amp;&amp; ssh remote "grep -c '^EMBEDDING_MODEL=gemini-embedding-2' ~/.hermes/.env" | grep -q "^1$"</automated>
  </verify>
  <acceptance_criteria>
    - Exactly 5 files contain exactly one `from lightrag_embedding import embedding_func` line.
    - Zero files still contain `model_name="gemini-embedding-001"` or `model="gemini-embedding-001"`: `grep -rn "gemini-embedding-001" *.py` returns nothing.
    - `cognee_wrapper.py` contains one `gemini-embedding-2` string on line ~27.
    - Remote `~/.hermes/.env` contains `EMBEDDING_MODEL=gemini-embedding-2`.
    - `python -c "import ingest_wechat; import query_lightrag; import kg_synthesize"` succeeds on remote with no ImportError.
  </acceptance_criteria>
  <done>Six duplicates replaced by one import; env var set.</done>
</task>

<task type="auto">
  <name>Task 0.4: Wave 0 re-embed — NanoVectorDB wipe + re-ingest for 18 existing docs (3072-dim migration)</name>
  <files>scripts/wave0_reembed.py</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-RESEARCH.md (Pattern 3 "NanoVectorDB Dim Change Requires Storage Wipe" — canonical migration path for 768→3072; Pitfall 1 dim assertion; Pitfall 4 ingestion dedup)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md (D-17 LightRAG ainsert path reused)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-00-wave0-scaffold-and-spike-PLAN.md (prior spike pattern — `scripts/phase0_delete_spike.py`)
    - ingest_wechat.py (post-Task-0.3) — now imports embedding_func from lightrag_embedding
    - lightrag_embedding.py (now at 3072 native dim)
  </read_first>
  <action>
    Create `scripts/wave0_reembed.py`. It re-embeds all 18 existing LightRAG docs using the new `gemini-embedding-2` at 3072 dim. Because dim changed from 768 → 3072, delete-by-id path is UNAVAILABLE — LightRAG fails dim assertion on init before `adelete_by_doc_id` can run. Strategy: read `full_docs.json` to recover the doc-text cache, back it up, wipe the 3 `vdb_*.json` files, then re-ingest each doc's text via `rag.ainsert()` on a freshly constructed LightRAG (3072-dim) — LightRAG rebuilds chunks, entities, and relationships in one pass.

    Required structure:
    ```python
    """Wave 0 re-embed: wipe NanoVectorDB and re-ingest 18 docs at gemini-embedding-2 / 3072 dim.

    Strategy (3072-dim migration, cannot use delete-by-id):
        1. Read RAG_WORKING_DIR/full_docs.json → {doc_id: {"content": str, ...}}
        2. Back up full_docs.json to full_docs.json.bak
        3. Wipe vdb_chunks.json, vdb_entities.json, vdb_relationships.json (and full_docs.json itself
           so LightRAG dedup re-admits each insert)
        4. Construct fresh LightRAG(embedding_dim=3072)
        5. For each doc-id from the backup: rag.ainsert(content) → LightRAG re-chunks,
           extracts entities, computes 3072-dim embeddings, writes new vdb files.
        6. Verify new vdb_chunks.json has `"embedding_dim": 3072`.

    Usage:
        python scripts/wave0_reembed.py --dry-run            # print plan, no mutations
        python scripts/wave0_reembed.py --one-doc <doc_id>   # test on single doc (uses temp storage dir)
        python scripts/wave0_reembed.py                      # full run (18 docs)
    """
    import argparse
    import asyncio
    import json
    import shutil
    from pathlib import Path

    from config import RAG_WORKING_DIR
    from lightrag_embedding import embedding_func

    STORAGE = Path(RAG_WORKING_DIR)
    FULL_DOCS = STORAGE / "full_docs.json"
    VDB_FILES = [STORAGE / f for f in ("vdb_chunks.json", "vdb_entities.json", "vdb_relationships.json")]

    async def main(dry_run: bool, one_doc: str | None) -> None:
        # 1. Read full_docs backup
        docs = json.loads(FULL_DOCS.read_text(encoding="utf-8"))
        # 2. Print before-counts per vdb file (embedding_dim + data length)
        # 3. Back up full_docs.json to full_docs.json.bak (overwrite allowed)
        # 4. if dry_run: for each doc_id, content in docs.items(): print(f"WOULD wipe vdb + re-ainsert {doc_id} ({len(content['content'])} chars)"); return
        # 5. Wipe: for p in VDB_FILES + [FULL_DOCS]: p.unlink(missing_ok=True)
        # 6. Construct LightRAG (fresh 3072-dim); await initialize_storages()
        # 7. For each doc_id → rag.ainsert(content); respect rpm throttle
        # 8. Verify: load new vdb_chunks.json, assert "embedding_dim": 3072
        # 9. Write run log to docs/spikes/wave0_reembed_log.md
    ```

    Throttle: respect `rpm_ceiling` from spike report. Parse `docs/spikes/embedding-002-contract.md` for `rpm_ceiling:` value; if it is < 100, keep `embedding_func_max_async=1` and `embedding_batch_num=20` (same as Phase 4 committed `0faab0c`). If ≥ 100, allow the default LightRAG concurrency.

    LightRAG construction pattern (embedding_dim now comes from the decorator on `embedding_func` = 3072):
    ```python
    from lightrag import LightRAG
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=llm_model_func,         # import from ingest_wechat or duplicate minimal copy
        embedding_func=embedding_func,          # from lightrag_embedding — 3072-dim
        llm_model_name="gemini-2.5-flash",
        embedding_func_max_async=1,
        embedding_batch_num=20,
        llm_model_max_async=2,
    )
    await rag.initialize_storages()
    ```

    Flags:
    - `--dry-run`: enumerate doc IDs and print planned actions; no filesystem mutations, no LightRAG construction.
    - `--one-doc <doc_id>`: operate on just that doc against a **temporary** storage dir (e.g., `/tmp/wave0_one_doc/`) so the production 18-doc graph is not partially wiped during testing.
    - default: process all doc IDs recovered from the backup.

    **SAFETY:** Before default-run wipe, require `confirm: "wipe"` kwarg OR a `--i-understand` CLI flag. The script should refuse to run without it and print the 3 vdb file paths it would delete.

    After run, write `docs/spikes/wave0_reembed_log.md` with:
    ```
    # Wave 0 Re-embed Log
    strategy: vdb-wipe-reingest (768→3072 dim migration)
    before: entities=<N>, relationships=<M>, chunks=<K>, embedding_dim=768
    processed: <D> docs
    after:  entities=<N2>, relationships=<M2>, chunks=<K2>, embedding_dim=3072
    errors: <list>
    ```

    **Baseline preservation:** Task 0.5 captures `tests/fixtures/wave0_baseline.json` BEFORE this script runs. This script must NOT touch `tests/fixtures/`. The wipe is scoped to `~/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json` + `full_docs.json` only.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python scripts/wave0_reembed.py --dry-run"</automated>
  </verify>
  <acceptance_criteria>
    - File `scripts/wave0_reembed.py` exists; first 5 lines contain a module docstring mentioning "Wave 0 re-embed" and "3072".
    - `grep -q "vdb_chunks.json\|vdb_entities.json\|vdb_relationships.json" scripts/wave0_reembed.py` returns 0 (wipe targets present).
    - `grep -q "ainsert" scripts/wave0_reembed.py` returns 0.
    - `grep -q "\-\-dry-run" scripts/wave0_reembed.py` returns 0.
    - `grep -q "\-\-one-doc" scripts/wave0_reembed.py` returns 0.
    - `grep -q "\-\-i-understand\|confirm=.wipe." scripts/wave0_reembed.py` returns 0 (safety gate present).
    - `grep -q "full_docs.json.bak\|shutil.copy" scripts/wave0_reembed.py` returns 0 (backup step present).
    - `grep -q "adelete_by_doc_id" scripts/wave0_reembed.py` returns **non-zero** (this path is explicitly NOT used for a dim change).
    - `--dry-run` invocation on remote exits 0 and prints ≥ 18 "WOULD wipe vdb + re-ainsert …" lines.
    - Actual run (after Task 0.5 captures baseline) produces `docs/spikes/wave0_reembed_log.md` with `embedding_dim=3072` present in the `after:` line.
    - Post-run, a fresh `grep '"embedding_dim"' ~/.hermes/omonigraph-vault/lightrag_storage/vdb_chunks.json` returns `3072`.
  </acceptance_criteria>
  <done>Re-embed script ready; to be executed AFTER Task 0.5 captures the -001/768 baseline snapshot.</done>
</task>

<task type="auto">
  <name>Task 0.5: Wave 0 benchmark — Chinese retrieval + cross-modal golden queries</name>
  <files>tests/verify_wave0_benchmark.py, tests/verify_wave0_crossmodal.py, tests/fixtures/wave0_baseline.json, tests/fixtures/wave0_golden_queries.json</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-PRD.md §2.4 success criteria table
    - .planning/phases/05-pipeline-automation/05-VALIDATION.md (Wave 0 Requirements block)
    - docs/testing/04-07-validation-results.md (Phase 4 validated queries — pick 3-5 from here)
    - query_lightrag.py (query invocation pattern; uses `rag.aquery(query, param=QueryParam(mode="hybrid"))`)
    - scripts/wave0_reembed.py (Task 0.4 — run order is: capture baseline → reembed → run benchmark)
  </read_first>
  <action>
    Create three files:

    **1. `tests/fixtures/wave0_golden_queries.json`** — 8 queries covering CN text, cross-modal, and optional EN:
    ```json
    {
      "queries": [
        {"id": "cn-1", "type": "chinese_text", "text": "Hermes Agent 的架构设计"},
        {"id": "cn-2", "type": "chinese_text", "text": "OpenClaw 的技术栈"},
        {"id": "cn-3", "type": "chinese_text", "text": "LightRAG 知识图谱检索机制"},
        {"id": "cn-4", "type": "chinese_text", "text": "Agent Harness 工程实践"},
        {"id": "cross-1", "type": "cross_modal", "text": "LightRAG 系统架构图"},
        {"id": "cross-2", "type": "cross_modal", "text": "知识图谱节点示意图"},
        {"id": "en-1", "type": "english_text", "text": "What is agentic RAG"},
        {"id": "en-2", "type": "english_text", "text": "LightRAG delete-by-id API"}
      ]
    }
    ```

    **2. `tests/verify_wave0_benchmark.py`** — the top-5 overlap benchmark:
    - Reads `wave0_golden_queries.json`.
    - Two modes controlled by env var `WAVE0_MODE`:
        - `WAVE0_MODE=baseline`: run each CN + EN query via `rag.aquery(..., param=QueryParam(mode="hybrid", response_type="Json"))`; extract top-5 retrieved chunk IDs from the response (use LightRAG's `only_need_context=True` param so retrieval returns doc ids, not synthesized text); write `tests/fixtures/wave0_baseline.json` as `{query_id: [chunk_id_1, ...chunk_id_5]}`.
        - `WAVE0_MODE=compare` (default): run the same queries, compare against baseline JSON, compute overlap = `len(set(new_top5) & set(baseline_top5)) / 5`. For each CN + EN query, assert overlap ≥ 0.6 (i.e., ≥ 3 of 5). Skip cross_modal queries (handled by the other verifier).
    - Exit 0 if all non-cross-modal queries pass ≥ 60% overlap; exit 1 otherwise.
    - Print a summary table: `query_id | overlap | pass/fail`.

    **3. `tests/verify_wave0_crossmodal.py`** — the cross-modal hit check:
    - Reads `wave0_golden_queries.json`, filters `type=="cross_modal"`.
    - Runs each query in `mode="hybrid"` with `only_need_context=True`.
    - For each query, assert ≥ 1 retrieved chunk's text body contains a URL matching regex `http://localhost:8765/\S+\.(?:jpg|jpeg|png)`.
    - Exit 0 if ≥ 1 of the 2 cross-modal queries hits; exit 1 otherwise.

    Document the execution order in each script's module docstring:
    ```
    # Order of operations:
    # 1. WAVE0_MODE=baseline python tests/verify_wave0_benchmark.py   # captures baseline
    # 2. python scripts/wave0_reembed.py                               # re-embed 18 docs
    # 3. python tests/verify_wave0_benchmark.py                        # post-check (compare mode)
    # 4. python tests/verify_wave0_crossmodal.py                       # cross-modal check
    ```
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; WAVE0_MODE=baseline venv/bin/python tests/verify_wave0_benchmark.py &amp;&amp; venv/bin/python scripts/wave0_reembed.py &amp;&amp; venv/bin/python tests/verify_wave0_benchmark.py &amp;&amp; venv/bin/python tests/verify_wave0_crossmodal.py"</automated>
  </verify>
  <acceptance_criteria>
    - Files `tests/verify_wave0_benchmark.py`, `tests/verify_wave0_crossmodal.py`, `tests/fixtures/wave0_golden_queries.json` exist.
    - `tests/fixtures/wave0_golden_queries.json` parses as valid JSON and has ≥ 8 queries.
    - `tests/fixtures/wave0_baseline.json` is created during the baseline mode run and contains top-5 arrays for every non-cross-modal query.
    - Post-re-embed benchmark exits 0 — CN queries must hit ≥ 60% top-5 overlap.
    - Cross-modal verifier exits 0 — ≥ 1 of 2 cross-modal queries has at least one image-URL chunk in top-5.
    - If either fails, Wave 0 is NOT green and Wave 0b MUST NOT start. Escalate to user.
  </acceptance_criteria>
  <done>Benchmark passing; graph quality validated; gate cleared for Wave 0b + Wave 1.</done>
</task>

<task type="auto">
  <name>Task 0.6: Fix PRD §2.4 model-name typo and supersession notes</name>
  <files>.planning/phases/05-pipeline-automation/05-PRD.md</files>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-PRD.md §2.4 (search for "embedding-002")
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md (PRD inconsistencies section)
    - .planning/phases/05-pipeline-automation/05-RESEARCH.md (Summary — model name is `gemini-embedding-2`, NOT `-002`)
  </read_first>
  <action>
    In `05-PRD.md`:

    1. Replace every occurrence of `embedding-002` (case-sensitive) with `gemini-embedding-2`. Use Edit tool, one replacement per occurrence if necessary. Expected occurrence count: ~5 in §2.4.

    2. Insert a `> **Superseded**` note at the top of §3.1.5 immediately under the heading:
       ```
       > **Superseded by Phase 5 D-07 (2026-04-28):** All RSS articles with depth_score ≥ 2 go through Zhihu 好问 enrichment regardless of language. The "英文 RSS 可能不需要增厚" note below is obsolete.
       ```

    3. Insert a `> **Superseded**` note at the top of §8 Wave 0b bullet:
       ```
       > **Superseded by Phase 5 D-10 (2026-04-28):** Ingestion filter is keyword match AND depth_score ≥ 2, NOT all 302 articles. Current keyword scope: `{openclaw, hermes, agent, harness}`.
       ```

    4. Insert a `> **Superseded**` note in §8 near `ENRICHMENT_LLM_MODEL = "deepseek-v4-flash"`:
       ```
       > **Superseded by Phase 4 D-12:** Question extraction uses Gemini 2.5 Flash Lite (with optional grounding). `ENRICHMENT_LLM_MODEL` no longer points at DeepSeek.
       ```

    Do NOT reword or re-structure the PRD. Insertion-only edits above.
  </action>
  <verify>
    <automated>grep -c "gemini-embedding-2" .planning/phases/05-pipeline-automation/05-PRD.md &amp;&amp; ! grep -q "embedding-002" .planning/phases/05-pipeline-automation/05-PRD.md &amp;&amp; grep -c "Superseded" .planning/phases/05-pipeline-automation/05-PRD.md | awk '{if(\$1>=3) exit 0; else exit 1}'</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "embedding-002" .planning/phases/05-pipeline-automation/05-PRD.md` returns 0.
    - `grep -c "gemini-embedding-2" .planning/phases/05-pipeline-automation/05-PRD.md` returns ≥ 5.
    - `grep -c "Superseded" .planning/phases/05-pipeline-automation/05-PRD.md` returns ≥ 3.
  </acceptance_criteria>
  <done>PRD model name corrected; 3 supersession notes added; PRD now matches CONTEXT.md locked decisions.</done>
</task>

</tasks>

<task type="auto">
  <name>Task 0.7: Bind image URLs with descriptive text for retrieval (2026-05-03)</name>
  <files>ingest_wechat.py, batch_ingest_from_spider.py</files>
  <read_first>
    - ingest_wechat.py lines 974-982 (image Reference line appending)
    - kg_synthesize.py lines 93-101 (synthesis prompt expects image URLs in context)
    - lib/lightrag_embedding.py `_IMAGE_URL_PATTERN` (matches localhost:8765 URLs)
  </read_first>
  <action>
    **Problem:** Image Reference lines are appended at the document end as bare
    ``[Image N Reference]: http://localhost:8765/...`` with zero descriptive
    text. When LightRAG chunks these, they form isolated chunks that hybrid
    search cannot retrieve. Even though inline images in the body (from
    ``localize_markdown``) carry alt text, the Reference-line fallback chunks
    are wasted — their image URLs are never surfaced in ``kg_synthesize``
    results, producing text-only answers for queries that should be
    image-rich.

    **Fix:** Two-pronged approach:

    1. **Parent doc Reference lines:** enrich with article title so bare-URL
       chunks are at least minimally retrievable (fallback for queries matching
       the article topic).

    2. **Vision sub-doc:** include the ``localhost:8765`` image URL alongside
       each vision-generated description. This is the primary retrieval path:
       the description text makes the chunk semantically searchable, and the
       URL lets ``kg_synthesize`` inline it as ``![desc](url)``.

    In ``ingest_wechat.py``:

    ```python
    # (1) Parent doc — BEFORE (bare)
    full_content += f"\\n\\n[Image {i} Reference]: {local_url}"
    # (1) Parent doc — AFTER (title context fallback)
    full_content += f"\\n\\nImage {i} from article '{title}': {local_url}"

    # (2) Vision sub-doc — BEFORE (description only, no URL)
    lines.append(f"- [image {i}]: {desc}")
    # (2) Vision sub-doc — AFTER (description + URL for kg_synthesize inlining)
    lines.append(f"- [image {i}]: {desc}  ({local_url})")
    ```
  </action>
  <verify>
    <automated>grep -c "from article '" ingest_wechat.py</automated>
  </verify>
  <acceptance_criteria>
    - ``ingest_wechat.py`` no longer contains bare ``[Image N Reference]:`` lines.
    - Reference lines include article title context.
    - ``kg_synthesize.py`` query for article topic returns chunks with image URLs in context.
  </acceptance_criteria>
  <done>Image Reference lines enriched with article title; retrievable by hybrid search.</done>
</task>

<task type="manual">
  <name>Task 0.8: Full reset + re-ingest after pipeline stabilization (2026-05-03)</name>
  <files>lightrag_storage/*, data/kol_scan.db</files>
  <read_first>
    - ingest_wechat.py (current ingestion pipeline)
    - lib/lightrag_embedding.py (3072-dim multimodal embedding)
    - batch_ingest_from_spider.py (batch orchestrator)
  </read_first>
  <action>
    **Problem:** SQLite DB ``articles.content_hash`` is an optimistic marker — it
    is written the moment ``rag.ainsert()`` is called, without verification that
    LightRAG actually persisted the document. This creates a growing gap between
    what the DB *thinks* is ingested and what LightRAG *actually* stores:

    | Source | Count | Notes |
    |--------|-------|-------|
    | ``kol_scan.db`` articles with ``content_hash IS NOT NULL`` | 57 | DB believes these are ingested |
    | ``kv_store_full_docs.json`` | 8 | LightRAG actually has these |
    | **Ghost articles** | **49** | Batch pipeline skips them, they don't exist in retrieval |

    Root causes:
    - Phase 5 Wave 0 wipe + re-ingest chain had silent failures (planned 18 → actual 8)
    - No post-ainsert verification exists (no ``rag.aget_by_id()`` round-trip check)
    - DB writes happen outside the retry/error path

    **Fix: Full reset once the pipeline is stable.** After Tasks 0.1–0.7 are all
    validated (multi-image embedding, description-URL binding, 3072-dim), execute
    a clean-slate re-ingest:

    ```bash
    # 1. Wipe LightRAG vector storage
    cd ~/.hermes/omonigraph-vault/lightrag_storage
    rm -f vdb_chunks.json vdb_entities.json vdb_relationships.json \
          kv_store_*.json graph_chunk_entity_relation.graphml full_docs.json

    # 2. Reset DB ingestion markers
    sqlite3 ~/OmniGraph-Vault/data/kol_scan.db \
      "UPDATE articles SET content_hash = NULL WHERE content_hash IS NOT NULL"

    # 3. Full batch re-ingest
    cd ~/OmniGraph-Vault
    venv/bin/python batch_ingest_from_spider.py
    ```

    **Verification mechanism (post-ainsert round-trip):** After each
    ``rag.ainsert(content, ids=[doc_id])``, call
    ``rag.aget_docs_by_ids([doc_id])`` to confirm the doc exists in LightRAG
    BEFORE writing ``content_hash`` to the DB. This eliminates the
    optimistic-marker gap permanently:

    ```python
    # In ingest_wechat.py, after rag.ainsert():
    statuses = await rag.aget_docs_by_ids([doc_id])
    if statuses and doc_id in statuses:
        # Confirmed in LightRAG — safe to mark
        conn.execute("UPDATE articles SET content_hash = ? WHERE url = ?",
                     (article_hash, url))
    else:
        # Failed — leave content_hash NULL so batch retries
        logger.warning("ainsert returned but doc %s not found in doc_status", doc_id)
    ```

    LightRAG uses the caller-supplied ``doc_id`` (e.g., ``wechat_{hash}``) as
    the key in both ``full_docs`` and ``doc_status`` KV stores.
    ``aget_docs_by_ids`` queries ``doc_status`` — a non-empty result with
    status=PROCESSED means the document was fully ingested (chunks, entities,
    relationships all persisted).

    **Trigger condition:** Do NOT execute until all of these are confirmed:
    - Task 0.1–0.3 (embedding consolidation, 3072-dim) ✅
    - Task 0.5 (cross-modal benchmark passing) ✅
    - Task 0.2b (``_build_contents`` multi-image fix) ✅
    - Task 0.7 (image URL binding with descriptions) ✅
    - At least 3 manual test articles ingested successfully end-to-end
    - ``kg_synthesize`` produces image-rich markdown for a visual query

    After reset, the DB count and LightRAG count should converge to within ±5%.
  </action>
  <verify>
    Post-reset: ``wc -l`` on ``kv_store_full_docs.json`` keys ≈ ``SELECT COUNT(*) FROM articles WHERE content_hash IS NOT NULL`` ± 5%.
  </verify>
  <acceptance_criteria>
    - Zero ghost articles: every ``content_hash IS NOT NULL`` row has a corresponding LightRAG doc.
    - ``kg_synthesize`` retrieval covers the full ingested corpus, not just 8 docs.
    - Cross-modal queries return image-URL chunks from the full re-ingested set.
  </acceptance_criteria>
  <done>
    **Verification hook (Task 0.8 sub-task) — code + tests COMPLETE 2026-05-02 (commit 585aa3b).**

    `ingest_wechat.py` now calls `rag.aget_docs_by_ids([doc_id])` immediately
    after `rag.ainsert(...)` returns and gates the entire DB write block
    (`content_hash` + `enriched=-1` + `ingestions` row) on
    `status == "PROCESSED"`. Non-PROCESSED responses (absent / failed / exception)
    log a warning and leave `content_hash` NULL so the batch re-scheduler retries
    — aligns with Phase 12 D-SUBDOC resume semantics.

    Three unit tests added to `tests/unit/test_text_first_ingest.py`:
    - `test_task08_hook_skips_content_hash_when_doc_absent_from_status`
    - `test_task08_hook_skips_content_hash_when_status_not_processed`
    - `test_task08_hook_writes_content_hash_when_status_processed`

    All 3 pass locally (Windows dev). Zero regression on other unit tests
    (pre-existing 2 failures in `test_text_first_ingest.py` confirmed via
    `git stash` as present on HEAD before this change; not in scope).

    **Remaining Task 0.8 actions (Hermes-only, R4 env ceiling):**
    Full reset + re-ingest of 378 articles still PENDING — see
    `docs/HERMES_PHASE5_WAVE0_PUNCH.md` for the operator runbook.
    After Hermes completes re-ingest + Task 0.5 benchmarks (Tasks 4.3 / 4.4
    in the v3.2-handoff prompt), this task closes and `05-00-SUMMARY.md`
    is written.
  </done>
</task>

</tasks>

<verification>
- `docs/spikes/embedding-002-contract.md` exists with all four required keys and `recommendation: proceed`.
- `lightrag_embedding.py` exports `embedding_func`; 5 files import from it; `cognee_wrapper.py` uses new model name; remote `.env` has `EMBEDDING_MODEL=gemini-embedding-2`.
- Task 0.2b (2026-05-03): `_build_contents` upgraded from single-image `re.search` → multi-image `findall`, capped at `_MAX_IMAGES_PER_REQUEST=6`. Plan and code both updated.
- Task 0.7 (2026-05-03): parent doc Reference lines enriched with article title; vision sub-doc lines include `localhost:8765` URLs alongside descriptions. Both paths now produce retrievable image-URL chunks for `kg_synthesize`.
- Task 0.8 (2026-05-03): 57 ghost articles identified (DB `content_hash` optimistic-marker gap). Full reset procedure documented; gated on pipeline stabilization. DB `content_hash` zeroed — 0 articles marked ingested, ready for clean-slate re-ingest.
- `scripts/wave0_reembed.py` executed on 18 docs (partial — only 8 survived in LightRAG; superseded by Task 0.8 full reset).
- `tests/verify_wave0_benchmark.py` and `tests/verify_wave0_crossmodal.py` both exit 0 on remote.
- PRD §2.4 typo fixed; 3 supersession notes added.
</verification>

<success_criteria>
- Spike report recommends "proceed".
- All 6 duplicate embedding_func sites consolidated into 1 shared module + 1 env-var change in `cognee_wrapper.py`.
- `_build_contents` handles ALL image URLs per chunk (findall, capped at 6), not just the first one.
- Image reference chunks are retrievable: parent doc carries article title context, vision sub-doc carries description + `localhost:8765` URL.
- DB `content_hash` gap eliminated: 0 ghost articles; after full reset (Task 0.8), LightRAG doc count ≈ DB ingested count within ±5%.
- Chinese retrieval top-5 overlap ≥ 60% per golden query.
- Cross-modal text→image retrieval hits ≥ 1 of 2 golden cross-modal queries, now with vision-described sub-doc chunks carrying image URLs.
- PRD typo fixed.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-00-SUMMARY.md` with: spike report verdict, final embedding dim (3072), list of 6 files consolidated, before/after graph entity counts + embedding_dim transition (768→3072), benchmark overlap percentages per query, and the `EMBEDDING_MODEL` env-var diff.
</output>

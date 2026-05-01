---
revised: "2026-05-01 — v3.1 closure alignment (commit 2b38e98). Added stage 6 sub_doc_ingest to checkpoint state machine per D-SUBDOC decision in 12-CONTEXT.md (absorbs v3.1 closure Finding 1 from docs/MILESTONE_v3.1_CLOSURE.md §6.1). Must-haves updated to include sub-doc ingest guard and resume path."
phase: 12-checkpoint-resume
plan: 02
type: execute
wave: 2
depends_on:
  - "12-00"
files_modified:
  - ingest_wechat.py
  - tests/unit/test_checkpoint_ingest_integration.py
autonomous: true
requirements:
  - CKPT-01
  - CKPT-03
user_setup: []

must_haves:
  truths:
    - "ingest_article(url) wraps each of the 6 stages (scrape, classify, image_download, text_ingest, vision_worker, sub_doc_ingest) with has_stage/read_stage/write_stage calls"
    - "On a second invocation with the same URL, completed stages are SKIPPED (log shows 'checkpoint hit: {stage}')"
    - "Failure at stage N leaves checkpoints 1..N-1 on disk and stage N absent — next run resumes from N"
    - "metadata.json is upserted at every stage completion with updated_at + last_completed_stage"
    - "vision_worker checkpoint writes per-image 05_vision/{image_id}.json (not a single .done marker)"
    - "sub_doc_ingest stage writes 06_sub_doc_ingest.done ONLY after sub-doc LightRAG ainsert returns AND entity extraction for all sub-doc chunks completes (D-SUBDOC 2026-05-01)"
    - "sub_doc_ingest stage is SKIPPED (marker written immediately) when 05_vision/ has zero success markers — no Vision descriptions means nothing to sub-doc-ingest; the marker prevents resume-loop"
    - "sub_doc_ingest re-run reads cached 05_vision/*.json (no re-Vision-API-calls); this is the Finding-1 remediation path for articles whose sub-doc was abandoned by the former 120s drain_timeout"
  artifacts:
    - path: "ingest_wechat.py"
      provides: "ingest_article with checkpoint read/write wrapping the 5 stages"
      contains: "from lib.checkpoint import"
    - path: "tests/unit/test_checkpoint_ingest_integration.py"
      provides: "Mock-based tests verifying skip-on-resume for each of the 5 stages"
      min_lines: 200
  key_links:
    - from: "ingest_wechat.py::ingest_article"
      to: "lib.checkpoint.has_stage / read_stage / write_stage / write_metadata"
      via: "guards around each stage"
      pattern: "has_stage\\(.*scrape"
    - from: "ingest_wechat.py::_vision_worker_impl"
      to: "lib.checkpoint.write_vision_description"
      via: "per-image checkpoint write"
      pattern: "write_vision_description"
---

<objective>
Wrap each of the 5 ingestion stages in `ingest_wechat.py::ingest_article` with checkpoint read/write calls so transient failures resume without re-doing completed work. Implements CKPT-01 (stage boundaries) and CKPT-03 (resume logic: skip any stage whose checkpoint marker is present).

Purpose: Gate-1 acceptance criterion 1 — "Single article with injected failure at stage 3 (image-download) resumes correctly at stage 4 (text-ingest) without re-running scrape/classify/image-download" lives or dies on this plan.

Output: modified `ingest_wechat.py` + integration tests proving each stage's skip-on-resume behavior.

Surgical constraint: DO NOT restructure `ingest_article`. Add `if has_stage(...): load from checkpoint; else: do work; write_stage(...)` guards at existing stage boundaries. Preserve the existing cache_content "final_content.md" path (legacy cache — orthogonal to checkpoints). DO NOT touch the MD5 `article_hash` used for image directory — that's the legacy image-dir namespace. Checkpoints use a SEPARATE sha256-16 hash from `lib.checkpoint.get_article_hash()`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/12-checkpoint-resume/12-CONTEXT.md
@.planning/phases/12-checkpoint-resume/12-00-SUMMARY.md
@lib/checkpoint.py
@ingest_wechat.py

<interfaces>
From lib/checkpoint.py (delivered by Plan 12-00):
```python
def get_article_hash(url: str) -> str: ...   # SHA256 [:16]
def has_stage(article_hash: str, stage: str) -> bool: ...
def read_stage(article_hash: str, stage: str) -> dict | list | str | bool | None: ...
def write_stage(article_hash: str, stage: str, data: dict | list | str | bytes | None = None) -> None: ...
def write_vision_description(article_hash: str, image_id: str, description: dict) -> None: ...
def write_metadata(article_hash: str, metadata: dict) -> None: ...

STAGE_FILES = {
    "scrape":         "01_scrape.html",
    "classify":       "02_classify.json",
    "image_download": "03_images/manifest.json",
    "text_ingest":    "04_text_ingest.done",
    "vision_worker":  "05_vision/",
    "sub_doc_ingest": "06_sub_doc_ingest.done",  # NEW 2026-05-01 D-SUBDOC
}
```

Current ingest_article stage map (from ingest_wechat.py lines 667-922):
1. **scrape**: 3-path cascade `scrape_wechat_ua` → `scrape_wechat_apify` → `scrape_wechat_mcp/cdp` (lines 743-769). Returns `article_data: dict` with `method`, `title`, `markdown` or `content_html`, `publish_time`, `img_urls`.
2. **classify**: Currently ABSENT inside ingest_article itself — classification lives in batch_ingest_from_spider.py (title-level) and Phase 10's scrape_first_classify (body-level). For Phase 12, classify step writes a placeholder record at the checkpoint (see Task 1 step 4).
3. **image_download**: `download_images` + `filter_small_images` (lines 799-810). Produces `url_to_path: dict[str, Path]` and `filter_stats`. Manifest = list of `{url, local_path, dimensions, filter_reason}`.
4. **text_ingest**: `rag.ainsert(full_content, ids=[doc_id])` (line 844). Mark `.done` AFTER this returns.
5. **vision_worker**: spawned as `asyncio.create_task(_vision_worker_impl(...))` (line 856). Each image's description goes into `05_vision/{image_id}.json` — partial completion acceptable.
6. **sub_doc_ingest** (NEW 2026-05-01 D-SUBDOC — absorbs v3.1 closure Finding 1): sub-doc LightRAG `ainsert` + entity extraction for all sub-doc chunks. Writes `06_sub_doc_ingest.done` marker on success. v3.1 Hermes prod run showed this needs ~5 min (only 2/7 chunks completed in the former 120s drain_timeout). Stage inherits Phase 9 single-article timeout `max(120 + 30 × chunks, 900)`. If `05_vision/` has zero success markers, marker is written immediately (no-op — nothing to sub-doc-ingest).

Hash note: current code computes `article_hash = hashlib.md5(url.encode()).hexdigest()[:10]` at line 689 for the images/{hash} dir. This is the LEGACY image hash. Phase 12 introduces a PARALLEL `ckpt_hash = get_article_hash(url)` (SHA256[:16]) used ONLY under checkpoints/{ckpt_hash}/. Both coexist — do NOT rename the legacy one.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Wrap ingest_article with checkpoint read/write at all 5 stage boundaries</name>
  <files>ingest_wechat.py</files>

  <read_first>
    - ingest_wechat.py lines 667-922 (the ingest_article function)
    - ingest_wechat.py lines 200-280 (_vision_worker_impl)
    - lib/checkpoint.py (get_article_hash, has_stage, read_stage, write_stage, write_vision_description, write_metadata)
    - .planning/phases/12-checkpoint-resume/12-CONTEXT.md §Resume Logic
  </read_first>

  <action>
**Integration plan — surgical additions only; do NOT restructure control flow.**

1. Add imports near existing `from lib import current_key, get_limiter` block:

```python
from lib.checkpoint import (
    get_article_hash as _ckpt_hash_fn,
    has_stage,
    read_stage,
    write_stage,
    write_vision_description,
    write_metadata,
)
```

2. At top of `ingest_article(url, rag=None)` body (right after `print(f"--- Starting Ingestion: {url} ---")`), compute checkpoint hash and bootstrap metadata:

```python
ckpt_hash = _ckpt_hash_fn(url)
write_metadata(ckpt_hash, {"url": url})
```

3. **Stage 1 — scrape**. Find `# 1. UA spoofing (primary...)` block (line ~742) and wrap the 3-path cascade:

```python
if has_stage(ckpt_hash, "scrape"):
    logger.info("checkpoint hit: scrape (hash=%s)", ckpt_hash)
    scraped_html = read_stage(ckpt_hash, "scrape")
    soup = BeautifulSoup(scraped_html, "html.parser")
    og = soup.find("meta", property="og:title")
    title = (og["content"] if og and og.has_attr("content") else None) or \
            (soup.title.string.strip() if soup.title and soup.title.string else "Untitled")
    publish_time = ""
    markdown, img_urls = process_content(scraped_html)
    article_data = {"method": "resumed", "title": title, "markdown": markdown,
                    "publish_time": publish_time, "img_urls": img_urls}
else:
    # EXISTING cascade body (lines 743-769, unchanged)
    article_data = await scrape_wechat_ua(url)
    if not article_data:
        article_data = await scrape_wechat_apify(url)
        # existing verification-page detection block unchanged
    if not article_data:
        if _is_mcp_endpoint(CDP_URL):
            article_data = await scrape_wechat_mcp(url)
        else:
            article_data = await scrape_wechat_cdp(url)
    if not article_data:
        print("Scraping failed (both Apify and browser fallback).")
        return None

    method = article_data.get("method", "unknown")
    if method == "apify":
        html_blob = f"<html><body><h1>{article_data.get('title','')}</h1>\n" \
                    f"{article_data.get('markdown','')}</body></html>"
    else:
        html_blob = article_data.get("content_html") or ""
    write_stage(ckpt_hash, "scrape", html_blob)
    write_metadata(ckpt_hash, {"title": article_data.get("title", "Untitled"),
                               "last_completed_stage": "scrape"})
```

The existing `method` discriminator logic below (`if method == "apify": ... elif method == "ua": ... else: ...`) must handle the new `method == "resumed"` value — route it through the `else` branch's markdown/img_urls extraction path (already prepared in the has_stage branch above; `article_data` already has markdown + img_urls populated, so downstream code that reads them works unchanged).

4. **Stage 2 — classify**. AFTER the scrape block, BEFORE image download:

```python
if has_stage(ckpt_hash, "classify"):
    logger.info("checkpoint hit: classify (hash=%s)", ckpt_hash)
    classification = read_stage(ckpt_hash, "classify")
else:
    # Phase 12 placeholder — Phase 13 can replace with real classify call.
    # The checkpoint PRESENCE is what CKPT-01/03 require.
    classification = {
        "depth": None,
        "topics": [],
        "rationale": "phase-12-placeholder",
        "model": None,
        "timestamp": time.time(),
    }
    write_stage(ckpt_hash, "classify", classification)
    write_metadata(ckpt_hash, {"last_completed_stage": "classify"})
```

5. **Stage 3 — image_download**. Find `unique_img_urls = list(dict.fromkeys(...))` (line ~799). Wrap:

```python
if has_stage(ckpt_hash, "image_download"):
    logger.info("checkpoint hit: image_download (hash=%s)", ckpt_hash)
    manifest = read_stage(ckpt_hash, "image_download")
    url_to_path = {entry["url"]: Path(entry["local_path"]) for entry in manifest
                   if entry.get("filter_reason") is None and entry.get("local_path")}
    # Reconstruct filter_stats best-effort from manifest.
    from image_pipeline import FilterStats as _FilterStats
    # Inspect FilterStats signature from image_pipeline; the existing shape uses:
    # kept / filtered_too_small / input. Adapt if the dataclass fields differ.
    kept_ct = len(url_to_path)
    too_small_ct = sum(1 for e in manifest if e.get("filter_reason") == "too_small")
    try:
        filter_stats = _FilterStats(input=len(manifest), kept=kept_ct,
                                    filtered_too_small=too_small_ct)
    except TypeError:
        # Fallback if FilterStats field names differ — construct empty instance
        filter_stats = _FilterStats()
    download_failed = sum(1 for e in manifest if e.get("filter_reason") == "download_failed_or_filtered")
    unique_img_urls = [e["url"] for e in manifest]
else:
    unique_img_urls = list(dict.fromkeys([u for u in img_urls if u.startswith('http')]))
    print(f"Found {len(unique_img_urls)} unique potential images. Downloading + filtering...")
    url_to_path = download_images(unique_img_urls, Path(article_dir))
    download_failed = len(unique_img_urls) - len(url_to_path)

    min_dim = int(os.environ.get("IMAGE_FILTER_MIN_DIM", 300))
    url_to_path, filter_stats = filter_small_images(url_to_path, min_dim=min_dim)
    print(f"Filtered {filter_stats.filtered_too_small} small images "
          f"(<{min_dim}px) — {filter_stats.kept} remaining")

    # Build + persist manifest
    manifest = []
    for u in unique_img_urls:
        entry = {"url": u, "local_path": None, "dimensions": None, "filter_reason": None}
        if u in url_to_path:
            p = url_to_path[u]
            entry["local_path"] = str(p)
            try:
                from PIL import Image
                with Image.open(p) as im:
                    entry["dimensions"] = list(im.size)
            except Exception:
                pass
        else:
            entry["filter_reason"] = "download_failed_or_filtered"
        manifest.append(entry)
    write_stage(ckpt_hash, "image_download", manifest)
    write_metadata(ckpt_hash, {"last_completed_stage": "image_download"})
```

6. **Stage 4 — text_ingest**. Find `await rag.ainsert(full_content, ids=[doc_id])` (line 844). Wrap:

```python
if has_stage(ckpt_hash, "text_ingest"):
    logger.info("checkpoint hit: text_ingest (hash=%s) — skipping rag.ainsert", ckpt_hash)
else:
    _register_pending_doc_id(article_hash, doc_id)
    await rag.ainsert(full_content, ids=[doc_id])
    _clear_pending_doc_id(article_hash)
    write_stage(ckpt_hash, "text_ingest")  # marker only
    write_metadata(ckpt_hash, {"last_completed_stage": "text_ingest"})
```

7. **Stage 5 — vision_worker**. Modify `_vision_worker_impl` signature to accept `ckpt_hash`:

```python
async def _vision_worker_impl(
    rag, article_hash, url_to_path, title,
    filter_stats, download_input_count, download_failed,
    ckpt_hash,  # NEW
):
```

Inside the describe-images loop (after `descriptions = describe_images(paths_list) if paths_list else {}`), add per-image checkpoint writes:

```python
for img_path, desc_text in descriptions.items():
    # EXISTING sub-doc build code unchanged ...

    # NEW: per-image checkpoint (never raises — fire-and-forget).
    image_id = Path(img_path).stem  # "img_0" from "img_0.jpg"
    try:
        write_vision_description(ckpt_hash, image_id, {
            "provider": "cascade",  # Phase 13 will replace with real provider name
            "description": desc_text,
            "latency_ms": None,
            "timestamp": time.time(),
        })
    except Exception as e:
        logger.warning("vision checkpoint write failed for %s: %s", image_id, e)
```

Update the call site at line 856 to pass `ckpt_hash=ckpt_hash`:

```python
vision_task = asyncio.create_task(_vision_worker_impl(
    rag=rag,
    article_hash=article_hash,
    url_to_path=url_to_path,
    title=title,
    filter_stats=filter_stats,
    download_input_count=len(unique_img_urls),
    download_failed=download_failed,
    ckpt_hash=ckpt_hash,  # NEW
))
```

8. **Stage 6 — sub_doc_ingest (NEW 2026-05-01 D-SUBDOC — absorbs v3.1 Finding 1)**. Add a new guarded stage AFTER the vision_task is created. The sub-doc stage runs synchronously inside `ingest_article` (not as an async task) so its success maps 1:1 to a checkpoint marker. This is the remediation path for articles whose former `drain_timeout=120s` abandoned sub-doc entity extraction.

   **Pattern (after the `vision_task = asyncio.create_task(...)` line in step 7):**

   ```python
   # Stage 6: sub_doc_ingest (D-SUBDOC 2026-05-01).
   # Await the async Vision worker result so we know which images got descriptions,
   # then run a SYNCHRONOUS sub-doc ainsert bounded by single-article timeout
   # formula max(120 + 30 × chunk_count, 900) instead of the legacy 120s drain.
   if has_stage(ckpt_hash, "sub_doc_ingest"):
       logger.info("checkpoint hit: sub_doc_ingest (hash=%s)", ckpt_hash)
   else:
       try:
           # Wait for Vision worker to finish (cancel any drain_timeout — sub-doc
           # lifecycle is now checkpoint-owned, not timer-bounded).
           await vision_task
       except Exception as e:
           logger.warning("vision_task raised on await (sub-doc will skip): %s", e)

       # Read cached Vision descriptions from 05_vision/*.json. No re-Vision-API-calls.
       from lib.checkpoint import list_vision_markers  # new helper
       vision_successes = list_vision_markers(ckpt_hash)  # returns [{image_id, provider, description, ...}]

       if vision_successes:
           # Build sub-doc text from cached descriptions + ainsert once.
           # Inherits Phase 9 single-article timeout: max(120 + 30 × chunks, 900).
           sub_doc_text = _build_sub_doc_from_vision(title, vision_successes)
           single_article_timeout = max(120 + 30 * estimate_chunk_count(sub_doc_text), 900)
           try:
               await asyncio.wait_for(
                   rag.ainsert(sub_doc_text, ids=[f"{doc_id}__subdoc"]),
                   timeout=single_article_timeout,
               )
               write_stage(ckpt_hash, "sub_doc_ingest")  # empty marker
               write_metadata(ckpt_hash, {"last_completed_stage": "sub_doc_ingest"})
           except asyncio.TimeoutError:
               logger.warning(
                   "sub_doc_ingest timeout after %ds (hash=%s) — will retry on resume",
                   single_article_timeout, ckpt_hash,
               )
               # Do NOT write marker; next run will resume this stage only.
       else:
           # No Vision successes — sub-doc has nothing to ingest. Write marker
           # immediately so resume logic does not loop on this article forever.
           logger.info("no vision successes, skipping sub_doc_ingest (hash=%s)", ckpt_hash)
           write_stage(ckpt_hash, "sub_doc_ingest")
           write_metadata(ckpt_hash, {"last_completed_stage": "sub_doc_ingest"})
   ```

   **Phase 13 coordination:** Phase 13 Vision Cascade will populate `provider` / `latency_ms` in each `05_vision/*.json` with real values. Phase 12's step 7 currently writes `"provider": "cascade"` as a placeholder — Phase 13 replaces this.

   **`lib/checkpoint.py` addition:** `list_vision_markers(article_hash) -> list[dict]` reads every `05_vision/*.json` file and returns the parsed dicts. If the `05_vision/` dir is missing or empty, returns `[]`. This is a small read-only helper; extend 12-00 Task 1's module API.

9. **Surgical self-check**: grep the diff for any line NOT related to checkpoint wiring. Remove those. Every new line traces to a CKPT-* requirement.

10. Run existing tests to confirm no regression:

```
.venv/Scripts/python -m pytest tests/unit/test_text_first_ingest.py tests/unit/test_vision_worker.py tests/unit/test_scrape_first_classify.py -v
```

If `test_vision_worker.py` breaks due to the new `ckpt_hash` parameter, update its call sites to pass a test hash (e.g. `ckpt_hash="0" * 16`). This is minor fixture maintenance, not a test-logic change.
  </action>

  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_text_first_ingest.py tests/unit/test_vision_worker.py tests/unit/test_scrape_first_classify.py -v</automated>
  </verify>

  <acceptance_criteria>
    - `grep -q "from lib.checkpoint import" ingest_wechat.py`
    - `grep -q "has_stage(ckpt_hash, \"scrape\")" ingest_wechat.py`
    - `grep -q "has_stage(ckpt_hash, \"classify\")" ingest_wechat.py`
    - `grep -q "has_stage(ckpt_hash, \"image_download\")" ingest_wechat.py`
    - `grep -q "has_stage(ckpt_hash, \"text_ingest\")" ingest_wechat.py`
    - `grep -q "has_stage(ckpt_hash, \"sub_doc_ingest\")" ingest_wechat.py` (D-SUBDOC 2026-05-01 — absorbs v3.1 Finding 1)
    - `grep -q "list_vision_markers" ingest_wechat.py` (sub-doc reads cached Vision descriptions)
    - `grep -q "write_vision_description" ingest_wechat.py`
    - `grep -q "write_metadata(ckpt_hash" ingest_wechat.py` (metadata updated at least once)
    - `grep -q "checkpoint hit:" ingest_wechat.py` (log message for skips)
    - `grep -q "hashlib.md5" ingest_wechat.py` (LEGACY image hash preserved — surgical)
    - `.venv/Scripts/python -c "import ingest_wechat; assert hasattr(ingest_wechat, 'ingest_article')"` exits 0
    - `.venv/Scripts/python -m pytest tests/unit/test_text_first_ingest.py tests/unit/test_vision_worker.py tests/unit/test_scrape_first_classify.py -v` exits 0 (no regression)
  </acceptance_criteria>

  <done>All 6 stages guarded by has_stage/write_stage (scrape, classify, image_download, text_ingest, vision_worker, sub_doc_ingest); existing Phase 10 tests still pass after fixture adjustments for the new ckpt_hash parameter; legacy MD5 image hash untouched; D-SUBDOC (v3.1 Finding 1 remediation) wired through.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Integration tests — skip-on-resume for each of the 5 stages</name>
  <files>tests/unit/test_checkpoint_ingest_integration.py</files>

  <read_first>
    - ingest_wechat.py (after Task 1 changes — find the 5 has_stage guards)
    - lib/checkpoint.py (write_stage, write_metadata signatures)
    - tests/unit/test_text_first_ingest.py (existing mock pattern for scrape/ainsert)
    - tests/unit/test_vision_worker.py (existing mock pattern for describe_images)
    - .planning/phases/12-checkpoint-resume/12-CONTEXT.md §Specific Ideas — "Failure Injection Test Recipe"
  </read_first>

  <behavior>
    Mock-based tests. No real network, no real LightRAG, no real Gemini.

    Test matrix (one test per row, parametrize where useful):

    - test_fresh_run_writes_all_five_stages:
        Mock every stage. Call ingest_article(url). Assert all 5 stage files exist afterward.

    - test_second_run_skips_scrape_when_scrape_checkpoint_present:
        Pre-seed `write_stage(hash, "scrape", "<html>cached</html>")`. Call ingest_article.
        Assert scrape_wechat_ua / scrape_wechat_apify / scrape_wechat_cdp mocks were NOT called.

    - test_second_run_skips_classify_when_classify_checkpoint_present:
        Pre-seed scrape + classify. Call ingest_article. Assert classify placeholder is READ, not re-generated (via log capture "checkpoint hit: classify").

    - test_second_run_skips_image_download_when_image_download_checkpoint_present:
        Pre-seed scrape + classify + image_download manifest. Assert download_images mock NOT called; url_to_path reconstructed from manifest.

    - test_second_run_skips_text_ingest_when_text_ingest_checkpoint_present:
        Pre-seed all through text_ingest. Assert rag.ainsert NOT called for parent doc.

    - test_failure_at_image_download_preserves_scrape_and_classify_checkpoints:
        Let scrape + classify succeed. Inject RuntimeError in download_images mock. Assert RuntimeError propagates; assert scrape + classify checkpoints EXIST; image_download manifest does NOT exist.

    - test_rerun_after_image_download_failure_skips_scrape_and_classify:
        Following the previous state, remove the RuntimeError mock. Re-call ingest_article. Assert scrape + classify NOT re-run (checkpoint hits logged); image_download IS run and its manifest is written.

    - test_vision_worker_writes_per_image_checkpoints:
        Mock describe_images to return {Path("img_0.jpg"): "desc A", Path("img_1.jpg"): "desc B"}. Run the Vision worker. Assert `05_vision/img_0.json` and `05_vision/img_1.json` exist with `{"description": ...}` content.

    - test_vision_checkpoint_write_failure_does_not_break_worker:
        Monkeypatch `lib.checkpoint.write_vision_description` to raise. Assert the Vision worker completes (fire-and-forget); assert a warning is logged.

    Fixture pattern (CRITICAL):
    - Use the same `OMNIGRAPH_CHECKPOINT_BASE_DIR` env-override from Plan 12-01 to redirect BASE_DIR to `tmp_path`.
    - Mock the 3 scrape functions to return a canned `article_data` dict.
    - Mock `download_images` to return `{url: tmp_path / "img_N.jpg"}` with stub JPEG bytes so PIL can read dimensions.
    - Mock `rag = MagicMock(); rag.ainsert = AsyncMock()` for the LightRAG seam.
    - Mock `describe_images` for Vision worker tests.
    - Mock `extract_entities` to return `[]` (we're not exercising Cognee here).
  </behavior>

  <action>
Create `tests/unit/test_checkpoint_ingest_integration.py`:

```python
"""Integration tests: checkpoint skip-on-resume across ingest_article stages.

Every stage transition must be guarded by a has_stage check; this test suite
proves each guard skips correctly when the prior checkpoint is pre-seeded.

All network + LightRAG + Vision calls are mocked — these tests are fast and
deterministic.
"""
import asyncio
import importlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _checkpoint_base(monkeypatch, tmp_path):
    base = tmp_path / "omonigraph-vault"
    base.mkdir(parents=True)
    monkeypatch.setenv("OMNIGRAPH_CHECKPOINT_BASE_DIR", str(base))
    import lib.checkpoint as ckpt
    importlib.reload(ckpt)
    yield ckpt


@pytest.fixture
def sample_url():
    return "https://mp.weixin.qq.com/s/test-article-12"


@pytest.fixture
def fake_article_data():
    return {
        "method": "ua",
        "title": "Test Article",
        "publish_time": "2026-04-30",
        "content_html": "<html><body><h1>Test</h1><p>Body text</p>"
                        "<img src='https://cdn.test/img0.jpg'/></body></html>",
        "img_urls": ["https://cdn.test/img0.jpg"],
    }


@pytest.fixture
def mock_ingest_deps(monkeypatch, tmp_path, fake_article_data):
    """Mock everything ingest_article touches except the checkpoint lib."""
    import ingest_wechat as iw

    async def fake_ua(url): return fake_article_data
    async def fake_apify(url): return None
    async def fake_cdp(url): return None
    async def fake_mcp(url): return None

    monkeypatch.setattr(iw, "scrape_wechat_ua", fake_ua)
    monkeypatch.setattr(iw, "scrape_wechat_apify", fake_apify)
    monkeypatch.setattr(iw, "scrape_wechat_cdp", fake_cdp)
    monkeypatch.setattr(iw, "scrape_wechat_mcp", fake_mcp)

    def fake_download(urls, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        result = {}
        for i, u in enumerate(urls):
            p = out_dir / f"img_{i}.jpg"
            # Write 1x1 transparent PNG bytes — PIL can open.
            p.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
                b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            result[u] = p
        return result
    monkeypatch.setattr(iw, "download_images", fake_download)

    # Keep filter_small_images as identity (all images pass; 1x1 PNG will actually be filtered
    # by min_dim=300, so stub it to return everything).
    def fake_filter(url_to_path, min_dim):
        from image_pipeline import FilterStats
        try:
            stats = FilterStats(input=len(url_to_path), kept=len(url_to_path),
                                filtered_too_small=0)
        except TypeError:
            stats = FilterStats()
        return url_to_path, stats
    monkeypatch.setattr(iw, "filter_small_images", fake_filter)

    async def fake_extract_entities(content): return []
    monkeypatch.setattr(iw, "extract_entities", fake_extract_entities)

    rag = MagicMock()
    rag.ainsert = AsyncMock()

    async def fake_get_rag(flush=True): return rag
    monkeypatch.setattr(iw, "get_rag", fake_get_rag)

    # Stub the Vision worker so tests don't need Gemini.
    async def fake_vision_worker(**kwargs): return None
    monkeypatch.setattr(iw, "_vision_worker_impl", fake_vision_worker)

    # Stub cognee_wrapper.remember_article
    async def fake_remember(**kwargs): return None
    monkeypatch.setattr(iw.cognee_wrapper, "remember_article", fake_remember)

    # Redirect BASE_IMAGE_DIR
    monkeypatch.setattr(iw, "BASE_IMAGE_DIR", str(tmp_path / "images"))
    os.makedirs(str(tmp_path / "images"), exist_ok=True)

    return iw, rag, fake_article_data


@pytest.mark.asyncio
async def test_fresh_run_writes_all_five_stages(_checkpoint_base, mock_ingest_deps, sample_url):
    iw, rag, _ = mock_ingest_deps
    await iw.ingest_article(sample_url)
    h = _checkpoint_base.get_article_hash(sample_url)
    assert _checkpoint_base.has_stage(h, "scrape")
    assert _checkpoint_base.has_stage(h, "classify")
    assert _checkpoint_base.has_stage(h, "image_download")
    assert _checkpoint_base.has_stage(h, "text_ingest")
    # vision_worker is stubbed — no per-image files expected in this test


@pytest.mark.asyncio
async def test_skip_scrape_when_cached(_checkpoint_base, mock_ingest_deps, sample_url, caplog):
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])

    # Replace scrape mocks with ones that would FAIL if called.
    called = {"ua": 0, "apify": 0, "cdp": 0}
    async def boom_ua(url): called["ua"] += 1; return None
    async def boom_apify(url): called["apify"] += 1; return None
    async def boom_cdp(url): called["cdp"] += 1; return None
    with patch.object(iw, "scrape_wechat_ua", boom_ua), \
         patch.object(iw, "scrape_wechat_apify", boom_apify), \
         patch.object(iw, "scrape_wechat_cdp", boom_cdp):
        caplog.set_level("INFO")
        await iw.ingest_article(sample_url)

    assert called == {"ua": 0, "apify": 0, "cdp": 0}
    assert "checkpoint hit: scrape" in caplog.text


@pytest.mark.asyncio
async def test_skip_image_download_when_manifest_exists(_checkpoint_base, mock_ingest_deps,
                                                        sample_url, tmp_path, caplog):
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])
    _checkpoint_base.write_stage(h, "classify", {
        "depth": None, "topics": [], "rationale": "seeded", "model": None, "timestamp": 0
    })
    p = tmp_path / "cached-img.jpg"
    p.write_bytes(b"fakejpeg")
    _checkpoint_base.write_stage(h, "image_download", [
        {"url": "https://cdn.test/img0.jpg", "local_path": str(p),
         "dimensions": [400, 400], "filter_reason": None}
    ])

    called = {"download": 0}
    def boom_download(urls, out_dir): called["download"] += 1; return {}
    with patch.object(iw, "download_images", boom_download):
        caplog.set_level("INFO")
        await iw.ingest_article(sample_url)

    assert called["download"] == 0
    assert "checkpoint hit: image_download" in caplog.text


@pytest.mark.asyncio
async def test_skip_text_ingest_when_done_marker(_checkpoint_base, mock_ingest_deps,
                                                  sample_url, caplog):
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])
    _checkpoint_base.write_stage(h, "classify", {"depth": None, "topics": [],
                                                  "rationale": "x", "model": None, "timestamp": 0})
    _checkpoint_base.write_stage(h, "image_download", [])
    _checkpoint_base.write_stage(h, "text_ingest")

    rag.ainsert.reset_mock()
    caplog.set_level("INFO")
    await iw.ingest_article(sample_url)

    rag.ainsert.assert_not_called()
    assert "checkpoint hit: text_ingest" in caplog.text


@pytest.mark.asyncio
async def test_failure_at_image_download_preserves_prior_checkpoints(
    _checkpoint_base, mock_ingest_deps, sample_url
):
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)

    def bad_download(urls, out_dir): raise RuntimeError("simulated download failure")
    with patch.object(iw, "download_images", bad_download):
        with pytest.raises(RuntimeError, match="simulated"):
            await iw.ingest_article(sample_url)

    assert _checkpoint_base.has_stage(h, "scrape")
    assert _checkpoint_base.has_stage(h, "classify")
    assert not _checkpoint_base.has_stage(h, "image_download")
    assert not _checkpoint_base.has_stage(h, "text_ingest")


@pytest.mark.asyncio
async def test_resume_after_image_download_failure(
    _checkpoint_base, mock_ingest_deps, sample_url, caplog
):
    iw, rag, art = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    # Seed the "after-first-failure" state.
    _checkpoint_base.write_stage(h, "scrape", art["content_html"])
    _checkpoint_base.write_stage(h, "classify", {"depth": None, "topics": [],
                                                  "rationale": "x", "model": None, "timestamp": 0})

    called = {"ua": 0}
    async def count_ua(url): called["ua"] += 1; return art
    with patch.object(iw, "scrape_wechat_ua", count_ua):
        caplog.set_level("INFO")
        await iw.ingest_article(sample_url)

    assert called["ua"] == 0
    assert "checkpoint hit: scrape" in caplog.text
    assert "checkpoint hit: classify" in caplog.text
    assert _checkpoint_base.has_stage(h, "image_download")
    assert _checkpoint_base.has_stage(h, "text_ingest")


@pytest.mark.asyncio
async def test_vision_worker_writes_per_image_checkpoints(_checkpoint_base, sample_url, tmp_path):
    """Unit-test the Vision checkpoint write inside _vision_worker_impl."""
    import ingest_wechat as iw
    h = _checkpoint_base.get_article_hash(sample_url)

    # Prepare URL→path map pointing to real temp files (PIL doesn't need to open them here).
    p0 = tmp_path / "img_0.jpg"; p0.write_bytes(b"\xff")
    p1 = tmp_path / "img_1.jpg"; p1.write_bytes(b"\xff")
    url_to_path = {"https://a/0": p0, "https://a/1": p1}

    rag = MagicMock(); rag.ainsert = AsyncMock()

    def fake_describe(paths):
        return {p0: "description A", p1: "description B"}

    from image_pipeline import FilterStats
    try:
        fs = FilterStats(input=2, kept=2, filtered_too_small=0)
    except TypeError:
        fs = FilterStats()

    with patch("ingest_wechat.describe_images", fake_describe):
        await iw._vision_worker_impl(
            rag=rag, article_hash="legacy_hash", url_to_path=url_to_path,
            title="T", filter_stats=fs, download_input_count=2, download_failed=0,
            ckpt_hash=h,
        )

    vision_dir = _checkpoint_base.get_checkpoint_dir(h) / "05_vision"
    assert (vision_dir / "img_0.json").exists()
    assert (vision_dir / "img_1.json").exists()
    content_0 = json.loads((vision_dir / "img_0.json").read_text())
    assert content_0["description"] == "description A"


@pytest.mark.asyncio
async def test_vision_checkpoint_write_failure_is_swallowed(
    _checkpoint_base, sample_url, tmp_path, caplog
):
    """If write_vision_description raises, the Vision worker must still complete."""
    import ingest_wechat as iw
    h = _checkpoint_base.get_article_hash(sample_url)

    p0 = tmp_path / "img_0.jpg"; p0.write_bytes(b"\xff")
    rag = MagicMock(); rag.ainsert = AsyncMock()

    from image_pipeline import FilterStats
    try:
        fs = FilterStats(input=1, kept=1, filtered_too_small=0)
    except TypeError:
        fs = FilterStats()

    def bad_write(*a, **kw): raise IOError("disk full")

    with patch("ingest_wechat.describe_images", lambda paths: {p0: "desc"}), \
         patch("ingest_wechat.write_vision_description", bad_write):
        caplog.set_level("WARNING")
        # Must NOT raise.
        await iw._vision_worker_impl(
            rag=rag, article_hash="legacy_hash", url_to_path={"https://a/0": p0},
            title="T", filter_stats=fs, download_input_count=1, download_failed=0,
            ckpt_hash=h,
        )
    assert "vision checkpoint write failed" in caplog.text
```

Add `import pytest_asyncio` is NOT needed if `pytest-asyncio` is already a dependency (check via `grep pytest-asyncio requirements.txt`). If not present, mark tests with `@pytest.mark.asyncio` and document the dependency addition.

If `pytest-asyncio` is missing, use the simpler `asyncio.run()` pattern:
```python
def test_X(...):
    asyncio.run(_async_body())
```
Executor picks based on what's already in requirements.txt. Check first with: `grep asyncio requirements.txt`.

Run the tests:
```
.venv/Scripts/python -m pytest tests/unit/test_checkpoint_ingest_integration.py -v
```

Fix any failures by adjusting the Task 1 ingest_wechat.py integration, not the test expectations. The test expectations ARE the resume-logic contract.
  </action>

  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_checkpoint_ingest_integration.py -v</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "^async def test_\|^def test_" tests/unit/test_checkpoint_ingest_integration.py` >= 8
    - `grep -q "def test_fresh_run_writes_all_five_stages" tests/unit/test_checkpoint_ingest_integration.py`
    - `grep -q "def test_failure_at_image_download_preserves_prior_checkpoints" tests/unit/test_checkpoint_ingest_integration.py`
    - `grep -q "def test_resume_after_image_download_failure" tests/unit/test_checkpoint_ingest_integration.py`
    - `grep -q "def test_vision_worker_writes_per_image_checkpoints" tests/unit/test_checkpoint_ingest_integration.py`
    - `.venv/Scripts/python -m pytest tests/unit/test_checkpoint_ingest_integration.py -v` exits 0 (all tests pass)
    - Existing Phase 10 tests still pass: `.venv/Scripts/python -m pytest tests/unit/test_text_first_ingest.py tests/unit/test_vision_worker.py -v` exits 0
  </acceptance_criteria>

  <done>8+ integration tests prove skip-on-resume for each stage and Vision per-image persistence; no regressions in Phase 10 tests.</done>
</task>

</tasks>

<verification>
1. Task 1 produces ingest_wechat.py with 5 has_stage guards (grep confirms all 5 stage names appear in has_stage calls)
2. Task 2 integration tests all pass
3. Existing Phase 10 test suite still passes (no regression)
4. Unit test from 12-00 still passes: `.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py -v`
</verification>

<success_criteria>
- 5 has_stage() guards present in ingest_wechat.py, one per stage
- Pre-seeding a checkpoint causes that stage's work to be skipped (verified by 5 tests, one per stage)
- Failure at stage N preserves checkpoints 1..N-1 (verified by test_failure_at_image_download_preserves_prior_checkpoints)
- Resume after failure skips completed stages (verified by test_resume_after_image_download_failure)
- Per-image vision checkpoints written (verified by test_vision_worker_writes_per_image_checkpoints)
- Surgical: legacy MD5 image-dir hash preserved; no other pipeline logic touched
- Zero regressions in tests/unit/test_text_first_ingest.py or tests/unit/test_vision_worker.py
</success_criteria>

<output>
After completion, create `.planning/phases/12-checkpoint-resume/12-02-SUMMARY.md` with:
- Diff summary: lines added / removed in ingest_wechat.py (target: < 150 lines added, 0 removed from existing pipeline logic)
- Test count + pass rate
- Any API-contract adjustments from <interfaces> (e.g. ckpt_hash passed to _vision_worker_impl)
- Files modified: `ingest_wechat.py` (edit), `tests/unit/test_checkpoint_ingest_integration.py` (new)
</output>

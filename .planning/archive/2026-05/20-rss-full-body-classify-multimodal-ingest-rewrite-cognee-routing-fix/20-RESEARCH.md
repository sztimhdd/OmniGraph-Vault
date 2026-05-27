# Phase 20: RSS Full-Body Classify + Multimodal Ingest Rewrite + Cognee Routing Fix — Research

**Researched:** 2026-05-06
**Domain:** Python async pipeline — RSS classify upgrade, LightRAG multimodal ingest, Cognee detach pattern
**Confidence:** HIGH (all findings from direct codebase reads; no speculative claims)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

| ID | Decision |
|----|----------|
| D-20.01 | Import `_build_fullbody_prompt`, `_call_fullbody_llm`, `FULLBODY_TRUNCATION_CHARS` from `batch_classify_kol` — do NOT copy the code |
| D-20.02 | RSS classify result columns: `depth_score INT`, `topics TEXT` (JSON array), `classify_rationale TEXT` — existing Phase 19 schema, no new columns |
| D-20.03 | `FULLBODY_THROTTLE_SECONDS = 4.5` replaces `THROTTLE_SECONDS = 0.3` in `rss_classify.py` |
| D-20.04 | `rss_classify.py` fetches `body` from DB; if `body IS NULL`, calls `_scrape_article_body(url)` inline to populate it before classification |
| D-20.05 | RSS LightRAG doc_id stays `f"rss-{article_id}"`, sub-doc stays `f"rss-{article_id}_images"` |
| D-20.06 | LightRAG `adelete_by_doc_id` must be called with **both** doc_ids on rollback — primary AND sub-doc |
| D-20.07 | `rss_ingest.py` rewrite imports and reuses `image_pipeline.{download_images, localize_markdown, describe_images}` directly — no copy |
| D-20.08 | Add `referer: str | None = None` parameter to `download_images` in `image_pipeline.py` |
| D-20.09 | SVG content-type filter in `download_images`: skip if `Content-Type` starts with `image/svg` |
| D-20.10 | RSS per-article timeout: `max(120 + 30 * chunk_count, 900)` — identical to KOL Phase 9 formula |
| D-20.11 | Per-module `_pending_doc_ids` tracker dict in `enrichment/rss_ingest` — do NOT share with `ingest_wechat` |
| D-20.12 | On TimeoutError: drain (cap_seconds=120) → `adelete_by_doc_id` → leave `enriched` column unchanged |
| D-20.13 | COG-02 mock test: mock `cognee.remember` to `asyncio.sleep(10)`, assert `remember_article` returns in < 100ms |
| D-20.14 | COG-03 retirement gate: live Hermes 3-article smoke required before removing `OMNIGRAPH_COGNEE_INLINE` gate |
| D-20.15 | If COG-02 mock fails: wrap `remember_article` call in `asyncio.create_task` (fire-and-forget) |
| D-20.16 | Reuse `lib/checkpoint.py` for RSS 5-stage markers: `01_scrape, 02_classify, 03_image_download, 04_text_ingest, 05_vision_worker` |

### Claude's Discretion
- Implementation order within each wave (RCL, RIN, COG sub-tasks)
- Whether to add `cap_seconds` to existing `_drain_pending_vision_tasks` or inline a local drain helper in `enrichment/rss_ingest.py`
- Exact test fixture structure for `test_rss_ingest_5stage.py`

### Deferred Ideas (OUT OF SCOPE)
- EN→CN translation (explicitly excluded from v3.4 per REQUIREMENTS.md)
- E2R-01 "enriched rate >= 60%" fixture (deferred to Phase 21)
- Vertex AI migration (post-Milestone B)
- Graded pre-scrape classification / title+excerpt probe (v3.5 candidate)
- Reject-reason versioning (`skip_reason_version` field)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RCL-01 | RSS classify reads `body` column; if NULL scrapes inline, then calls `_build_fullbody_prompt` + `_call_fullbody_llm` imported from `batch_classify_kol` | Verified: import chain safe; `rss_classify.py` already imports `get_deepseek_api_key` from `batch_classify_kol` — no new circular risk |
| RCL-02 | Throttle constant renamed `FULLBODY_THROTTLE_SECONDS = 4.5`; per-topic loop replaced by single multi-topic call matching Phase 10 KOL pattern | Verified: `_build_fullbody_prompt` accepts `topic_filter: list[str] | None`; returns single JSON with all topics |
| RCL-03 | Article-level daily cap check gates out articles after body-classification cost is known | Confirmed: existing `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP` env var governs this gate |
| RIN-01 | 5-stage ingest: `01_scrape -> 02_classify -> 03_image_download -> 04_text_ingest -> 05_vision_worker` via `lib/checkpoint.py` | Verified: `lib/checkpoint.py` `write_stage()` API uses short keys (`scrape`, `classify`, etc.) — see mismatch note below |
| RIN-02 | `download_images` gains `referer: str | None = None` + SVG content-type filter | Verified: current signature has no referer; addition is backward-compatible |
| RIN-03 | Per-module `_pending_doc_ids` tracker in `enrichment/rss_ingest` (not shared with `ingest_wechat`) | Confirmed: `ingest_wechat._PENDING_DOC_IDS` is module-scoped; RSS gets its own dict |
| RIN-04 | TimeoutError rollback: drain 120s -> `adelete_by_doc_id` on both doc_ids -> no `enriched` update | Verified: `adelete_by_doc_id` is the correct LightRAG cleanup API |
| RIN-05 | Vision sub-doc `f"rss-{article_id}_images"` with same format as WeChat sub-doc | Confirmed: `ingest_wechat._vision_worker_impl` writes `# Images for {title}\n\n- [image {i}]: {desc}  ({local_url})\n` — RSS must match |
| RIN-06 | `_build_contents` regex `http://localhost:8765/\S+?\.(?:jpg|jpeg|png)` must match `localize_markdown` output | Verified: `lib/lightrag_embedding.py:_IMAGE_URL_PATTERN` matches `http://localhost:8765/{hash}/{n}.jpg`; RSS must use `get_article_hash(url)` (SHA-256[:16]) for image paths |
| COG-02 | `remember_article` detaches from main pipeline: mock test returns in < 100ms | Research shows current `asyncio.wait_for(timeout=5.0)` blocks ~5s — D-20.15 `asyncio.create_task` wrap IS required |
| COG-03 | Retire `OMNIGRAPH_COGNEE_INLINE` gate after live 3-article Hermes smoke | Verified: gate in `ingest_wechat.py:_cognee_inline_enabled()` / lines 1167-1176; retirement gated on live smoke per D-20.14 |
</phase_requirements>

---

## Summary

Phase 20 upgrades three subsystems in parallel: (1) RSS classify switches from a per-topic summary-string prompt to a single multi-topic full-body LLM call by importing shared functions from `batch_classify_kol`; (2) the RSS ingest rewrite adds a 5-stage checkpoint-aware pipeline with image download, vision description, and per-article timeout/rollback matching the KOL pattern; (3) Cognee `remember_article` is refactored to fire-and-forget (`asyncio.create_task`) so a blocked Cognee call cannot stall article ingestion.

All three deliverables build directly on Phase 19 schema (`body`, `depth_score`, `topics`, `classify_rationale` columns) which is already present in the DB. The core challenge is that several D-decisions reference function signatures or behaviors that do not yet exist in the codebase and must be implemented — most notably the `cap_seconds` drain parameter (D-20.12), the `referer` download parameter (D-20.08/09), and the Cognee detach refactor (D-20.15).

**Primary recommendation:** Implement in wave order RCL -> RIN -> COG. RCL unblocks RIN (full-body classify is needed before 5-stage ingest makes sense); COG-02 can be done in parallel once the file structure is clear. Each wave has independent unit tests that can be green-lit before moving to the next.

---

## Standard Stack

### Core (already installed — no new packages)

| Library | Version | Purpose | Note |
|---------|---------|---------|------|
| `asyncio` (stdlib) | 3.11+ | Async pipeline, `create_task`, `wait_for` | No install needed |
| `lightrag` | pinned in requirements.txt | KG engine — `ainsert`, `aquery`, `adelete_by_doc_id` | Already used by `ingest_wechat` |
| `cognee` | pinned in requirements.txt | Memory layer — `cognee.remember` | Already used by `cognee_wrapper` |
| `lib/checkpoint.py` | project-local | 5-stage checkpoint markers | Already exists — reuse as-is |
| `lib/image_pipeline.py` | project-local | `download_images`, `localize_markdown`, `describe_images` | Needs `referer` param added |
| `batch_classify_kol.py` | project-local | `_build_fullbody_prompt`, `_call_fullbody_llm` | Safe import — already used by rss_classify |

### No new packages required

Phase 20 is a rewrite/upgrade of existing code. All dependencies are already installed. No `pip install` steps needed.

---

## Architecture Patterns

### Recommended Module Structure (post-Phase 20)

```
enrichment/
    rss_classify.py        # upgraded: full-body classify, FULLBODY_THROTTLE_SECONDS=4.5
    rss_ingest.py          # rewrite: 5-stage pipeline, _pending_doc_ids tracker
    rss_schema.py          # unchanged (Phase 19 schema already complete)
    rss_fetch.py           # unchanged
lib/
    checkpoint.py          # unchanged (reused for RSS stages)
    image_pipeline.py      # add referer param + SVG filter to download_images
cognee_wrapper.py          # add asyncio.create_task wrap in remember_article
batch_classify_kol.py      # unchanged (only import from here, no edits)
```

### Pattern 1: Import-not-copy (D-20.01)

The `_build_fullbody_prompt` and `_call_fullbody_llm` functions in `batch_classify_kol.py` are private (single-underscore) but importable. `rss_classify.py` already imports `get_deepseek_api_key` from the same module, establishing the import chain is safe.

```python
# enrichment/rss_classify.py -- add to existing imports
from batch_classify_kol import (
    _build_fullbody_prompt,
    _call_fullbody_llm,
    FULLBODY_TRUNCATION_CHARS,
)

FULLBODY_THROTTLE_SECONDS = 4.5  # replaces THROTTLE_SECONDS = 0.3
```

### Pattern 2: 5-Stage RSS Ingest with Checkpoint

```python
# enrichment/rss_ingest.py -- per-article pipeline sketch
async def _ingest_one_article(rag, db, row: dict) -> bool:
    url = row["url"]
    article_hash = get_article_hash(url)    # lib/checkpoint.py SHA-256[:16]
    ckpt = CheckpointDir(article_hash)      # lib/checkpoint.py

    # Stage 01: scrape (body already in DB from classify step)
    if not ckpt.stage_done("scrape"):
        body = row["body"] or await _scrape_article_body(url)
        ckpt.write_stage("scrape", body.encode())

    # Stage 02: classify gate (depth_score already set by rss_classify.py)
    if not ckpt.stage_done("classify"):
        ckpt.write_stage("classify", b"done")

    # Stage 03: image download
    if not ckpt.stage_done("image_download"):
        image_urls = _extract_image_urls(row["body"])
        dest_dir = BASE_IMAGE_DIR / article_hash
        url_to_path = download_images(image_urls, dest_dir, referer=url)  # D-20.08
        ckpt.write_stage("image_download", json.dumps({...}).encode())

    # Stage 04: text ingest
    doc_id = f"rss-{row['article_id']}"
    if not ckpt.stage_done("text_ingest"):
        localized = localize_markdown(row["body"], url_to_path, article_hash)
        budget_s = max(120 + 30 * max(1, len(localized) // 1000), 900)  # D-20.10
        await asyncio.wait_for(rag.ainsert(localized, ids=[doc_id]), timeout=budget_s)
        _pending_doc_ids[article_hash] = doc_id
        ckpt.write_stage("text_ingest", b"done")

    # Stage 05: vision worker
    if not ckpt.stage_done("vision_worker"):
        task = asyncio.create_task(_vision_worker_rss(rag=rag, ...))
        _pending_doc_ids[f"{article_hash}_images"] = f"rss-{row['article_id']}_images"
        await _drain_rss_vision_tasks(cap_seconds=120)
        ckpt.write_stage("vision_worker", b"done")

    del _pending_doc_ids[article_hash]
    return True
```

### Pattern 3: Cognee Fire-and-Forget (D-20.15)

```python
# cognee_wrapper.py -- remember_article refactor
async def remember_article(title: str, url: str, entities: list, summary_gist: str = "") -> bool:
    try:
        # Fire-and-forget: do NOT await; returns immediately (< 1ms)
        asyncio.create_task(
            cognee.remember(
                f"Article: {title}\nURL: {url}\nEntities: {entities}\nGist: {summary_gist}",
                run_in_background=True,
            )
        )
        return True
    except Exception as exc:
        logger.warning("remember_article task creation failed: %s", exc)
        return False
```

D-20.13 mock test passes: even if `cognee.remember` is mocked to `asyncio.sleep(10)`, the caller returns in < 1ms because the task is not awaited.

### Pattern 4: TimeoutError Rollback (D-20.12)

```python
# enrichment/rss_ingest.py -- exception handler
except asyncio.TimeoutError:
    logger.warning("Timeout on article %s -- draining and rolling back", article_id)
    await _drain_rss_vision_tasks(cap_seconds=120)
    for doc_id in (f"rss-{article_id}", f"rss-{article_id}_images"):
        try:
            await rag.adelete_by_doc_id(doc_id)
        except Exception as del_exc:
            logger.warning("adelete_by_doc_id(%s) failed: %s", doc_id, del_exc)
    # Do NOT update enriched column (D-20.12)
    _pending_doc_ids.pop(article_hash, None)
    return False
```

### Pattern 5: Local Drain Helper (resolves D-20.12 cap_seconds mismatch)

```python
# enrichment/rss_ingest.py -- module-local drain, NOT imported from batch_ingest_from_spider
async def _drain_rss_vision_tasks(cap_seconds: float = 120.0) -> None:
    pending = [t for t in asyncio.all_tasks()
               if t is not asyncio.current_task() and not t.done()]
    if not pending:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=cap_seconds,
        )
    except asyncio.TimeoutError:
        for t in pending:
            if not t.done():
                t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
```

### Anti-Patterns to Avoid

- **Don't use `hashlib.md5(url)[:12]` for article hash** — must use `get_article_hash(url)` from `lib/checkpoint.py` (SHA-256[:16]). Current `rss_ingest.py` line 244 has the old pattern — replace it.
- **Don't share `_pending_doc_ids` between modules** — D-20.11 is explicit; RSS gets its own dict
- **Don't set `enriched=1` on TimeoutError rollback** — leave unchanged so the article is retried next run
- **Don't call `_drain_pending_vision_tasks(cap_seconds=...)` from batch_ingest_from_spider** — that function takes no parameters; use the local `_drain_rss_vision_tasks` helper
- **Don't use `asyncio.wait_for` in `remember_article`** — the whole point of D-20.15 is fire-and-forget via `create_task`
- **Don't include EN->CN translation** — explicitly out of scope per REQUIREMENTS.md

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Full-body classify prompt | Custom prompt in rss_classify.py | `_build_fullbody_prompt` from `batch_classify_kol` | Already battle-tested for KOL; multi-topic single-call; truncation logic included |
| LLM dispatch (DeepSeek/Vertex) | New dispatch in rss_classify.py | `_call_fullbody_llm` from `batch_classify_kol` | Handles both providers; retry logic; structured output parsing |
| Image URL regex | Inline regex in rss_ingest.py | `_IMAGE_URL_PATTERN` from `lib/lightrag_embedding.py` | Must match exactly for KG content extraction to work |
| Article hash | `hashlib.md5(url)[:12]` in rss_ingest.py | `get_article_hash(url)` from `lib/checkpoint.py` | SHA-256[:16]; must match checkpoint dir naming |
| Per-article timeout budget | Custom timeout calc | formula `max(120 + 30 * chunk_count, 900)` (inline or import `_compute_article_budget_s`) | Identical to KOL Phase 9 formula; tested at scale |
| Image download + SVG filter | New HTTP client | `download_images` with added `referer` + SVG params | Already handles redirects, timeouts, retries |
| Checkpoint stage machinery | New file marker system | `lib/checkpoint.py` | Atomic writes, idempotent reads — already used by KOL |

**Key insight:** Phase 20 is an application of the KOL pipeline pattern to RSS. At least 6 shared components can be imported directly. The rewrite value is in wiring them together for RSS, not in rebuilding them.

---

## Critical Research Findings (Q1-Q10)

### Q1: `_drain_pending_vision_tasks` and `cap_seconds=120`

**Finding:** `_drain_pending_vision_tasks()` in `batch_ingest_from_spider.py` takes NO parameters. It uses a module-level `VISION_DRAIN_TIMEOUT = 120.0` constant.

D-20.12 says "drain (cap_seconds=120)" — this references a cap, not the existing function signature.

**Recommended resolution:** Define `_drain_rss_vision_tasks(cap_seconds: float = 120.0)` as a local helper in `enrichment/rss_ingest.py` (Pattern 5 above). This avoids modifying `batch_ingest_from_spider.py` (would change KOL behavior) and aligns with D-20.11 per-module separation.

### Q2: Import safety for `_build_fullbody_prompt` / `_call_fullbody_llm`

**Finding:** Safe. `rss_classify.py` already contains:
```python
from batch_classify_kol import get_deepseek_api_key
```
No circular import risk. `batch_classify_kol` imports `from lib import INGESTION_LLM, generate_sync` — both are available at `rss_classify.py` import time.

Module-level side effect in `batch_classify_kol`: `_load_hermes_env()` is called at import time. This reads `~/.hermes/.env`. Since `rss_classify.py` also loads from this file, there is no conflict — `_load_hermes_env` uses `os.environ.setdefault` semantics (does not overwrite).

### Q3: Cognee `remember_article` blocking behavior

**Finding:** The current implementation in `cognee_wrapper.py` lines 109-151:
```python
await asyncio.wait_for(
    cognee.remember(..., run_in_background=True),
    timeout=5.0,
)
```
If `cognee.remember` itself blocks (e.g., mocked to `asyncio.sleep(10)`), `asyncio.wait_for` will block for exactly 5.0 seconds before raising `TimeoutError` and returning `False`. Wall-clock: ~5s, NOT < 100ms.

**D-20.13 mock test WILL FAIL without D-20.15 change.** The `asyncio.create_task` refactor (D-20.15) IS required, not optional.

### Q4: Vision sub-doc format for RSS

**Finding from `ingest_wechat._vision_worker_impl`:**
```
# Images for {title}

- [image 1]: {description}  (http://localhost:8765/{article_hash}/{filename})
- [image 2]: {description}  (http://localhost:8765/{article_hash}/{filename})
```
RSS must match this format exactly, substituting `article_hash = get_article_hash(url)` (SHA-256[:16]) and `doc_id = f"rss-{article_id}_images"`.

Local image URL format `http://localhost:8765/{article_hash}/{n}.jpg` is matched by `_IMAGE_URL_PATTERN` in `lib/lightrag_embedding.py`.

### Q5: `download_images` signature change

**Current signature:**
```python
def download_images(urls: list[str], dest_dir: Path) -> dict[str, Path]:
```

**Required post-Phase-20 signature:**
```python
def download_images(
    urls: list[str],
    dest_dir: Path,
    referer: str | None = None,  # D-20.08
) -> dict[str, Path]:
```

SVG filter (D-20.09) — add after `response = requests.get(url, ...)`:
```python
content_type = response.headers.get("Content-Type", "")
if content_type.startswith("image/svg"):
    logger.debug("Skipping SVG image: %s", url)
    continue
```

Both changes are backward-compatible: `referer=None` is the default (old callers unaffected), and SVG filter only skips images that would have been stored as non-renderable SVG data anyway.

### Q6: Translation removal confirmed

**Finding:** REQUIREMENTS.md Wave 2 "Out of Scope for v3.4" explicitly states EN->CN translation is excluded. The `rss_ingest.py` module docstring mentions translation — this docstring is outdated. Phase 20 rewrite drops `_translate_to_chinese` and `langdetect` entirely. Classify and ingest on original body language.

### Q7: `_pending_doc_ids` clear semantics

**Finding from `ingest_wechat.py`:**
- Set after successful `ainsert` (or after vision worker completes sub-doc insert)
- Cleared only on success path (`_clear_pending_doc_id` called in vision worker completion handler)
- On rollback: cleared explicitly after `adelete_by_doc_id`

RSS must mirror this: `_pending_doc_ids[article_hash] = doc_id` after `ainsert` success; `del _pending_doc_ids[article_hash]` after vision worker completes; `_pending_doc_ids.pop(article_hash, None)` on rollback.

### Q8: PROCESSED gate preservation

**Finding from `enrichment/rss_ingest.py` lines 184-207** — this gate must not be removed or bypassed in the rewrite:
```python
cur.execute(
    "SELECT 1 FROM ingestions WHERE article_id = ? AND status = 'ok'",
    (article_id,),
)
if cur.fetchone():
    logger.debug("Article %s already ingested (status=ok), skipping", article_id)
    continue  # in loop / return False in helper
```
This is the idempotency guard preventing re-ingestion of articles already in the KG.

### Q9: Phase 20 fixture scope (E2R-01 deferral)

Phase 21 STK-01 will validate `adelete_by_doc_id` completeness across all 4 storage layers. Phase 20 unit tests use in-test stub data with mocked LightRAG. The "enriched rate >= 60%" E2R-01 fixture is deferred to Phase 21 as explicitly out of scope.

Phase 20 test scope: unit tests with mocked rag/db, mock test for Cognee detach, smoke test for classify import.

### Q10: Checkpoint stage name API clarification

**Finding from `lib/checkpoint.py`:**
- `STAGE_FILES` dict keys: `scrape`, `classify`, `image_download`, `text_ingest`, `vision_worker`, `sub_doc_ingest`
- `write_stage(ckpt_hash, stage_name, content)` takes the short key (e.g., `"scrape"`)
- File on disk: `checkpoints/{ckpt_hash}/01_scrape.html` (numeric prefix in filename, not in API key)

D-20.16 says "stage names: `01_scrape, 02_classify, ...`" — these are file names on disk, not the API keys. The `write_stage()` API call should use the short keys: `"scrape"`, `"classify"`, `"image_download"`, `"text_ingest"`, `"vision_worker"`. All 5 Phase-20 stage keys are already present in `lib/checkpoint.py STAGE_FILES`.

---

## Common Pitfalls

### Pitfall 1: Wrong `_drain_pending_vision_tasks` call signature

**What goes wrong:** Code writes `await _drain_pending_vision_tasks(cap_seconds=120)` — raises `TypeError: _drain_pending_vision_tasks() got unexpected keyword argument 'cap_seconds'`.

**Why it happens:** D-20.12 language implies a parameter that doesn't exist in the shared function.

**How to avoid:** Define `_drain_rss_vision_tasks(cap_seconds: float = 120.0)` as a local helper in `enrichment/rss_ingest.py`. Do not modify `batch_ingest_from_spider._drain_pending_vision_tasks`.

### Pitfall 2: Cognee `asyncio.create_task` precondition

**What goes wrong:** `asyncio.create_task(...)` raises `RuntimeError: no running event loop` if called from a synchronous context.

**Why it happens:** `remember_article` is `async def` so a running loop exists when it executes — the issue only appears in tests that don't set up an event loop.

**How to avoid:** `remember_article` must remain `async def`. Test fixtures must use `asyncio.run()` or `pytest-asyncio`. The `create_task` call is safe inside any `async` function.

### Pitfall 3: Wrong hash function for checkpoint dirs

**What goes wrong:** `rss_ingest.py` line 244 uses `hashlib.md5(url.encode())[:12]` — if not replaced with `get_article_hash(url)` (SHA-256[:16]), checkpoint dirs and image paths use different hashes from what `lib/checkpoint.py` expects.

**How to avoid:** Replace the `hashlib.md5` line at rss_ingest line 244. Import `get_article_hash` from `lib/checkpoint.py`.

**Warning signs:** Checkpoint dir not found on resume; image URLs in sub-doc don't match `_IMAGE_URL_PATTERN`.

### Pitfall 4: `adelete_by_doc_id` partial rollback

**What goes wrong:** On rollback, only primary doc_id deleted; sub-doc `rss-{article_id}_images` left in KG. Future run re-inserts primary but sub-doc already exists — stale image descriptions.

**How to avoid:** Exception handler MUST call `adelete_by_doc_id` for both `f"rss-{article_id}"` AND `f"rss-{article_id}_images"`. Wrap each in its own try/except to avoid one failure blocking the other.

### Pitfall 5: Daily cap timing at 4.5s/call

**What it means:** 500 articles x 4.5s = 2,250 seconds = 37.5 minutes wall-clock for classify pass. This is acceptable for a daily batch but rules out re-classify on every ingest run. The 4.5s throttle is required for full-body LLM calls (rate limit protection), not a typo.

### Pitfall 6: SVG images breaking vision pipeline

**What goes wrong:** Without D-20.09 filter, `download_images` downloads SVG bytes, PIL tries to open them, gets `UnidentifiedImageError`.

**How to avoid:** D-20.09 filter: check `Content-Type: image/svg+xml` and `continue` before writing to disk. Already covered by the `download_images` signature change.

---

## Validation Architecture

> Nyquist Dimension 8. `workflow.nyquist_validation` not explicitly set to `false` in `.planning/config.json` — section required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (no pytest.ini detected; tests run as `python -m pytest tests/unit/`) |
| Config file | None detected — use `python -m pytest tests/unit/ -v` |
| Quick run command | `python -m pytest tests/unit/test_rss_classify_fullbody.py tests/unit/test_cognee_remember_detaches.py -x -v` |
| Full suite command | `python -m pytest tests/unit/ -v --tb=short` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RCL-01 | `rss_classify.py` reads `body` column; scrapes inline if NULL; calls `_build_fullbody_prompt` | unit + mock | `python -m pytest tests/unit/test_rss_classify_fullbody.py::test_classify_reads_body -x` | No — Wave 0 |
| RCL-02 | Single multi-topic call replaces per-topic loop; `FULLBODY_THROTTLE_SECONDS = 4.5` | unit | `python -m pytest tests/unit/test_rss_classify_fullbody.py::test_single_call_multi_topic -x` | No — Wave 0 |
| RCL-03 | Daily cap gate fires at article-level after classify | unit | `python -m pytest tests/unit/test_rss_classify_fullbody.py::test_daily_cap_gates_article -x` | No — Wave 0 |
| RIN-01 | 5 checkpoint stage files created in order on successful ingest | unit + mock | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_5_stage_checkpoints -x` | No — Wave 0 |
| RIN-02 | `download_images` passes `Referer` header; skips SVG | unit | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_download_images_referer_svg -x` | No — Wave 0 |
| RIN-03 | `_pending_doc_ids` in rss_ingest distinct from ingest_wechat tracker | unit | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_pending_doc_ids_isolated -x` | No — Wave 0 |
| RIN-04 | TimeoutError triggers drain -> adelete_by_doc_id both doc_ids -> enriched unchanged | unit + mock | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_timeout_rollback -x` | No — Wave 0 |
| RIN-05 | Vision sub-doc format `rss-{id}_images` matches WeChat format | unit | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_vision_subdoc_format -x` | No — Wave 0 |
| RIN-06 | `localize_markdown` output URLs match `_IMAGE_URL_PATTERN` regex | unit | `python -m pytest tests/unit/test_rss_ingest_5stage.py::test_image_url_pattern_match -x` | No — Wave 0 |
| COG-02 | `remember_article` returns in < 100ms when `cognee.remember` mocked to `asyncio.sleep(10)` | mock-only | `python -m pytest tests/unit/test_cognee_remember_detaches.py::test_remember_returns_fast -x` | No — Wave 0 |
| COG-03 | `OMNIGRAPH_COGNEE_INLINE` gate present until retirement; live 3-article Hermes smoke required | live-Hermes manual | N/A — manual SSH smoke on Hermes | N/A manual |

### COG-03 Retirement Criteria (D-20.14)

COG-03 is gated on a live Hermes smoke test, not automated CI. Steps:

1. Deploy Phase 20 code to Hermes via `git pull`
2. Run `python ingest_wechat.py <url>` for 3 different articles with `OMNIGRAPH_COGNEE_INLINE=1`
3. Verify: no stall in ingestion (each article < 120s wall-clock)
4. Verify: `cognee_wrapper.py` logs show `create_task` path (no `wait_for`)
5. Only after 3/3 success: remove `OMNIGRAPH_COGNEE_INLINE` env gate from `ingest_wechat.py`

### Sampling Rate

- **Per task commit:** `python -m pytest tests/unit/test_rss_classify_fullbody.py tests/unit/test_rss_ingest_5stage.py tests/unit/test_cognee_remember_detaches.py -x`
- **Per wave merge:** `python -m pytest tests/unit/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work` + COG-03 live Hermes smoke complete

### Wave 0 Gaps (all test files must be created before implementation)

- [ ] `tests/unit/test_rss_classify_fullbody.py` — covers RCL-01, RCL-02, RCL-03
  - Fixtures: mock `_build_fullbody_prompt`, `_call_fullbody_llm`, in-memory SQLite with `rss_articles` table
  - Key assertions: single LLM call per article (not per topic), throttle constant value, body-null inline scrape triggered
- [ ] `tests/unit/test_rss_ingest_5stage.py` — covers RIN-01 through RIN-06
  - Fixtures: mock `rag.ainsert`, `rag.adelete_by_doc_id`, `download_images`, `describe_images`, tmp checkpoint dir
  - Key assertions: stage files written in order, SVG skipped, both doc_ids deleted on rollback, enriched NOT updated on timeout
- [ ] `tests/unit/test_cognee_remember_detaches.py` — covers COG-02
  - Fixture: `cognee.remember = asyncio.sleep(10)` (monkeypatch)
  - Key assertion: `await remember_article(...)` returns in < 100ms (use `time.perf_counter()`)
  - Expected result after D-20.15: PASS. Expected result with current code (before D-20.15): FAIL (~5s)

---

## Runtime State Inventory

> Phase 20 is an upgrade/rewrite — no rename or migration.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | Phase 19 columns (`body`, `depth_score`, `topics`, `classify_rationale`) already in `kol_scan.db` rss_articles table | None — schema complete |
| Live service config | Hermes: `OMNIGRAPH_COGNEE_INLINE=0` (default gate closed) | After COG-03 smoke: set `OMNIGRAPH_COGNEE_INLINE=1` on Hermes |
| OS-registered state | None — verified (no Task Scheduler tasks, no pm2 processes for this module) | None |
| Secrets/env vars | `OMNIGRAPH_COGNEE_INLINE` gate env var preserved until COG-03 live smoke passes | No change until smoke complete |
| Build artifacts | None — pure Python, no compiled artifacts | None |

---

## Environment Availability

> Phase 20 is code-only on local Windows dev box. All dependencies already installed.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All modules | Yes | 3.11 (venv) | — |
| lightrag | RIN-01..06 | Yes | pinned in requirements.txt | — |
| cognee | COG-02, COG-03 | Yes | pinned in requirements.txt | — |
| pytest | All unit tests | Yes | installed in venv | — |
| `lib/checkpoint.py` | RIN-01 | Yes | project-local | — |
| `lib/image_pipeline.py` | RIN-02 | Yes | project-local (needs edit) | — |
| Hermes SSH (remote) | COG-03 smoke only | Yes | see hermes_ssh.md | — |

**Missing dependencies with no fallback:** None.

**Phase 19 pending operator steps (Hermes SSH items):** Do NOT block Phase 20. Code is shipped; operator steps are Hermes-side config only. Phase 20 can proceed in parallel.

---

## State of the Art

| Old Approach | Current Approach (Phase 20) | Impact |
|--------------|----------------------------|--------|
| Per-topic summary-string classify | Single full-body multi-topic call (`_build_fullbody_prompt`) | 1 LLM call per article vs N calls; saves quota |
| `THROTTLE_SECONDS = 0.3` | `FULLBODY_THROTTLE_SECONDS = 4.5` | 15x slower rate; required for full-body LLM calls |
| `hashlib.md5(url)[:12]` for article hash | `get_article_hash(url)` SHA-256[:16] | Consistent with checkpoint dir naming |
| `asyncio.wait_for(cognee.remember, timeout=5.0)` | `asyncio.create_task(cognee.remember(...))` | Non-blocking; < 100ms return |
| RSS ingest uses `row["summary"]` (truncated) | RSS ingest uses `row["body"]` (full text, up to 8000 chars) | Higher-quality KG entities |
| `_translate_to_chinese` call in rss_ingest | Removed entirely | Simplification; out-of-v3.4 scope |

**Deprecated/outdated after Phase 20:**
- `THROTTLE_SECONDS = 0.3` in `rss_classify.py`: replaced by `FULLBODY_THROTTLE_SECONDS = 4.5`
- `CLASSIFY_PROMPT` multi-line template in `rss_classify.py`: replaced by `_build_fullbody_prompt` import
- `_translate_to_chinese` and `langdetect` calls in `rss_ingest.py`: removed (out of v3.4 scope)
- `asyncio.wait_for(..., timeout=5.0)` in `remember_article`: replaced by `asyncio.create_task`

---

## Open Questions

1. **`_compute_article_budget_s` import side effects**
   - What we know: Function is in `batch_ingest_from_spider.py` at lines 152-166
   - What's unclear: Does importing from `batch_ingest_from_spider` trigger module-level side effects (env loading, DB init)?
   - Recommendation: Read `batch_ingest_from_spider.py` top-level imports before importing. If side effects exist, inline the formula in `enrichment/rss_ingest.py`: `max(120 + 30 * max(1, len(content) // 1000), 900)`.

2. **Vision sub-doc insertion timeout**
   - What we know: Vision worker runs as background task; drain caps at 120s
   - What's unclear: Should the vision `ainsert` for sub-doc count against the article's `budget_s` or the 120s drain cap?
   - Recommendation: Vision worker gets the flat 120s drain cap. Text ingest (Stage 04) timeout is `budget_s`. These are independent timeouts.

3. **`lib/checkpoint.py` stage 5 API key name**
   - What we know: `STAGE_FILES` has `vision_worker` as a key; D-20.16 uses `05_vision_worker` as the name
   - Planner note: Confirm `write_stage(ckpt_hash, "vision_worker", ...)` is the correct call (not `"05_vision_worker"`). Based on current `lib/checkpoint.py` structure, short key is correct.

---

## Sources

All findings are from direct codebase reads within this session. Confidence is HIGH for all claims.

### Primary (HIGH confidence — direct file reads)

| File | Sections Read | Findings |
|------|--------------|---------|
| `.planning/phases/20-.../20-CONTEXT.md` | All | 16 locked D-decisions |
| `.planning/REQUIREMENTS.md` | All | RCL-01..03, RIN-01..06, COG-01..03; translation out of scope |
| `.planning/STATE.md` | All | Phase 19 verified; execute gate lifted |
| `batch_classify_kol.py` | 219-368 | `_build_fullbody_prompt`, `_call_fullbody_llm`, `FULLBODY_TRUNCATION_CHARS` |
| `batch_ingest_from_spider.py` | 93-166 | `_drain_pending_vision_tasks` (no params), `_compute_article_budget_s` |
| `ingest_wechat.py` | 260-390, 796-810, 1163-1176 | `_pending_doc_ids` tracker, `_vision_worker_impl`, Cognee gate |
| `enrichment/rss_ingest.py` | 1-325 | Current impl, PROCESSED gate (lines 184-207), hash line 244 |
| `enrichment/rss_classify.py` | 1-237 | `THROTTLE_SECONDS`, `CLASSIFY_PROMPT`, classify loop |
| `enrichment/rss_schema.py` | 1-104 | Phase 19 columns verified present |
| `image_pipeline.py` | 149-285 | `download_images` current signature; no referer/SVG filter |
| `cognee_wrapper.py` | 109-151 | `remember_article` with `wait_for(timeout=5.0)` — blocks ~5s |
| `lib/checkpoint.py` | 1-254 | `STAGE_FILES`, `write_stage`, `get_article_hash` |
| `lib/lightrag_embedding.py` | 1-50 | `_IMAGE_URL_PATTERN` regex |
| `tests/unit/` | Directory listing | Confirmed Phase-20 test files do not yet exist |
| `.planning/phases/19-.../19-VERIFICATION.md` | All | Phase 19 10/10 GREEN; 4 operator items do not block Phase 20 |

### Secondary (MEDIUM confidence)

- Translation removal: REQUIREMENTS.md "Out of Scope for v3.4" — HIGH confidence (official project spec, not inferred)

### Tertiary (LOW confidence)

- None. All findings sourced from direct codebase reads.

---

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | All packages verified in requirements.txt / project files |
| Architecture Patterns | HIGH | Direct code reads of all referenced functions and call sites |
| Don't Hand-Roll | HIGH | Import paths verified; no circular import risks found |
| Pitfalls | HIGH | Root causes traced to specific lines in source code |
| Test Map | HIGH | Existing test infrastructure verified; gap list from direct directory listing |
| Cognee detach (Q3) | HIGH | Current `wait_for(timeout=5.0)` behavior directly verified in `cognee_wrapper.py` |
| Drain function (Q1) | HIGH | `_drain_pending_vision_tasks` signature directly read from source — no parameters |

**Research date:** 2026-05-06
**Valid until:** 2026-06-06 (stable internal codebase; no external API version risk)

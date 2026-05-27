# Phase 12: Checkpoint/Resume Mechanism (B1) - Context

**Gathered:** 2026-04-30
**Revised:** 2026-05-01 based on v3.1 closure (commit 2b38e98). Changes: (1) v3.1 Phase 9 dependency updated from "pending gate-passing" to "closed @ 2b38e98"; (2) **New locked decision D-SUBDOC: Vision sub-doc lifecycle moves into the checkpoint state machine** — absorbs v3.1 closure Finding 1 (`vision_worker_drain_timeout=120s` too short for prod sub-doc entity extraction ~5 min on Hermes DeepSeek, only 2/7 sub-doc chunks completed). See Hermes `docs/HERMES_E2E_VERIFICATION_v3.1_20260501.md` §6. Stage 5 `vision_worker` is now per-image success markers (already planned) PLUS a new `06_sub_doc_ingest` terminal marker tracking sub-doc entity-merge completion.
**Status:** Ready for planning
**Source:** PRD Express Path (`.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B1) + v3.1 closure Finding 1 (routed per `docs/MILESTONE_v3.1_CLOSURE.md` §6.1)

<domain>
## Phase Boundary

**Delivers:** Per-article checkpoint persistence at 5 stage boundaries so transient failures resume without re-scraping or re-processing prior stages. Core artifacts:
1. **`lib/checkpoint.py`** — checkpoint directory management, atomic file writes, resume state detection
2. **`scripts/checkpoint_reset.py`** — CLI to delete checkpoints (`--hash <hash>` per-article; `--all` full wipe)
3. **`scripts/checkpoint_status.py`** — CLI to list in-flight checkpoints + current stage
4. **Integration hooks in `ingest_wechat.py` / `batch_ingest_from_spider.py`** — call checkpoint read/write at each of the 5 stage boundaries

**Does NOT deliver:**
- Vision Cascade logic (Phase 13; Phase 12 only persists Vision descriptions once computed)
- SiliconFlow balance check (Phase 13)
- Regression test fixtures (Phase 14)
- Operator runbook documentation (Phase 15)
- LightRAG rollback semantics — inherited from v3.1 Phase 9 (STATE-02, STATE-03) which delivers idempotent rollback on `wait_for` timeout

**Dependency:** v3.1 Phase 9 (`get_rag(flush=True)`, rollback semantics) — **closed 2026-05-01 @ commit 2b38e98** (26/26 REQs delivered; E2E-02 gate revised to <600s; see `docs/MILESTONE_v3.1_CLOSURE.md`). Checkpoint resume for `04_text_ingest.done` relies on v3.1's rollback of partial inserts.

**Absorbed finding (v3.1 closure §6.1):** Hermes's v3.1 E2E run emitted `{"event": "vision_worker_drain_timeout", "timeout_s": 120.0}` — the 28-image sub-doc started LightRAG entity extraction but only 2 of 7 sub-doc chunks completed before the drain timeout fired. Sub-doc lifecycle can no longer be treated as "fire-and-forget" bounded by a drain timer; it needs a checkpoint stage so that (a) resume can distinguish "not yet started" from "partial" from "complete", and (b) `drain_timeout` is no longer the safety net. See decision **D-SUBDOC** below.

</domain>

<decisions>
## Implementation Decisions (from PRD §B1)

### Checkpoint Directory Layout (CKPT-01, CKPT-02) — verbatim

```
~/.hermes/omonigraph-vault/checkpoints/
├── {article_hash}/
│   ├── metadata.json          # {url, title, created_at, updated_at, last_completed_stage}
│   ├── 01_scrape.html         # Raw scraped HTML
│   ├── 02_classify.json       # {depth, topics, rationale, model, timestamp}
│   ├── 03_images/
│   │   ├── img_000.jpg
│   │   ├── img_001.png
│   │   └── manifest.json      # [{url, local_path, dimensions, filter_reason}]
│   ├── 04_text_ingest.done    # Empty marker file; presence = text ingest completed
│   ├── 05_vision/
│   │   ├── img_000.json       # {provider, description, latency_ms, timestamp}
│   │   └── img_001.json       # Per-image Vision description success markers
│   └── 06_sub_doc_ingest.done # NEW (2026-05-01 D-SUBDOC): empty marker; presence = sub-doc LightRAG ainsert + entity extraction all 7 chunks complete
```

**Stage names (6 checkpoints — was 5 pre-v3.1-closure; stage 6 added per D-SUBDOC):**
1. `scrape` → writes `01_scrape.html`
2. `classify` → writes `02_classify.json`
3. `image_download` → writes `03_images/` + `03_images/manifest.json`
4. `text_ingest` → writes `04_text_ingest.done` marker
5. `vision_worker` → writes `05_vision/{image_id}.json` per-image (image description results; partial completion acceptable — individual image failures do not fail the stage)
6. `sub_doc_ingest` → writes `06_sub_doc_ingest.done` marker when sub-doc LightRAG `ainsert` + entity extraction complete for ALL sub-doc chunks (NEW per D-SUBDOC; was previously treated as fire-and-forget bounded by `drain_timeout=120s` which Hermes v3.1 closure proved insufficient — only 2/7 sub-doc chunks completed in 120s)

### D-SUBDOC (2026-05-01): Sub-doc lifecycle is checkpoint-managed (absorbs v3.1 Finding 1)

**Problem:** v3.1 Phase 10 ARCH-02/ARCH-03 shipped async Vision worker with an `asyncio.create_task` drain timeout of 120s. Hermes's 2026-05-01 prod run emitted `vision_worker_drain_timeout` — the 28-image sub-doc needed ~5 min for entity extraction, only 2/7 chunks completed. Text ingest was unaffected (ARCH-04 verified), but sub-doc content was silently dropped.

**Locked decision:**
- Sub-doc entity-extraction completion becomes its own checkpoint stage `06_sub_doc_ingest.done`
- `drain_timeout` no longer gates sub-doc success — it becomes a "time budget observer" that logs but does not fail
- Resume logic (see below) treats `06_sub_doc_ingest.done` absence as "sub-doc needs re-run" IF `05_vision/` has ≥1 success marker (i.e., there ARE Vision descriptions to sub-doc-ingest)
- Sub-doc chunking re-run is safe: LightRAG `ainsert` with a sub-doc `file_path` pointing to the same parent article is idempotent (same chunks, same entities, merges into existing graph)
- Timeout budget for sub-doc re-run: inherits Phase 9 single-article formula `max(120 + 30 × chunk_count, 900)`, typically 900s is sufficient (Hermes observed ~5min = 300s for 7 chunks)

**Operator impact:** If an article's `06_sub_doc_ingest.done` is missing on resume, the batch pipeline re-runs ONLY the sub-doc ingestion stage (reads cached Vision descriptions from `05_vision/`; no re-scraping, no re-classification, no re-Vision-API-calls). Expected overhead: ~5 min per article needing sub-doc resume.

**Path root:** `~/.hermes/omonigraph-vault/checkpoints/` (note the typo `omonigraph` is canonical — do NOT rename per CLAUDE.md Lessons Learned)

**article_hash computation:** `hashlib.sha256(url.encode()).hexdigest()[:16]` (16-char prefix; matches existing `images/{hash}/` pattern)

### Resume Logic (CKPT-03) — verbatim PRD §B1.3

On `ingest_article(url, rag=rag)` call:
1. Compute `article_hash` from URL
2. If `checkpoints/{article_hash}/` does NOT exist → start fresh (full 6-stage pipeline)
3. If exists, load `metadata.json` and inspect completed stages (check in this order, highest-numbered first):
   - `06_sub_doc_ingest.done` exists → article fully complete (text + sub-doc); skip entirely (idempotent no-op)
   - `04_text_ingest.done` exists, no `06_sub_doc_ingest.done` → text is in graph; re-enter at `vision_worker` step (if Vision descriptions missing) or `sub_doc_ingest` step (if `05_vision/` has success markers but `06` missing). **This is the primary Finding-1 remediation path.**
   - `03_images/manifest.json` exists, no `04_text_ingest.done` → resume from text_ingest step; load manifest + images, skip scrape + classify + image-download
   - `02_classify.json` exists, no `03_images/` → resume from image-download step; load classification, skip scrape + classify
   - `01_scrape.html` exists, no `02_classify.json` → resume from classify step; load scrape, skip scrape
   - Only `metadata.json` exists → start from scrape step (as if fresh, but preserve metadata)

### Atomicity (CKPT-04) — verbatim PRD §B1.4

- Every checkpoint file write MUST use atomic pattern: `write to {path}.tmp` → `os.rename({path}.tmp, {path})` (same pattern as `canonical_map.json` in `cognee_batch_processor.py`)
- `metadata.json` updated at EACH stage completion via atomic write (updates `updated_at` + tracks `last_completed_stage`)
- Checkpoint directory creation is idempotent (`os.makedirs(..., exist_ok=True)`)
- No cleanup between retry attempts — reuse checkpoints for fast resume
- A crash mid-write leaves only `.tmp` files which are ignored on resume (only final non-`.tmp` files count as stage-complete)

### Manual Reset Scripts (CKPT-05) — verbatim PRD §B1.5

**`scripts/checkpoint_reset.py`:**
```bash
python scripts/checkpoint_reset.py --hash {article_hash}  # remove one article's dir
python scripts/checkpoint_reset.py --all                   # remove entire checkpoints/ dir
```
- `--hash`: `shutil.rmtree(checkpoints_dir / hash)` with confirmation prompt
- `--all`: `shutil.rmtree(checkpoints_dir)` with explicit `--confirm` flag required (safety guard per CLAUDE.md "guard clauses before destructive actions")

**`scripts/checkpoint_status.py`:**
```bash
python scripts/checkpoint_status.py
# Output:
# hash | url                          | last_stage         | age   | status
# a1b2 | https://...article1           | text_ingest_done   | 2h    | complete
# c3d4 | https://...article2           | classify_done      | 5m    | in_flight
# e5f6 | https://...article3           | scrape_done        | 30s   | in_flight
```
- Iterates `checkpoints/` subdirs, inspects presence of each stage marker, prints Markdown or TSV table
- Useful for `watch` monitoring: `watch -n 5 'python scripts/checkpoint_status.py | tail -20'`

### `lib/checkpoint.py` Public API (Claude's Discretion on internal structure)

**MANDATORY public functions:**
```python
def get_article_hash(url: str) -> str: ...
def get_checkpoint_dir(article_hash: str) -> Path: ...
def has_stage(article_hash: str, stage: str) -> bool: ...  # stage in {scrape, classify, image_download, text_ingest, vision_worker, sub_doc_ingest}
def read_stage(article_hash: str, stage: str) -> dict | str | None: ...  # returns parsed content or None
def write_stage(article_hash: str, stage: str, data: dict | str | bytes) -> None: ...  # atomic write
def write_metadata(article_hash: str, metadata: dict) -> None: ...  # atomic upsert
def read_metadata(article_hash: str) -> dict: ...
def reset_article(article_hash: str) -> None: ...  # delete dir
def reset_all() -> None: ...  # delete checkpoints/ root
def list_checkpoints() -> list[dict]: ...  # for status script
```

**Stage-to-file mapping (internal):**
```python
STAGE_FILES = {
    "scrape": "01_scrape.html",
    "classify": "02_classify.json",
    "image_download": "03_images/manifest.json",  # dir + manifest
    "text_ingest": "04_text_ingest.done",          # empty marker
    "vision_worker": "05_vision/",                 # dir (per-image success markers)
    "sub_doc_ingest": "06_sub_doc_ingest.done",    # NEW 2026-05-01 D-SUBDOC: sub-doc entity extraction complete for all chunks
}
```

### Integration Points (Claude's Discretion on exact line edits)

**`ingest_wechat.py` / `batch_ingest_from_spider.py`:**
Wrap each stage in try/except + checkpoint calls:
```python
# Pseudocode
article_hash = get_article_hash(url)
if not has_stage(article_hash, "scrape"):
    html = scrape(url)
    write_stage(article_hash, "scrape", html)
else:
    html = read_stage(article_hash, "scrape")

if not has_stage(article_hash, "classify"):
    classification = classify(html)
    write_stage(article_hash, "classify", classification)
else:
    classification = read_stage(article_hash, "classify")

# ... and so on for image_download, text_ingest, vision_worker, sub_doc_ingest

# D-SUBDOC integration (2026-05-01): sub-doc stage is ONLY entered if vision_worker
# produced ≥1 success marker. Skipping sub-doc when Vision entirely failed (the
# text_only_article fixture case, or all-providers-down case) is correct behavior —
# no sub-doc chunks means nothing to ingest. has_stage(..., "sub_doc_ingest") should
# return True in that case (treat as "no-op satisfied") so resume does not loop.
if not has_stage(article_hash, "sub_doc_ingest"):
    vision_successes = list_vision_markers(article_hash)  # helper: reads 05_vision/*.json
    if vision_successes:
        await ingest_sub_doc(article_hash, rag=rag, descriptions=vision_successes)
        # Single ainsert for the whole sub-doc; LightRAG entity extraction runs async
        # inside ainsert. Timeout inherits Phase 9 formula max(120 + 30×chunks, 900).
        write_stage(article_hash, "sub_doc_ingest", b"")  # empty marker
    else:
        # No Vision successes — sub-doc has nothing to ingest; mark done anyway
        # so resume logic does not loop.
        write_stage(article_hash, "sub_doc_ingest", b"")
```

### Claude's Discretion

- **Internal data structures** in `lib/checkpoint.py` (dataclasses, enums, etc.) — planner picks
- **Error handling** for corrupt checkpoint files (e.g., invalid JSON in `02_classify.json`) — planner decides recovery strategy (skip vs re-compute)
- **Logging format** for checkpoint ops — use existing `logger = logging.getLogger(...)` pattern from `cognee_wrapper.py`
- **Test coverage**: at minimum an integration test that simulates crash at each stage + verifies resume correctly picks up; unit tests for atomic write semantics

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B1 — verbatim requirements
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §Acceptance Criteria Gate 1 — end-to-end acceptance

### Dependency Interfaces (v3.1)
- v3.1 Phase 9 `get_rag(flush=True)` contract — `lib/lightrag_state.py` or similar; checkpoint resume for `04_text_ingest.done` relies on idempotent rollback (STATE-02)
- v3.1 Phase 10 text-first `ainsert()` → image sub-doc append pattern (ARCH-03)
- `ingest_wechat.py::ingest_article(url, rag=rag, ...)` — current entry point signature
- `batch_ingest_from_spider.py` — current batch entry point

### Existing Patterns to Replicate
- `cognee_batch_processor.py` — `canonical_map.json` atomic write pattern (write `.tmp` → `os.rename`); entity_buffer idempotent `.processed` marker
- `config.py::BASE_DIR` — `~/.hermes/omonigraph-vault/` path constant
- `ingest_wechat.py::_article_hash` — if existing, reuse; otherwise mirror pattern from `~/.hermes/omonigraph-vault/images/{hash}/`
- `scripts/` directory conventions (shebang, argparse, entry point)

### Files to Read Before Modifying
- `ingest_wechat.py` (full file, ~150-line `ingest_article` function)
- `batch_ingest_from_spider.py` (full file — batch entry point)
- `config.py` (20 lines — path constants)
- `cognee_batch_processor.py` — atomic write reference implementation
- `.gitignore` (verify `checkpoints/` would be gitignored if created under repo root — it's actually under `~/.hermes/` so no repo-level gitignore concern)

</canonical_refs>

<specifics>
## Specific Ideas

### Atomic Write Reference Pattern (from `cognee_batch_processor.py`)

```python
def _atomic_write(path: Path, content: str | bytes, mode: str = "w") -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, mode) as f:
        f.write(content)
    os.rename(tmp_path, path)  # atomic on POSIX; atomic-enough on Windows
```

### Failure Injection Test Recipe

For CKPT-03 validation (Gate 1 criterion 1):
1. Run `ingest_article(url="...gpt55_article_url...")` with mock that raises `RuntimeError` after `image_download` stage
2. Verify `checkpoints/{hash}/03_images/manifest.json` exists, `04_text_ingest.done` does NOT
3. Re-run `ingest_article(url=...)` without mock
4. Verify `scrape` + `classify` + `image_download` are SKIPPED (assert logs or via mock observers)
5. Verify final graph contains article chunks + entities

### Status Script Output Format

```
python scripts/checkpoint_status.py

CHECKPOINTS (5 total, 2 in-flight, 3 complete)

hash      | url                           | last_stage         | age    | status
----------|-------------------------------|--------------------|--------|----------
a1b2c3d4  | https://mp.weixin.qq.com/s/X  | text_ingest        | 2h15m  | complete
b2c3d4e5  | https://mp.weixin.qq.com/s/Y  | classify           | 5m     | in_flight
c3d4e5f6  | https://mp.weixin.qq.com/s/Z  | scrape             | 30s    | in_flight
...
```

### Commit Plan

Logical split for clean atomic commits:
1. `lib/checkpoint.py` + unit tests (atomic writes, stage detection)
2. `scripts/checkpoint_reset.py` + `scripts/checkpoint_status.py`
3. `ingest_wechat.py` integration (wrap each of the 5 stages)
4. `batch_ingest_from_spider.py` integration (batch-level resume loop)
5. End-to-end integration test (failure injection at each stage)

</specifics>

<deferred>
## Deferred Ideas (out of scope)

- **Provider circuit breaker state** persisted in checkpoint — that's Phase 13 (Vision Cascade); Phase 12's Vision checkpoint only stores descriptions once computed, not provider failure history
- **Batch-level progress checkpoint** (e.g., which articles in batch have completed) — Phase 17 concern
- **Checkpoint compaction / cleanup policy** — no automatic deletion of old checkpoints; operator runs `checkpoint_reset.py --all` manually
- **Cross-machine checkpoint sync** — checkpoints are local to the machine running the batch; no distributed coordination
- **Integrity verification** (hash of checkpoint contents) — atomic writes considered sufficient for this phase; integrity checks deferred

</deferred>

---

*Phase: 12-checkpoint-resume*
*Context gathered: 2026-04-30 via PRD Express Path*

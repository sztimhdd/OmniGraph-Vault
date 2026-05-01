# Phase 12: Checkpoint/Resume Mechanism (B1) - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning
**Source:** PRD Express Path (`.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B1)

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
- LightRAG rollback semantics — assumes v3.1 Phase 9 (STATE-02, STATE-03) delivered idempotent rollback on `wait_for` timeout

**Dependency:** v3.1 Phase 9 (`get_rag(flush=True)`, rollback semantics) must be gate-passing before Phase 12 merges — checkpoint resume for `04_text_ingest.done` relies on clean rollback of partial inserts.

</domain>

<decisions>
## Implementation Decisions (from PRD §B1)

### Checkpoint Directory Layout (CKPT-01, CKPT-02) — verbatim

```
~/.hermes/omonigraph-vault/checkpoints/
├── {article_hash}/
│   ├── metadata.json          # {url, title, created_at, updated_at}
│   ├── 01_scrape.html         # Raw scraped HTML
│   ├── 02_classify.json       # {depth, topics, rationale, model, timestamp}
│   ├── 03_images/
│   │   ├── img_000.jpg
│   │   ├── img_001.png
│   │   └── manifest.json      # [{url, local_path, dimensions, filter_reason}]
│   ├── 04_text_ingest.done    # Empty marker file; presence = text ingest completed
│   └── 05_vision/
│       ├── img_000.json       # {provider, description, latency_ms, timestamp}
│       └── img_001.json
```

**Stage names (the 5 checkpoints):**
1. `scrape` → writes `01_scrape.html`
2. `classify` → writes `02_classify.json`
3. `image_download` → writes `03_images/` + `03_images/manifest.json`
4. `text_ingest` → writes `04_text_ingest.done` marker
5. `vision_worker` → writes `05_vision/{image_id}.json` per-image (async, fire-and-forget; NO `.done` — partial completion is expected)

**Path root:** `~/.hermes/omonigraph-vault/checkpoints/` (note the typo `omonigraph` is canonical — do NOT rename per CLAUDE.md Lessons Learned)

**article_hash computation:** `hashlib.sha256(url.encode()).hexdigest()[:16]` (16-char prefix; matches existing `images/{hash}/` pattern)

### Resume Logic (CKPT-03) — verbatim PRD §B1.3

On `ingest_article(url, rag=rag)` call:
1. Compute `article_hash` from URL
2. If `checkpoints/{article_hash}/` does NOT exist → start fresh (full 5-stage pipeline)
3. If exists, load `metadata.json` and inspect completed stages:
   - `04_text_ingest.done` exists → article already ingested; skip to Vision worker cleanup only
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
def has_stage(article_hash: str, stage: str) -> bool: ...  # stage in {scrape, classify, image_download, text_ingest, vision_worker}
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
    "vision_worker": "05_vision/",                 # dir (per-image files)
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

# ... and so on for image_download, text_ingest, vision_worker
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

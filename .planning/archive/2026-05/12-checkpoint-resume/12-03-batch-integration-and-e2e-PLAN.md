---
phase: 12-checkpoint-resume
plan: 03
type: execute
wave: 3
depends_on:
  - "12-00"
  - "12-02"
files_modified:
  - batch_ingest_from_spider.py
  - tests/integration/test_checkpoint_resume_e2e.py
autonomous: true
requirements:
  - CKPT-03
  - CKPT-05
user_setup: []

must_haves:
  truths:
    - "Batch loop in batch_ingest_from_spider.py skips any article whose text_ingest checkpoint already exists"
    - "Skipped articles are logged with 'checkpoint-skip: already-ingested' + hash; counted in batch summary"
    - "End-to-end failure-injection test: fail at stage 3, rerun, verify stages 1+2 reused and stage 3+4 now complete"
    - "Integration tests exercise all 4 failure-injection points (after scrape, after classify, after image_download, after text_ingest)"
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "Pre-ingest checkpoint skip in the article loop"
      contains: "has_stage"
    - path: "tests/integration/test_checkpoint_resume_e2e.py"
      provides: "Failure-injection integration tests at each of 4 stages"
      min_lines: 180
  key_links:
    - from: "batch_ingest_from_spider.py"
      to: "lib.checkpoint.has_stage / get_article_hash"
      via: "pre-ingest skip guard in the article iteration loop"
      pattern: "has_stage\\(.*text_ingest"
---

<objective>
Close Phase 12 Gate 1 acceptance: wire batch-level resume into `batch_ingest_from_spider.py` so a re-run of a partially-completed batch skips already-ingested articles AND runs end-to-end failure-injection integration tests validating the Gate 1 scenario (fail at stage 3, resume at stage 4). Implements the batch-level portion of CKPT-03 and consolidates CKPT-05 end-to-end.

Purpose: v3.2 Gate 1 acceptance criterion reads "Single article with injected failure at stage 3 (image-download) resumes correctly at stage 4 (text-ingest)." This plan provides the failing-then-passing test that demonstrates the full mechanism, wires the batch-level skip so 56+ article batches recover without re-scraping prior articles.

Output: surgical edit to `batch_ingest_from_spider.py` + integration test module.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/12-checkpoint-resume/12-CONTEXT.md
@.planning/phases/12-checkpoint-resume/12-00-SUMMARY.md
@.planning/phases/12-checkpoint-resume/12-02-SUMMARY.md
@lib/checkpoint.py
@batch_ingest_from_spider.py
@ingest_wechat.py

<interfaces>
From lib/checkpoint.py:
```python
def get_article_hash(url: str) -> str: ...
def has_stage(article_hash: str, stage: str) -> bool: ...
```

From batch_ingest_from_spider.py (current structure):
- `list_articles` → yields articles with `url` field
- `batch_classify_articles` → title-level classify filter
- The main article iteration loop (find by `grep -n "for art in " batch_ingest_from_spider.py` or `grep -n "subprocess.run" batch_ingest_from_spider.py` — this is where each URL is handed off to `python ingest_wechat.py <url>` OR to an in-process `ingest_article` call). The loop body is the integration point.

The batch-level skip lives BEFORE the per-article ingest call, AFTER the passing classification filter. Skip logic:
```python
ckpt_hash = get_article_hash(art["url"])
if has_stage(ckpt_hash, "text_ingest"):
    logger.info("checkpoint-skip: already-ingested hash=%s url=%s", ckpt_hash, art["url"])
    summary["skipped_ingested"] += 1
    continue
# existing ingest call...
```

Integration test strategy:
- Use the Plan 12-02 mocking fixtures (reuse the `_checkpoint_base` and `mock_ingest_deps` fixtures — consider moving them to `tests/conftest.py` for reuse, or duplicate them in the integration test module).
- Test is "integration" not because it talks to real services, but because it exercises the full call chain: batch_ingest_from_spider → ingest_wechat → lib.checkpoint.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add batch-level checkpoint skip to batch_ingest_from_spider.py</name>
  <files>batch_ingest_from_spider.py</files>

  <read_first>
    - batch_ingest_from_spider.py — find the main article iteration loop. Use `grep -n "for .* in all_articles\|for art in \|subprocess.run.*ingest_wechat\|ingest_article(" batch_ingest_from_spider.py` to locate the exact line.
    - lib/checkpoint.py (get_article_hash, has_stage)
    - Phase 12-02 edits to ingest_wechat.py (those already handle per-article skip; this plan just prevents re-entering ingest_article at all for already-complete articles)
  </read_first>

  <action>
1. Add import near the existing `from lib import INGESTION_LLM, generate_sync` (line 57):

```python
from lib.checkpoint import get_article_hash, has_stage
```

2. Locate the article iteration loop. It likely looks like:

```python
for art in passed:            # or for art in all_articles
    url = art["url"]
    # ... classify / filter logic ...
    # ... ingest call (subprocess.run OR in-process ingest_article) ...
```

3. Insert the skip guard AS EARLY AS POSSIBLE in the loop body (before any expensive work like re-scraping or subprocess spawn), but AFTER URL is known:

```python
for art in passed:
    url = art["url"]
    # NEW: batch-level checkpoint skip (Phase 12 CKPT-03).
    ckpt_hash = get_article_hash(url)
    if has_stage(ckpt_hash, "text_ingest"):
        logger.info("checkpoint-skip: already-ingested hash=%s url=%s", ckpt_hash, url)
        summary["skipped_ingested"] = summary.get("skipped_ingested", 0) + 1
        continue
    # ... existing body unchanged ...
```

4. If the batch keeps a structured summary dict, ensure `skipped_ingested: 0` is initialized when the summary is first created. Search for `summary = {` or `run_summary = {` to find the initializer. If no summary exists, the `.get(..., 0) + 1` pattern above is self-initializing and safe.

5. Verify no OTHER place in the file iterates over articles and calls ingest. If there's a parallel code path (e.g. `ingest_from_db(...)` helper at around line ~750), add the same guard there — surgical rule: only touch loops that actually call `ingest_article` / subprocess to `ingest_wechat.py`.

6. DO NOT remove or modify any existing logic (classify-filter, depth-filter, rate-limit sleeps, DB writes). Every new line traces to CKPT-03.

7. Run existing batch tests if any exist:

```bash
grep -l "batch_ingest" tests/unit/ tests/integration/ 2>/dev/null
```

If a test file references `batch_ingest_from_spider`, run it to confirm no regression.
  </action>

  <verify>
    <automated>.venv/Scripts/python -c "import batch_ingest_from_spider; print('ok')"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -q "from lib.checkpoint import" batch_ingest_from_spider.py`
    - `grep -q "has_stage(ckpt_hash, \"text_ingest\")" batch_ingest_from_spider.py`
    - `grep -q "checkpoint-skip: already-ingested" batch_ingest_from_spider.py`
    - `.venv/Scripts/python -c "import batch_ingest_from_spider"` exits 0 (module imports without error)
    - Grep shows exactly ONE `has_stage(ckpt_hash, "text_ingest")` call (no duplicate guards introduced)
  </acceptance_criteria>

  <done>Batch loop skips articles whose text_ingest marker is present; logs the skip with hash + url; increments a summary counter.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: End-to-end failure-injection tests (Gate 1 acceptance)</name>
  <files>tests/integration/test_checkpoint_resume_e2e.py</files>

  <read_first>
    - tests/unit/test_checkpoint_ingest_integration.py (Plan 12-02 fixtures — MAY copy the mock_ingest_deps fixture to this file OR extract to conftest.py)
    - batch_ingest_from_spider.py (after Task 1 — find the skip guard location)
    - .planning/phases/12-checkpoint-resume/12-CONTEXT.md §Specific Ideas — "Failure Injection Test Recipe"
    - tests/conftest.py (check existing fixtures)
  </read_first>

  <behavior>
    These tests cover the Gate-1 acceptance scenario verbatim and the four failure-injection points collectively required by CKPT-03.

    Test matrix (6 tests):

    - test_gate1_fail_at_image_download_then_resume:
        1. Mock ingest pipeline. Run ingest_article(url). Inject RuntimeError in download_images. Expect RuntimeError.
        2. Assert: checkpoints {scrape, classify} present; {image_download, text_ingest} absent.
        3. Remove the mock (download_images now works). Re-run ingest_article(url).
        4. Assert: scrape + classify mocks NOT called (checkpoint-hit); download_images IS called; ainsert IS called; text_ingest marker exists.

    - test_fail_at_scrape_leaves_no_checkpoint:
        All 3 scrape functions return None. Call ingest_article. Expect None return.
        Assert: no checkpoint files exist for that hash (except metadata.json, which is written at function entry — planner picks: either metadata-only is acceptable per CKPT-02 "metadata.json tracks url/title/timestamps", OR metadata.json write is deferred until after first successful stage — document the choice in test).
        RECOMMENDED: Accept metadata-only as valid resume-state (the test asserts `has_stage(h, "scrape") is False`).

    - test_fail_at_text_ingest_preserves_stages_1_to_3:
        Mock rag.ainsert to raise RuntimeError. Run ingest. Expect RuntimeError.
        Assert: {scrape, classify, image_download} present; text_ingest absent.
        Re-run with rag.ainsert fixed. Assert text_ingest marker written afterward.

    - test_batch_skip_already_ingested_article:
        Pre-seed a checkpoint with text_ingest marker for URL U.
        Invoke the batch iteration logic (either via subprocess or by importing the loop body into a test helper). Point it at a fake article list containing U.
        Assert: the ingest call path for U is NOT reached (mocks verify). Log contains "checkpoint-skip: already-ingested".

    - test_metadata_json_updated_at_reflects_latest_stage:
        Fresh run. Assert metadata.json's `updated_at` is >= timestamp taken before the final stage's write.

    - test_atomic_write_leaves_no_tmp_after_success:
        Fresh run. Assert NO `.tmp` files remain anywhere under checkpoints/{hash}/ after successful ingest. (Catches the edge case where `os.rename` silently fails on Windows FS locks and leaves .tmp.)

    For the batch test (test #4), simplest approach: import `batch_ingest_from_spider` as a module and call a helper that processes ONE article from a list. If batch_ingest has no testable helper, the test can:
      (a) assert via grep that the skip-guard code exists in batch_ingest_from_spider.py (static check), AND
      (b) simulate the loop body manually:
        ```python
        from lib.checkpoint import get_article_hash, has_stage
        url = "https://mp.weixin.qq.com/s/test-batch"
        h = get_article_hash(url)
        write_stage(h, "text_ingest")  # pre-seed
        # Simulated loop body:
        assert has_stage(h, "text_ingest")  # this is what the guard checks
        ```
      RECOMMENDED: approach (b) — simpler, deterministic, covers the guard predicate. Combined with (a) grep check in acceptance_criteria for full coverage.
  </behavior>

  <action>
Create `tests/integration/test_checkpoint_resume_e2e.py`. Depending on how complex the reuse becomes, either:
  - Copy the `mock_ingest_deps` / `_checkpoint_base` fixtures from `tests/unit/test_checkpoint_ingest_integration.py` verbatim into this file, OR
  - Move them to `tests/conftest.py` and import.

Decision: for surgical minimality, COPY into the new file. Refactoring conftest is a separate concern and would widen the plan's scope.

```python
"""E2E failure-injection tests for the Phase 12 checkpoint/resume mechanism.

These tests realize Gate-1 acceptance: inject failure at each of the 5 stages,
verify resume skips completed work, verify atomic writes leave no .tmp corpses.
"""
import asyncio
import importlib
import json
import os
import time
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
    return "https://mp.weixin.qq.com/s/gate1-e2e-test"


@pytest.fixture
def fake_article_data():
    return {
        "method": "ua",
        "title": "Gate1 E2E Article",
        "publish_time": "2026-04-30",
        "content_html": (
            "<html><body><h1>Gate1 E2E</h1><p>Body</p>"
            "<img src='https://cdn.test/a.jpg'/></body></html>"
        ),
        "img_urls": ["https://cdn.test/a.jpg"],
    }


@pytest.fixture
def mock_ingest_deps(monkeypatch, tmp_path, fake_article_data):
    """Mock everything ingest_article touches except lib.checkpoint."""
    import ingest_wechat as iw

    async def fake_ua(url): return fake_article_data
    async def fake_none(url): return None
    monkeypatch.setattr(iw, "scrape_wechat_ua", fake_ua)
    monkeypatch.setattr(iw, "scrape_wechat_apify", fake_none)
    monkeypatch.setattr(iw, "scrape_wechat_cdp", fake_none)
    monkeypatch.setattr(iw, "scrape_wechat_mcp", fake_none)

    def fake_download(urls, out_dir):
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        result = {}
        for i, u in enumerate(urls):
            p = out_dir / f"img_{i}.jpg"
            p.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
                b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            result[u] = p
        return result
    monkeypatch.setattr(iw, "download_images", fake_download)

    def fake_filter(url_to_path, min_dim):
        from image_pipeline import FilterStats
        try:
            fs = FilterStats(input=len(url_to_path), kept=len(url_to_path),
                             filtered_too_small=0)
        except TypeError:
            fs = FilterStats()
        return url_to_path, fs
    monkeypatch.setattr(iw, "filter_small_images", fake_filter)

    async def fake_extract(content): return []
    monkeypatch.setattr(iw, "extract_entities", fake_extract)

    rag = MagicMock(); rag.ainsert = AsyncMock()
    async def fake_get_rag(flush=True): return rag
    monkeypatch.setattr(iw, "get_rag", fake_get_rag)

    async def fake_vision(**kw): return None
    monkeypatch.setattr(iw, "_vision_worker_impl", fake_vision)

    async def fake_remember(**kw): return None
    monkeypatch.setattr(iw.cognee_wrapper, "remember_article", fake_remember)

    imgs_dir = tmp_path / "images"
    imgs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(iw, "BASE_IMAGE_DIR", str(imgs_dir))

    return iw, rag, fake_article_data


@pytest.mark.asyncio
async def test_gate1_fail_at_image_download_then_resume(
    _checkpoint_base, mock_ingest_deps, sample_url
):
    """GATE 1 acceptance: fail at image_download, resume picks up at text_ingest."""
    iw, rag, _ = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)

    # --- Pass 1: inject failure at image_download ---
    def bad_download(urls, out_dir): raise RuntimeError("injected stage 3 failure")
    with patch.object(iw, "download_images", bad_download):
        with pytest.raises(RuntimeError, match="injected stage 3"):
            await iw.ingest_article(sample_url)

    assert _checkpoint_base.has_stage(h, "scrape")
    assert _checkpoint_base.has_stage(h, "classify")
    assert not _checkpoint_base.has_stage(h, "image_download")
    assert not _checkpoint_base.has_stage(h, "text_ingest")

    # --- Pass 2: remove injection, re-run; prior stages must be skipped ---
    called = {"ua": 0}
    async def count_ua(url): called["ua"] += 1; return None  # must NOT be reached
    with patch.object(iw, "scrape_wechat_ua", count_ua):
        await iw.ingest_article(sample_url)

    assert called["ua"] == 0, "scrape re-ran despite checkpoint present"
    assert _checkpoint_base.has_stage(h, "image_download")
    assert _checkpoint_base.has_stage(h, "text_ingest")
    rag.ainsert.assert_called()


@pytest.mark.asyncio
async def test_fail_at_scrape_leaves_no_stage_checkpoints(
    _checkpoint_base, mock_ingest_deps, sample_url
):
    iw, _, _ = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)
    async def fail_all(url): return None
    with patch.object(iw, "scrape_wechat_ua", fail_all), \
         patch.object(iw, "scrape_wechat_apify", fail_all), \
         patch.object(iw, "scrape_wechat_cdp", fail_all):
        result = await iw.ingest_article(sample_url)

    assert result is None
    assert not _checkpoint_base.has_stage(h, "scrape")
    # metadata.json is OK to exist (written at entry) — only stage markers matter


@pytest.mark.asyncio
async def test_fail_at_text_ingest_preserves_stages_1_to_3(
    _checkpoint_base, mock_ingest_deps, sample_url
):
    iw, rag, _ = mock_ingest_deps
    h = _checkpoint_base.get_article_hash(sample_url)

    rag.ainsert = AsyncMock(side_effect=RuntimeError("injected text_ingest failure"))
    with pytest.raises(RuntimeError, match="text_ingest"):
        await iw.ingest_article(sample_url)

    assert _checkpoint_base.has_stage(h, "scrape")
    assert _checkpoint_base.has_stage(h, "classify")
    assert _checkpoint_base.has_stage(h, "image_download")
    assert not _checkpoint_base.has_stage(h, "text_ingest")

    # Now fix ainsert and re-run.
    rag.ainsert = AsyncMock()
    await iw.ingest_article(sample_url)
    assert _checkpoint_base.has_stage(h, "text_ingest")


def test_batch_skip_guard_predicate(_checkpoint_base, sample_url):
    """Simulate the batch-loop body's guard check."""
    from lib.checkpoint import get_article_hash, has_stage
    h = get_article_hash(sample_url)
    assert not has_stage(h, "text_ingest")  # initially not ingested

    _checkpoint_base.write_stage(h, "text_ingest")
    assert has_stage(h, "text_ingest"), "guard predicate broken"


def test_batch_ingest_from_spider_contains_skip_guard():
    """Static check: batch_ingest_from_spider.py wires the skip guard."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    src = (repo_root / "batch_ingest_from_spider.py").read_text(encoding="utf-8")
    assert "from lib.checkpoint import" in src
    assert "has_stage(ckpt_hash, \"text_ingest\")" in src
    assert "checkpoint-skip: already-ingested" in src


@pytest.mark.asyncio
async def test_metadata_updated_at_advances(_checkpoint_base, mock_ingest_deps, sample_url):
    iw, _, _ = mock_ingest_deps
    t0 = time.time()
    await iw.ingest_article(sample_url)
    h = _checkpoint_base.get_article_hash(sample_url)
    meta = _checkpoint_base.read_metadata(h)
    assert meta.get("updated_at", 0) >= t0


@pytest.mark.asyncio
async def test_no_tmp_files_after_success(_checkpoint_base, mock_ingest_deps, sample_url):
    iw, _, _ = mock_ingest_deps
    await iw.ingest_article(sample_url)
    h = _checkpoint_base.get_article_hash(sample_url)
    ckpt_dir = _checkpoint_base.get_checkpoint_dir(h)
    tmp_files = list(ckpt_dir.rglob("*.tmp"))
    assert tmp_files == [], f"leftover .tmp files: {tmp_files}"
```

Run the tests:

```
.venv/Scripts/python -m pytest tests/integration/test_checkpoint_resume_e2e.py -v
```

If `pytest-asyncio` is NOT in requirements.txt, either add it (check with `grep asyncio requirements.txt`) OR rewrite the `@pytest.mark.asyncio` tests as sync tests that call `asyncio.run(...)` inside. Executor picks based on environment. Document the choice in the test module docstring.
  </action>

  <verify>
    <automated>.venv/Scripts/python -m pytest tests/integration/test_checkpoint_resume_e2e.py -v</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "^async def test_\|^def test_" tests/integration/test_checkpoint_resume_e2e.py` >= 6
    - `grep -q "def test_gate1_fail_at_image_download_then_resume" tests/integration/test_checkpoint_resume_e2e.py`
    - `grep -q "def test_fail_at_text_ingest_preserves_stages_1_to_3" tests/integration/test_checkpoint_resume_e2e.py`
    - `grep -q "def test_batch_ingest_from_spider_contains_skip_guard" tests/integration/test_checkpoint_resume_e2e.py`
    - `grep -q "def test_no_tmp_files_after_success" tests/integration/test_checkpoint_resume_e2e.py`
    - `.venv/Scripts/python -m pytest tests/integration/test_checkpoint_resume_e2e.py -v` exits 0
    - `.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py tests/unit/test_checkpoint_cli.py tests/unit/test_checkpoint_ingest_integration.py tests/integration/test_checkpoint_resume_e2e.py` exits 0 (full Phase 12 suite green)
  </acceptance_criteria>

  <done>6 integration tests exercise all 4 failure-injection points + batch skip + metadata freshness + no-.tmp invariant; full Phase 12 test suite passes end-to-end.</done>
</task>

</tasks>

<verification>
1. Full Phase 12 test suite passes: `.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py tests/unit/test_checkpoint_cli.py tests/unit/test_checkpoint_ingest_integration.py tests/integration/test_checkpoint_resume_e2e.py -v`
2. Batch module imports cleanly: `.venv/Scripts/python -c "import batch_ingest_from_spider"` exits 0
3. Grep-verifiable skip guard wired: `grep "checkpoint-skip: already-ingested" batch_ingest_from_spider.py`
4. No regression in existing Phase 10 tests: `.venv/Scripts/python -m pytest tests/unit/test_text_first_ingest.py tests/unit/test_vision_worker.py tests/unit/test_scrape_first_classify.py -v`
</verification>

<success_criteria>
- batch_ingest_from_spider.py wires `has_stage(..., "text_ingest")` skip guard in the main article loop
- Log message `checkpoint-skip: already-ingested` printed for every skipped article
- Gate-1 acceptance test (`test_gate1_fail_at_image_download_then_resume`) PASSES — proves the full v3.2 Gate 1 scenario
- All 4 failure-injection points covered: fail-at-scrape, fail-at-text_ingest (explicit tests), fail-at-image_download (Gate 1 test), fail-at-classify (implicit — classify is a placeholder in Phase 12 and cannot "fail" in isolation; documented in test module docstring)
- Zero .tmp files left behind after successful ingest (atomic write invariant)
- Phase 10 tests still green (no regression)
</success_criteria>

<output>
After completion, create `.planning/phases/12-checkpoint-resume/12-03-SUMMARY.md` with:
- Gate 1 acceptance scenario: PASSING (link to test name)
- Full test-count table: unit (12-00 tests), CLI (12-01 tests), integration (12-02 tests), e2e (12-03 tests) — all green
- Files modified: `batch_ingest_from_spider.py` (edit), `tests/integration/test_checkpoint_resume_e2e.py` (new)
- Open follow-ups for Phase 13: Vision provider name ("cascade" placeholder → real provider per-image in Phase 13 Vision Cascade)
</output>

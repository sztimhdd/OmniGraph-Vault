---
phase: 18-daily-ops-hygiene
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - ingest_wechat.py
  - tests/unit/test_image_cap.py
autonomous: true
requirements: [HYG-02]
must_haves:
  truths:
    - "`ingest_wechat.py` applies a hard cap of `MAX_IMAGES_PER_ARTICLE` (default 60, env-overridable via `OMNIGRAPH_MAX_IMAGES_PER_ARTICLE`) on the kept image set AFTER `filter_small_images`"
    - "Truncation logs a WARNING-level message with original count + cap + dropped count"
    - "Truncation is deterministic (stable dict-insertion order; drops the tail, preserves the head)"
    - "Checkpoint manifest only records the kept entries — resume reads the same truncated manifest and does not re-download dropped images"
  artifacts:
    - path: "ingest_wechat.py"
      provides: "Image cap applied between filter_small_images and localize_markdown; no behavior change for articles ≤60 images"
      min_lines_touched: 10
    - path: "tests/unit/test_image_cap.py"
      provides: "Unit tests for cap off/at/over boundary + env override + logging"
      min_lines: 90
  key_links:
    - from: "ingest_wechat.py"
      to: "url_to_path (kept image dict)"
      via: "truncation after filter_small_images, before manifest build"
      pattern: "MAX_IMAGES_PER_ARTICLE"
---

<objective>
Add a hard N-image cap to `ingest_wechat.py` to resolve the 118-image edge case from Wave 0 Close-Out § F. Cap defaults to 60 images per article; env-overridable via `OMNIGRAPH_MAX_IMAGES_PER_ARTICLE`. Truncation happens AFTER `filter_small_images` (so the cap counts "keepable" images, not the pre-filter noise) and BEFORE manifest persistence (so the checkpoint stays consistent across resume).

Purpose: the 118-image edge case hung LightRAG's entity-merge for ~14 min in Wave 0. The cost/value of a tail image (image #117 of 118) is minimal — the first 60 images already carry the article's visual argument. Cap + warning gives us bounded ingestion time without burning on the image-weight tail.

Decision rationale (YOLO default: option A from user brief):
- **(a) N-image cap** — bounded time per article, simple to reason about, trivial to unit-test. Cost: possibly lose a couple of relevant late-article images on extreme outliers (118 / 67 articles = ~1.5% of a Wave 0-class batch).
- **(b) Timeout extension** — kicks the can down the road; a 250-image article still hangs.
- **(c) Both** — appropriate once (b) becomes needed. For now (a) alone; reopen if post-cap articles still hit Phase 9 timeouts.

Choosing (a). Default 60 because: Wave 0 median kept-image count was ~10–15; p95 was ~40; 60 gives ~2× p95 headroom without opening the door to the long tail.
</objective>

<execution_context>
Windows dev machine. `ingest_wechat.py` test path is unit-only (no live WeChat scrape). Tests must mock `download_images` + `filter_small_images` or call the cap logic through a thin helper extracted from the ingest flow.
</execution_context>

<context>
@.planning/phases/18-daily-ops-hygiene/18-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-00-SUMMARY.md
@ingest_wechat.py

<where_to_cap>
Current flow in `ingest_wechat.py` (lines 943–973):

```
unique_img_urls = list(dict.fromkeys([u for u in img_urls if u.startswith('http')]))
url_to_path = download_images(unique_img_urls, Path(article_dir))   # downloads ALL
url_to_path, filter_stats = filter_small_images(url_to_path, min_dim=min_dim)
# ... manifest building uses url_to_path + unique_img_urls
```

Cap insertion point: AFTER `filter_small_images`, BEFORE manifest construction. Rationale:
- Filtering before cap: `filter_small_images` drops banners/icons regardless; those shouldn't count toward the cap.
- Capping before download: wrong — we can't filter pre-download (we don't know the dimensions yet).
- Capping after filter: right — we only cap on "keepable, useful" images.

The cap truncates `url_to_path` (OrderedDict-like insertion order is stable since Py 3.7). The manifest build loop already iterates `unique_img_urls` and marks dropped entries with `filter_reason=...`; we extend this to mark capped-out entries with `filter_reason="over_cap"` so the manifest stays complete + the checkpoint-resume path is consistent.
</where_to_cap>

<proposed_diff_sketch>
```python
# After filter_small_images, before manifest build:

MAX_IMAGES_PER_ARTICLE = int(os.environ.get("OMNIGRAPH_MAX_IMAGES_PER_ARTICLE", 60))

if len(url_to_path) > MAX_IMAGES_PER_ARTICLE:
    original_count = len(url_to_path)
    # Preserve head; drop tail. dict insertion order is stable (Py 3.7+).
    kept_items = list(url_to_path.items())[:MAX_IMAGES_PER_ARTICLE]
    dropped = list(url_to_path.items())[MAX_IMAGES_PER_ARTICLE:]
    url_to_path = dict(kept_items)
    dropped_urls = {u for u, _ in dropped}
    logger.warning(
        "image cap hit: article=%s kept=%d/%d dropped=%d (MAX_IMAGES_PER_ARTICLE=%d)",
        article_hash, len(url_to_path), original_count,
        len(dropped), MAX_IMAGES_PER_ARTICLE,
    )
else:
    dropped_urls = set()

# Then in the manifest-build loop, extend the filter_reason logic:
for u in unique_img_urls:
    entry = {"url": u, "local_path": None, "dimensions": None, "filter_reason": None}
    if u in url_to_path:
        # ...existing kept path...
    elif u in dropped_urls:
        entry["filter_reason"] = "over_cap"
    else:
        entry["filter_reason"] = "download_failed_or_filtered"
    manifest.append(entry)
```

`logger` is already defined at module top of `ingest_wechat.py`. No new import needed.
</proposed_diff_sketch>

<unit_test_shape>
Tests call a small testable helper — to avoid end-to-end scrape dependencies, extract the cap logic into `_apply_image_cap(url_to_path, max_images)` returning `(capped_dict, dropped_urls, original_count)`. The ingest flow calls this helper. Tests call the helper directly.

Helper location: `ingest_wechat.py` module scope, next to the `_ckpt_hash_fn` helpers.

Five tests:
1. `test_cap_under_threshold_is_noop` — 20 images, cap=60 → no change, dropped=∅
2. `test_cap_at_exact_threshold_is_noop` — 60 images, cap=60 → no change, dropped=∅
3. `test_cap_over_threshold_truncates_tail` — 70 images, cap=60 → kept 60 (first 60), dropped=last 10
4. `test_cap_env_override_respected` — set `OMNIGRAPH_MAX_IMAGES_PER_ARTICLE=5`; 10 images → kept 5, dropped 5
5. `test_cap_preserves_insertion_order` — explicit dict with known ordered keys → kept list matches head of input
</unit_test_shape>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 18-01.1: Extract `_apply_image_cap()` helper + wire into ingest flow</name>
  <files>ingest_wechat.py, tests/unit/test_image_cap.py</files>
  <behavior>
    - `_apply_image_cap(url_to_path, max_images)` returns `(capped_dict, dropped_urls, original_count)`.
    - When `len(url_to_path) <= max_images`: returns `(url_to_path, set(), original_count)`.
    - When `> max_images`: returns head-preserving truncation.
    - Ingest flow calls helper between `filter_small_images` and manifest build.
    - Manifest marks dropped entries with `filter_reason="over_cap"`.
    - WARNING log emitted on truncation (and only on truncation).
    - Env var `OMNIGRAPH_MAX_IMAGES_PER_ARTICLE` overrides default 60.
  </behavior>
  <read_first>
    - ingest_wechat.py lines 940–973 (filter + manifest build region)
    - 05-00-SUMMARY § F — deferred item original description
    - CLAUDE.md § "Vision Cascade" (3-consecutive-failure circuit breaker is INDEPENDENT of image cap; cap does not replace it)
  </read_first>
  <action>
    1. Add `_apply_image_cap()` helper near module-level utility functions in `ingest_wechat.py`.
    2. Add `MAX_IMAGES_PER_ARTICLE` module-level constant (env-resolved at import time via `int(os.environ.get("OMNIGRAPH_MAX_IMAGES_PER_ARTICLE", 60))`).
    3. Call the helper right after `filter_small_images` returns; pass through the returned `url_to_path`.
    4. Extend manifest loop to recognize `dropped_urls` → `filter_reason="over_cap"`.
    5. Write 5 unit tests covering under/at/over/env-override/order-preservation.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python -m pytest tests/unit/test_image_cap.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "MAX_IMAGES_PER_ARTICLE" ingest_wechat.py` — constant present.
    - `grep -q "OMNIGRAPH_MAX_IMAGES_PER_ARTICLE" ingest_wechat.py` — env override wired.
    - `grep -q "over_cap" ingest_wechat.py` — manifest tag present.
    - `grep -q "_apply_image_cap" ingest_wechat.py` — helper wired.
    - 5 pytest tests pass.
    - `tests/unit/test_image_cap.py` ≥ 90 lines.
    - No regression: existing `tests/unit/test_ingest_wechat*` tests still pass (run full ingest_wechat subsection).
  </acceptance_criteria>
  <done>118-image edge case bounded; articles over 60 kept images log a warning and truncate to 60.</done>
</task>

</tasks>

<verification>
- Unit tests all green (5 new + existing ingest_wechat unit tests unregressed).
- Static audit passes (grep checks above).
- No Hermes-side verification required for Wave 1 (cap is a bounded-behavior change; no external API / cron / Telegram). Real 118-image regression gated on a future batch.
</verification>

<success_criteria>
- HYG-02 satisfied: articles over 60 kept images are bounded in ingestion time.
- No behavior change for the 98.5% of articles with ≤ 60 kept images.
- Operator has a single env var to adjust the cap without code change.
</success_criteria>

<output>
After completion, create `.planning/phases/18-daily-ops-hygiene/18-01-SUMMARY.md` documenting: final cap value + rationale, any articles in the 67-article Wave 0 sample that would have been capped (if discoverable from existing manifests), test coverage summary.
</output>

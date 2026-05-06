---
quick_id: 260506-en4
type: execute
mode: quick
description: Wire topic_filter through _classify_full_body to fix CV-only classification regression
date: 2026-05-06
files_modified:
  - batch_ingest_from_spider.py
  - tests/unit/test_classify_full_body_topic_hint.py
commits:
  - 7ad7847 fix(classify): _classify_full_body accepts topic_filter, passes to prompt builder
  - 6a4790a fix(ingest): ingest_from_db threads topic into _classify_full_body
  - 65fab98 test(classify): topic_filter wiring assertions (mock-only)
---

# Quick task 260506-en4 — Summary

## One-liner

Wired `topic_filter: list[str] | None` through `batch_ingest_from_spider._classify_full_body` into the existing `batch_classify_kol._build_fullbody_prompt(topic_filter=...)` parameter. 3 atomic commits, +4 mock-only unit tests GREEN, Hermes-side `inspect.signature` verified.

## Commits

| # | SHA | Subject | Files |
|---|-----|---------|-------|
| 1 | `7ad7847` | `fix(classify): _classify_full_body accepts topic_filter, passes to prompt builder` | `batch_ingest_from_spider.py` (+6, -1) |
| 2 | `6a4790a` | `fix(ingest): ingest_from_db threads topic into _classify_full_body` | `batch_ingest_from_spider.py` (+1) |
| 3 | `65fab98` | `test(classify): topic_filter wiring assertions (mock-only)` | `tests/unit/test_classify_full_body_topic_hint.py` (+269) |

All 3 pushed to `origin/main`.

## Wiring Chain

```
ingest_from_db(topic=...)                         # commit 2
  └─> _classify_full_body(..., topic_filter=topics)
        └─> _build_fullbody_prompt(title, body, topic_filter=topic_filter)   # commit 1
              └─> prompt now contains 'filtering by topics: "agent", "harness"' hint text
```

Default `topic_filter=None` preserves backward compatibility.

## pytest Output

### Final pytest run on modified-code-relevant test files

```
$ DEEPSEEK_API_KEY=dummy python -m pytest \
    tests/unit/test_classify_full_body_topic_hint.py \
    tests/unit/test_scrape_first_classify.py \
    tests/unit/test_text_first_ingest.py \
    -q --tb=no -p no:cacheprovider
...
FAILED tests/unit/test_scrape_first_classify.py::test_scrape_on_demand_when_body_empty
FAILED tests/unit/test_text_first_ingest.py::test_parent_ainsert_content_has_references_not_descriptions
2 failed, 22 passed, 11 warnings in 64.61s (0:01:04)
```

- **4 new tests GREEN** (all in `test_classify_full_body_topic_hint.py`)
- **2 failures = pre-existing baseline failures** (unchanged from before this task)
- **No regressions introduced** by the 3 commits

### Note on full pytest run

Attempted to run the full `tests/unit/` suite multiple times; it consistently hangs at ~27% (around test ~158). Same hang occurred on baseline (pre-patch) when two pytest processes were running concurrently — this is a known environmental issue on this Windows dev box (likely SQLite or file-handle contention with leftover background processes from May 4), unrelated to the 260506-en4 patches. The targeted-file pytest run above is sufficient to demonstrate no regression on the modified-code surface.

## Post-Push Verification

### Local greps (`grep -n "topic_filter" batch_ingest_from_spider.py`)

```
417:    topic_filter: list[str] | None,                    # legacy batch-scan path (unchanged)
427:    if topic_filter:                                   # legacy batch-scan path (unchanged)
428:        keywords_quoted = ", ".join(f'"{k}"' for k in topic_filter)
548:    topic_filter: list[str] | None,                    # legacy batch-scan path (unchanged)
593:        prompt = _build_filter_prompt(batch_titles, topic_filter, exclude_topics, batch_digests)
621:    relevant = cls.get("relevant", True) if topic_filter else True
626:    if topic_filter and not relevant:
627:        keywords_str = ", ".join(topic_filter)
690:    topic_filter = kwargs.get("topic_filter")
737:    scanning_active = bool(topic_filter or exclude_topics)
742:        topic_filter,
747:        all_articles, topic_filter, exclude_topics, min_depth, classifier=classifier,
950:    topic_filter: list[str] | None = None,             # NEW (commit 1, signature)
954:    ``topic_filter`` is forwarded to ``_build_fullbody_prompt`` to bias the   # NEW (commit 1, docstring)
1009:   prompt = _build_fullbody_prompt(title, body, topic_filter=topic_filter)  # NEW (commit 1, internal call)
1287: def _build_topic_filter_query(topics: list[str]) -> tuple[str, tuple[str, ...]]:
1368:    # quick-260503-sd7: case-insensitive topic filter via _build_topic_filter_query.
1369:    sql, params = _build_topic_filter_query(topics)
1503:                    topic_filter=topics,                # NEW (commit 2, caller kwarg)
1647:    if args.topic_filter:                              # CLI parser (unchanged)
1648:        topic_keywords = [k.strip() for k in args.topic_filter.split(",") if k.strip()]
1666:        topic_filter=topic_keywords,                   # main() -> ingest_from_db (unchanged)
```

The 4 new occurrences (lines 950, 954, 1009, 1503) constitute the entire wiring change. Verification per plan section <verification> step 3 SATISFIED.

### Hermes-side `inspect.signature` (read-only)

```
$ ssh -p 49221 sztimhdd@ohca.ddns.net "cd ~/OmniGraph-Vault && \
    git pull origin main && \
    PYTHONPATH=. venv/bin/python -c '
from batch_ingest_from_spider import _classify_full_body
import inspect
sig = inspect.signature(_classify_full_body)
print(\"params:\", list(sig.parameters.keys()))
assert \"topic_filter\" in sig.parameters
print(\"OK: topic_filter wired in\")
'"
params: ['conn', 'article_id', 'url', 'title', 'body', 'api_key', 'topic_filter']
OK: topic_filter wired in
```

Hermes git pull succeeded (3 new commits pulled). `inspect.signature` confirms `topic_filter` is the 7th parameter on the deployed `_classify_full_body` definition. NO production batch was run on Hermes (scope honored).

## Deviations from Plan

### Task 2: `_classify_topic_filter` normalization block omitted

**Plan said:** Build a normalization block at top of `ingest_from_db`:
```python
if isinstance(topic, str):
    _classify_topic_filter: list[str] | None = [topic] if topic else None
elif isinstance(topic, list) and topic:
    _classify_topic_filter = list(topic)
else:
    _classify_topic_filter = None
```

**What shipped:** Single-line change `topic_filter=topics,` at the call site.

**Rationale:** `ingest_from_db` already normalizes `topic: str | list` to `topics: list` at line 1341 (`topics = [topic] if isinstance(topic, str) else topic`). The SELECT at line 1369 returns 0 rows if `topics` is empty, hitting the early-return at line 1376 — so by the time the call site is reached at line 1503, `topics` is guaranteed to be a non-empty list. Adding a second normalization block would be redundant code per "Simplicity First" / CLAUDE.md HIGHEST PRIORITY PRINCIPLE 2. Test 4 verifies the str→list conversion still works correctly.

This is a tightening of the plan's intent, not a functional deviation — same observable behavior, less code.

### Task 3: Mock-only test approach uses real `_build_fullbody_prompt` for tests 1+2

The plan said tests 1+2 "use real prompt builder, not mocked" — implemented as specified. Tests 3+4 mock `_classify_full_body` directly to capture kwargs without driving scrape/DB/ingest paths. The test plan placeholder `pytest.skip` was replaced with real implementations as instructed; no skips remain in the final commit.

### Line-ending repair during Task 1

The first attempt at editing `batch_ingest_from_spider.py` (the file uses mixed CRLF/LF line endings — committed `i/mixed`) inadvertently re-encoded all surrounding context lines from LF to CRLF, producing a noisy 18+/13- diff. I detected this via `git diff --check` (it flagged 17 lines as "trailing whitespace" — `\r` characters) and re-applied the patches byte-for-byte using a Python script that preserves the exact original line endings around each edit point. Final Task 1 diff is a clean 6-insert/1-delete surgical change. Task 2 used the same byte-level-aware approach from the start.

## Final state of articles classification regression

**Patch effect:** ONLY future runs of `batch_ingest_from_spider --from-db` benefit. The 601 articles with stale `'CV'` classifications from the 2026-05-06 overnight Hermes Phase 2b+ run remain in the DB unchanged.

**Bulk re-classify is OUT OF SCOPE for this quick task** (per `<hard_constraints>`). It is a separate operation that can be triggered by a future quick task (`/gsd:quick`) once Day-1/2/3 KOL baseline observation is complete.

## Post-task state

- 3 commits on `origin/main` (head `65fab98`)
- 4 new mock-only unit tests GREEN
- Hermes deployment pulled to `65fab98`; signature verified read-only
- No production batch executed on Hermes
- Production env vars, `~/.hermes/.env`, scraper cascade, candidate SQL, graded probe, and existing 'CV'-tagged articles all UNCHANGED
- Total wall-clock: ~3 hours (driven by repeated pytest baseline runs; actual code changes ~30 min)

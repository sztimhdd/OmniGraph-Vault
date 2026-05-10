# Quick 260510-siw — Eliminate outer/inner double-INSERT design smell

## Outcome

Outer `batch_ingest_from_spider.ingest_article` is now the sole writer for the `ingestions` table. The inner `ingest_wechat.ingest_article` no longer writes to `ingestions` — the 5-line `INSERT OR IGNORE INTO ingestions` block (lines 1314-1318) has been surgically removed. To communicate whether the inner's PROCESSED gate passed, the outer's return type was widened from `tuple[bool, float]` to `tuple[bool, float, bool]`, where the third element is `doc_confirmed`. Both main-loop call sites in `batch_ingest_from_spider.py` now unpack 3 values and gate `status='ok'` on `(success AND doc_confirmed)`, eliminating the split-brain race condition where two writers could disagree on the final row state.

## Files Changed

- `ingest_wechat.py` — removed INSERT OR IGNORE INTO ingestions block (5 lines). UPDATE articles SET content_hash and SET enriched preserved (still gated on `doc_confirmed`).
- `batch_ingest_from_spider.py` — outer `ingest_article` return type widened; 4 return points updated; 2 main-loop call sites updated.
- `tests/unit/test_ingest_article_processed_gate.py` — `success, wall =` unpacked to `success, wall, doc_confirmed =`; `assert doc_confirmed is False` added.

## Verification — pytest

Log: `.scratch/siw-pytest-1778447810.log`

Last 50 lines verbatim:

```
        article_data = _make_article_data(url, img_urls=img_urls)
        _patch_common(monkeypatch, _fake_rag, article_data, url_to_path)
    
        call_order: list[str] = []
    
        async def _recording_ainsert(*args, **kwargs):
            call_order.append("parent_ainsert")
    
        _fake_rag.ainsert = AsyncMock(side_effect=_recording_ainsert)
    
        async def _recording_worker(**kwargs):
            call_order.append("vision_worker")
            return None
    
        monkeypatch.setattr(ingest_wechat, "_vision_worker_impl", _recording_worker)
    
        result = await ingest_wechat.ingest_article(url, rag=_fake_rag)
        if isinstance(result, asyncio.Task):
            await result  # let worker finish so it gets recorded
    
        # parent_ainsert must appear before vision_worker in the call order.
>       assert "parent_ainsert" in call_order
E       AssertionError: assert 'parent_ainsert' in ['vision_worker']

tests\unit\test_text_first_ingest.py:291: AssertionError
---------------------------- Captured stdout call -----------------------------
--- Starting Ingestion: https://mp.weixin.qq.com/s/test_order ---
Starting ingestion process...
Scraping successful using method: resumed
Ingesting into LightRAG...
Buffered 0 entities for async processing.
--- Successfully Ingested! ---
Article: Untitled
Hash: 87d884d534
Method: resumed
Local Path: C:\Users\huxxha\AppData\Local\Temp\pytest-of-huxxha\pytest-383\test_vision_worker_spawn_order0\87d884d534
---------------------------- Captured stderr call -----------------------------
18:17:01 INFO ingest_wechat checkpoint hit: scrape (hash=8503ae6418c37edf)
18:17:01 INFO ingest_wechat checkpoint hit: classify (hash=8503ae6418c37edf)
18:17:01 INFO ingest_wechat checkpoint hit: image_download (hash=8503ae6418c37edf)
18:17:01 INFO ingest_wechat checkpoint hit: text_ingest (hash=8503ae6418c37edf) skipping rag.ainsert
------------------------------ Captured log call -----------------------------
INFO     ingest_wechat:ingest_wechat.py:1005 checkpoint hit: scrape (hash=8503ae6418c37edf)
INFO     ingest_wechat:ingest_wechat.py:1101 checkpoint hit: classify (hash=8503ae6418c37edf)
INFO     ingest_wechat:ingest_wechat.py:1119 checkpoint hit: image_download (hash=8503ae6418c37edf)
INFO     ingest_wechat:ingest_wechat.py:1224 checkpoint hit: text_ingest (hash=8503ae6418c37edf) skipping rag.ainsert
=========================== short test summary info ===========================
FAILED tests/unit/test_text_first_ingest.py::test_parent_ainsert_content_has_references_not_descriptions
FAILED tests/unit/test_text_first_ingest.py::test_vision_worker_spawn_order_after_parent_ainsert
================== 2 failed, 26 passed in 127.63s (0:02:07) ===================
```

Note: the 2 failures in `test_text_first_ingest.py` are pre-existing — confirmed by running the same test suite against the unmodified code (git stash → run → stash pop). Baseline showed identical 2 failures. This quick does NOT touch `ingest_wechat.ingest_article`'s return signature; those tests call inner directly, not outer.

`test_ingest_article_processed_gate.py` — all 6 tests PASSED including `test_outer_catches_inner_runtime_error_returns_failed` with the new 3-tuple unpack and `doc_confirmed is False` assertion.
`test_checkpoint_ingest_integration.py` — all 11 tests PASSED.

## Verification — grep

Log: `.scratch/siw-grep-1778447342.log`

```
=== inner (ingest_wechat.py): expect 0 matches ===
(no matches — expected)

=== outer (batch_ingest_from_spider.py): expect skipped+main-loop matches only ===
1570:                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
1695:                        "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
1746:                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
1792:                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
1804:                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
1822:                    "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
1846:                        "INSERT OR REPLACE INTO ingestions(article_id, source, status, skip_reason_version) "
=== tuple[bool, float, bool] ===
242:) -> tuple[bool, float, bool]:
=== success and doc_confirmed ===
827:            elif success and doc_confirmed:
1735:                elif success and doc_confirmed:
=== 3-tuple unpack count ===
2
```

- `ingest_wechat.py` has 0 INSERT INTO ingestions matches (confirmed exit code 1 from grep)
- `batch_ingest_from_spider.py` has exactly 1 `tuple[bool, float, bool]` (line 242 — return annotation)
- `batch_ingest_from_spider.py` has exactly 2 `elif success and doc_confirmed:` (lines 827 + 1735)
- 3-tuple unpack `success, wall, doc_confirmed = await ingest_article` count: 2

## Out-of-Scope (unchanged)

- `tests/unit/test_ainsert_persistence_contract.py` — NOT touched (parallel quick 260510-gkw has WIP; hard out-of-scope)
- `_verify_doc_processed_or_raise` body in `ingest_wechat.py` — NOT touched
- `doc_confirmed = True` local variable at `ingest_wechat.py:1298` — NOT touched (still gates UPDATE articles writes)
- Pattern A poll budget — NOT added
- Vision sub-doc verification logic — NOT touched
- `ingestions` table schema / migration files — NOT touched
- Outer's try/except STRUCTURE in `batch_ingest_from_spider.py` — NOT touched (only return statement values changed)
- `_status_is_processed` / `aget_docs_by_ids` calls — NOT touched
- UPDATE articles SET content_hash / SET enriched statements in `ingest_wechat.py` — NOT touched (preserved, still gated on doc_confirmed)

## Diff Stat Sanity

`git diff --stat HEAD~1 HEAD` (commit 3a58838):

```
 .planning/STATE.md                                 |   3 +-
 .../260510-oxq-PLAN.md                             | 404 +++++++++++++++++++++
 .../260510-oxq-SUMMARY.md                          | 121 ++++++
 batch_ingest_from_spider.py                        |  18 +-
 ingest_wechat.py                                   |   5 -
 tests/unit/test_ingest_article_processed_gate.py   |   3 +-
 6 files changed, 538 insertions(+), 16 deletions(-)
```

Files in diff are ONLY from the allowlist: `ingest_wechat.py`, `batch_ingest_from_spider.py`, `tests/unit/test_ingest_article_processed_gate.py`, `.planning/STATE.md`, `.planning/quick/260510-oxq-*/`.

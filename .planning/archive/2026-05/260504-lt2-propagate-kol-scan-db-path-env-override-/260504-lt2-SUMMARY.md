---
phase: 260504-lt2
type: quick
status: complete
completed: "2026-05-04T16:05:00Z"
requirements:
  - LT2-01  # batch_classify_kol.py:26 DB_PATH env override
  - LT2-02  # batch_scan_kol.py:36 DB_PATH env override
  - LT2-03  # ingest_wechat.py:86 DB_PATH env override
  - LT2-04  # kg_synthesize.py:13 DB_PATH env override
  - LT2-05  # cognee_batch_processor.py:41 DB_PATH env override
  - LT2-06  # enrichment/daily_digest.py:42 DB env override
  - LT2-07  # enrichment/orchestrate_daily.py:36 DB env override
  - LT2-08  # enrichment/rss_classify.py:37 DB env override
  - LT2-09  # enrichment/rss_fetch.py:30 DB env override (+import os)
  - LT2-10  # enrichment/rss_ingest.py:54 DB env override
  - LT2-11  # enrichment/run_enrich_for_id.py:31 DB env override
  - LT2-12  # mock-only regression tests (23 assertions)
commits:
  - 366e7fe  # LT2-01
  - b12a294  # LT2-02
  - 0ebaeb7  # LT2-03
  - 90f4091  # LT2-04
  - eb8314a  # LT2-05
  - 911f3fe  # LT2-06
  - 2c47265  # LT2-07
  - d1c044d  # LT2-08
  - cb443e6  # LT2-09
  - 9feafdc  # LT2-10
  - 4fa028a  # LT2-11
  - 0674eb5  # LT2-12
files_touched:
  - batch_classify_kol.py                # MODIFIED (LT2-01)
  - batch_scan_kol.py                    # MODIFIED (LT2-02)
  - ingest_wechat.py                     # MODIFIED (LT2-03)
  - kg_synthesize.py                     # MODIFIED (LT2-04)
  - cognee_batch_processor.py            # MODIFIED (LT2-05)
  - enrichment/daily_digest.py           # MODIFIED (LT2-06)
  - enrichment/orchestrate_daily.py      # MODIFIED (LT2-07)
  - enrichment/rss_classify.py           # MODIFIED (LT2-08)
  - enrichment/rss_fetch.py              # MODIFIED (LT2-09)  +import os
  - enrichment/rss_ingest.py             # MODIFIED (LT2-10)
  - enrichment/run_enrich_for_id.py      # MODIFIED (LT2-11)
  - tests/unit/test_kol_scan_db_path_override.py  # NEW (LT2-12)
---

# Quick Task 260504-lt2 — KOL_SCAN_DB_PATH Propagation Summary

## One-liner

Propagated the af6f5bc env-override pattern (originally `batch_ingest_from_spider.py:86`
in Quick 260504-g7a/e2e) across the 11 remaining DB path call sites so classify /
scan / synthesize / cognee / enrichment all respect `KOL_SCAN_DB_PATH` — enabling
full local dev pipeline runs against `.dev-runtime/data/kol_scan.db`. Hermes
production behavior unchanged (env unset → byte-identical fallback per file).

## Commits

| # | SHA | File | Change |
|---|-----|------|--------|
| 1 | `366e7fe` | `batch_classify_kol.py:26` | `DB_PATH = Path(os.environ.get("KOL_SCAN_DB_PATH", str(PROJECT_ROOT / "data" / "kol_scan.db")))` |
| 2 | `b12a294` | `batch_scan_kol.py:36` | same pattern, `PROJECT_ROOT` base |
| 3 | `0ebaeb7` | `ingest_wechat.py:86` | same pattern, `Path(__file__).parent` base |
| 4 | `90f4091` | `kg_synthesize.py:13` | same pattern, `Path(__file__).parent` base |
| 5 | `eb8314a` | `cognee_batch_processor.py:41` | same pattern, `Path(__file__).parent` base |
| 6 | `911f3fe` | `enrichment/daily_digest.py:42` | `DB = Path(os.environ.get("KOL_SCAN_DB_PATH", "data/kol_scan.db"))` (CWD-relative fallback) |
| 7 | `2c47265` | `enrichment/orchestrate_daily.py:36` | same CWD-relative pattern |
| 8 | `d1c044d` | `enrichment/rss_classify.py:37` | same CWD-relative pattern |
| 9 | `cb443e6` | `enrichment/rss_fetch.py:30` | same CWD-relative pattern **+ added `import os`** (only file in batch that needed it) |
| 10 | `9feafdc` | `enrichment/rss_ingest.py:54` | same CWD-relative pattern |
| 11 | `4fa028a` | `enrichment/run_enrich_for_id.py:31` | same CWD-relative pattern |
| 12 | `0674eb5` | `tests/unit/test_kol_scan_db_path_override.py` | 23 mock-only subprocess-isolated assertions |

All 12 pushed atomically to `origin/main` in a single batch.

## Why two fallback shapes?

| Group | Pre-change default | Fallback after LT2 |
|-------|--------------------|--------------------|
| 5 root scripts (LT2-01..05) | `PROJECT_ROOT / "data" / "kol_scan.db"` or `Path(__file__).parent / "data" / "kol_scan.db"` | same, wrapped with `os.environ.get(..., str(...))` |
| 6 enrichment scripts (LT2-06..11) | bare `Path("data/kol_scan.db")` (CWD-relative) | same bare `"data/kol_scan.db"` literal |

Byte-identical pre-change behavior when env var is unset. Hermes production
`~/.hermes/.env` does NOT set `KOL_SCAN_DB_PATH`, so all 11 fallbacks kick in
exactly as before.

## Test coverage

`tests/unit/test_kol_scan_db_path_override.py` — **23 tests, all green**:

- 11 × `test_env_override_routes_to_custom_path` — env-set routing works per module
- 11 × `test_env_unset_preserves_default_fallback` — env-unset fallback ends in `data/kol_scan.db`
- 1 × `test_batch_ingest_from_spider_pattern_is_the_reference` — pins af6f5bc so future reverts cascade-fail

Tests use `subprocess.run` with a clean environment per module because
`DB_PATH = Path(os.environ.get(...))` is evaluated at import time. Standard
`monkeypatch` + `importlib.reload` would not work for modules with side-effectful
import chains (DeepSeek eager-import at `lib/llm_deepseek.py:87`). Subprocess
isolation handles both.

## Verification

```
=== unit regression ===
479 passed / 17 failed (17 == pre-existing baseline; +25 new green vs. pre-LDEV,
                         of which +23 are from LT2 + +2 drift from unrelated tests)

=== local smoke re-run (per user requirement) ===
venv\Scripts\python batch_ingest_from_spider.py --from-db
    --topic-filter openclaw,hermes,agent,harness --min-depth 2 --max-articles 1

Result:
- ingestions count 82 → 83 (id=205 article_id=333 status=ok @ 15:59:41)
- lightrag_storage graphml 53 KB → 102 KB (100 nodes / 113 edges)
- vdb_entities.json 1.2 MB → 2.4 MB
- 4 images ingested via OpenRouter vision (LDEV-06 skip-list honored)
- Vertex-only LLM traffic confirmed (same as 260504-g7a/e2e run)

=== acceptance checks ===
grep -nE 'data.?kol_scan\.db' <11 target files> -> no hardcoded matches remain
git diff <each file> -> fallback string is byte-identical to pre-change form
```

## Out-of-scope (not touched per hard constraints)

- `batch_ingest_from_spider.py:86` — already done (af6f5bc); LT2 does not re-touch.
- `enrichment/merge_and_ingest.py:51` — already had the same env var pattern before LT2.
- `run_uat_ingest.py:13`, `scripts/seed_rss_feeds.py:21` — hardcoded paths exist but
  NOT in the user's 11-file list. Per hard constraint ("不动列表外任何文件"), left
  alone; can be addressed in a follow-up quick if needed.
- `ROADMAP.md`, phase status, `VALIDATION.md`, Hermes `~/.env`, `~/.hermes/` — untouched.

## Duration

~40 minutes wall clock including 6-minute smoke re-run. Iterations used: 1 of 5 budget.

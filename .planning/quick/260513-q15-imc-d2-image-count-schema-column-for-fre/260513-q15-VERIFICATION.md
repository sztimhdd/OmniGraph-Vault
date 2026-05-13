---
phase: quick-260513-q15
verifier: gsd-verifier
date: 2026-05-13
status: passed
commit: 4f3a47b
---

# Phase quick-260513-q15 Verification Report

**Phase Goal:** D2 image_count schema column for fresh-article budget (issue #2 follow-up). Persist `articles.image_count` at WeChat scrape time so fresh-article daily-cron budget calc reads real count BEFORE post-vision body-stripping; T1-b1 disk fallback retained as defense-in-depth.

**Verified:** 2026-05-13
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | D2 chosen over D1; scrape path unchanged | PASS | `git diff 4f3a47b~1 4f3a47b -- ingest_wechat.py \| grep -iE "apify\|cdp\|playwright\|connect_over_cdp\|browser_navigate\|scrape"` returns no matches; only the UPDATE block was added (post-`write_metadata` at line 1275 onwards). Apify/CDP/MCP/UA paths untouched. |
| 2 | image_count is a hint, not a gate — persist failure logs WARNING and falls through | PASS | `ingest_wechat.py:1289`: `except Exception as _ic_exc: logger.warning("image_count persist failed: %s", _ic_exc)` — non-fatal, no re-raise. Code continues to next stage. |
| 3 | image_count=None preserves T1-b1 fallback chain | PASS | `batch_ingest_from_spider.py:251-254`: `if image_count is not None and image_count >= 0: resolved_image_count = image_count else: resolved_image_count = _count_images_in_body(full_content, url=url)` — None branch falls through to body regex (which itself falls through to disk at line 213: `return _count_images_on_disk(url)`). |
| 4 | Only WeChat persists image_count; RSS body retains markdown | PASS | `Grep image_count\|UPDATE.*image_count` over `enrichment/` and `lib/` returns ZERO `UPDATE rss_articles SET image_count` matches. The two `enrichment/fetch_zhihu.py` hits (lines 238, 283) are dict-key uses, not DB writes. `enrichment/rss_rescrape_bodies.py:67` only updates `body`, not `image_count`. |
| 5 | SELECT uses COALESCE(image_count, 0) | PASS | `batch_ingest_from_spider.py:1492` (WeChat arm): `COALESCE(a.image_count, 0) AS image_count`; line 1513 (RSS arm): `COALESCE(r.image_count, 0) AS image_count`. Both UNION arms widened. |
| 6 | T1-b1 disk fallback (_count_images_on_disk) preserved | PASS | `batch_ingest_from_spider.py:167` defines `_count_images_on_disk`; line 213 calls it from `_count_images_in_body` (the regex path). The regex path is reached when image_count kwarg is None (line 254). Function not removed, not modified by 4f3a47b. |
| 7 | INTEGER DEFAULT 0 with no CHECK constraint | PASS | `migrations/011_add_image_count.sql` lines 19-20: `ALTER TABLE articles ADD COLUMN image_count INTEGER DEFAULT 0;` and `ALTER TABLE rss_articles ADD COLUMN image_count INTEGER DEFAULT 0;`. `grep -nE "^\s*CHECK\s*\(" migrations/011_add_image_count.sql` returns exit=1 (no match — forbidden_regex satisfied). |
| 8 | PROMPT_VERSION_LAYER2 untouched | PASS | `git diff 4f3a47b~1 4f3a47b -- batch_ingest_from_spider.py \| grep PROMPT_VERSION` returns no matches. |
| 9 | Migration + backfill NOT applied to prod | PASS | `python -c "PRAGMA table_info(articles)"` on `data/kol_scan.db` returns columns `[id, account_id, title, url, digest, update_time, scanned_at, content_hash, enriched, body]` — image_count NOT present. Same for `rss_articles`: 16 columns ending at `classify_rationale`, no image_count. |
| 10 | Surgical: no edits to T1-b1 fallback, RSS scrape path, image_count==0 boundary protection | PASS | `git diff 4f3a47b~1 4f3a47b` shows 6 hunks all in expected regions. `_count_images_on_disk` (line 167-191) and `_count_images_in_body` (line 193-213) bodies untouched (only docstring of `_compute_article_budget_s` changed). The `image_count is not None and image_count >= 0` check at line 251 preserves the zero-boundary semantic (kwarg=0 still routes to "use 0" not "fall through"). |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/011_add_image_count.sql` | Both ALTER statements; no CHECK | PASS | Lines 19-20 contain the two ALTER TABLE ADD COLUMN. `grep -nE "^\s*CHECK\s*\("` returns exit=1. File is 21 lines. |
| `scripts/backfill_image_count.py` | exports count_images, backfill, main; md5(url)[:10] hash; OMNIGRAPH_BASE_DIR | PASS | Lines 41 (`def count_images`), 62 (`def backfill`), 87 (`def main`). Line 49: `hashlib.md5(url.encode("utf-8")).hexdigest()[:10]`. Line 37: `os.environ.get("OMNIGRAPH_BASE_DIR")`. |
| `ingest_wechat.py` | UPDATE block at ~line 1275; uses DB_PATH; logger.warning line | PASS | Block at lines 1281-1290. Line 1281: `if DB_PATH.exists():`. Line 1289: `logger.warning("image_count persist failed: %s", _ic_exc)`. NO `KOL_DB_PATH` (grep returned no matches). |
| `batch_ingest_from_spider.py` | image_count kwarg; both UNION arms COALESCE; 8-tuple unpack at 1864-ish; call site passes kwarg | PASS | Line 220: `image_count: int \| None = None`. Lines 1492 + 1513: `COALESCE(...)` in both arms. Line 1885 (drift +21 from plan's 1864): 8-tuple unpack with `image_count_row`. Line 1827: call site with `image_count=image_count_d` kwarg. |
| `tests/unit/test_timeout_budget.py` | 4 new test fns; existing 20 untouched; ~+66 lines | PASS | `grep -c "^def test_"` returns 24 (20 baseline + 4 new). Diff shows +66 insertions, 0 deletions. New tests: `test_image_count_kwarg_takes_precedence_over_regex` (line 267), `..._over_disk` (276), `..._zero_explicit_no_image_budget` (297), `..._none_falls_back_to_regex_or_disk` (317). |
| `tests/unit/test_backfill_image_count.py` | ≥3 test fns | PASS | `grep -c "^def test_"` returns 3: `test_count_images_existing_dir_returns_count` (line 12), `test_count_images_missing_dir_returns_zero` (30), `test_backfill_updates_rows_with_disk_files` (39). 80-line file. |

**Score:** 6/6 artifacts verified

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| Hermes design review (D2 over D1) | mig 011 + ingest_wechat.py:~1275 | Schema + scrape-time UPDATE | PASS | mig 011 file present with 2 ALTER statements; ingest_wechat.py:1281-1290 has the UPDATE block immediately after write_metadata at line 1274 (zero-line gap). |
| Issue #2 follow-up (T1-b1 d767580 only fixed re-ingestion) | batch_ingest_from_spider.py:_compute_article_budget_s + line 1806 call site | image_count kwarg highest priority; T1-b1 retained | PASS | Signature widened at line 216-221 with `image_count: int \| None = None` kwarg; priority ladder at 251-254 (kwarg → regex → disk). Call site at line 1827 passes image_count_d=row[7]. T1-b1 (`_count_images_on_disk` at line 167) NOT removed. |
| CLAUDE.md staging-race rule (explicit git add, never -A) | Final commit step | git add <explicit-files> | PASS | `git show --stat 4f3a47b` shows exactly 6 files changed (no spillover from sibling work). Commit message body present and references Hermes 2026-05-13 design review. The 6 files match the planned `files_modified` list verbatim. |
| ingest_wechat.py:269 DB_PATH (existing) | ingest_wechat.py:~1274 image_count UPDATE | Reuse DB_PATH constant; do NOT introduce KOL_DB_PATH alias | PASS | Line 1281 uses `DB_PATH.exists()`; line 1283 uses `sqlite3.connect(str(DB_PATH))`. `grep KOL_DB_PATH ingest_wechat.py` returns no matches — no alias introduced. |
| SELECT (UNION articles + rss_articles) | Per-article tuple unpack at line 1864 + line 1806 budget call | COALESCE(...) at end of SELECT; widen 7-tuple to 8-tuple | PASS | All 3 widening points present: (1) SELECT both arms add COALESCE column at end (lines 1492, 1513); (2) per-article unpack at line 1885 has 8 names with `image_count_row` last; (3) call site at line 1827 reads `row[7]` and passes `image_count=image_count_d`. |

**Score:** 5/5 key links verified

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 27 tests pass | `venv/Scripts/python.exe -m pytest tests/unit/test_timeout_budget.py tests/unit/test_backfill_image_count.py --tb=short -q` | `27 passed in 3.33s` | PASS |
| mig 011 has no CHECK constraint | `grep -nE "^\s*CHECK\s*\(" migrations/011_add_image_count.sql` | exit=1 (no match) | PASS |
| Production DB column NOT present | `python -c PRAGMA table_info(articles)` on `data/kol_scan.db` | `image_count` NOT in returned column list | PASS |
| RSS path has zero `image_count` UPDATE | `Grep image_count` on `enrichment/` + `lib/` | Only fetch_zhihu.py dict-key uses; zero `UPDATE rss_articles SET image_count` | PASS |
| Regression-guard substring preserved | `grep '_compute_article_budget_s(body' batch_ingest_from_spider.py` | Line 1827: `article_budget = _compute_article_budget_s(body or "", url=url_d, image_count=image_count_d)` — single-line preserves the substring | PASS |

### Anti-Patterns Found

None. All 6 file diffs are surgical and trace directly to the goal:
- mig 011: 21 lines, only `ALTER TABLE` statements + comment header
- backfill: 101 lines, single-purpose script with hash + count + UPDATE
- ingest_wechat.py: +16 lines, single try/except UPDATE block
- batch_ingest_from_spider.py: 4 hunks (signature/body, two SELECT arms, call site, tuple unpack) — no drift
- test additions: append-only

No TODO/FIXME, no `return null/[]/{}` placeholders, no console.log-only handlers, no hardcoded empty data, no orphan files.

### Deviation Review

**Deviation 1 — Single-line call site to satisfy `test_drain_layer2_queue_call_site_uses_dynamic_budget` regression guard:**
- VERIFIED. The test exists at `tests/unit/test_timeout_budget.py:216` and asserts (line 244): `assert "_compute_article_budget_s(body" in drain_body`.
- Call site at `batch_ingest_from_spider.py:1827`: `article_budget = _compute_article_budget_s(body or "", url=url_d, image_count=image_count_d)` — preserves the literal substring `_compute_article_budget_s(body` intact.
- This is a sound deviation: the multiline form would have broken the regression guard. Reverting to single-line is the correct surgical move (CLAUDE.md PRINCIPLE 3 — match existing style) and the test was NOT modified (Task 3 done criteria preserved).
- VERDICT: REASONABLE. Test asserts substring presence, and the substring IS present.

**Deviation 2 — Python sqlite3 module substituted for sqlite3 CLI (CLI not on Windows dev box):**
- VERIFIED. The plan's `<verify shell="bash">` blocks invoke `sqlite3 /tmp/test_mig011.db ".schema articles" | grep image_count`. On Windows dev, `sqlite3` CLI is not on PATH (`bash: sqlite3: command not found`).
- Substitution: `python -c "import sqlite3; conn = sqlite3.connect(...)"` invocations driven via `executescript()` and `PRAGMA table_info()` queries. Both check the same end-state (column exists in schema; column has correct type/default).
- Assertion strength: equivalent. `.schema` text-search and `PRAGMA table_info()` are different APIs but both reach the same source-of-truth (sqlite_master metadata).
- Production DB never touched in either form.
- VERDICT: REASONABLE. Environment workaround with no semantic loss.

### Final Verdict

All 10 truths PASS. All 6 artifacts PASS. All 5 key links PASS. All 5 behavioral spot-checks PASS. Both deviations are reasonable.

The codebase post-commit `4f3a47b` matches the must_haves contract from `260513-q15-PLAN.md` with zero gaps. The quick achieved its goal: D2 schema column for fresh-article budget is in place, T1-b1 fallback retained, scrape path untouched, RSS path untouched, prod DB unmodified, 27 tests pass.

Status: **passed**

No human verification required.

---

_Verified: 2026-05-13_
_Verifier: Claude (gsd-verifier)_

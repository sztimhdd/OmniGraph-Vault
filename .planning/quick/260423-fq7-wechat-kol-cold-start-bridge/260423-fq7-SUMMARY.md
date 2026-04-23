---
task: 260423-fq7
title: WeChat KOL Cold-Start Bridge
phase: quick
type: feature
completed: 2026-04-23
commits:
  - 7860c2c  # Task 1 — scrub KOL credentials, add kol_config.py to .gitignore
  - dd47a09  # Task 2 — batch_ingest_from_spider.py bridge script
files_created:
  - batch_ingest_from_spider.py
  - spiders/__init__.py        # gitignored — local only
  - spiders/wechat_spider.py   # gitignored — local only
files_modified: []
---

# Quick Task 260423-fq7: WeChat KOL Cold-Start Bridge — Summary

## One-liner

WeChat MP article lister (requests + pagination, no Selenium) wired to a batch bridge that calls `ingest_wechat.py` per URL, with dry-run mode and per-run JSON summary output.

## What Was Built

### Task 1 (commit 7860c2c)
- Scrubbed KOL credentials from `docs/KOL_COLDSTART_SETUP.md` — replaced all real tokens/cookies/fakeids with `<your-…>` placeholders.
- Added `kol_config.py` to `.gitignore` so local credential files are never committed.

### Task 2 (commit dd47a09)

**`spiders/__init__.py`** (gitignored)
- Empty package init — marks `spiders/` as a Python package.

**`spiders/wechat_spider.py`** (gitignored)
- `list_articles(token, cookie, fakeid, days_back, max_articles)` — calls the WeChat MP backend API (`/cgi-bin/appmsg`) with standard browser headers.
- Paginates in steps of 20 until the cutoff date (`days_back`) or `max_articles` is reached.
- Returns `list[dict]` with keys: `title`, `url`, `update_time` (unix timestamp), `fakeid`.
- Raises `requests.HTTPError` on non-200 responses.

**`batch_ingest_from_spider.py`** (committed)
- Reads `kol_config.TOKEN`, `kol_config.COOKIE`, `kol_config.FAKEIDS` from the local-only `kol_config.py`.
- Iterates accounts, calls `list_articles()`, then calls `ingest_wechat.py <url>` as a subprocess per article.
- `--dry-run` flag lists articles without ingesting.
- `--days-back` (default 90) and `--max-articles` (default 50) are configurable.
- Writes a JSON summary to `data/coldstart_run_{timestamp}.json` with per-article status (`ok`, `failed`, `skipped_no_url`, `dry_run`).
- Falls back to `sys.executable` if `venv/Scripts/python.exe` is absent.

## Verification Status

**Dry-run import check** — to be verified by user before live run:

```bash
# 1. Create kol_config.py with real credentials (gitignored)
# See docs/KOL_COLDSTART_SETUP.md for the exact format

# 2. Smoke-test the spider module standalone
python -c "from spiders.wechat_spider import list_articles; print('import OK')"

# 3. Dry-run — lists articles, calls NO ingest
python batch_ingest_from_spider.py --dry-run --days-back 30 --max-articles 5

# Expected output:
#   === Account: <name> (fakeid=<id>) ===
#   Found N articles for <name>
#   [1/N] <title>
#     [dry-run] would ingest: https://mp.weixin.qq.com/s/...
#   Summary written to data/coldstart_run_<timestamp>.json
#   Done — N ok, 0 failed, 0 skipped
```

## Human Verification Checkpoint

Before running the full live batch:

1. Confirm `kol_config.py` exists with `TOKEN`, `COOKIE`, and `FAKEIDS` dict populated.
2. Run dry-run (step 3 above) — verify article list looks correct and URLs are well-formed.
3. Check `data/coldstart_run_<timestamp>.json` — all entries should have `"status": "dry_run"`.
4. If dry-run looks good, run live: `python batch_ingest_from_spider.py --days-back 90 --max-articles 50`
5. Monitor `~/.hermes/omonigraph-vault/lightrag_storage/` to confirm new entities are being written.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

- [x] `batch_ingest_from_spider.py` exists at project root
- [x] `spiders/__init__.py` exists locally (gitignored)
- [x] `spiders/wechat_spider.py` exists locally (gitignored)
- [x] Commit `7860c2c` exists (Task 1)
- [x] Commit `dd47a09` exists (Task 2)
- [x] `spiders/` confirmed gitignored (`.gitignore` line 26)
- [x] `kol_config.py` not committed (gitignored)

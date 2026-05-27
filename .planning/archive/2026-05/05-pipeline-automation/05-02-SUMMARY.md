---
phase: 05-pipeline-automation
plan: 02
subsystem: rss-fetch
tags: [wave1, rss, fetch, feedparser, langdetect]
status: complete
created: 2026-05-02
completed: 2026-05-02
---

# Plan 05-02 SUMMARY — RSS fetcher with dedup + fault tolerance

**Status:** Complete (local; live feed smoke deferred to Hermes)
**Wave:** 1
**Depends on:** 05-01 (SUMMARY pushed 2026-05-02)

## 1. What shipped

| Task | Artifact | Status |
|------|----------|--------|
| 2.1  | `enrichment/rss_fetch.py` | runs on mocked feedparser; all branches covered |
| 2.1  | `tests/unit/test_rss_fetch.py` (7 tests) | 7/7 pass |

## 2. Behaviors verified by unit tests

| # | Test | Verifies |
|---|------|----------|
| 1 | `test_insert_three_entries` | 3 entries → 3 rows in `rss_articles` |
| 2 | `test_rerun_is_dedup_noop` | second run inserts 0 (URL UNIQUE) |
| 3 | `test_skips_too_short` | body < 500 chars → skipped |
| 4 | `test_skips_unsupported_language` | Russian body → skipped (langdetect 'ru' not in {en, zh*}) |
| 5 | `test_feed_level_fault_tolerance_and_error_count` | bozo=1 with no entries increments `error_count`; other feeds still run; successful feed resets `error_count=0` |
| 6 | `test_last_fetched_at_set_on_success` | `last_fetched_at` written on OK path |
| 7 | `test_dry_run_writes_nothing` | `--dry-run` does not UPDATE rss_feeds nor INSERT rss_articles |

## 3. Pre-filter thresholds (locked at file top)

```python
FEED_DELAY_SECONDS   = 2.0    # PRD §3.1.3
FEED_TIMEOUT_SECONDS = 15     # socket.setdefaulttimeout
MIN_CONTENT_CHARS    = 500    # PRD §3.1.3
SUPPORTED_LANGS      = {"en", "zh-cn", "zh-tw", "zh"}
```

## 4. Implementation notes

- `feedparser.parse(xml_url, agent=USER_AGENT)` plus a module-level
  `socket.setdefaulttimeout(FEED_TIMEOUT_SECONDS)` is the 15s per-feed
  timeout strategy per RESEARCH.md Pitfall 6.
- A feed is treated as "failed" only when `bozo=1 AND no entries`. Many
  valid feeds have `bozo=1` warnings but still yield entries — those are
  kept.
- `cur.rowcount == 1` is the per-row insert indicator (plan L-21 noted
  this; `conn.total_changes` would be cumulative across the connection).
- On success `rss_feeds.error_count` is reset to 0 (not just incremented
  on failure). This lets a previously-failing feed recover naturally.
- `time.sleep(FEED_DELAY_SECONDS)` is mocked in unit tests; on real runs
  it produces the 2s delay between feeds.
- `--dry-run` path preserves the length logic (`articles` is still
  computed so log lines stay informative), but does NOT call INSERT or
  UPDATE.

## 5. Local smokes

Unit tests only. A live `--max-feeds 5 --dry-run` smoke requires network
access to `feedparser.parse` targets; Windows dev proxy blocks many RSS
hosts. This is a Hermes-side gate (next section).

## 6. Hermes-side verification (operator to run)

```bash
cd ~/OmniGraph-Vault && git pull --ff-only
venv/bin/pip install -r requirements.txt

# Unit tests
venv/bin/python -m pytest tests/unit/test_rss_fetch.py -v

# Dry-run smoke (no DB writes)
venv/bin/python enrichment/rss_fetch.py --max-feeds 5 --dry-run

# Real run — a few minutes; at 2s/feed × 92 feeds ≈ 3+ min
venv/bin/python enrichment/rss_fetch.py --max-feeds 20
sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM rss_articles;"

# Re-run must be near-zero inserts (dedup)
venv/bin/python enrichment/rss_fetch.py --max-feeds 20
```

Expected first-pass insertion: tens to low hundreds of rows across 20
feeds. Expected re-run: 0–few (only brand-new posts since last fetch).

## 7. Known caveats

- Some feeds return long UTF-8 encoded HTML entities that langdetect
  may misclassify on first ~2000 chars. Behaviour left conservative:
  such articles are dropped rather than inserted under a wrong
  language — preserves downstream graph consistency.
- `published_at` is stored as whatever string feedparser produces
  (no parsing/normalization). Downstream digest SQL is responsible
  for any date-sensitive filtering.

## 8. Commits

1. (pending) — `feat(05-02): rss_fetch.py + 7 unit tests + SUMMARY`

## 9. Hand-off

Plan 05-02 complete. Plan 05-03 (`enrichment/rss_classify.py`) unblocked:
`rss_articles` rows now flow in via `rss_fetch.py`; classifier can query
them.

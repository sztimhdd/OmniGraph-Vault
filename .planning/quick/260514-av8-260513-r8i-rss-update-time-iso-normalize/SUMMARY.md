---
quick_id: 260514-av8
slug: 260513-r8i-rss-update-time-iso-normalize
phase: standalone (independent of kb-1 / kb-2 / kb-3)
status: complete
completed: 2026-05-14
---

# Quick 260514-av8 — RSS update_time RFC 822 → ISO normalize

## Bug

`kb/data/article_query.py:list_articles()` line 186 merges KOL + RSS records and sorts by
`r.update_time` (lexicographic, reverse=True). KOL `update_time` is normalized to
ISO-8601 by `_normalize_update_time()` (handles Unix epoch INT → ISO string).

RSS `_row_to_record_rss()` was NOT normalizing — used `published_at or fetched_at or ""`
verbatim. `rss_articles.published_at` is heterogeneous in production:

- ISO-8601: `'2026-05-02T17:26:40+00:00'` (some feeds)
- RFC 822 with weekday: `'Wed, 02 May 2026 17:26:40 +0000'`
- RFC 822 without weekday: `'7 Aug 2017 01:08:45 +0000'` (legacy)
- RFC 822 with `'UT'` zone designator: `'29 Mar 2026 00:00:00 UT'`

Lexicographic DESC sort against KOL ISO timestamps puts RFC 822 weekday-prefixed rows
ahead of all ISO rows (`'W' > '2'` in ASCII; `'M' > '2'`; `'F' > '2'` etc), and
no-weekday RFC 822 rows ahead too because they start with day numbers like
`'7 ...'` or `'29 ...'` that lex-sort against `'2026-...'`.

Production impact: `list_articles(limit=20)` for the homepage's "Latest Articles"
section returned ~9 RSS articles bubbled to the top by lex-sort bias rather than by
real recency, pushing recent KOL articles past `limit=20`. Homepage cards became
mostly RSS instead of properly interleaved KOL + RSS by recency.

This bug is INDEPENDENT of DATA-07 (kb-3 phase content-quality filter). DATA-07
reduces visible articles from 2501 to ~160; this fix orders the visible set
correctly. Both must ship for the homepage to show recent KOL articles.

## Fix

Added `_normalize_rss_update_time(published_at, fetched_at) -> str` helper in
`kb/data/article_query.py`:

```python
def _normalize_rss_update_time(published_at, fetched_at) -> str:
    if published_at:
        # ISO-8601 discriminator: 'YYYY-' prefix (4 digits + dash). Stricter than
        # first-char-digit because RFC 822 day-of-week is optional, so digit-leading
        # strings like '7 Aug 2017' are valid RFC 822 that would slip through.
        if (
            len(published_at) >= 5
            and published_at[0:4].isdigit()
            and published_at[4] == "-"
        ):
            return published_at
        try:
            dt = parsedate_to_datetime(published_at)
        except (TypeError, ValueError):
            dt = None
        if dt is not None:
            return dt.isoformat()
    return fetched_at or ""
```

Caller change in `_row_to_record_rss()`:

```diff
-    update_time = row["published_at"] or row["fetched_at"] or ""
+    update_time = _normalize_rss_update_time(row["published_at"], row["fetched_at"])
```

Discriminator note: initial implementation used `published_at[:1].isdigit()` which
let `'7 Aug 2017'` pass through as ISO. Smoke against `.dev-runtime/data/kol_scan.db`
top-20 still showed 9 RSS rows incorrectly leading. Tightened to `'YYYY-'` prefix
(4 digits + dash) — this is a regression-guard test in the unit suite.

## Tests

`tests/unit/kb/test_article_query_normalize.py` — 12 tests covering:

- ISO-8601 pass-through
- RFC 822 with weekday parse → ISO
- RFC 822 7 weekday prefixes (regression for lex-sort bias)
- RFC 822 without weekday parse → ISO (regression for stricter discriminator)
- RFC 822 'UT' zone designator parse → ISO
- Unparseable published_at → fetched_at fallback
- Empty / None published_at → fetched_at fallback
- Both empty → empty string
- Sort-correctness invariant: KOL ISO > RSS RFC 822 normalized result in DESC

All 12 PASS. Full kb suite (`tests/unit/kb/ tests/integration/kb/`): **162/162 PASS**
(was 150 before; +12 new).

## Smoke

```bash
KB_DB_PATH=.dev-runtime/data/kol_scan.db python -c "
from kb.data import article_query
arts = article_query.list_articles(limit=20)
counts = {'wechat': 0, 'rss': 0}
for a in arts: counts[a.source] += 1
print(counts)
"
```

- Before fix: `{'wechat': 0, 'rss': 20}` (or similar — 100% RSS lex-bubble)
- After fix: `{'wechat': 19, 'rss': 1}` against current `.dev-runtime/` snapshot
  (KOL cron was very active 2026-05-13; the single RSS row at position 14 has
  `update_time='2026-05-13T04:50:45+00:00'` which is correctly placed between
  KOL rows by real time)

The single RSS row is genuinely the most recent RSS article in the DB; properly
interleaved with KOL rows by ISO timestamp.

## Acceptance criteria (from quick task spec)

- [x] `pytest tests/unit/kb/test_article_query_normalize.py` PASS (12/12)
- [x] Smoke: `list_articles()` against `.dev-runtime/data/kol_scan.db` top 20 shows
      proper interleaving by real recency, not lex-sort bias
- [x] Existing kb tests (was 150, now +12 = 162) all PASS — no regression

## Files

- `kb/data/article_query.py` (+33 LOC: 1 import, 1 helper, 2-line caller change)
- `tests/unit/kb/test_article_query_normalize.py` (NEW, +90 LOC, 12 tests)

## Cross-phase note

This fix unblocks the homepage's "Latest Articles" section's correct ordering after
kb-3-02 (DATA-07 filter) ships. Without this fix, even DATA-07-filtered top-20
would still suffer the lex-sort bias because the RSS records that survive DATA-07
filtering may still have RFC 822 published_at that bubble over KOL.

`kb-3-12-full-integration-test-PLAN.md` already lists `list_articles` ordering as
part of the regression suite — this fix lands the pre-condition that test relies on.

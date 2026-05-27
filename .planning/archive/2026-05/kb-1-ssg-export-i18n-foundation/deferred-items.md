# Phase kb-1 Deferred Items

Out-of-scope discoveries surfaced during phase kb-1 execution. Not fixed in
their originating plan; tracked here for future planning.

## kb-1-10 (2026-05-13): RSS published_at format heterogeneity

**Surfaced during:** kb-1-10 real-DB smoke (`KB_DB_PATH=.dev-runtime/data/kol_scan.db ... export --limit 3`)

**Finding:** `rss_articles.published_at` column contains mixed format strings:
- ISO-8601: `'2026-05-02T17:26:40+00:00'`
- RFC 822: `'Wed, 4 Sep 2024 04:31:00 +0000'`

**Effect:** RFC 822 strings sort lexicographically AFTER ISO-8601 strings
(because `'W'` > `'2'` in ASCII). So the merged DESC sort in `list_articles`
surfaces chronologically-old RFC-822 RSS rows ahead of recent ISO-8601 KOL
rows. Sitemap `<lastmod>` for these rows shows `Wed, 4 Sep` (truncated to
10 chars) instead of an ISO date.

**Out of scope for kb-1-10 per CLAUDE.md "Surgical Changes":** kb-1-10's gap
was specifically the int-vs-str TypeError crash. The RFC 822 / ISO-8601
heterogeneity is a pre-existing data shape issue independent of the row
mapper bug; the KOL-side normalization in this plan does not affect RSS rows.

**Suggested future fix (NOT in this plan):**
1. Add ISO-8601 normalization for `_row_to_record_rss` (mirror `_normalize_update_time`
   but parse RFC 822 → ISO; use `email.utils.parsedate_to_datetime`).
2. OR: one-shot migration sweep on `rss_articles.published_at` to backfill ISO format.

**Evidence:** `.scratch/kb-1-10-real-db-smoke-20260513-091713.log` lines 36-41 (sitemap
sample showing RFC 822 truncation) and 64-71 (out-of-scope finding section).

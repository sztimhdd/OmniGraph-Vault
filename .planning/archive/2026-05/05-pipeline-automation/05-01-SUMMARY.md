---
phase: 05-pipeline-automation
plan: 01
subsystem: rss-schema-and-opml
tags: [wave1, rss, schema, opml, seed]
status: complete
created: 2026-05-02
completed: 2026-05-02
---

# Plan 05-01 SUMMARY — RSS schema + OPML bundle + seed

**Status:** Complete
**Wave:** 1 (started)
**Depends on:** 05-00 (closed 2026-05-02 @ `0109c02`)

## 1. What shipped

| Task | Artifact | Status |
|------|----------|--------|
| 1.1  | `enrichment/rss_schema.py` + `tests/unit/test_rss_schema.py` (7 tests) | 7/7 pass |
| 1.2  | `init_rss_schema(conn)` wired at end of `batch_scan_kol.init_db` | verified via `init_db(tmp)` smoke |
| 1.3  | `data/karpathy_hn_2025.opml` bundled + `feedparser`/`langdetect` in `requirements.txt` + `tests/verify_rss_opml.py` | 92 feeds parse; 3/3 sample URLs found |
| 1.4  | `scripts/seed_rss_feeds.py` | local smoke: 0 → 92; re-run 92 → 92 (idempotent) |

## 2. Feed counts

| Step | Count |
|------|-------|
| OPML outline\[@type='rss'\] entries | 92 |
| `rss_feeds` rows after first seed (local tmp DB) | 92 |
| `rss_feeds` rows after second seed (re-run) | 92 |
| Sample-URL hits (simonwillison / gwern / antirez) | 3/3 |

The spec plan cited `paulgraham` as a sample; the actual gist at
`emschwartz/e6d2bf860ccc367fe37ff953ba6de66b` (filename
`hn-popular-blogs-2025.opml`) does NOT include paulgraham. `antirez` was
substituted; `simonwillison` and `gwern` retained. 92-count is the
authoritative gate, not the specific sample list.

## 3. Schema DDL reference

Three tables, all idempotent via `CREATE TABLE IF NOT EXISTS`:

- `rss_feeds` — feed registry, `xml_url UNIQUE`, `active INTEGER DEFAULT 1`,
  `error_count INTEGER DEFAULT 0`.
- `rss_articles` — fetched articles, `url UNIQUE`, `enriched INTEGER DEFAULT 0`
  (state machine 0 → 2 per D-19), `content_hash` + `content_length` columns.
- `rss_classifications` — per-article × topic classification, `UNIQUE(article_id,
  topic)`, `depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3)`. Column
  layout mirrors Phase 10 `classifications` for operator-tooling compatibility.

Full DDL at [enrichment/rss_schema.py](../../../enrichment/rss_schema.py).

## 4. OPML quirks encountered

- Gist filename is `hn-popular-blogs-2025.opml`, not `karpathy_hn_2025.opml`.
  File bundled in-repo under the Phase 5 plan's canonical name.
- Gist fetched via `gh api gists/<id> --jq '.files[<filename>].content'`.
  Direct `raw.githubusercontent.com` URL returns 404 for this gist without
  knowing the current raw-commit hash; `gh api` is the reliable path.
- OPML structure: single `<outline text="Blogs">` with 92 child
  `<outline type="rss" xmlUrl="...">` entries. No category subfolders.
- `data/` is gitignored; `.gitignore` amended to `data/*` + explicit
  `!data/karpathy_hn_2025.opml` negation so the file is tracked while
  `kol_scan.db` and other runtime state stay ignored.

## 5. Hermes-side verification (to run on remote)

Manual smokes for Hermes operator, not blocking local completion:

```bash
# Pull and install new deps
cd ~/OmniGraph-Vault && git pull --ff-only
venv/bin/pip install -r requirements.txt

# Run init_db and seed
venv/bin/python -c "import batch_scan_kol; batch_scan_kol.init_db(__import__('pathlib').Path('data/kol_scan.db'))"
sqlite3 data/kol_scan.db ".tables" | tr ' ' '\n' | grep -E '^rss_'
# Expected:
#   rss_articles
#   rss_classifications
#   rss_feeds

venv/bin/python scripts/seed_rss_feeds.py
sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM rss_feeds;"
# Expected: 92
```

## 6. Confirmed: re-seed is a no-op

Second run of `seed_rss_feeds.py` on the same DB produces
`rss_feeds count: 92 -> 92`. INSERT OR IGNORE + UNIQUE(xml_url) holds.

## 7. Commits

1. `ad71fa2 feat(05-01): add enrichment/rss_schema.py + unit tests`
2. `e1418bf feat(05-01): wire init_rss_schema into batch_scan_kol.init_db`
3. `0a115ab feat(05-01): bundle karpathy_hn_2025.opml + add feedparser/langdetect deps`
4. (this SUMMARY + scripts/seed_rss_feeds.py)

## 8. Hand-off

Plan 05-01 complete. Plan 05-02 (`enrichment/rss_fetch.py`) unblocked —
schema tables + 92-feed registry in place.

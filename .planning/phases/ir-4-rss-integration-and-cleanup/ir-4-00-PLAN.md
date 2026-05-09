# ir-4 W0 — Pre-flight audit (read-only)

**Status:** done (no code commit; report only)
**Report:** `.scratch/ir-4-w0-preflight-20260508-175008.md` (gitignored, 295 lines)

## Why W0

Original plan from user prompt assumed certain structural facts that needed
verification before W1 started. Two "feared STOP" conditions and 10
architectural details verified before any production code change.

## Items audited (all PASS or non-STOP discovery)

| Item | Verdict | Action |
|---|---|---|
| `feeds` table presence | **misnamed** — actual table is `rss_feeds` (92 rows) | W1 SQL JOIN uses `rss_feeds f` |
| `rss_articles` layer2_* columns | local DB missing 4 cols (production has them) | apply migration 007 to local before W1 G2 |
| `_scrape_generic` helper | exists at `lib/scraper.py:283` | W2 uses public `scrape_url(url)` auto-route |
| `persist_layer1/2_verdicts` source-aware | already dispatch by source (lib/article_filter.py:585+639) | W2 needs no change to persist functions |
| `ArticleMeta.source` field | already present (line 113) | W2 just wires caller |
| `ingestions` FK + CHECK + enrichment_id | FK to `articles(id)`; status CHECK 6 values; `enrichment_id TEXT` col | W1 migration 008 must drop FK + preserve CHECK + preserve enrichment_id |
| `step_7_ingest_all` body | wraps both KOL + RSS sub-commands | W4 collapses to single dual-source invocation |
| `register_phase5_cron.sh:81-83` | registers `rss-classify` cron | W3 inline removes |
| 67 grep hits across `*.{py,sh,md,json,yaml,yml}` | most are `.planning/`/`docs/` historical | 11 real consumers (W3+W4 retire 4 files; edit 7) |
| `rss_articles.body` fill ratio | 27% have body >100 chars (445/1600) | W2 RSS body skip-scrape threshold = 100 |

## STOP-and-redesign threshold

Triggered if any of:

- `rss_articles` missing layer1_verdict columns (would force migration 008
  scope expansion to add them)
- `_scrape_generic` not present in `lib/scraper.py` (would force W2 to add it)
- `persist_layer1/2` not source-aware (would force W2 to refactor those
  functions, expanding scope significantly)
- 5+ surprise consumers in grep (would force scope re-evaluation)

None triggered. W0 cleared the path for W1.

## User open questions answered (4)

| Q | A | Effect |
|---|---|---|
| Q1: auto-apply migration 007 to local DB? | YES with timestamped backup | Done at `.scratch/ir-4-w1-mig007-local.log` (8 cols added on 1st run, all SKIP on 2nd) |
| Q2: rename step_7? | KEEP NAME | step_7_ingest_all docstring updated to reflect dual-source semantics |
| Q3: `layer2_score` column in scope? | NO (out of ir-4) | migration 007 only has 4 layer2_* cols; score persistence is future migration 009 |
| Q4: `max_rss` removal break Hermes cron? | NO (operator confirmed via SSH probe) | W4 dropped `max_rss` from step_7 and `run()` signatures |

# Quick 260510-p1s — Standalone batch_classify_rss_layer2.py cron

## What changed

- NEW `batch_classify_rss_layer2.py` (220 lines) — argparse CLI + asyncio.run drain, mirrors KOL Layer 2 scoring via lib.article_filter.layer2_full_body_score
- NEW `tests/unit/test_batch_classify_rss_layer2.py` (291 lines, 7 tests) — mock-only, no network calls
- EDIT `scripts/register_phase5_cron.sh` (+6 lines, one add_job block)

## Why

Post-ir-4 (LF-5.2 retired `enrichment/rss_classify.py`), RSS articles had no Layer 2
classifier tick. Their `layer2_verdict` stayed NULL forever, blocking the ingest cron's
`layer2_verdict='ok'` gate. KOL's analogous tick (`daily-classify-kol` @ 08:15) had no
RSS counterpart. This quick adds it as `daily-classify-rss-layer2` @ 08:20 ADT.

## Smoke evidence

- **Pytest: 7/7 GREEN** — see `.scratch/rss-layer2-pytest-20260510-181244.log` L1-L18
  (last line: `7 passed in 2.23s`)

- **Dry-run: 88 RSS candidate rows found, [DRY-RUN] logged for all 18 batches, no UPDATE applied**
  — see `.scratch/rss-layer2-dryrun-20260510-181244.log` L1-L20
  Post-run DB check: `SELECT COUNT(*) FROM rss_articles WHERE layer2_at >= datetime('now','-1 minute')` returned 0 (no rows updated).

- **Cron syntax: `bash -n` exit 0** + grep confirms ordering:
  `daily-classify-kol` (line 88) → `daily-classify-rss-layer2` (line 94) → `daily-enrich` (line 101)
  — see `.scratch/rss-layer2-cron-syntax-20260510-181244.txt` L1-L5

## Operator follow-up (Hermes side)

SSH Hermes, then:

```bash
cd ~/OmniGraph-Vault && git pull --ff-only
bash scripts/register_phase5_cron.sh
hermes cron list | grep daily-classify-rss-layer2
```

Expected: `ADD daily-classify-rss-layer2 @ 20 8 * * *` on first run,
`SKIP` on subsequent runs. Tomorrow 08:20 ADT first natural fire. Watch
`/tmp/rss-layer2-YYYYMMDD.log` for the per-row classification output.

Note: real LLM calls will route through DeepSeek (corp-blocked locally but available on Hermes). The 88-row backlog in `.dev-runtime/data/kol_scan.db` will drain on the first Hermes cron fire.

## Files NOT touched (per surgical-changes principle)

- `batch_ingest_from_spider.py`
- `batch_classify_kol.py`
- `lib/article_filter.py`
- `tests/unit/test_ainsert_persistence_contract.py`
- `rss_articles` schema (no migrations)

## Risk

LOW. Net-new code path. Existing crons untouched. Cron syntax validated locally.
Rollback: `git revert HEAD` (reverts the 5 changed/new files atomically).

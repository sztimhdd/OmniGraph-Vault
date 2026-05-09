# ir-4 Phase Closure — RSS integration into batch ingest + legacy pipeline cleanup

**Date:** 2026-05-09
**Phase:** v3.5-Ingest-Refactor / ir-4
**Status:** Code complete on local main; awaiting user `继续` to push origin/main +
operator deploy via `HERMES-DEPLOY-ir-4.md`. **LF-4.4 sign-off DONE locally**;
production validation lands at Step 7 of the deploy runbook.

## Commits (5 atomic, forward-only)

| Wave | Plan | Commit | Description |
|---|---|---|---|
| W1 | `ir-4-01-PLAN.md` | `5d943f8` | feat(ir-4 W1): migration 008 dual-source ingestions + UNION ALL candidate SQL (LF-4.4) |
| W2 | `ir-4-02-PLAN.md` | `df495c8` | feat(ir-4 W2): _needs_scrape helper + _persist_scraped_body source dispatch (LF-4.4) |
| W3 | `ir-4-03-PLAN.md` | `4cc3757` | refactor(ir-4 W3): retire enrichment/rss_classify.py + step_2 + cron registration (LF-5.2) |
| W4 | `ir-4-04-PLAN.md` | `9ff330d` | refactor(ir-4 W4): retire enrichment/rss_ingest.py + step_7 RSS branch + harness rss hint (LF-5.1) |
| W5 | (this file) | `<W5 hash>` | docs(ir-4 W5): close-out — PLAN dir + HERMES-DEPLOY + CLOSURE + STATE/ROADMAP |

W0 was an audit-only wave (no commit) — report at
`.scratch/ir-4-w0-preflight-20260508-175008.md`. Migration 007 was
applied to the local `.dev-runtime/data/kol_scan.db` ahead of W1 G2 to
bring local in sync with production (idempotent twin runner; backup left
at `.dev-runtime/data/kol_scan.db.pre-007-20260508-212825.bak`).

Net delta across W1..W4: **+1062 / -944 = +118 lines** (W1 added migration
+ tests, W3+W4 retired more lines than they added).

## REQ coverage (with scope-deviation note)

| REQ | Wave | Status | Evidence |
|---|---|---|---|
| LF-4.4 | W1 + W2 | **DONE** | Dual-source UNION ALL (commit `5d943f8`) + dispatch helpers (commit `df495c8`); 1749 candidates verified end-to-end; 7-col tuple via cursor.description; FIFO transition KOL→RSS at row 149; anti-join 0 false positives. See `.scratch/ir-4-w1-dualsql.log` + `.scratch/ir-4-w1-mig008-1st.log`. |
| LF-5.1 (effective) | W4 | **DONE** | `enrichment/rss_ingest.py` deleted; step_7 unified to single dual-source invocation; harness rss mode prints migration hint. See `.scratch/ir-4-w4-rss-mode.log`. |
| LF-5.2 (effective) | W3 | **DONE** | `enrichment/rss_classify.py` deleted; step_2 + rss-classify cron registration removed. See commit `4cc3757`. |
| LF-5.1 (REQ-text) | — | **DEFERRED** | REQ text targets `_classify_full_body`/`_call_deepseek_fullbody`/`_build_fullbody_prompt` in `batch_ingest_from_spider.py`. These functions still serve the KOL graded-classify path (`OMNIGRAPH_GRADED_CLASSIFY=1`). Out of ir-4 scope per user prompt. |
| LF-5.2 (REQ-text) | — | **DEFERRED** | REQ text targets `batch_classify_kol.py` deletion. The file is still the entrypoint for the live `daily-classify-kol` cron at "15 8 * * *". Out of ir-4 scope. |
| LF-5.3 | — | **DEFERRED** | DROP TABLE classifications + rss_classifications. REQ explicitly marks "optional, run only after operator confirms no consumer reads these tables for 7 days post-cleanup". |

### Scope deviation summary

The user prompt for ir-4 redirected the cleanup track from the original
REQ scope (LF-5.1 dead functions, LF-5.2 batch_classify_kol.py, LF-5.3
table drops) to a different and more impactful target: deleting the
legacy `enrichment/rss_classify.py` + `enrichment/rss_ingest.py`
pipelines that became redundant once the dual-source `--from-db` path
absorbed RSS. The original LF-5.x REQs remain pending and may be picked
up in a follow-up cleanup phase (likely v3.6 or post-milestone hygiene
quick).

## Local validation gate evidence

All gates PASS at every wave boundary. Logs gitignored; paths cited for
reviewer access via local checkout.

| Wave | Gate | Result | Evidence |
|---|---|---|---|
| W0 | pre-flight audit | 4 critical structural facts verified; 4 user open questions answered | `.scratch/ir-4-w0-preflight-20260508-175008.md` |
| — | local migration 007 catch-up | 8 cols ADD on 1st run, all SKIP on 2nd run (idempotent) | `.scratch/ir-4-w1-mig007-local.log` |
| W1 | G1 migration 008 idempotency | 1st: 577 rows migrated, all source='wechat', integrity:[(ok,)], fk:[]; 2nd: SKIP all 5 ops | `.scratch/ir-4-w1-mig008-1st.log`, `.scratch/ir-4-w1-mig008-2nd.log`, `.scratch/ir-4-w1-integrity.log` |
| W1 | G2 dual-source SQL | KOL=149 + RSS=1600 = 1749 candidates; 7 named cols; FIFO transition row 149; anti-join 0 false positives (122 wechat-ok rows correctly excluded) | `.scratch/ir-4-w1-dualsql.log` |
| W1 | G3 pytest | 37/37 W1 tests PASS (24 SQL + 13 migration). 3 pre-existing failures verified pre-existing on main pre-W1 via `git stash` + selective re-run | `.scratch/ir-4-w1-pytest-w1tests.log` |
| W1 | G4 harness smoke | EXIT=0, total inputs=1749 (matches G2) | `.scratch/ir-4-w1-kol-dryrun.log` |
| W2 | G1 pytest (W1+W2) | 72/72 PASS after fixing over-eager site_hint regex | `.scratch/ir-4-w2-pytest.log` |
| W2 | G2 harness regression | EXIT=0, total inputs=1749 unchanged | `.scratch/ir-4-w2-kol-dryrun.log` |
| W3 | G1 pytest | 106/106 PASS across W1+W2+W3 testsuites | `.scratch/ir-4-w3-pytest.log` |
| W3 | grep verify | 0 active code references to rss_classify or step_2_classify_rss; all hits are retirement comments / regression guards | `git grep -n "rss_classify\|step_2_classify_rss"` (in commit message) |
| W3 | G2 harness regression | EXIT=0, total inputs=1749 unchanged | `.scratch/ir-4-w3-kol-dryrun.log` |
| W4 | G1 pytest | 105/105 PASS across all ir-4 testsuites | `.scratch/ir-4-w4-pytest.log` |
| W4 | grep verify | 0 active code references to rss_ingest or step_2_classify_rss | (in commit message) |
| W4 | G2 harness rss-mode hint | EXIT=0, prints migration hint pointing at kol mode | `.scratch/ir-4-w4-rss-mode.log` |
| W4 | G2 harness kol regression | EXIT=0, total inputs=1749 unchanged | `.scratch/local-e2e-kol-20260509-103557.log` |

## Deviations vs. original prompt

The user prompt for ir-4 split work into 5 waves W1..W5 with W2
explicitly owning all `ingest_from_db` consumer-side changes. In
practice W1 had to pull the consumer-side updates forward to keep main
runnable end-to-end after W1 (otherwise the SQL returns 7-col rows but
the consumer unpacks 6, breaking the harness G4 regression smoke). W2's
remaining scope was therefore reduced to the dispatch helpers
(`_needs_scrape`, `_persist_scraped_body` source-dispatch, scrape_url
auto-route, removal of W1's KOL-only gate) plus the comprehensive
dispatch tests. User ack'd this deviation post-W1 ("4 deviations all
batch'd, 继续").

Other minor deviations (all user-ack'd):

- W1 introduced a temporary `if source == 'wechat'` scrape gate to make
  W1 atomically runnable; W2 lifted it. Between W1 and W2, RSS rows
  silent-skip the scrape — accepted because the deploy is one atomic
  push of all 5 commits, so production never sees the W1-only state.
- 3 pre-existing flaky tests (`test_text_first_ingest` 2 + 
  `test_vision_worker` 1) were flagged via `git stash` + pre-W1 main
  re-run; not fixed in W1/W4 (out of ir-4 scope). One fixture was
  cosmetically updated (`test_vision_worker.py`) so the SQL no longer
  raises "no such table: rss_articles" before the pre-existing failure
  mode triggers.
- Migration 007 was applied locally as a one-time sync action, with
  timestamped backup, logged to `.scratch/ir-4-w1-mig007-local.log`.
  The migration itself is already on production (operator SSH probe
  confirmed all 8 cols pre-ir-4).

## Hermes deploy gate

**Awaiting user `继续`** to:

1. Push local main → origin/main (5 ir-4 commits in one push).
2. Run `HERMES-DEPLOY-ir-4.md` Step-by-step on production:
   - Backup DB
   - Pause daily-ingest cron
   - Apply migration 008
   - Verify schema + rebuild idempotency
   - Remove legacy rss-classify cron job
   - Manual smoke (max=2)
   - Resume daily-ingest cron
   - Day-1 audit at +24h

Operator runbook in `HERMES-DEPLOY-ir-4.md`. Failure-mode + rollback
sections present.

## Known unknowns (operator-side at deploy time)

- Production candidate counts (KOL + RSS) — local snapshot showed 149
  KOL + 1600 RSS, production will differ. Deploy Step 6 captures the
  day-0 baseline.
- Real RSS ingest behavior at scale — local validation only proved the
  dispatch path is wired correctly; the first real run will surface any
  edge cases in the generic scraper cascade for diverse RSS feed URLs
  (W0 audit showed 92 distinct feeds spanning blogs / news / dev sites).
- Layer 2 + ainsert behavior on RSS-shaped content — DeepSeek Layer 2
  was tuned on KOL article bodies; RSS feeds may have different
  body-shape distributions (shorter, more excerpts) that affect the
  reject rate.
- Backlog drain wall-clock — the 1500+ RSS pool will take 4-5 weeks at
  the recommended cadence (50/day catch-up + 30/day baseline). ir-3's
  7-day observation window starts after deploy, so the milestone is
  formally close-able 7 days after Step 8 completes successfully (or
  later if the day-1 audit at Step 10 surfaces issues).

## Next phase

ir-3 (calendar wait + observation). v3.5 milestone closes at ir-3 PASS
+ backlog drain stable. Cleanup of LF-5.1/5.2/5.3 (REQ-text scope) may
spawn a v3.5 follow-up quick or roll into v3.6.

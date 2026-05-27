---
id: 260508-ev2
title: daily-ingest cron deploy hardening (F1a + F1b + F2)
status: shipped
mode: quick
created: 2026-05-08
shipped: 2026-05-08
total_commits: 4
forward_only_git: true
---

# Quick 260508-ev2 — Summary

Three orthogonal fixes for the 2026-05-08 09:00 ADT cron failure documented
in `docs/bugreports/2026-05-08-cron-ingest-failure.md`. Each task is one
atomic commit; all four (3 code + 1 docs) land on `main` forward-only.

R3 (cron model selection — `gemini-2.5-flash` instead of DeepSeek) is
operator-only and covered by `HERMES-DEPLOY-260508-ev2.md` Step 3.
R4/R5 (vision worker timing, QR fallback) are out of scope.

## Commits

### F1a — Apify dual-token rotation
- **Commit:** `f6d6abe177202273272a00fc4f5d2cfaf98d86f2`
- **What:** Extracts `_apify_call(token, url)` helper from `scrape_wechat_apify`.
  Public function tries `APIFY_TOKEN` first; on **any** Exception falls through
  to `APIFY_TOKEN_BACKUP`; if both raise re-raises the LAST exception. Both
  unset preserves the legacy "skip Apify" path. New env var documented in
  `.env.example`.
- **Why:** Cron R1 root cause — primary Apify token returned `Maximum charged
  results must be greater than zero` for 5/5 articles, wasting ~150s of the
  900s budget on hard-fail loops. Backup token gives the cascade a second
  shot before falling through to UA.

### F1b — Cascade reorder UA-first + `SCRAPE_CASCADE` env override
- **Commit:** `80bdcd34f618205b5341108f5fd85c67df8ea7f5`
- **What:** `lib/scraper.py` default cascade tuple changed from
  `(apify, cdp, mcp, ua)` to `(ua, apify, cdp, mcp)`. New
  `_resolve_cascade_order()` reads `SCRAPE_CASCADE` env (comma list of
  `{ua, apify, cdp, mcp}`) — invalid/empty → default + warning.
  `ingest_wechat.py:982-989` direct cascade has cosmetic if/else inversion
  (CDP-local now appears first textually; semantics unchanged via
  `_is_mcp_endpoint(CDP_URL)` mutual exclusivity).
- **Why:** Cron R1 also showed UA was the only path that worked — 5/5
  articles succeeded on UA after the prior 3 layers wasted ~600s combined.
  UA-first eliminates the wasted attempts; the env var lets cron pin
  `SCRAPE_CASCADE=ua` (or `ua,apify`) when the upper layers are known
  broken without redeploying code.

### F2 — `cron_daily_ingest.sh` tmux helper
- **Commit:** `36ab63e34ee5ebb584afd41ba347815662534c15`
- **What:** New `scripts/cron_daily_ingest.sh` (executable, mode `100755`)
  detects same-day alive sessions (refuses double-launch), reaps dead panes,
  kills cross-day stale `daily-ingest-*` sessions, then launches the chained
  command `cleanup_stuck_docs.py --all-failed && batch_ingest_from_spider.py
  --from-db --max-articles ${1:-10}` inside detached tmux. Default
  `MAX_ARTICLES=10`. Single-line log path
  `/tmp/daily-ingest-YYYYMMDD-HHMM.log`.
- **Why:** Cron R2 — Hermes terminal tool 900s ceiling truncated the batch
  mid-vision-drain after only 1 article had landed (single-article p50
  ≈11min). Tmux runs the python process detached so the cron prompt becomes
  monitor-only (tail log + `tmux ls` + DB row count) instead of blocking on
  the long-running batch.

### Docs commit (this file)
- **Commit:** _(this commit, hash assigned at landing)_
- **What:** PLAN.md + this SUMMARY.md + `HERMES-DEPLOY-260508-ev2.md`
  operator runbook.

## Test evidence

| Task | Log path | PASS/Total | Lines |
|------|----------|------------|-------|
| Baseline | `.scratch/quick-260508-ev2-baseline.log` | 45/45 | totals on final line `45 passed, 11 warnings in 106.17s` |
| F1a | `.scratch/quick-260508-ev2-f1a.log` | 3/3 + 45/45 regression | new tests L10-L12, totals L44; regression appended at file tail |
| F1b | `.scratch/quick-260508-ev2-f1b.log` | 5/5 + 59/59 regression | new tests L10-L14; regression on final line `59 passed, 11 warnings in 11.18s` |
| F2 | `.scratch/quick-260508-ev2-f2.log` | 4 PASS + 1 SKIP + 64/64 regression | new tests L10-L14 (shellcheck SKIPPED — not in PATH on Windows host); regression on final line `64 passed, 11 warnings in 11.33s` |

ZERO live network calls — all tests use `unittest.mock` / `monkeypatch`.

Regression suite covered: `test_scraper.py`, `test_scrape_first_classify.py`,
`test_scrape_on_demand_apify_markdown.py`, `test_scraper_ua_img_merge.py`,
`test_ingest_wechat_cognee_gate.py`, `test_apify_rotation.py`,
`test_scrape_cascade_order.py`, `test_checkpoint_ingest_integration.py` —
all 64 tests PASS unchanged.

## Out-of-scope confirmation

- Did NOT modify `~/.hermes/.env`
- Did NOT modify `~/.hermes/cron/jobs.json`
- Did NOT SSH Hermes
- Did NOT touch `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE-v3.5.md`
- Did NOT touch LightRAG / Layer 1 / Layer 2 / migration code
- ZERO live network calls (Apify, WeChat, etc.)

## Operator handoff

See `HERMES-DEPLOY-260508-ev2.md` for the runbook the operator runs on the
Hermes host (git pull, env update, cron prompt update, smoke test, exit
criteria).

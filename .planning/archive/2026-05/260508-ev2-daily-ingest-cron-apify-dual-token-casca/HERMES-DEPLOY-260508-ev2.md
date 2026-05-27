---
title: HERMES-DEPLOY runbook for quick 260508-ev2
target: Hermes production host (operator: Hai)
mode: monitor-only cron prompt
created: 2026-05-08
---

# HERMES-DEPLOY — quick 260508-ev2

Runbook for the operator to apply the 4 commits from quick 260508-ev2 to the
Hermes production host. **Self-contained: do not require re-reading
`260508-ev2-PLAN.md`.**

The 3 code fixes (F1a, F1b, F2) address R1 + R2 from the
`docs/bugreports/2026-05-08-cron-ingest-failure.md` postmortem. R3 (cron
model selection) is operator-only and addressed in **Step 3** below.

## Step 1 — Pull code

```
ssh <hermes-host>
cd ~/OmniGraph-Vault
git pull --ff-only
git log --oneline -5  # confirm 4 commits from quick 260508-ev2 are present
```

Expected commit titles in `git log`:

- `docs(quick-260508-ev2): plan + summary + Hermes deploy runbook`
- `feat(scripts): F2 cron_daily_ingest.sh tmux helper with stuck-doc pre-flight cleanup`
- `feat(scraper): F1b cascade reorder ua-first + SCRAPE_CASCADE env var override`
- `feat(ingest): F1a Apify dual-token rotation — primary→backup chain on any exception`

If `git pull` reports "diverged" or non-fast-forward — STOP, do not force.
Investigate before proceeding (forward-only deploy convention).

## Step 2 — Env update (`~/.hermes/.env`)

Append the new env vars **only if absent** (do not duplicate). Use idempotent
appends:

```
grep -q '^APIFY_TOKEN_BACKUP=' ~/.hermes/.env || \
  echo "APIFY_TOKEN_BACKUP=${APIFY_TOKEN_BACKUP_VALUE:?set this var to the backup token from Hai's session notes before running}" >> ~/.hermes/.env

# NOTE: The literal backup token was provided by the user in the 260508-dep
# session prompt. Retrieve it from that conversation (or Hai's password manager)
# and export APIFY_TOKEN_BACKUP_VALUE before running the line above. The token
# is intentionally NOT committed to this repo — keeps GitHub secret scanning happy.

# Optional cascade override (RECOMMENDED for cron — UA-only is fastest while
# Apify token is wedged). Once Apify token is fixed, change to "ua,apify" or
# unset entirely (default = ua,apify,cdp,mcp).
grep -q '^SCRAPE_CASCADE=' ~/.hermes/.env || \
  echo 'SCRAPE_CASCADE=ua,apify' >> ~/.hermes/.env
```

Verify:

```
grep -E '^(APIFY_TOKEN_BACKUP|SCRAPE_CASCADE)=' ~/.hermes/.env
```

Expect exactly 2 lines.

## Step 3 — Cron prompt update (R3 fix + monitor-only template)

Cron job ID: `2b7a8bee53e0` (daily-ingest, 06:00 ADT). Edit
`~/.hermes/cron/jobs.json` for that entry; replace the existing
`run batch_ingest_from_spider.py …` prompt with the **monitor-only template**:

```
执行 ~/OmniGraph-Vault/scripts/cron_daily_ingest.sh 10 启动 daily-ingest tmux session。

等待 30s 让 cleanup + LightRAG init 启动,然后:
1. tmux ls 确认 daily-ingest-YYYYMMDD session 存在
2. tail -50 /tmp/daily-ingest-*.log 看 cleanup 输出 + ingest 启动行
3. 查 SQLite ingestions 表今日 count(如果 N > 0,说明已开始 ingest)
4. 简短 Telegram 报告:tmux session 状态 / log tail / ingestions count

不要 attach to tmux session(后台运行即可)。
不要 SIGTERM batch_ingest 进程。
不要等到 ingest 跑完(可能 1 小时+)。
```

**R3 fix — model selection:** in the same `jobs.json` entry, set:

```
"model": {"provider": "deepseek", "model": "deepseek-chat"}
```

Currently the field is `null` and inherits the Hermes gateway default
(`gemini-2.5-flash` with 250 RPD ceiling). Pinning DeepSeek removes the
batch-internal 429 risk for ~80-120 LLM calls per article.

Reload Hermes cron after editing:

```
hermes cron reload   # or whatever the operator's reload command is
```

## Step 4 — Manual trigger + verify

Two options to trigger the new tmux helper:

**Option A — Hermes cron-run-now** (executes the prompt edited in Step 3):

```
hermes cron run-now 2b7a8bee53e0
```

**Option B — direct script smoke (3-article run, faster verify):**

```
cd ~/OmniGraph-Vault
bash scripts/cron_daily_ingest.sh 3
```

Either way, verify within 60s:

```
tmux ls | grep daily-ingest                    # session present
tail -50 /tmp/daily-ingest-$(date +%Y%m%d)-*.log  # cleanup output + ingest start

# DB confirmation — count of today's ingestions:
sqlite3 data/kol_scan.db \
  "SELECT count(*) FROM ingestions WHERE date(ingested_at)=date('now','localtime')"
```

## Step 5 — Exit criteria

Sign off when ALL of the following hold:

- [ ] `tmux ls` shows the `daily-ingest-YYYYMMDD` session active OR cleanly
      exited (look at `/tmp/daily-ingest-*.log` tail — should end with the
      `time -v` summary, NOT a SIGTERM)
- [ ] `/tmp/daily-ingest-*.log` shows the cleanup script completed without
      raising, and at least 1 article reached LightRAG (look for
      `[layer2]` markers + `LightRAG init` line)
- [ ] `ingestions` table has ≥1 fresh row from today (`SELECT count(*) ...`
      from Step 4 returns ≥1)
- [ ] No `Apify scraping failed: Maximum charged results must be greater
      than zero` lines in the log (R1 fix verified)
- [ ] No `BrowserType.connect_over_cdp: Timeout 30000ms exceeded` lines
      in the log if `SCRAPE_CASCADE=ua,apify` was set (cascade did not
      attempt the wedged CDP path)

## Rollback

If Step 4 trigger fails or Step 5 criteria are not met:

1. Revert env file edits (remove the 2 new lines added in Step 2)
2. Revert cron prompt to the previous text (operator's note: keep a copy
   before editing in Step 3)
3. The 4 commits in `~/OmniGraph-Vault` can stay — they are inert without
   the env vars and the new cron prompt. The legacy entrypoint
   `batch_ingest_from_spider.py --from-db --max-articles 10` still works
   when invoked directly (just slower because it inherits the legacy
   cascade order).

Do NOT `git revert` the 4 commits unless a code-path bug surfaces (the
F1a / F1b / F2 changes are forward-compatible with the legacy cron
invocation).

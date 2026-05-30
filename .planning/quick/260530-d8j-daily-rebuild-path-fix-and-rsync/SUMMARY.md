# 260530-d8j daily_rebuild path fix + Phase 5 rsync — SUMMARY

**Status:** ✅ CLOSED 2026-05-30 01:06 UTC
**Commit:** `f56a4a6` on `origin/main`
**Net diff:** +29 / −10 LoC, single file (`kb/scripts/daily_rebuild.sh`)
**Wall clock:** Phase 0–6 ~50 min (agent: 0–4 ~30 min; orchestrator: 5–6 ~20 min)

---

## What shipped

`kb/scripts/daily_rebuild.sh` v2:

1. **Bug 1 fix** — `export KB_INSTALL_PREFIX KB_DB_PATH KB_PYTHON` so subprocesses (`python -m kb.scripts.detect_article_lang`, `python kb/export_knowledge_base.py`, etc.) inherit the correct paths. Previously `: "${VAR:=...}"` set defaults but never `export`-ed them, so `kb/config.py:_env_path()` fell back to `~/.hermes/data/kol_scan.db` (nonexistent). Phase 1 silent-failed every 12:00 UTC since 2026-05-20.

2. **Bug 2 fix** — new Phase 5: `rsync -a --delete kb/output/ /var/www/kb/`. Caddy serves `/var/www/kb/` per `/etc/caddy/Caddyfile :80 handle /kb/* { root * /var/www/kb }`, but SSG bake writes `/root/OmniGraph-Vault/kb/output/`. No prior sync mechanism; `/var/www/kb/` had been stale since 2026-05-20 (last manual `cp -r`). Phase 5 wraps `|| { log; true; }` so a transient rsync error doesn't poison cron status.

Phase numbering updated `[N/4]` → `[N/5]` consistently.

## End-to-end verification (Phase 5 — orchestrator triggered manually)

```
ssh aliyun-vitaclaw "bash /root/OmniGraph-Vault/kb/scripts/daily_rebuild.sh"

[2026-05-30T09:05:??+08:00][daily-rebuild] [1/5] detect_article_lang
[2026-05-30T09:05:??+08:00][daily-rebuild] [1/5] OK         ← Bug 1 fixed (was ERROR DB not found)
[2026-05-30T09:05:??+08:00][daily-rebuild] [2/5] export_knowledge_base
... 293 articles + 180 entities + 5 topics + 19 wiki rendered
[2026-05-30T09:05:51+08:00][daily-rebuild] [2/5] OK
[2026-05-30T09:05:51+08:00][daily-rebuild] [3/5] rebuild_fts
[rebuild_fts] indexed 293 rows in 1.25s
[2026-05-30T09:05:53+08:00][daily-rebuild] [3/5] OK
[2026-05-30T09:05:53+08:00][daily-rebuild] [4/5] wal_checkpoint(TRUNCATE) + VACUUM
[2026-05-30T09:05:53+08:00][daily-rebuild] [4/5] OK
[2026-05-30T09:05:53+08:00][daily-rebuild] [5/5] rsync kb/output/ -> /var/www/kb/
[2026-05-30T09:05:53+08:00][daily-rebuild] [5/5] OK         ← Bug 2 fixed
[2026-05-30T09:05:53+08:00][daily-rebuild] ===== daily rebuild complete =====
```

Total wall: ~25 s for the full pipeline including rsync (~29 MB sync to `/var/www/kb/`).

## Aliyun KB site state post-fix

- 293 articles (vs 275 yesterday, +18 today daily-ingest)
- 180 entity pages
- 5 topic pages
- 19 wiki entity pages including **5 new Copilot Studio** (copilot-studio / declarative-agent / generative-orchestration / copilot-studio-vs-azure-ai-foundry / mcp-in-copilot-studio)
- Caddy serves: `http://101.133.154.49/kb/`

## Why this matters (user requirement #3 closure)

User stated 2026-05-28: "**每天阿里云负责扫描刮削筛选入库建图**" + "**翻译**".

Before this quick:

- ✅ daily-ingest cron was running (12:00 UTC)
- ✅ translate cron was running (14:00 UTC, since 2026-05-29 quick `260529-arm-translate-cron`)
- ❌ **daily_rebuild.sh** SSG bake cron silent-failed Phase 1 since 2026-05-20 (Bug 1)
- ❌ Even if it had run, no sync to `/var/www/kb/` (Bug 2) → users would still see stale

After this quick:

- ✅ daily_rebuild.sh runs all 5 phases end-to-end (Bug 1 fix verified)
- ✅ Caddy serve dir auto-syncs (Bug 2 fix verified)
- ✅ Tomorrow 12:00 UTC cron will produce a fully-fresh KB site without manual intervention

User requirement #3 is now end-to-end automated.

## Strategy choice (Phase 1 DECIDE)

User chose **Strategy A** (export env vars in daily_rebuild.sh). Rejected Strategy B (modify `detect_article_lang.py` defaults) because:

- `kb/config.py:34 _env_path()` already supports `KB_DB_PATH` env override — no python change needed
- Smaller blast radius (one file vs two)
- B would risk affecting other callers of `kb.config` (Hermes scripts, pytest fixtures)

## Decisions log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Strategy A vs B | A | kb/config already supports env, B is unnecessary |
| 2 | Phase 5 placement | LAST after WAL checkpoint | If rsync fails, DB integrity already ensured |
| 3 | rsync `--delete` | YES | kb/output/ is complete tree; deletes orphans like `index.html.bak-*` (pre-existing in `/var/www/kb/`) |
| 4 | rsync wrapping | non-fatal `\|\| { log; true; }` | Match Phase 4 pattern; transient rsync error shouldn't poison cron status |
| 5 | KB_SERVE_DIR env override | YES | Allow override for non-prod environments (dev / test) |

## Next actions filed

| Issue | Slug | Severity |
|---|---|---|
| sync_to_databricks.sh `apps start` auto-creates pending deployment, breaks Step 9c | `260530-sync-script-redeploy-race` | MEDIUM (1 of 2 sync runs hit it 2026-05-29) |
| sync_to_databricks.sh `read -p` doesn't get stdin in `run_in_background=true` | `260530-sync-script-yes-flag` | LOW (workaround: clean staging dir before launch) |
| Tavily module not installed on Aliyun (translate cron warning, non-fatal) | `260530-aliyun-tavily-install` | LOW |
| Vertex 429 RESOURCE_EXHAUSTED on batch 4 today (30 articles stay NULL) | not yet filed | LOW (per-day burst, not chronic) |

## Cross-references

- Memory: [[aliyun_kb_serve_dir_gap]] — root cause analysis for Bug 2 (now resolved by this quick)
- Memory: [[aliyun_drift_recovery_260528_lessons]] — Lesson 1 v2 v3 v4 systemd discipline preserved (this quick didn't touch timer/service config)
- Commit message: `f56a4a6`
- Companion quicks shipped same day: `260529-arm-translate-cron`, `260529-arx-sync-to-databricks`, `260529-d3p-promote-deploy-sh`, `260529-hlu-wiki-schema-bake-upgrade`

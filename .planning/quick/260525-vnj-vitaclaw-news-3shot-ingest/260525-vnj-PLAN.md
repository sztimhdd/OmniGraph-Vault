---
phase: quick/260525-vnj-vitaclaw-news-3shot-ingest
plan: 260525-vnj-PLAN
type: ops-config
wave: single
depends_on: []
files_modified:
  - /etc/systemd/system/omnigraph-daily-digest.service          # Aliyun (P2)
  - /etc/systemd/system/omnigraph-daily-ingest.service          # Aliyun (P4)
  - /etc/systemd/system/omnigraph-afternoon-ingest.service      # Aliyun (P4)
  - /etc/systemd/system/omnigraph-evening-ingest.service        # Aliyun (P4)
  - /etc/systemd/system/omnigraph-afternoon-ingest.timer        # Aliyun (P5)
  - root crontab                                                # Aliyun (P1)
autonomous: yes
requirements:
  - vitaclaw-site /data/agent-news.json regenerated daily by cron
  - JSON contract v1, exactly 5 items, ISO 8601 generatedAt
  - 3 ingest crons fire at 08:00 / 14:00 / 20:00 CST, each --max-articles 10
must_haves:
  - daily-digest.service ExecStart points at scripts/export_vitaclaw_agent_news.py
  - --output flag writes to /opt/vitaclaw/.../dist/data/agent-news.json
  - afternoon-ingest.timer OnCalendar=*-*-* 06:00:00 UTC (was 17:00 UTC)
  - all 3 ingest services use --max-articles 10
  - ghost cron gen_agent_news.sh removed from crontab
---

# 260525-vnj — vitaclaw agent-news.json + 3-shot ingest

Config-only quick. No code change in this repo. All mutations are on Aliyun
ECS (`aliyun-vitaclaw`) systemd unit files + root crontab. This document is
the trackable artifact for the change.

## What changed (Aliyun)

### P1 — Remove ghost cron

`gen_agent_news.sh` referenced in root crontab did not exist on disk.
Removed via `crontab -l | grep -v gen_agent_news.sh | crontab -`.
Remaining cron line: `0 12 * * * /root/OmniGraph-Vault/kb/scripts/daily_rebuild.sh`.

### P2 — Swap daily-digest ExecStart

`/etc/systemd/system/omnigraph-daily-digest.service`

- before: `ExecStart=…/python …/enrichment/daily_digest.py`
- after:  `ExecStart=…/python …/scripts/export_vitaclaw_agent_news.py --output /opt/vitaclaw/control-plane/vitaclaw-site/dist/data/agent-news.json`
- unit name preserved (no disable/enable churn). Backup `.bak-vnj` saved.
- P3 (patch DEFAULT_OUTPUT in script) intentionally skipped — explicit
  `--output` flag in ExecStart bypasses the Hermes-rooted default.

### P4 — Bump --max-articles 5 → 10

3 ingest services updated:

- `omnigraph-daily-ingest.service`
- `omnigraph-afternoon-ingest.service`
- `omnigraph-evening-ingest.service`

### P5 — Reschedule afternoon-ingest timer

`/etc/systemd/system/omnigraph-afternoon-ingest.timer`

- `OnCalendar=*-*-* 17:00:00 UTC` → `*-*-* 06:00:00 UTC` (= 14:00 CST)
- Description updated: "14:00 ADT (17:00 UTC)" → "14:00 CST (06:00 UTC)"

After all edits: `systemctl daemon-reload`.

## P6 — Timer verification

All 3 ingest timers `enabled` + `active`, correct NEXT timestamps for
Tue 08:00 / 14:00 / 20:00 CST. daily-digest timer also enabled+active.

## P7 — Smoke + contract verification

Manual run on Aliyun:

```
systemctl start omnigraph-daily-digest.service
# exit 0
```

JSON captured to `.scratch/260525-vnj-p7-evidence.json` (4107 bytes,
gitignored). Contract verified:

- `contractVersion = 1`
- `items.length = 5`
- `generatedAt = 2026-05-25T13:41:21.115712Z` (ISO 8601 UTC)
- All 5 items: `layer=layer2`, `sourceDomain=mp.weixin.qq.com`,
  `curationStatus=passed`
- Sources: PaperWeekly / 老刘说NLP / 程序员鱼皮 (×2) / 叶小钗
- All items carry tags + summaryZh + originalUrl + ISO timestamps

## Hard constraints honored

- No SSH / cookie / token / password literals in any file
- No `kol_config.py` commit
- No `git add -A` / `git add .` — explicit file add only
- No amend / reset / force-push
- LightRAG untouched; STATE.md / ROADMAP.md / REQUIREMENTS.md untouched
- Hermes untouched (this quick is Aliyun-only)

## Evidence

`.scratch/260525-vnj-p7-evidence.json` — full JSON output of the
post-swap daily-digest run, validated against contract v1.

## Follow-up

- Cache-bust + browser/curl smoke verifying vitaclaw homepage consumes
  the new `agent-news.json` (immediately after P8 commit).
- Tomorrow's natural cron firings (06:00 / 12:00 / 14:00 UTC) are the
  first unattended end-to-end validation.

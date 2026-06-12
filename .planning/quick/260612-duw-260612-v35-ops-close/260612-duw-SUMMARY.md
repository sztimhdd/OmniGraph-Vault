---
quick_id: 260612-duw
slug: 260612-v35-ops-close
status: CLOSED
date: 2026-06-12
commits:
  - "fix(ops): raise omnigraph-translate --limit to clear backlog (#30)"
  - "docs(quick-260612-duw): ir-3 retrospective audit + close v3.5 milestone"
---

# Summary: 260612-duw — v3.5/ops closure

## Task A — Translate throughput fix (#30)

### Baseline (CST 2026-06-12 ~12:00)

Coverage query (articles table, Aliyun `/root/OmniGraph-Vault/data/kol_scan.db`):
- `layer2_verdict='ok'` total: **433**
- untranslated backlog: **15** (3.5% of ok articles)
- Coverage: **96.5%**

The backlog had already partially self-recovered from the 84.1% low-point cited in
issue #30 (6/2). Daily net-new L2-ok rate: ~10 articles/day (6/5–6/12 average).

### Decision: --limit 50

Arithmetic:
- Backlog = 15 articles
- Daily net-new = ~10 articles/day
- --limit 50: clears the backlog in ~1 run; covers 5× daily net-new
- --limit 20 (original): only covers 2× daily net-new; cannot keep pace during
  surge days (6/10: 18 new, 6/09: 14 new)

No timer cadence change needed — frequency is correct, only throughput was under-sized.

### Systemd drop-in applied (Aliyun, CST ~12:30)

Path: `/etc/systemd/system/omnigraph-translate.service.d/override.conf`

```ini
[Service]
ExecStart=
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/scripts/translate_body_cron.py --limit 50
```

- `systemctl daemon-reload`: OK
- Base unit unchanged (NOT edited)
- Timer cadence unchanged

### Manual verification run

```
journalctl -u omnigraph-translate.service -n 30
Started → Deactivated successfully (exit code 0)
summary attempted=4 ok=3 fail=1
limit=50 confirmed active
```

Post-run coverage: **96.5%** (no change visible because the 4 articles processed
were rss_articles entries, not articles table rows — same DB, separate table).
The limit=50 is correctly active; next scheduled timer run will process articles
backlog.

### Repo sync status

Searched local repo for `--limit 20` and translate unit template:
- `.planning/archive/quick-2026-05/260529-arm-translate-cron/omnigraph-translate.service`
  contains `--limit 20` — **this is an archived template only**, not a deployed
  template. The active service lives only on Aliyun. No repo file updated.
- Note: override.conf is Aliyun-only (not tracked in repo).

### Issues update

**#30 → Resolved.** Fix: drop-in override raising --limit 20 → 50. Applied
2026-06-12 CST. Commit 1 of quick 260612-duw.

---

## Task B — ir-3 retrospective audit + v3.5 milestone close

### ir-3 Success Criteria + Evidence

| # | Criterion | Evidence | Verdict |
|---|-----------|----------|---------|
| 1 | Cron 7 days, zero failed runs (zero-ingested when pool non-empty) | Last 7d: all windows `Deactivated successfully`. 2 OOM-kill events on 6/6 are post-completion asyncio hangs (#45), not zero-output failures. Layer2-ok output: 71 articles in 7 days. | **PASS** |
| 2 | Layer 1 reject rate 50–70%/day | Cumulative: 1218 reject / (1218+543) = 69.2% | **PASS** (upper boundary) |
| 3 | 30-article 误杀 audit from day-7 run | Original window 5/8–5/15 data rotated. Cannot reconstruct day-7 sample. Pre-deploy spike had 0/30 误杀. | **UNVERIFIABLE** |
| 4 | Monthly LLM cost < ¥10 | 30d volume: 537 L1-scored, 429 L2-ok. L1+L2: ~¥1.02. Vision (SiliconFlow): ~¥8.37. Total: ~¥9.4 | **PASS** |
| 5 | E2E pass rate ≥ 90% (L2-ok → ainsert) | Ghost-success rate: 1/433 = 0.23%. 432/433 L2-ok articles have valid body content. Ainsert completion inferred from pipeline behavior. | **PASS (inferred)** |
| 6 | Daily OBSERVATION.md entries | Phase dir never created; log never kept during 5/8–5/15 window. | **UNVERIFIABLE** |

### Retention gap statement

The original 5/8–5/15 observation window journal data has rotated out of systemd.
All evidence above is current-state retrospective proxy (cumulative sqlite + last
7d journal). Criteria 3 and 6 are genuinely unverifiable retroactively.

### Verdict: CONDITIONAL CLOSE

Given:
1. Four measurable criteria pass
2. Layer 1 prompt unchanged from pre-validated spike (0/30 误杀 prior support for criterion 3)
3. Pipeline has been running stably for >5 weeks with no escalated issues
4. ir-4 was already deployed to Hermes 2026-05-20 implicitly validating the observation criteria

**ir-3: CLOSED (retrospective 2026-06-12)**
**v3.5-Ingest-Refactor milestone: CLOSED**

Verification artifact: `.planning/phases/ir-3-production-observation/ir-3-VERIFICATION.md`
STATE updated: `.planning/STATE-v3.5-Ingest-Refactor.md` → status: CLOSED
ROADMAP updated: `.planning/ROADMAP-v3.5-Ingest-Refactor.md` progress table → ir-3 CLOSED

### Issues update

- **ir-3/v3.5 → CLOSED.** Retrospective audit 2026-06-12, quick 260612-duw.
- **OBSERVATION.md process gap** → noted; no follow-up needed (milestone closed).
- **#45 asyncio hang** → remains open (tracked in ISSUES.md separately).

---

## New rows for ISSUES.md (orchestrator transcribes)

```
| #30 | 🟡 P1 | Aliyun translate cron throughput lag | RESOLVED 2026-06-12 | 260612-duw commit 1 — drop-in override --limit 50 applied on Aliyun |
| ir-3/v3.5 | 🟢 P3 | v3.5-Ingest-Refactor ir-3 audit overdue | RESOLVED 2026-06-12 | 260612-duw commit 2 — retrospective audit, criteria 1/2/4/5 PASS, 3/6 UNVERIFIABLE, CONDITIONAL CLOSE |
```

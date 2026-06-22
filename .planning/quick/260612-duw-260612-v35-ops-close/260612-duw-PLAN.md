---
quick_id: 260612-duw
slug: 260612-v35-ops-close
description: "260612-v35-ops-close — (A) fix #30 translate throughput drift via systemd drop-in; (B) ir-3 retrospective audit + close v3.5 milestone"
date: 2026-06-12
status: planned
must_haves:
  truths:
    - "Task A: override.conf written to /etc/systemd/system/omnigraph-translate.service.d/override.conf with --limit 100 (or data-justified value)"
    - "Task A: daemon-reload successful, one manual start confirms climb in coverage"
    - "Task B: ir-3-VERIFICATION.md written at .planning/phases/ir-3-production-observation/ir-3-VERIFICATION.md"
    - "Task B: ir-3 + v3.5 milestone closed in STATE-v3.5-Ingest-Refactor.md + ROADMAP-v3.5-Ingest-Refactor.md (only if B3 verdict = PASS)"
    - "Two separate commits: commit 1 = Task A (SUMMARY note + any repo template sync); commit 2 = Task B (VERIFICATION + STATE/ROADMAP)"
  artifacts:
    - ".planning/quick/260612-duw-260612-v35-ops-close/260612-duw-SUMMARY.md"
  key_links:
    - ".planning/STATE-v3.5-Ingest-Refactor.md"
    - ".planning/ROADMAP-v3.5-Ingest-Refactor.md"
---

# Plan: 260612-duw — v3.5/ops closure

## Task 1: Task A — Translate throughput fix (Aliyun systemd write-op)

**Goal:** Fix #30 translate throughput drift by raising --limit in omnigraph-translate.service via systemd drop-in.

**Commit:** `fix(ops): raise omnigraph-translate --limit to clear backlog (#30)`

### Steps

**A1 — Diagnose (read-only SSH)**

```bash
# 1. Capture service definition
ssh aliyun-vitaclaw "systemctl cat omnigraph-translate.service"

# 2. Check for existing drop-in override
ssh aliyun-vitaclaw "ls /etc/systemd/system/omnigraph-translate.service.d/ 2>/dev/null && cat /etc/systemd/system/omnigraph-translate.service.d/override.conf 2>/dev/null || echo 'no override.conf'"

# 3. Timer cadence
ssh aliyun-vitaclaw "systemctl list-timers omnigraph-translate.timer --all"

# 4. Inspect schema first (column names may vary)
ssh aliyun-vitaclaw "sqlite3 /root/OmniGraph-Vault/data/kol_scan.db '.schema articles' | grep -iE 'body_translated|layer2'"

# 5. Measure backlog
ssh aliyun-vitaclaw "set -a; source /root/.hermes/.env; set +a; /root/OmniGraph-Vault/venv-aim1/bin/python -c \"import sqlite3; c=sqlite3.connect('file:/root/OmniGraph-Vault/data/kol_scan.db?mode=ro',uri=True); cur=c.cursor(); cur.execute(\\\"SELECT COUNT(*) FROM articles WHERE layer2_verdict='ok'\\\"); ok=cur.fetchone()[0]; cur.execute(\\\"SELECT COUNT(*) FROM articles WHERE layer2_verdict='ok' AND (body_translated IS NULL OR body_translated='')\\\"); untr=cur.fetchone()[0]; print(f'untranslated backlog={untr} of ok={ok} = {100*(ok-untr)/ok:.1f}% covered')\""

# 6. Daily net-new rate (last 7 days of new layer2='ok' rows, using created_at or published_at)
# Inspect available date column first, then query
```

**A2 — Decide --limit value**

- If backlog ≤ 100: --limit 50 (clears in 2 days at current throughput)
- If backlog 100-500: --limit 100 (clears in 1-5 days)
- If backlog > 500: --limit 150 (clears in ≤5 days)
- The chosen limit must EXCEED daily net-new rate with margin (≥2× net-new)
- State arithmetic in SUMMARY

**A3 — Apply via systemd drop-in (NEVER edit base unit)**

```bash
# First capture exact ExecStart from base unit
ssh aliyun-vitaclaw "systemctl cat omnigraph-translate.service | grep ExecStart"

# Write drop-in (substitute <NEW_LIMIT> and <EXACT_EXECSTART_WITHOUT_LIMIT_20>)
ssh aliyun-vitaclaw "mkdir -p /etc/systemd/system/omnigraph-translate.service.d && cat > /etc/systemd/system/omnigraph-translate.service.d/override.conf << 'EOF'
[Service]
ExecStart=
ExecStart=<EXACT_BASE_EXECSTART_WITH_LIMIT_REPLACED>
EOF"

# Reload (NO --now, NO start yet)
ssh aliyun-vitaclaw "systemctl daemon-reload && echo 'daemon-reload OK'"

# Verify the override is active
ssh aliyun-vitaclaw "systemctl show omnigraph-translate.service | grep ExecStart"
```

**A4 — Verify (one controlled manual run)**

```bash
# Start once (EnvironmentFile auto-loads; NO --now flag needed here since this IS the explicit start)
ssh aliyun-vitaclaw "systemctl start omnigraph-translate.service"

# Wait for completion (poll until inactive or failed, max 10min for --limit 100)
# Check logs
ssh aliyun-vitaclaw "journalctl -u omnigraph-translate.service -n 50 --no-pager | grep -E 'Started|Deactivated|translated|limit|exit code|error|Error'"

# Re-measure coverage (compare to A1 baseline)
ssh aliyun-vitaclaw "set -a; source /root/.hermes/.env; set +a; /root/OmniGraph-Vault/venv-aim1/bin/python -c \"import sqlite3; c=sqlite3.connect('file:/root/OmniGraph-Vault/data/kol_scan.db?mode=ro',uri=True); cur=c.cursor(); cur.execute(\\\"SELECT COUNT(*) FROM articles WHERE layer2_verdict='ok'\\\"); ok=cur.fetchone()[0]; cur.execute(\\\"SELECT COUNT(*) FROM articles WHERE layer2_verdict='ok' AND (body_translated IS NULL OR body_translated='')\\\"); untr=cur.fetchone()[0]; print(f'untranslated backlog={untr} of ok={ok} = {100*(ok-untr)/ok:.1f}% covered')\""
```

**A5 — Repo sync check**

Search local repo for translate unit template or `--limit 20`:
- `kb/deploy/`, `scripts/`, `databricks-deploy/`
- If found: update to match new limit
- If not tracked: note in SUMMARY (config lives only on Aliyun)

**Commit 1** (Task A artifacts):
- Files: `260612-duw-SUMMARY.md` (partial, Task A section), any repo template files updated in A5
- Message: `fix(ops): raise omnigraph-translate --limit to clear backlog (#30)`
- Note: override.conf lives on Aliyun only (not repo); document in SUMMARY

---

## Task 2: Task B — ir-3 retrospective + v3.5 close (read-only SSH + local doc writes)

**Goal:** Retroactively audit ir-3 criteria against current evidence, close ir-3 and v3.5 milestone if criteria pass.

**Commit:** `docs(quick-260612-duw): ir-3 retrospective audit + close v3.5 milestone`

### ir-3 Acceptance Criteria (from ROADMAP-v3.5-Ingest-Refactor.md)

Quoted verbatim:
1. Hermes cron runs 7 consecutive days with zero failed runs (failure = zero ingested when pool non-empty)
2. Observed Layer 1 reject rate per day in 50–70% band
3. Operator draws 30-article sample from day-7 run; zero 误杀 (false positives)
4. Measured monthly LLM cost < ¥10/month
5. End-to-end ingest pass rate ≥ 90% (Layer1+Layer2 passing → LightRAG ainsert)
6. Daily observation entries in `.planning/phases/ir-3-*/OBSERVATION.md`

### Steps

**B1 — Read local planning files (already done above)**

Extract exact criteria from ROADMAP — done.

**B2 — Gather retrospective evidence via SSH (read-only)**

```bash
# Layer 1 reject rate (current cumulative)
ssh aliyun-vitaclaw "set -a; source /root/.hermes/.env; set +a; sqlite3 /root/OmniGraph-Vault/data/kol_scan.db \"SELECT layer1_verdict, COUNT(*) as n FROM articles GROUP BY layer1_verdict ORDER BY n DESC\""

# Also check rss_articles if table exists
ssh aliyun-vitaclaw "sqlite3 /root/OmniGraph-Vault/data/kol_scan.db \"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%rss%'\""

# Ghost-success estimate: processed rows with empty body
ssh aliyun-vitaclaw "sqlite3 /root/OmniGraph-Vault/data/kol_scan.db \"SELECT COUNT(*) FROM ingestions WHERE status='ok' AND article_id IN (SELECT id FROM articles WHERE (body IS NULL OR body='') AND layer2_verdict='ok')\" 2>/dev/null || echo 'query failed'"

# Cron reliability: recent 7 days
ssh aliyun-vitaclaw "journalctl -u 'omnigraph-*-ingest.service' --since '7 days ago' --no-pager 2>/dev/null | grep -cE 'Failed|exit-code|failed'"

# E2E pass rate: batch_timeout_metrics recent files
ssh aliyun-vitaclaw "ls -t /root/OmniGraph-Vault/data/batch_timeout_metrics_*.json 2>/dev/null | head -5 | xargs -I{} sh -c 'echo \"=== {} ===\"; python3 -c \"import json,sys; d=json.load(open(sys.argv[1])); print(f\\\"completed={d.get(\\\\\"completed_articles\\\\\",d.get(\\\\\"ok\\\\\",\\\\\"?\\\\\"))}/{d.get(\\\\\"total_articles\\\\\",d.get(\\\\\"total\\\\\",\\\\\"?\\\\\"))}\\\")\" {}'"

# Cost estimate: volume × per-article cost
# From knowledge: ingest ~5-10 articles/day, Layer 1 = Gemini Flash Lite, Layer 2 = DeepSeek
# Estimate from ingest volume
ssh aliyun-vitaclaw "sqlite3 /root/OmniGraph-Vault/data/kol_scan.db \"SELECT COUNT(*) FROM ingestions WHERE status='ok' AND created_at >= date('now', '-30 days')\" 2>/dev/null || sqlite3 /root/OmniGraph-Vault/data/kol_scan.db \"SELECT COUNT(*) FROM ingestions WHERE status='ok'\""
```

**B3 — Verdict**

Criteria mapping to retrospective evidence:
1. **7-day cron reliability** → recent 7-day journal failure count (proxy: if 0 failures in recent 7d → pass)
2. **Layer 1 reject rate 50-70%** → current cumulative reject rate from sqlite
3. **30-article 误杀 audit** → CANNOT verify retroactively (no original sample). Mark UNVERIFIABLE with note.
4. **Monthly cost < ¥10** → volume × known costs
5. **E2E pass rate ≥ 90%** → batch_timeout_metrics completed/total
6. **OBSERVATION.md daily log** → NOTE: ir-3 phase dir was never created; daily log was never kept

**Verdict rule:**
- If criteria 1, 2, 4, 5 pass AND criteria 3/6 are flagged UNVERIFIABLE (not FAIL), close CONDITIONALLY with retention-gap caveat
- If any of criteria 1, 2, 4, 5 FAIL → do NOT close; file what failed + next step

**B4 — Write local docs**

Create `.planning/phases/ir-3-production-observation/` directory if absent.
Write `ir-3-VERIFICATION.md` with evidence + verdict.

Update STATE-v3.5-Ingest-Refactor.md + ROADMAP-v3.5-Ingest-Refactor.md:
- ir-3 row: `in progress (calendar wait)` → `CLOSED (retrospective 2026-06-12)` if B3=pass
- Milestone status: `deployed-in-observation` → `CLOSED` if B3=pass
- ir-4 was already deployed to Hermes 2026-05-20 so effectively the whole milestone is done

**Commit 2** (Task B artifacts):
- Files: `.planning/phases/ir-3-production-observation/ir-3-VERIFICATION.md`, `.planning/STATE-v3.5-Ingest-Refactor.md`, `.planning/ROADMAP-v3.5-Ingest-Refactor.md`
- Message: `docs(quick-260612-duw): ir-3 retrospective audit + close v3.5 milestone`

---

## SUMMARY.md structure

Write `.planning/quick/260612-duw-260612-v35-ops-close/260612-duw-SUMMARY.md` after both tasks complete.

Required sections:
- Task A: baseline coverage % → post-fix coverage %, --limit arithmetic, override.conf content, manual-run exit code, repo-sync status
- Task B: 5 ir-3 criteria + retrospective evidence per criterion + CLOSE/STILL-OPEN verdict with retention-gap caveat
- New issues for ISSUES.md transcription: #30 → Resolved, ir-3/v3.5 → closed (or still-open reason)
- UNKNOWN for any probe that couldn't run

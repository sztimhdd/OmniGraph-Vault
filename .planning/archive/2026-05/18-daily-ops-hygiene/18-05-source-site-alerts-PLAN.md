---
phase: 18-daily-ops-hygiene
plan: 05
type: execute
wave: 2
depends_on: [05-06 Task 6.3 (Phase 5 Exit State written)]
blocked: true
files_modified:
  - enrichment/orchestrate_daily.py
  - scripts/pipeline_health.py
  - tests/unit/test_pipeline_health_alerts.py
autonomous: true
requirements: [HYG-06]
must_haves:
  truths:
    - "`orchestrate_daily.py` emits Telegram alerts on three threshold breaches: WeChat daily scan count < 50% of trailing 7-day median; RSS feeds_fail/total > 20%; classifier error rate > 10%"
    - "Alert emoji: 🟡 for warning thresholds; 🔴 for critical (WeChat drop > 75% or total classify failure)"
    - "`scripts/pipeline_health.py` prints a 7-day rolling stats report (for manual operator use; same data source as the thresholds)"
    - "No new DB tables; thresholds computed from existing `articles.scraped_at` / `rss_articles.fetched_at` / `rss_fetch_log.status` / `classifications.article_id` counts"
  artifacts:
    - path: "enrichment/orchestrate_daily.py"
      provides: "3 Telegram threshold alerts appended to step-9 failure handler logic"
      min_lines_touched: 60
    - path: "scripts/pipeline_health.py"
      provides: "7-day rolling stats printer for operator triage"
      min_lines: 80
    - path: "tests/unit/test_pipeline_health_alerts.py"
      provides: "Unit tests for threshold evaluation logic + alert message shape"
      min_lines: 90
  key_links:
    - from: "enrichment/orchestrate_daily.py"
      to: "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars"
      via: "requests.post to api.telegram.org on threshold breach"
      pattern: "sendMessage"
---

<objective>
Detect source-site changes and pipeline-health anomalies BEFORE the operator hears about it from "daily digest is empty". Three threshold-driven Telegram alerts bolted onto the existing Phase 5 Wave 2 `orchestrate_daily.py` orchestrator:

1. **WeChat scan anomaly** — today's scan count < 50% of trailing 7-day median → 🟡 alert. < 25% → 🔴. Detects WeChat account bans, anti-abuse triggers, spider regressions.
2. **RSS feeds_fail ratio** — today's `feeds_fail / total_feeds` > 20% → 🟡. > 50% → 🔴. Detects mass-feed-dead (DNS issues, DDoS, subscription expiry).
3. **Classifier error rate** — today's `classified_failures / classified_attempts` > 10% → 🟡. > 50% → 🔴. Detects DeepSeek API brown-outs, prompt-drift, or classification-schema regressions.

Plus a standalone `scripts/pipeline_health.py` that prints the 7-day rolling stats for manual triage — no alerting, just numbers.

**This plan is BLOCKED** on Phase 5 Task 6.3 for the same reason as 18-04: the observation window may reveal which anomaly classes are most common (and thus which thresholds are most load-bearing), and adding them after absorbing that evidence produces better thresholds than guessing now.
</objective>

<execution_context>
When unblocked: `orchestrate_daily.py` has a step_9 Telegram-on-failure hook already (Phase 5 Wave 2). This plan extends that hook pattern into three additional pre-return checks. Windows unit tests mock `requests.post` — Hermes verification is a real daily run where no thresholds trip → no alerts.
</execution_context>

<context>
@.planning/phases/18-daily-ops-hygiene/18-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-04-SUMMARY.md
@enrichment/orchestrate_daily.py
@batch_scan_kol.py
@enrichment/rss_fetch.py

<precondition>
Phase 5 Wave 3 Exit State must be final. Reasons identical to 18-04. Additional reason for 18-05: Wave 3 observation may show a 4th anomaly class (e.g., Cognee entity-buffer backlog growth, image-server-down detection, LightRAG storage size anomaly). Better to absorb into HYG-06 than to amend post-land.
</precondition>

<threshold_math>
Compute from SQLite in-session:

```python
def wechat_scan_anomaly(conn):
    today = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE DATE(scraped_at) = DATE('now')"
    ).fetchone()[0]
    # Median of trailing 7 days excluding today
    trailing = conn.execute(
        """SELECT COUNT(*) FROM articles
           WHERE DATE(scraped_at) >= DATE('now', '-7 days')
             AND DATE(scraped_at) < DATE('now')
           GROUP BY DATE(scraped_at)
           ORDER BY 1"""
    ).fetchall()
    if not trailing:
        return None  # not enough history
    counts = sorted(c[0] for c in trailing)
    median = counts[len(counts)//2]
    if median == 0:
        return None
    ratio = today / median
    if ratio < 0.25: return ("critical", today, median, ratio)
    if ratio < 0.50: return ("warning",  today, median, ratio)
    return None
```

Similar shape for rss_fetch_log fail ratio and classifications failure rate.

Emit ONE Telegram message per anomaly — 🔴 for critical, 🟡 for warning, containing the today-count, median, and operator action ("verify WeChat cookies / check DeepSeek status page / ...").
</threshold_math>

<pipeline_health_script_shape>
```python
"""scripts/pipeline_health.py — 7-day rolling stats for operator triage.

Prints one section per pipeline stage: scan, classify, ingest, enrich, digest.
No alerting; side-effect-free read-only.
"""
# Format:
#  Stage       Today   7-day median   Ratio
#  scan-kol    47      52             0.90  OK
#  rss-fetch   8/92    8/92 total     fail=0.04  OK
#  classify    303     310            0.98  OK
#  ingest      3       3              1.00  OK
#  digest      1       1              1.00  OK
```
</pipeline_health_script_shape>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 18-05.1: Threshold-evaluator + Telegram alerts in orchestrate_daily.py</name>
  <files>enrichment/orchestrate_daily.py, tests/unit/test_pipeline_health_alerts.py</files>
  <behavior>
    - 3 anomaly-evaluation functions return tuples or None.
    - Orchestrator calls each after step_8 (digest) and before step_9 (Telegram failure) terminators.
    - Alert messages carry 🟡/🔴 emoji prefix + today/median + operator action.
    - Unit tests cover: ratio edge cases (exact threshold, zero-history, today-above-median), Telegram message shape.
  </behavior>
  <!-- Deferred until unblock. Task body filled at execution time with Phase 5 Exit State findings. -->
</task>

<task type="auto" tdd="true">
  <name>Task 18-05.2: scripts/pipeline_health.py read-only stats printer</name>
  <files>scripts/pipeline_health.py, tests/unit/test_pipeline_health_print.py</files>
  <behavior>
    - Prints stage-by-stage today vs 7-day median.
    - No Telegram, no side effects, no database writes.
    - Exit 0 always; operator reads the output.
  </behavior>
  <!-- Deferred until unblock. -->
</task>

</tasks>

<verification>
Filled at execution time.
</verification>

<success_criteria>
- HYG-06 satisfied: when a source site changes behavior, the operator gets a Telegram ping inside 24h of the first affected daily run.
- `pipeline_health.py` gives the operator a single-command triage view without DB spelunking.
- No database schema changes (thresholds computed on existing tables).
</success_criteria>

<output>
After execution, create `.planning/phases/18-daily-ops-hygiene/18-05-SUMMARY.md` documenting: threshold values adopted, any Phase 5 observation-window anomalies absorbed, operator runbook update.
</output>

<blocked_note>
THIS PLAN IS BLOCKED on Phase 5 Task 6.3 (Phase 5 Exit State finalization). Do NOT execute until unblocked — the observation window may identify additional anomaly classes worth including.
</blocked_note>

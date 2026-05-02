---
phase: 05-pipeline-automation
plan: 04
type: execute
wave: 2
depends_on: [05-02, 05-03, 05-03b]
files_modified:
  - enrichment/orchestrate_daily.py
  - tests/unit/test_orchestrate.py
autonomous: true
requirements: [D-07, D-15, D-16, D-18]
must_haves:
  truths:
    - "`enrichment/orchestrate_daily.py` implements the 9-step state machine from PRD §3.2"
    - "Each step is a function returning (success: bool, summary: str, next_step: str|None)"
    - "Non-critical failures (one feed 404, one article scrape fail) log + continue"
    - "Critical failures (CDP dead, DB locked, LightRAG 500) trigger Telegram alert + stop"
    - "`--dry-run` flag skips scrape + batch submit + LightRAG ainsert; prints planned actions"
    - "`--skip-scan` flag skips Steps 3-5 (for re-running classify/enrich without re-scraping)"
    - "Invokes existing Hermes-drive pattern for enrichment step — shells out to `enrich_article` skill per article per D-07"
  artifacts:
    - path: "enrichment/orchestrate_daily.py"
      provides: "9-step daily pipeline state machine"
      min_lines: 200
    - path: "tests/unit/test_orchestrate.py"
      provides: "Step-wise unit tests for success/failure/next_step transitions"
      min_lines: 60
  key_links:
    - from: "enrichment/orchestrate_daily.py Step 6 enrich_deep"
      to: "enrich_article Hermes skill"
      via: "subprocess invoking `enrichment/run_enrich_for_id.py --source {kol|rss} --article-id <id>` (bridge translates DB row → env vars ARTICLE_PATH/URL/HASH and calls `hermes skill run enrich_article`) per D-07"
      pattern: "enrich_article"
    - from: "enrichment/orchestrate_daily.py Step 7 ingest_all"
      to: "batch_ingest_from_spider.py"
      via: "subprocess `python batch_ingest_from_spider.py --from-db --topic-filter <scope>`"
      pattern: "batch_ingest_from_spider"
    - from: "enrichment/orchestrate_daily.py critical error"
      to: "Phase 4 Telegram delivery path"
      via: "Telegram send_message (D-18 carried forward)"
      pattern: "telegram\\|send_message"
---

<objective>
Build `enrichment/orchestrate_daily.py`: the 9-step state-machine cron body that runs the full daily pipeline. Reuses `rss_fetch`, `rss_classify`, existing KOL scripts, `enrich_article` Hermes skill, and `batch_ingest_from_spider.py`. Terminates on critical failures with a Telegram alert; non-blocking on recoverable ones.

Purpose: This is the Wave 2 centerpiece — without a state machine, the cron either (a) fails silently on errors, or (b) calls all 9 steps independently without dependency awareness. PRD §3.2 defines the contract.

Output: state machine ready for Plan 05-06 cron registration.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-PRD.md
@.planning/phases/05-pipeline-automation/05-VALIDATION.md
@.planning/phases/05-pipeline-automation/05-02-rss-fetch-PLAN.md
@.planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md
@enrichment/rss_fetch.py
@enrichment/rss_classify.py
@batch_scan_kol.py
@batch_classify_kol.py
@batch_ingest_from_spider.py
@lib/batch_timeout.py
@lib/checkpoint.py
@docs/OPERATOR_RUNBOOK.md

<infra_composition>
**v3.1/v3.2 infrastructure composition (added 2026-05-01):**

Orchestrator is the COMPOSITION layer over already-instrumented helpers. **Do NOT reimplement checkpoint/timeout/cascade at this level** — they live one layer below.

- **Step 7 `ingest_all` batch budget**: The `batch_ingest_from_spider.py` invocation inherits `OMNIGRAPH_BATCH_TIMEOUT_SEC` (default 28800s, v3.2 Phase 17) automatically via `lib/batch_timeout.py` instrumentation wired by v3.2 commit `d5c1686`. Orchestrator does NOT pass its own timeout to this subprocess unless operator explicitly overrides via env. Keep the existing `subprocess.run(..., timeout=3600)` fallback in `_run()` as a defense-in-depth upper bound — but the substantive budget lives in `lib/batch_timeout.py`, not here. If operator needs a different total budget for the daily run, they set `OMNIGRAPH_BATCH_TIMEOUT_SEC` in `~/.hermes/.env` per `docs/OPERATOR_RUNBOOK.md` §batch-timeout.
- **Checkpoint automatic**: Both KOL (`batch_ingest_from_spider.py` → `ingest_wechat.py`) and RSS (`enrichment/rss_ingest.py` per 05-03b) per-article ingest are wrapped in `lib/checkpoint.py` guards already. Orchestrator does NOT need to set up checkpoints. On retry/resume, articles that finished stage 6 (`sub_doc_ingest`) are skipped automatically — no orchestrator-level logic required.
- **Vision cascade automatic**: Images in either source flow through `image_pipeline.describe_images()` → `lib/vision_cascade.py` cascade + circuit breaker. No orchestrator involvement. Circuit breaker state persists via module-level `_CIRCUIT_STATE` (in-memory per process) — a single orchestrator run sees consistent breaker state; next day's run starts fresh (acceptable).
- **Telegram critical-failure alert (D-18)**: Follow `_telegram_alert()` pattern as planned. Add one operational detail per `docs/OPERATOR_RUNBOOK.md`: if Step 7 exits due to `OMNIGRAPH_BATCH_TIMEOUT_SEC` exhaustion (timeout before processing all queued articles), the alert message MUST include "batch_timeout_exceeded — see OPERATOR_RUNBOOK §recovery-from-batch-timeout". Recovery is "re-run orchestrator tomorrow; checkpoint/resume will pick up where it left off".
- **Scope guardrail**: Do NOT import `lib.checkpoint`, `lib.vision_cascade`, `lib.batch_timeout` directly in `orchestrate_daily.py`. Orchestrator is pure subprocess glue. Direct imports would violate the layering and the D-16 "Hermes drives" pattern (orchestrator should be thin + subprocess-based so cron prompts can substitute for it).
</infra_composition>

<interfaces>
PRD §3.2 step list:
```
Step 1: fetch_rss()          → enrichment/rss_fetch.py
Step 2: classify_rss()       → enrichment/rss_classify.py
Step 3: health_check()       → existing 07:55 cron logic (CDP + credential refresh)
Step 4: scan_kol()           → batch_scan_kol.py --daily
Step 5: classify_kol()       → batch_classify_kol.py --topic <all>
Step 6: enrich_deep()        → for each depth>=2 article (KOL + RSS), invoke enrich_article skill per D-07
Step 7: ingest_all()         → batch_ingest_from_spider.py --from-db
Step 8: generate_digest()    → enrichment/daily_digest.py (Plan 05-05)
Step 9: deliver()            → Telegram delivery (D-18)
```

Phase 4 `enrich_article` skill invocation pattern (from `skills/enrich_article/SKILL.md`):
```
hermes skill run enrich_article --article-id <id>
# OR
hermes skill run enrich_article --url <wechat_or_rss_url>
```
Exact invocation shape: verify by reading skills/enrich_article/SKILL.md before writing the orchestrator.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 4.1: Build `enrichment/orchestrate_daily.py` with 9-step state machine</name>
  <files>enrichment/orchestrate_daily.py, tests/unit/test_orchestrate.py</files>
  <behavior>
    - Test 1: All 9 steps defined as functions returning `(bool, str, str|None)`.
    - Test 2: On a successful run (all steps return `success=True`), the machine traverses step_1 → step_9 in order and prints a summary.
    - Test 3: Non-critical failure (step returns `success=False` with `critical=False`) logs warning, increments failure counter, continues to next step.
    - Test 4: Critical failure (step returns `success=False` with `critical=True`) triggers Telegram alert and halts — subsequent steps NOT called.
    - Test 5: `--dry-run` does not invoke subprocesses; prints the planned command for each step.
    - Test 6: `--skip-scan` skips Steps 3, 4, 5 (health_check, scan_kol, classify_kol) and proceeds to Step 6.
    - Test 7 (BLOCKER 5): When step_8 returns `StepResult(success=False, summary="digest_error")`, step_9 calls `_telegram_alert` exactly once with a message containing "digest failed", and the orchestrator exit status reflects failure.
  </behavior>
  <read_first>
    - .planning/phases/05-pipeline-automation/05-PRD.md §3.2 (full step spec)
    - .planning/phases/05-pipeline-automation/05-CONTEXT.md (D-07 uniform enrichment, D-18 Telegram reuse)
    - skills/enrich_article/SKILL.md (invocation shape — confirm actual flag names before using)
    - skills/enrich_article/scripts/ (if any — reference for CLI)
    - batch_scan_kol.py (CLI flags — `--daily`? check)
    - batch_classify_kol.py (CLI flags — needed for Step 5)
    - batch_ingest_from_spider.py (CLI flags after Plan 05-00b Task 0b.2 update)
  </read_first>
  <action>
    Create `enrichment/orchestrate_daily.py`:

    ```python
    """Daily pipeline orchestrator — 9-step state machine per PRD §3.2.

    Non-critical failures: log + continue.
    Critical failures: Telegram alert + stop.

    Invoked by Hermes cron; follows "Hermes drives" D-16 (the cron prompt says
    "run enrichment/orchestrate_daily.py"; the orchestrator in turn invokes
    enrich_article skill via subprocess `hermes skill run`).

    Usage:
        venv/bin/python enrichment/orchestrate_daily.py
        venv/bin/python enrichment/orchestrate_daily.py --dry-run
        venv/bin/python enrichment/orchestrate_daily.py --skip-scan
    """
    from __future__ import annotations

    import argparse
    import logging
    import os
    import sqlite3
    import subprocess
    import sys
    from dataclasses import dataclass
    from pathlib import Path
    from typing import Callable

    import requests  # L-22 fix: module-level import (previously inside _telegram_alert)

    DB = Path("data/kol_scan.db")
    PYTHON = Path("venv/bin/python")
    KEYWORDS = "openclaw,hermes,agent,harness"  # D-10

    logger = logging.getLogger("orchestrate_daily")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    @dataclass
    class StepResult:
        success: bool
        summary: str
        critical: bool = False
        next_step: str | None = None

    def _run(cmd: list[str], dry_run: bool, critical: bool = False) -> StepResult:
        logger.info(f"{'DRY ' if dry_run else ''}RUN: {' '.join(cmd)}")
        if dry_run:
            return StepResult(True, f"dry: {' '.join(cmd)}")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if r.returncode != 0:
                return StepResult(False, f"exit={r.returncode} stderr={r.stderr[:500]}", critical=critical)
            return StepResult(True, r.stdout[:500])
        except subprocess.TimeoutExpired:
            return StepResult(False, "timeout", critical=critical)
        except Exception as ex:
            return StepResult(False, f"exception: {ex}", critical=critical)

    def step_1_fetch_rss(dry_run: bool) -> StepResult:
        return _run([str(PYTHON), "enrichment/rss_fetch.py"], dry_run, critical=False)

    def step_2_classify_rss(dry_run: bool) -> StepResult:
        return _run([str(PYTHON), "enrichment/rss_classify.py"], dry_run, critical=False)

    def step_3_health_check(dry_run: bool) -> StepResult:
        # H-13 fix: delegate to the existing 07:55 health-check cron (id e7afccd9931b).
        # Orchestrator never runs health-check itself. Unconditional pass-through.
        return StepResult(True, "health_check delegated to 07:55 cron (e7afccd9931b)", critical=False)

    def step_4_scan_kol(dry_run: bool) -> StepResult:
        return _run([str(PYTHON), "batch_scan_kol.py", "--days-back", "1"], dry_run, critical=True)

    def step_5_classify_kol(dry_run: bool) -> StepResult:
        cmd = [str(PYTHON), "batch_classify_kol.py",
               "--topic", "Agent", "--topic", "LLM", "--topic", "RAG",
               "--topic", "NLP", "--topic", "CV",
               "--min-depth", "2", "--days-back", "1"]
        return _run(cmd, dry_run, critical=False)

    def step_6_enrich_deep(dry_run: bool) -> StepResult:
        """Per D-07: all depth>=2 articles (KOL + RSS) go through enrich_article.

        Discovery: query DB for unenriched depth>=2 articles from today. For each,
        invoke `hermes skill run enrich_article --article-id <id>` via subprocess.
        """
        if dry_run:
            return StepResult(True, "dry: would enrich depth>=2 articles")
        conn = sqlite3.connect(DB)
        # KOL side
        kol_ids = [r[0] for r in conn.execute(
            """SELECT DISTINCT a.id FROM articles a
               JOIN classifications c ON c.article_id = a.id
               WHERE c.depth_score >= 2 AND COALESCE(a.enriched, 0) < 2
                 AND date(a.fetched_at) = date('now','localtime')"""
        ).fetchall()]
        # RSS side
        rss_ids = [r[0] for r in conn.execute(
            """SELECT DISTINCT a.id FROM rss_articles a
               JOIN rss_classifications c ON c.article_id = a.id
               WHERE c.depth_score >= 2 AND COALESCE(a.enriched, 0) < 2
                 AND date(a.fetched_at) = date('now','localtime')"""
        ).fetchall()]
        conn.close()
        enriched = 0
        failed = 0
        # BLOCKER 2 fix: enrich_article takes env vars (ARTICLE_PATH/URL/HASH),
        # NOT CLI flags. Delegate to run_enrich_for_id.py bridge which does the
        # env-var translation (see 05-03b Task 3b.1).
        for aid in kol_ids:
            r = _run([str(PYTHON), "enrichment/run_enrich_for_id.py",
                      "--source", "kol", "--article-id", str(aid)], False, critical=False)
            if r.success: enriched += 1
            else: failed += 1
        for aid in rss_ids:
            r = _run([str(PYTHON), "enrichment/run_enrich_for_id.py",
                      "--source", "rss", "--article-id", str(aid)], False, critical=False)
            if r.success: enriched += 1
            else: failed += 1
        return StepResult(True, f"enriched={enriched} failed={failed}")

    def step_7_ingest_all(dry_run: bool) -> StepResult:
        # BLOCKER 3 fix: ingest BOTH KOL (batch_ingest_from_spider.py) AND RSS
        # (enrichment/rss_ingest.py per 05-03b). Non-blocking; aggregate summary.
        kol_cmd = [str(PYTHON), "batch_ingest_from_spider.py",
                   "--from-db", "--topic-filter", KEYWORDS, "--min-depth", "2"]
        kol_r = _run(kol_cmd, dry_run, critical=False)
        rss_cmd = [str(PYTHON), "enrichment/rss_ingest.py"]
        rss_r = _run(rss_cmd, dry_run, critical=False)
        combined_success = kol_r.success and rss_r.success
        summary = f"KOL: {kol_r.summary[:200]} | RSS: {rss_r.summary[:200]}"
        return StepResult(combined_success, summary, critical=False)

    def step_8_generate_digest(dry_run: bool) -> StepResult:
        return _run([str(PYTHON), "enrichment/daily_digest.py"], dry_run, critical=False)

    def step_9_deliver(dry_run: bool, step_8_result: StepResult | None = None) -> StepResult:
        # BLOCKER 5 fix: if step_8 (digest generation) failed, fire Telegram alert.
        # Success path: daily_digest.py already handled delivery inside step_8.
        if step_8_result is None or step_8_result.success:
            return StepResult(True, "delivered by step_8 (daily_digest.py handles Telegram)", critical=False)
        _telegram_alert(f"Phase 5 digest failed: {step_8_result.summary[:300]}")
        return StepResult(False, f"digest failed; alert sent: {step_8_result.summary[:200]}", critical=False)

    def _telegram_alert(message: str) -> None:
        """Reuse Phase 4 D-13/D-18 Telegram delivery."""
        # The Phase 4 delivery path may be a helper in telegram_send.py or similar.
        # Confirm path before executing; fall back to logging a clear marker.
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not (bot_token and chat_id):
            logger.error(f"CRITICAL (no Telegram creds): {message}")
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": f"[OmniGraph orchestrate_daily] {message}"},
                timeout=10,
            )
        except Exception as ex:
            logger.error(f"Telegram send failed: {ex} (original msg: {message})")

    def run(dry_run: bool, skip_scan: bool) -> dict:
        steps: list[tuple[str, Callable[[bool], StepResult]]] = [
            ("1_fetch_rss", step_1_fetch_rss),
            ("2_classify_rss", step_2_classify_rss),
            ("3_health_check", step_3_health_check),
            ("4_scan_kol", step_4_scan_kol),
            ("5_classify_kol", step_5_classify_kol),
            ("6_enrich_deep", step_6_enrich_deep),
            ("7_ingest_all", step_7_ingest_all),
            ("8_generate_digest", step_8_generate_digest),
            ("9_deliver", step_9_deliver),
        ]
        skip_names = {"3_health_check", "4_scan_kol", "5_classify_kol"} if skip_scan else set()
        results: dict[str, StepResult] = {}
        failures = 0
        for name, fn in steps:
            if name in skip_names:
                logger.info(f"SKIP {name} (--skip-scan)")
                continue
            # step_9 needs step_8's result to decide whether to fire the Telegram alert
            if name == "9_deliver":
                r = fn(dry_run, results.get("8_generate_digest"))
            else:
                r = fn(dry_run)
            results[name] = r
            logger.info(f"{name}: success={r.success} critical={r.critical} summary={r.summary[:200]}")
            if not r.success:
                failures += 1
                if r.critical:
                    _telegram_alert(f"CRITICAL: step {name} failed: {r.summary}")
                    break
        return {"failures": failures, "results": {k: v.success for k, v in results.items()}}

    def main() -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--skip-scan", action="store_true")
        args = p.parse_args()
        out = run(args.dry_run, args.skip_scan)
        logger.info(f"done: {out}")
        sys.exit(0 if out["failures"] == 0 else 1)

    if __name__ == "__main__":
        main()
    ```

    Create `tests/unit/test_orchestrate.py` with the 7 behavioral tests (Test 7 covers BLOCKER 5 digest-failure Telegram alert) — use `unittest.mock.patch("enrichment.orchestrate_daily._run", ...)` to inject step results and verify transitions.
  </action>
  <verify>
    <automated>ssh remote "cd ~/OmniGraph-Vault &amp;&amp; venv/bin/python -m pytest tests/unit/test_orchestrate.py -v &amp;&amp; venv/bin/python enrichment/orchestrate_daily.py --dry-run --skip-scan"</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/orchestrate_daily.py` exists; ≥ 200 lines.
    - Defines exactly 9 `step_<n>_*` functions.
    - `grep -c "def step_" enrichment/orchestrate_daily.py` returns 9.
    - `grep -q "StepResult" enrichment/orchestrate_daily.py` returns 0.
    - `grep -q "critical=True" enrichment/orchestrate_daily.py` returns 0 (critical flag used).
    - `grep -q "_telegram_alert" enrichment/orchestrate_daily.py` returns 0.
    - `grep -q "hermes.*skill.*run.*enrich_article" enrichment/orchestrate_daily.py` returns 0 (D-07 enforcement).
    - All 7 pytest tests pass (Test 7 covers BLOCKER 5 digest-failure alert).
    - `--dry-run --skip-scan` on remote exits 0 and prints planned commands for all 6 non-skipped steps.
    - `grep -q "rss_ingest" enrichment/orchestrate_daily.py` returns 0 (BLOCKER 3: RSS path is wired into step_7).
    - `grep -q "batch_ingest_from_spider" enrichment/orchestrate_daily.py` returns 0 (KOL path preserved).
    - `grep -q "run_enrich_for_id" enrichment/orchestrate_daily.py` returns 0 (BLOCKER 2: uses the bridge, not hardcoded skill CLI flags).
    - `! grep -q "hermes.*skill.*run.*enrich_article.*--article-id" enrichment/orchestrate_daily.py` (BLOCKER 2: wrong CLI usage MUST be absent).
    - `grep -q "_telegram_alert" enrichment/orchestrate_daily.py` returns 0 (BLOCKER 5: alert path present for step_9 to call).
  </acceptance_criteria>
  <done>Orchestrator state machine complete; ready for Plan 05-05 digest integration + Plan 05-06 cron.</done>
</task>

</tasks>

<verification>
- `enrichment/orchestrate_daily.py --dry-run --skip-scan` exits 0 on remote.
- Unit tests pass (6 scenarios).
- Telegram alert fires on critical failure (mocked in test).
</verification>

<success_criteria>
- All 9 steps defined per PRD §3.2.
- Non-critical vs critical failure handling correct.
- D-07: enrichment invoked per depth≥2 article regardless of source.
- D-18: Telegram path wired for critical failures.
</success_criteria>

<output>
After completion, create `.planning/phases/05-pipeline-automation/05-04-SUMMARY.md` with: step list, critical-vs-non-critical classification per step, Telegram trigger condition, `--dry-run` sample output.
</output>

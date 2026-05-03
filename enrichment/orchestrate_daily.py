"""Daily pipeline orchestrator — 9-step state machine per PRD §3.2.

Non-critical failures: log + continue.
Critical failures: Telegram alert + stop.

Enrichment policy (D-07 REVISED 2026-05-02 + D-19):
  Step 6 enriches KOL (WeChat) articles only. RSS is excluded entirely.
  SQL is forward-only — only today's fresh scans are enriched.

Invoked manually for debugging; the production cron bodies live in
scripts/register_phase5_cron.sh per D-16 "Hermes drives".

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

import requests

DB = Path("data/kol_scan.db")
PYTHON = Path("venv/bin/python")
KEYWORDS = "openclaw,hermes,agent,harness"  # D-10
DEFAULT_TOPICS: tuple[str, ...] = ("Agent", "LLM", "RAG", "NLP", "CV")
SUBPROCESS_TIMEOUT_SECONDS = 3600  # defence-in-depth; real batch budget is
# OMNIGRAPH_BATCH_TIMEOUT_SEC (v3.2 Phase 17) inside batch_ingest_from_spider.

logger = logging.getLogger("orchestrate_daily")


@dataclass
class StepResult:
    success: bool
    summary: str
    critical: bool = False
    next_step: str | None = None


def _run(cmd: list[str], dry_run: bool, critical: bool = False) -> StepResult:
    logger.info("%sRUN: %s", "DRY " if dry_run else "", " ".join(cmd))
    if dry_run:
        return StepResult(True, f"dry: {' '.join(cmd)}")
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        if r.returncode != 0:
            return StepResult(
                False,
                f"exit={r.returncode} stderr={r.stderr[:500]}",
                critical=critical,
            )
        return StepResult(True, r.stdout[:500])
    except subprocess.TimeoutExpired:
        return StepResult(False, "timeout", critical=critical)
    except Exception as ex:
        return StepResult(False, f"exception: {ex}", critical=critical)


def step_1_fetch_rss(dry_run: bool) -> StepResult:
    return _run([str(PYTHON), "enrichment/rss_fetch.py"], dry_run, critical=False)


def step_2_classify_rss(dry_run: bool) -> StepResult:
    return _run(
        [str(PYTHON), "enrichment/rss_classify.py"], dry_run, critical=False
    )


def step_3_health_check(dry_run: bool) -> StepResult:
    # Delegated to the existing 07:55 health-check cron (id e7afccd9931b).
    # Orchestrator never runs health-check itself. Unconditional pass-through.
    return StepResult(
        True,
        "health_check delegated to 07:55 cron (e7afccd9931b)",
        critical=False,
    )


def step_4_scan_kol(dry_run: bool) -> StepResult:
    # Scanner is critical: without fresh scans, nothing downstream has input.
    return _run(
        [str(PYTHON), "batch_scan_kol.py", "--daily"],
        dry_run,
        critical=True,
    )


def step_5_classify_kol(dry_run: bool) -> StepResult:
    """Classify today's KOL rows across all 5 topics.

    batch_classify_kol.py accepts a single --topic per invocation. Looping
    is the contract (matches production pattern from Wave 0 catch-up).
    """
    summaries: list[str] = []
    any_failure = False
    for topic in DEFAULT_TOPICS:
        r = _run(
            [str(PYTHON), "batch_classify_kol.py", "--topic", topic, "--min-depth", "2"],
            dry_run,
            critical=False,
        )
        summaries.append(f"{topic}={'ok' if r.success else 'fail'}")
        if not r.success:
            any_failure = True
    return StepResult(not any_failure, "; ".join(summaries), critical=False)


def step_6_enrich_deep(dry_run: bool) -> StepResult:
    """Per D-07 REVISED 2026-05-02 + D-19: KOL only, forward-only.

    SQL scope:
      - `articles` + `classifications` tables (WeChat KOL source)
      - `depth_score >= 2` AND `enriched < 2`
      - `date(fetched_at) = today` — forward-only guard; historical
        shallow articles are NOT retroactively enriched
    RSS is excluded entirely. run_enrich_for_id.py's RSS branch is a
    guarded no-op by design; we never invoke it from here.
    """
    if dry_run:
        return StepResult(
            True,
            "dry: would enrich today's KOL depth>=2 articles (RSS excluded per D-07)",
        )
    conn = sqlite3.connect(DB)
    kol_ids = [
        r[0]
        for r in conn.execute(
            """SELECT DISTINCT a.id FROM articles a
               JOIN classifications c ON c.article_id = a.id
               WHERE c.depth_score >= 2 AND COALESCE(a.enriched, 0) < 2
                 AND date(a.fetched_at) = date('now','localtime')"""
        ).fetchall()
    ]
    conn.close()
    enriched = 0
    failed = 0
    # enrich_article takes env vars (ARTICLE_PATH/URL/HASH), NOT CLI flags.
    # Delegate to run_enrich_for_id.py bridge (see 05-03b Task 3b.1).
    for aid in kol_ids:
        r = _run(
            [
                str(PYTHON),
                "enrichment/run_enrich_for_id.py",
                "--source",
                "kol",
                "--article-id",
                str(aid),
            ],
            False,
            critical=False,
        )
        if r.success:
            enriched += 1
        else:
            failed += 1
    return StepResult(
        True,
        f"enriched={enriched} failed={failed} (KOL only; RSS excluded per D-07)",
        critical=False,
    )


def step_7_ingest_all(dry_run: bool) -> StepResult:
    """Ingest BOTH KOL (batch_ingest_from_spider) and RSS (rss_ingest).

    Non-blocking per-branch; aggregate summary so one branch's failure
    doesn't mask the other.
    """
    kol_cmd = [
        str(PYTHON),
        "batch_ingest_from_spider.py",
        "--from-db",
        "--topic-filter",
        KEYWORDS,
        "--min-depth",
        "2",
    ]
    kol_r = _run(kol_cmd, dry_run, critical=False)
    rss_cmd = [str(PYTHON), "enrichment/rss_ingest.py"]
    rss_r = _run(rss_cmd, dry_run, critical=False)
    combined_success = kol_r.success and rss_r.success
    summary = f"KOL: {kol_r.summary[:200]} | RSS: {rss_r.summary[:200]}"
    return StepResult(combined_success, summary, critical=False)


def step_8_generate_digest(dry_run: bool) -> StepResult:
    return _run(
        [str(PYTHON), "enrichment/daily_digest.py"], dry_run, critical=False
    )


def step_9_deliver(
    dry_run: bool, step_8_result: StepResult | None = None
) -> StepResult:
    """daily_digest.py handles its own Telegram send. This step is
    responsible for firing a Telegram alert if step_8 failed."""
    if step_8_result is None or step_8_result.success:
        return StepResult(
            True,
            "delivered by step_8 (daily_digest.py handles Telegram)",
            critical=False,
        )
    _telegram_alert(
        f"Phase 5 digest failed: {step_8_result.summary[:300]}"
    )
    return StepResult(
        False,
        f"digest failed; alert sent: {step_8_result.summary[:200]}",
        critical=False,
    )


def _telegram_alert(message: str) -> None:
    """Reuse Phase 4 D-13/D-18 Telegram delivery path."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (bot_token and chat_id):
        logger.error("CRITICAL (no Telegram creds): %s", message)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"[OmniGraph orchestrate_daily] {message}",
            },
            timeout=10,
        )
    except Exception as ex:
        logger.error(
            "Telegram send failed: %s (original msg: %s)", ex, message
        )


def run(dry_run: bool, skip_scan: bool) -> dict:
    steps: list[tuple[str, Callable]] = [
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
    skip_names: set[str] = (
        {"3_health_check", "4_scan_kol", "5_classify_kol"}
        if skip_scan
        else set()
    )
    results: dict[str, StepResult] = {}
    failures = 0
    for name, fn in steps:
        if name in skip_names:
            logger.info("SKIP %s (--skip-scan)", name)
            continue
        # step_9 needs step_8's result to decide whether to fire the alert.
        if name == "9_deliver":
            r = fn(dry_run, results.get("8_generate_digest"))
        else:
            r = fn(dry_run)
        results[name] = r
        logger.info(
            "%s: success=%s critical=%s summary=%s",
            name,
            r.success,
            r.critical,
            r.summary[:200],
        )
        if not r.success:
            failures += 1
            if r.critical:
                _telegram_alert(f"CRITICAL: step {name} failed: {r.summary}")
                break
    return {"failures": failures, "results": {k: v.success for k, v in results.items()}}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-scan", action="store_true")
    args = p.parse_args()
    out = run(args.dry_run, args.skip_scan)
    logger.info("done: %s", out)
    sys.exit(0 if out["failures"] == 0 else 1)


if __name__ == "__main__":
    main()

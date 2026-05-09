"""Unit tests for enrichment.orchestrate_daily — 9-step state machine.

Per plan 05-04, file name could be test_orchestrate.py; we use
test_orchestrate_daily.py to match the module name and avoid collision
with the Phase 4 orchestrate skill tests.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from enrichment import orchestrate_daily as od
from enrichment.orchestrate_daily import StepResult


# ---------------------------------------------------------------------
# Test 1 — all 8 active step functions exist with correct signature shape.
# v3.5 ir-4 (LF-5.2): step_2_classify_rss retired (rss_classify.py deleted;
# RSS now flows through Layer 1 inside batch_ingest_from_spider --from-db).
# Numeric IDs stay non-contiguous (1, 3, 4, ..., 9) so cron history that
# references "step 2" cannot accidentally re-route.
# ---------------------------------------------------------------------
def test_eight_active_step_functions_defined() -> None:
    names = [n for n in dir(od) if n.startswith("step_") and not n.startswith("step_result")]
    expected = {
        "step_1_fetch_rss",
        "step_3_health_check",
        "step_4_scan_kol",
        "step_5_classify_kol",
        "step_6_enrich_deep",
        "step_7_ingest_all",
        "step_8_generate_digest",
        "step_9_deliver",
    }
    assert expected.issubset(set(names))


def test_step_2_classify_rss_retired() -> None:
    """Regression guard: step_2_classify_rss must NOT be re-introduced
    (would re-link the deleted enrichment/rss_classify.py)."""
    assert not hasattr(od, "step_2_classify_rss"), (
        "ir-4 LF-5.2: step_2_classify_rss was retired with rss_classify.py. "
        "RSS classification now happens inside Layer 1 of "
        "batch_ingest_from_spider's --from-db candidate SQL."
    )


# ---------------------------------------------------------------------
# Test 2 — happy path traverses all 9 steps in order
# ---------------------------------------------------------------------
def test_success_path_traverses_all_9_steps() -> None:
    called: list[str] = []

    def fake_run(cmd, dry_run, critical=False):
        called.append(cmd[1] if len(cmd) > 1 else cmd[0])
        return StepResult(True, "ok")

    with patch.object(od, "_run", side_effect=fake_run), \
         patch("sqlite3.connect"):
        # Step 6 uses sqlite3 directly — patch to return empty result set
        with patch("enrichment.orchestrate_daily.sqlite3") as mock_sql:
            mock_conn = mock_sql.connect.return_value
            mock_conn.execute.return_value.fetchall.return_value = []
            out = od.run(dry_run=False, skip_scan=False)
    assert out["failures"] == 0
    # All 8 active step names present in results (step_2 retired in ir-4 LF-5.2)
    assert set(out["results"].keys()) == {
        "1_fetch_rss", "3_health_check", "4_scan_kol",
        "5_classify_kol", "6_enrich_deep", "7_ingest_all",
        "8_generate_digest", "9_deliver",
    }


# ---------------------------------------------------------------------
# Test 3 — non-critical failure logs + continues
# ---------------------------------------------------------------------
def test_non_critical_failure_continues() -> None:
    def fake_run(cmd, dry_run, critical=False):
        # Fail step_1 (rss_fetch) which is non-critical
        if "rss_fetch.py" in " ".join(cmd):
            return StepResult(False, "synthetic fail", critical=False)
        return StepResult(True, "ok")

    with patch.object(od, "_run", side_effect=fake_run), \
         patch("enrichment.orchestrate_daily.sqlite3") as mock_sql:
        mock_sql.connect.return_value.execute.return_value.fetchall.return_value = []
        out = od.run(dry_run=False, skip_scan=False)
    # Failure recorded but traversal continued
    assert out["failures"] >= 1
    assert "9_deliver" in out["results"], "non-critical failure must NOT halt"


# ---------------------------------------------------------------------
# Test 4 — critical failure triggers Telegram + halts
# ---------------------------------------------------------------------
def test_critical_failure_triggers_alert_and_halts() -> None:
    def fake_run(cmd, dry_run, critical=False):
        if "batch_scan_kol" in " ".join(cmd):
            return StepResult(False, "scanner dead", critical=True)
        return StepResult(True, "ok")

    with patch.object(od, "_run", side_effect=fake_run), \
         patch.object(od, "_telegram_alert") as mock_alert:
        out = od.run(dry_run=False, skip_scan=False)
    # step_4 failed critical => halt; steps 5..9 must NOT be in results
    assert "4_scan_kol" in out["results"]
    assert "5_classify_kol" not in out["results"]
    assert "9_deliver" not in out["results"]
    mock_alert.assert_called()
    called_msg = mock_alert.call_args[0][0]
    assert "CRITICAL" in called_msg and "4_scan_kol" in called_msg


# ---------------------------------------------------------------------
# Test 5 — --dry-run prints planned commands without invoking subprocess
# ---------------------------------------------------------------------
def test_dry_run_prints_without_subprocess() -> None:
    with patch("enrichment.orchestrate_daily.subprocess.run") as mock_subp:
        out = od.run(dry_run=True, skip_scan=False)
    assert mock_subp.call_count == 0
    # All 8 active steps completed successfully in dry-run (step_2 retired in ir-4 LF-5.2)
    assert out["failures"] == 0
    assert len(out["results"]) == 8


# ---------------------------------------------------------------------
# Test 6 — --skip-scan skips steps 3, 4, 5
# ---------------------------------------------------------------------
def test_skip_scan_skips_three_steps() -> None:
    with patch.object(od, "_run", return_value=StepResult(True, "ok")), \
         patch("enrichment.orchestrate_daily.sqlite3") as mock_sql:
        mock_sql.connect.return_value.execute.return_value.fetchall.return_value = []
        out = od.run(dry_run=False, skip_scan=True)
    assert "3_health_check" not in out["results"]
    assert "4_scan_kol" not in out["results"]
    assert "5_classify_kol" not in out["results"]
    # Remaining 5 active steps ran (1, 6, 7, 8, 9 — step_2 retired in ir-4 LF-5.2)
    for expected in ("1_fetch_rss", "6_enrich_deep",
                     "7_ingest_all", "8_generate_digest", "9_deliver"):
        assert expected in out["results"], f"{expected} should have run"
    # Regression guard: step_2 must NOT appear in results dict
    assert "2_classify_rss" not in out["results"], (
        "ir-4 LF-5.2: step_2 was retired with rss_classify.py"
    )


# ---------------------------------------------------------------------
# Test 7 — BLOCKER 5: step_8 failure triggers Telegram in step_9
# ---------------------------------------------------------------------
def test_step_8_failure_triggers_telegram_in_step_9() -> None:
    def fake_run(cmd, dry_run, critical=False):
        if "daily_digest.py" in " ".join(cmd):
            return StepResult(False, "digest_error", critical=False)
        return StepResult(True, "ok")

    with patch.object(od, "_run", side_effect=fake_run), \
         patch.object(od, "_telegram_alert") as mock_alert, \
         patch("enrichment.orchestrate_daily.sqlite3") as mock_sql:
        mock_sql.connect.return_value.execute.return_value.fetchall.return_value = []
        out = od.run(dry_run=False, skip_scan=False)
    # step_9 ran and recorded failure (because step_8 failed)
    assert "9_deliver" in out["results"]
    assert out["results"]["9_deliver"] is False
    # Telegram alert fired from step_9 path
    digest_alerts = [
        c for c in mock_alert.call_args_list
        if "digest failed" in c.args[0]
    ]
    assert len(digest_alerts) == 1
    assert "digest_error" in digest_alerts[0].args[0]


# ---------------------------------------------------------------------
# Test 8 — D-19 compliance: step_6 queries articles only, no RSS tables
# ---------------------------------------------------------------------
def test_step_6_sql_does_not_touch_rss_tables() -> None:
    captured_sql: list[str] = []

    class FakeConn:
        def execute(self, sql, *args):
            captured_sql.append(sql)
            class Res:
                def fetchall(self_inner):
                    return []
            return Res()

        def close(self):
            pass

    with patch("enrichment.orchestrate_daily.sqlite3.connect", return_value=FakeConn()):
        od.step_6_enrich_deep(dry_run=False)
    assert captured_sql, "step_6 must issue at least one SQL query"
    joined = " ".join(captured_sql).lower()
    assert "rss_articles" not in joined
    assert "rss_classifications" not in joined
    assert "articles" in joined  # KOL table must be referenced
    assert "date(a.scanned_at) = date('now','localtime')" in " ".join(captured_sql) \
        or "date('now','localtime')" in joined


# ---------------------------------------------------------------------
# Test 9 — step_6 calls run_enrich_for_id.py bridge, not hermes skill directly
# ---------------------------------------------------------------------
def test_step_6_uses_bridge_not_direct_skill() -> None:
    invocations: list[list[str]] = []

    def fake_run(cmd, dry_run, critical=False):
        invocations.append(cmd)
        return StepResult(True, "ok")

    class FakeConn:
        def execute(self, sql, *args):
            class Res:
                def fetchall(self_inner):
                    return [(42,), (43,)]
            return Res()

        def close(self):
            pass

    with patch.object(od, "_run", side_effect=fake_run), \
         patch("enrichment.orchestrate_daily.sqlite3.connect", return_value=FakeConn()):
        od.step_6_enrich_deep(dry_run=False)
    assert len(invocations) == 2, "one bridge call per KOL article"
    for cmd in invocations:
        joined = " ".join(cmd)
        assert "run_enrich_for_id.py" in joined
        assert "--source kol" in joined
        assert "--source rss" not in joined
        # Hermes skill CLI must NOT be invoked directly
        assert "hermes" not in joined


# ---------------------------------------------------------------------
# Test 10 — JN6-01: --step N runs only step N, others skipped
# ---------------------------------------------------------------------
def test_step_flag_runs_only_that_step() -> None:
    with patch.object(od, "_run", return_value=StepResult(True, "ok")), \
         patch("enrichment.orchestrate_daily.sqlite3") as mock_sql:
        mock_sql.connect.return_value.execute.return_value.fetchall.return_value = []
        out = od.run(dry_run=True, skip_scan=False, step=7)
    assert "7_ingest_all" in out["results"]
    # Other 7 active steps must be skipped (step_2 retired in ir-4 LF-5.2).
    for other in (
        "1_fetch_rss", "3_health_check", "4_scan_kol",
        "5_classify_kol", "6_enrich_deep", "8_generate_digest", "9_deliver",
    ):
        assert other not in out["results"], f"{other} must be skipped when --step 7"
    assert out["failures"] == 0


# ---------------------------------------------------------------------
# Test 11 — ir-4 LF-5.1: step_7 invokes ONLY batch_ingest_from_spider with
# --from-db; the legacy enrichment/rss_ingest.py was retired so the second
# sub-command is gone. --max-kol caps the unified dual-source pool.
# ---------------------------------------------------------------------
def test_max_kol_appended_to_unified_cmd() -> None:
    captured: list[list[str]] = []

    def fake_run(cmd, dry_run, critical=False):
        captured.append(list(cmd))
        return StepResult(True, "ok")

    with patch.object(od, "_run", side_effect=fake_run):
        od.run(dry_run=True, skip_scan=False, step=7, max_kol=20)

    kol_cmds = [c for c in captured if any("batch_ingest_from_spider.py" in x for x in c)]
    rss_cmds = [c for c in captured if any("rss_ingest.py" in x for x in c)]
    assert len(kol_cmds) == 1, f"expected 1 unified cmd, got {kol_cmds}"
    assert len(rss_cmds) == 0, (
        f"ir-4 LF-5.1: rss_ingest.py was retired; step_7 must NOT invoke "
        f"it. Got: {rss_cmds}"
    )
    assert kol_cmds[0][-2:] == ["--max-articles", "20"]


# ---------------------------------------------------------------------
# Test 12 — ir-4 LF-5.1: step_7 unified — no separate --max-rss path.
# ---------------------------------------------------------------------
def test_step_7_does_not_invoke_legacy_rss_ingest() -> None:
    """Regression guard: ensure no fallback path resurrects rss_ingest.py.
    Run step_7 with no caps and no max_rss kwarg (the kwarg is gone) — only
    the unified batch_ingest_from_spider command should be issued."""
    captured: list[list[str]] = []

    def fake_run(cmd, dry_run, critical=False):
        captured.append(list(cmd))
        return StepResult(True, "ok")

    with patch.object(od, "_run", side_effect=fake_run):
        od.run(dry_run=True, skip_scan=False, step=7)

    rss_cmds = [c for c in captured if any("rss_ingest.py" in x for x in c)]
    assert not rss_cmds, (
        f"ir-4 LF-5.1: enrichment/rss_ingest.py was retired and step_7 "
        f"must never spawn it. Got: {rss_cmds}"
    )
    # The dispatch should still produce exactly one ingest invocation.
    ingest_cmds = [c for c in captured if any("batch_ingest_from_spider.py" in x for x in c)]
    assert len(ingest_cmds) == 1


def test_run_signature_drops_max_rss() -> None:
    """ir-4 LF-5.1: the ``run()`` and ``step_7_ingest_all()`` signatures
    must NOT accept a ``max_rss`` keyword. Pre-ir-4 callers passing it
    should fail loudly so they stop being silently dropped."""
    import inspect

    run_params = list(inspect.signature(od.run).parameters)
    assert "max_rss" not in run_params, (
        f"ir-4 LF-5.1: run() must not accept max_rss; got {run_params}"
    )
    step7_params = list(inspect.signature(od.step_7_ingest_all).parameters)
    assert "max_rss" not in step7_params, (
        f"ir-4 LF-5.1: step_7_ingest_all() must not accept max_rss; "
        f"got {step7_params}"
    )

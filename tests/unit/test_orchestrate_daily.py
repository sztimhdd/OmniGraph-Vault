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
# Test 1 — all 9 step functions exist with correct signature shape
# ---------------------------------------------------------------------
def test_nine_step_functions_defined() -> None:
    names = [n for n in dir(od) if n.startswith("step_") and not n.startswith("step_result")]
    expected = {
        "step_1_fetch_rss",
        "step_2_classify_rss",
        "step_3_health_check",
        "step_4_scan_kol",
        "step_5_classify_kol",
        "step_6_enrich_deep",
        "step_7_ingest_all",
        "step_8_generate_digest",
        "step_9_deliver",
    }
    assert expected.issubset(set(names))


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
    # All 9 step names present in results
    assert set(out["results"].keys()) == {
        "1_fetch_rss", "2_classify_rss", "3_health_check", "4_scan_kol",
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
    # All 9 steps completed successfully in dry-run
    assert out["failures"] == 0
    assert len(out["results"]) == 9


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
    # Remaining 6 steps ran
    for expected in ("1_fetch_rss", "2_classify_rss", "6_enrich_deep",
                     "7_ingest_all", "8_generate_digest", "9_deliver"):
        assert expected in out["results"], f"{expected} should have run"


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
    assert "date(a.fetched_at) = date('now','localtime')" in " ".join(captured_sql) \
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
    for other in (
        "1_fetch_rss", "2_classify_rss", "3_health_check", "4_scan_kol",
        "5_classify_kol", "6_enrich_deep", "8_generate_digest", "9_deliver",
    ):
        assert other not in out["results"], f"{other} must be skipped when --step 7"
    assert out["failures"] == 0


# ---------------------------------------------------------------------
# Test 11 — JN6-01: --max-kol appended only to KOL branch cmd
# ---------------------------------------------------------------------
def test_max_kol_appended_to_kol_cmd() -> None:
    captured: list[list[str]] = []

    def fake_run(cmd, dry_run, critical=False):
        captured.append(list(cmd))
        return StepResult(True, "ok")

    with patch.object(od, "_run", side_effect=fake_run):
        od.run(dry_run=True, skip_scan=False, step=7, max_kol=20, max_rss=None)

    kol_cmds = [c for c in captured if any("batch_ingest_from_spider.py" in x for x in c)]
    rss_cmds = [c for c in captured if any("rss_ingest.py" in x for x in c)]
    assert len(kol_cmds) == 1, f"expected 1 KOL cmd, got {kol_cmds}"
    assert len(rss_cmds) == 1, f"expected 1 RSS cmd, got {rss_cmds}"
    assert kol_cmds[0][-2:] == ["--max-articles", "20"]
    assert "--max-articles" not in rss_cmds[0]


# ---------------------------------------------------------------------
# Test 12 — JN6-01: --max-rss appended only to RSS branch cmd
# ---------------------------------------------------------------------
def test_max_rss_appended_to_rss_cmd() -> None:
    captured: list[list[str]] = []

    def fake_run(cmd, dry_run, critical=False):
        captured.append(list(cmd))
        return StepResult(True, "ok")

    with patch.object(od, "_run", side_effect=fake_run):
        od.run(dry_run=True, skip_scan=False, step=7, max_kol=None, max_rss=5)

    kol_cmds = [c for c in captured if any("batch_ingest_from_spider.py" in x for x in c)]
    rss_cmds = [c for c in captured if any("rss_ingest.py" in x for x in c)]
    assert len(kol_cmds) == 1
    assert len(rss_cmds) == 1
    assert rss_cmds[0][-2:] == ["--max-articles", "5"]
    assert "--max-articles" not in kol_cmds[0]

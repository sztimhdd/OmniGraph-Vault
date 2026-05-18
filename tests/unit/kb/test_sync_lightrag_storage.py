"""Unit tests for kb/scripts/sync_lightrag_storage.py (kb-v2.2-1 F12).

All subprocess/ssh interactions mocked via monkeypatch — no real network in CI.
"""
from __future__ import annotations

import subprocess
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import kb.scripts.sync_lightrag_storage as m
from kb.scripts.sync_lightrag_storage import (
    MemoryProbeResult,
    MemoryReport,
    SyncState,
    atomic_swap,
    monitor_post_restart_memory,
    predict_ceiling_hit,
    rsync_to_staging,
)


# ---------------------------------------------------------------------------
# 1. atomic_swap happy path
# ---------------------------------------------------------------------------


def test_atomic_swap_happy_path(monkeypatch):
    """mv chain executed in correct order; backup path returned."""
    calls: list[str] = []

    def mock_ssh(host, cmd, *, check=True):
        calls.append(cmd)
        return MagicMock(stdout="", returncode=0)

    monkeypatch.setattr(m, "ssh_run", mock_ssh)
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)

    result = atomic_swap(
        "aliyun-vitaclaw",
        "/root/.hermes/lightrag_storage",
        "/root/.hermes/lightrag_storage_NEW",
        "20260518T120000Z",
    )

    assert result == "/root/.hermes/lightrag_storage.OLD-20260518T120000Z"
    assert len(calls) == 1
    cmd = calls[0]
    # Both mv operations present
    assert "/root/.hermes/lightrag_storage /root/.hermes/lightrag_storage.OLD-20260518T120000Z" in cmd
    assert "/root/.hermes/lightrag_storage_NEW /root/.hermes/lightrag_storage" in cmd
    # backup mv must precede staging mv
    assert cmd.index("lightrag_storage.OLD") < cmd.index("lightrag_storage_NEW")


# ---------------------------------------------------------------------------
# 2. rollback triggered on smoke fail (main() orchestration)
# ---------------------------------------------------------------------------


def test_atomic_swap_rollback_on_smoke_fail(monkeypatch):
    """smoke_test returns False -> rollback() called -> kb-api restarted."""
    rollback_calls: list[tuple] = []

    monkeypatch.setattr(m, "rsync_to_staging", lambda *a, **k: None)
    monkeypatch.setattr(m, "pause_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "start_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "atomic_swap", lambda *a, **k: "/root/ls.OLD-TS")
    monkeypatch.setattr(
        m, "monitor_post_restart_memory",
        lambda h, **k: MemoryProbeResult("ok", (), 0, 0.85),
    )
    monkeypatch.setattr(m, "check_memory_budget",
                        lambda h: MemoryReport(100, 2_000_000_000, 0.05))
    monkeypatch.setattr(m, "smoke_test", lambda h, u: False)
    monkeypatch.setattr(
        m, "rollback",
        lambda host, live, backup: rollback_calls.append((live, backup)),
    )
    monkeypatch.setattr(m, "update_state_file", lambda *a, **k: None)
    monkeypatch.setattr(m, "_read_state_file", lambda h, p: None)
    monkeypatch.setattr(m, "_read_state_history", lambda h, p: [])
    monkeypatch.setattr(m, "ssh_run",
                        lambda h, c, **k: MagicMock(stdout="0\n", returncode=0))
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)

    with pytest.raises(SystemExit) as exc:
        m.main(["--source-host", "hermes", "--force"])

    assert exc.value.code == 1
    assert len(rollback_calls) == 1
    live_path, backup_path = rollback_calls[0]
    assert "lightrag_storage" in live_path
    assert backup_path == "/root/ls.OLD-TS"


# ---------------------------------------------------------------------------
# 3. state file roundtrip
# ---------------------------------------------------------------------------


def test_state_file_roundtrip():
    """SyncState -> asdict -> reconstruct -> equal SyncState (frozen equality)."""
    original = SyncState(
        last_success_ts="2026-05-18T12:00:00+00:00",
        vdb_total_bytes=1_234_567_890,
        sync_wallclock_s=120.5,
        memory_pct_at_sync=0.57,
        backup_path_kept="/root/.hermes/lightrag_storage.OLD-20260518T120000Z",
    )
    d = asdict(original)
    reconstructed = SyncState(
        last_success_ts=d["last_success_ts"],
        vdb_total_bytes=d["vdb_total_bytes"],
        sync_wallclock_s=d["sync_wallclock_s"],
        memory_pct_at_sync=d["memory_pct_at_sync"],
        backup_path_kept=d["backup_path_kept"],
    )
    assert reconstructed == original


# ---------------------------------------------------------------------------
# 4. memory threshold WARN triggers
# ---------------------------------------------------------------------------


def test_memory_threshold_warn_triggers(monkeypatch):
    """MemoryReport.pct=0.95 with threshold=0.9 -> memory_warn event emitted."""
    logged_events: list[str] = []

    monkeypatch.setattr(m, "rsync_to_staging", lambda *a, **k: None)
    monkeypatch.setattr(m, "pause_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "start_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "atomic_swap", lambda *a, **k: "/OLD")
    monkeypatch.setattr(
        m, "monitor_post_restart_memory",
        lambda h, **k: MemoryProbeResult("ok", (), 0, 0.85),
    )
    monkeypatch.setattr(
        m, "check_memory_budget",
        lambda h: MemoryReport(int(0.95 * 2_000_000_000), 2_000_000_000, 0.95),
    )
    monkeypatch.setattr(m, "smoke_test", lambda h, u: True)
    monkeypatch.setattr(m, "update_state_file", lambda *a, **k: None)
    monkeypatch.setattr(m, "_read_state_file", lambda h, p: None)
    monkeypatch.setattr(m, "_read_state_history", lambda h, p: [])
    monkeypatch.setattr(m, "ssh_run",
                        lambda h, c, **k: MagicMock(stdout="0\n", returncode=0))
    monkeypatch.setattr(m, "_log_event", lambda event, details: logged_events.append(event))

    m.main(["--source-host", "hermes", "--memory-warn-threshold", "0.9", "--force"])

    assert "memory_warn" in logged_events


# ---------------------------------------------------------------------------
# 5. memory threshold WARN silent below
# ---------------------------------------------------------------------------


def test_memory_threshold_warn_silent_below(monkeypatch):
    """MemoryReport.pct=0.5 with threshold=0.9 -> no memory_warn event."""
    logged_events: list[str] = []

    monkeypatch.setattr(m, "rsync_to_staging", lambda *a, **k: None)
    monkeypatch.setattr(m, "pause_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "start_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "atomic_swap", lambda *a, **k: "/OLD")
    monkeypatch.setattr(
        m, "monitor_post_restart_memory",
        lambda h, **k: MemoryProbeResult("ok", (), 0, 0.85),
    )
    monkeypatch.setattr(
        m, "check_memory_budget",
        lambda h: MemoryReport(int(0.5 * 2_000_000_000), 2_000_000_000, 0.5),
    )
    monkeypatch.setattr(m, "smoke_test", lambda h, u: True)
    monkeypatch.setattr(m, "update_state_file", lambda *a, **k: None)
    monkeypatch.setattr(m, "_read_state_file", lambda h, p: None)
    monkeypatch.setattr(m, "_read_state_history", lambda h, p: [])
    monkeypatch.setattr(m, "ssh_run",
                        lambda h, c, **k: MagicMock(stdout="0\n", returncode=0))
    monkeypatch.setattr(m, "_log_event", lambda event, details: logged_events.append(event))

    m.main(["--source-host", "hermes", "--memory-warn-threshold", "0.9", "--force"])

    assert "memory_warn" not in logged_events


# ---------------------------------------------------------------------------
# 6. rsync excludes correct
# ---------------------------------------------------------------------------


def test_rsync_excludes_correct(monkeypatch):
    """rsync command includes all 3 --exclude= flags."""
    rsync_cmds: list[list[str]] = []

    def mock_run(cmd, **kwargs):
        rsync_cmds.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)

    rsync_to_staging(
        "hermes", "/src/lightrag_storage/", "./.relay/",
        "aliyun-vitaclaw", "/dst/lightrag_storage_NEW/",
    )

    all_args = [arg for cmd in rsync_cmds for arg in cmd]
    assert "--exclude=*.tmp" in all_args
    assert "--exclude=.bak*" in all_args
    assert "--exclude=*.lock" in all_args
    # Dry-run flag absent by default
    assert "--dry-run" not in all_args


# ---------------------------------------------------------------------------
# 7. rsync partial failure → SystemExit(1), swap never called
# ---------------------------------------------------------------------------


def test_rsync_partial_failure_returns_error(monkeypatch):
    """CalledProcessError on rsync -> SystemExit(1) before any swap attempted."""
    swap_calls: list[str] = []

    monkeypatch.setattr(
        m, "atomic_swap",
        lambda *a, **k: swap_calls.append("swap") or "/OLD",
    )
    monkeypatch.setattr(m, "pause_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "start_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "_read_state_file", lambda h, p: None)
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)

    def failing_run(cmd, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "rsync":
            raise subprocess.CalledProcessError(23, cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(subprocess, "run", failing_run)

    with pytest.raises(SystemExit) as exc:
        m.main(["--source-host", "hermes", "--force"])

    assert exc.value.code == 1
    assert len(swap_calls) == 0


# ---------------------------------------------------------------------------
# 8. first run with no prior state file
# ---------------------------------------------------------------------------


def test_state_file_first_run_no_prior_state(monkeypatch):
    """No prior state file -> proceeds without idempotency-skip; update_state_file called."""
    update_calls: list[str] = []

    monkeypatch.setattr(m, "rsync_to_staging", lambda *a, **k: None)
    monkeypatch.setattr(m, "pause_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "start_target_kb_api", lambda h: None)
    monkeypatch.setattr(m, "atomic_swap", lambda *a, **k: "/OLD")
    monkeypatch.setattr(
        m, "monitor_post_restart_memory",
        lambda h, **k: MemoryProbeResult("ok", (), 0, 0.85),
    )
    monkeypatch.setattr(m, "check_memory_budget",
                        lambda h: MemoryReport(100, 2_000_000_000, 0.05))
    monkeypatch.setattr(m, "smoke_test", lambda h, u: True)
    monkeypatch.setattr(
        m, "update_state_file",
        lambda *a, **k: update_calls.append("called"),
    )
    monkeypatch.setattr(m, "_read_state_file", lambda h, p: None)   # no prior state
    monkeypatch.setattr(m, "_read_state_history", lambda h, p: [])
    monkeypatch.setattr(m, "ssh_run",
                        lambda h, c, **k: MagicMock(stdout="500\n", returncode=0))
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)

    # No --force needed: prior state is None so idempotency guard is skipped
    m.main(["--source-host", "hermes"])

    assert len(update_calls) == 1


# ---------------------------------------------------------------------------
# 9. idempotency guard skips within 24h
# ---------------------------------------------------------------------------


def test_idempotency_guard_skips_within_24h(monkeypatch):
    """last_success_ts 1h ago + no --force -> exit 0; rsync NEVER called."""
    rsync_calls: list[str] = []

    one_hour_ago = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
    recent_state = SyncState(
        last_success_ts=one_hour_ago,
        vdb_total_bytes=1000,
        sync_wallclock_s=60.0,
        memory_pct_at_sync=0.5,
        backup_path_kept="/OLD",
    )

    monkeypatch.setattr(m, "_read_state_file", lambda h, p: recent_state)
    monkeypatch.setattr(
        m, "rsync_to_staging",
        lambda *a, **k: rsync_calls.append("rsync"),
    )
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)

    with pytest.raises(SystemExit) as exc:
        m.main(["--source-host", "hermes"])  # no --force

    assert exc.value.code == 0
    assert len(rsync_calls) == 0


# ---------------------------------------------------------------------------
# 10. monitor_post_restart_memory triggers on sustained breach (SYNC-04 addendum)
# ---------------------------------------------------------------------------


def test_monitor_post_restart_memory_triggers_rollback_on_sustained_breach(monkeypatch):
    """2+ consecutive samples > 0.85 -> status='exceeded'; exits probe early."""
    call_count = [0]

    def mock_memory(host: str) -> MemoryReport:
        call_count[0] += 1
        return MemoryReport(
            current_bytes=int(0.92 * 2_000_000_000),
            max_bytes=2_000_000_000,
            pct=0.92,  # consistently above 0.85 threshold
        )

    monkeypatch.setattr(m, "check_memory_budget", mock_memory)
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)

    result = monitor_post_restart_memory(
        "aliyun-vitaclaw", max_pct=0.85, sample_interval_s=1, sample_count=10
    )

    assert result.status == "exceeded"
    assert result.consecutive_breach_count >= 2
    assert result.triggered_threshold == 0.85
    assert len(result.samples) < 10  # exited early, did not exhaust all samples


# ---------------------------------------------------------------------------
# 11. monitor_post_restart_memory inconclusive on ssh failures (SYNC-04 addendum)
# ---------------------------------------------------------------------------


def test_monitor_post_restart_memory_inconclusive_does_not_rollback(monkeypatch):
    """< 2 samples obtainable (ssh failures) -> status='inconclusive'; no rollback."""
    call_count = [0]

    def mock_memory(host: str) -> MemoryReport:
        call_count[0] += 1
        if call_count[0] >= 2:
            raise subprocess.CalledProcessError(255, ["ssh"])
        return MemoryReport(current_bytes=100, max_bytes=2_000_000_000, pct=0.05)

    monkeypatch.setattr(m, "check_memory_budget", mock_memory)
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)

    result = monitor_post_restart_memory(
        "aliyun-vitaclaw", max_pct=0.85, sample_interval_s=1, sample_count=10
    )

    assert result.status == "inconclusive"
    assert result.consecutive_breach_count == 0
    # Caller MUST NOT rollback on inconclusive (documented in SYNC-04 addendum)
    assert len(result.samples) < 2


# ---------------------------------------------------------------------------
# 12. predict_ceiling_hit warns at 90 days (SYNC-04 addendum)
# ---------------------------------------------------------------------------


def test_predict_ceiling_hit_warn_at_90_days():
    """Linear history of 4 weekly syncs projects ceiling hit within 90 days."""
    today = date.today()
    base = datetime(today.year, today.month, today.day, 0, 0, tzinfo=timezone.utc) - timedelta(days=21)

    mb = 1024 * 1024
    growth_mb_per_day = 30   # 30 MB/day growth
    start_mb = 350

    # 4 weekly data points: days 0, 7, 14, 21 relative to base
    history = [
        SyncState(
            last_success_ts=(base + timedelta(days=i * 7)).isoformat(),
            vdb_total_bytes=(start_mb + i * 7 * growth_mb_per_day) * mb,
            sync_wallclock_s=120.0,
            memory_pct_at_sync=0.3 + i * 0.02,
            backup_path_kept=f"/OLD-{i}",
        )
        for i in range(4)
    ]
    # Ceiling set exactly 21+60=81 days from base => ~60 days from today
    ceiling = (start_mb + 81 * growth_mb_per_day) * mb

    result = predict_ceiling_hit(history, ceiling)

    assert result is not None
    days_out = (result - today).days
    # Should project within 90-day warn window (allowing ±5 days for floating-point)
    assert 1 <= days_out <= 95


# ---------------------------------------------------------------------------
# 13. predict_ceiling_hit returns None below 4 samples (SYNC-04 addendum)
# ---------------------------------------------------------------------------


def test_predict_ceiling_hit_returns_none_below_4_samples():
    """< 4 history points (or zero) -> predict_ceiling_hit returns None."""
    mb = 1024 * 1024
    base = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
    history_3 = [
        SyncState(
            last_success_ts=(base + timedelta(days=i * 7)).isoformat(),
            vdb_total_bytes=(100 + i * 70) * mb,
            sync_wallclock_s=60.0,
            memory_pct_at_sync=0.3,
            backup_path_kept=f"/OLD-{i}",
        )
        for i in range(3)  # exactly 3 — one short of threshold
    ]

    assert predict_ceiling_hit(history_3, 2_000 * mb) is None
    assert predict_ceiling_hit([], 2_000 * mb) is None

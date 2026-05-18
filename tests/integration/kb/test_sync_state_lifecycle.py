"""Integration tests for kb/scripts/sync_lightrag_storage.py — state lifecycle
and rollback path (kb-v2.2-1 F12).

Uses local-cp simulation: ssh_run is monkeypatched to perform local shutil
operations against tmp_path, so the full orchestration sequence runs without
any real network/SSH.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import kb.scripts.sync_lightrag_storage as m
from kb.scripts.sync_lightrag_storage import (
    MemoryProbeResult,
    MemoryReport,
    SyncState,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sync_dirs(tmp_path: Path):
    """
    Creates a minimal local directory scaffold that mirrors the remote layout:
      live_dir/    — "production" lightrag_storage
      staging_dir/ — lightrag_storage_NEW (pre-swap staging)
      relay_dir/   — Windows relay copy
      state_file   — JSON state path (initially absent)

    Returns a dict with all paths and a sentinel file list for byte-equality checks.
    """
    live_dir = tmp_path / "lightrag_storage"
    staging_dir = tmp_path / "lightrag_storage_NEW"
    relay_dir = tmp_path / ".sync-relay"
    state_file = tmp_path / "sync-state.json"

    live_dir.mkdir()
    staging_dir.mkdir()
    relay_dir.mkdir()

    # Populate live_dir with sentinel content
    (live_dir / "nodes.json").write_text('{"n":1}')
    (live_dir / "edges.json").write_text('{"e":2}')

    # Populate staging_dir with updated content (different from live)
    (staging_dir / "nodes.json").write_text('{"n":99}')
    (staging_dir / "edges.json").write_text('{"e":88}')
    (staging_dir / "new_chunk.bin").write_bytes(b"\x00\x01\x02")

    return {
        "live_dir": live_dir,
        "staging_dir": staging_dir,
        "relay_dir": relay_dir,
        "state_file": state_file,
        "tmp_path": tmp_path,
    }


def _make_local_ssh_run(dirs: dict):
    """
    Returns a drop-in replacement for ssh_run that executes locally against
    the tmp_path scaffold instead of over SSH.

    Handles only the subset of commands the orchestrator actually issues:
      - mv <a> <b>             — rename/move paths
      - mv <a> <b> && mv <c> <d> — atomic swap (double mv)
      - rm -rf <path>          — remove directory tree
      - systemctl stop/start   — no-op (service control)
      - systemctl show -p ...  — returns fake memory values (15% usage)
      - cat <path>             — read file contents
      - printf '%s' '<json>' > <path> — write JSON to file
      - du -sb ... | awk ...   — returns "1234567" (fake size)
    """
    import re

    def local_ssh_run(host: str, cmd: str, *, check: bool = True) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""

        # Double mv (atomic_swap)
        double_mv = re.match(
            r"mv\s+(\S+)\s+(\S+)\s+&&\s+mv\s+(\S+)\s+(\S+)", cmd
        )
        if double_mv:
            src1, dst1, src2, dst2 = [Path(p) for p in double_mv.groups()]
            src1.rename(dst1)
            src2.rename(dst2)
            return result

        # Single mv
        single_mv = re.match(r"mv\s+(\S+)\s+(\S+)$", cmd)
        if single_mv:
            src, dst = Path(single_mv.group(1)), Path(single_mv.group(2))
            src.rename(dst)
            return result

        # rm -rf <path> && mv <src> <dst>  (rollback compound pattern — match first)
        rm_mv = re.match(r"rm\s+-rf\s+(\S+)\s+&&\s+mv\s+(\S+)\s+(\S+)$", cmd)
        if rm_mv:
            rm_target = Path(rm_mv.group(1))
            mv_src = Path(rm_mv.group(2))
            mv_dst = Path(rm_mv.group(3))
            if rm_target.exists():
                shutil.rmtree(rm_target)
            mv_src.rename(mv_dst)
            return result

        # rm -rf (standalone)
        rm_rf = re.match(r"rm\s+-rf\s+(\S+)", cmd)
        if rm_rf:
            target = Path(rm_rf.group(1))
            if target.exists():
                shutil.rmtree(target)
            return result

        # systemctl stop/start (no-op)
        if "systemctl stop" in cmd or "systemctl start" in cmd:
            return result

        # systemctl show -p MemoryCurrent -p MemoryMax (fake 15% of 2GB)
        if "systemctl show" in cmd and "MemoryCurrent" in cmd:
            max_b = 2_000_000_000
            cur_b = int(0.15 * max_b)
            result.stdout = f"MemoryCurrent={cur_b}\nMemoryMax={max_b}\n"
            return result

        # cat <path>
        cat_m = re.match(r"cat\s+(\S+)", cmd)
        if cat_m:
            p = Path(cat_m.group(1).replace(" 2>/dev/null", "").strip())
            if p.exists():
                result.stdout = p.read_text()
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        # printf '%s' '<json>' > <path>
        printf_m = re.match(r"printf '%s'\s+'(.+)'\s+>\s+(\S+)$", cmd, re.DOTALL)
        if printf_m:
            payload, path = printf_m.group(1), Path(printf_m.group(2))
            path.write_text(payload)
            return result

        # du -sb ... | awk
        if cmd.startswith("du -sb"):
            result.stdout = "1234567\n"
            return result

        # fallback — no-op success
        return result

    return local_ssh_run


# ---------------------------------------------------------------------------
# 1. Full sync cycle writes correct state file
# ---------------------------------------------------------------------------


def test_full_sync_cycle_writes_state_file(sync_dirs, monkeypatch):
    """
    Full happy path (local-cp sim):
    - prior state absent → idempotency guard skipped
    - rsync fills staging (pre-populated fixture)
    - atomic_swap swaps dirs
    - smoke_test passes
    - state file written with sane last_success_ts / vdb_total_bytes / memory_pct_at_sync
    """
    dirs = sync_dirs
    local_ssh = _make_local_ssh_run(dirs)

    monkeypatch.setattr(m, "ssh_run", local_ssh)
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)

    # rsync: copy staging_dir content back to staging_dir (already populated)
    monkeypatch.setattr(m, "rsync_to_staging", lambda *a, **k: None)

    # OOM probe — always ok
    monkeypatch.setattr(
        m, "monitor_post_restart_memory",
        lambda h, **k: MemoryProbeResult("ok", (), 0, 0.85),
    )

    # smoke_test passes
    monkeypatch.setattr(m, "smoke_test", lambda h, u: True)

    # _read_state_history returns empty list (no growth prediction)
    monkeypatch.setattr(m, "_read_state_history", lambda h, p: [])

    argv = [
        "--source-host", "hermes",
        "--target-host", str(dirs["tmp_path"]),
        "--target-path", str(dirs["live_dir"]) + "/",
        "--state-file", str(dirs["state_file"]),
        "--public-smoke-url", "http://localhost",
        "--force",
    ]

    # Patch update_state_file to write into the local state_file directly
    written_states: list[SyncState] = []

    def fake_update_state_file(target_host, state_file_path, state, extra=None):
        written_states.append(state)
        d = state.__dict__ if hasattr(state, "__dict__") else vars(state)
        from dataclasses import asdict
        payload = asdict(state)
        payload["history"] = []
        if extra:
            payload.update(extra)
        Path(state_file_path).write_text(json.dumps(payload))

    monkeypatch.setattr(m, "update_state_file", fake_update_state_file)
    # _read_state_file returns None (first run)
    monkeypatch.setattr(m, "_read_state_file", lambda h, p: None)

    m.main(argv)

    assert len(written_states) == 1
    state = written_states[0]

    # last_success_ts is a non-empty ISO timestamp
    assert state.last_success_ts
    assert "T" in state.last_success_ts  # ISO 8601 format

    # wallclock is positive
    assert state.sync_wallclock_s > 0

    # memory_pct is in valid range (from fake systemctl show: 0.15)
    assert 0.0 <= state.memory_pct_at_sync <= 1.0

    # backup_path_kept is set
    assert state.backup_path_kept


# ---------------------------------------------------------------------------
# 2. Smoke failure triggers rollback — live dir restored
# ---------------------------------------------------------------------------


def test_smoke_failure_triggers_rollback_path(sync_dirs, monkeypatch):
    """
    smoke_test returns False → rollback() called → live_dir restored to
    pre-swap content byte-for-byte; exit code is 1.
    """
    dirs = sync_dirs
    local_ssh = _make_local_ssh_run(dirs)

    # Record the live_dir contents before sync starts
    live_before: dict[str, bytes] = {}
    for f in sorted(dirs["live_dir"].rglob("*")):
        if f.is_file():
            live_before[f.name] = f.read_bytes()

    assert live_before, "fixture must have files in live_dir"

    monkeypatch.setattr(m, "ssh_run", local_ssh)
    monkeypatch.setattr(m, "_log_event", lambda *a, **k: None)
    monkeypatch.setattr(m, "rsync_to_staging", lambda *a, **k: None)
    monkeypatch.setattr(
        m, "monitor_post_restart_memory",
        lambda h, **k: MemoryProbeResult("ok", (), 0, 0.85),
    )
    # check_memory_budget returns safe value (used post-probe)
    monkeypatch.setattr(
        m, "check_memory_budget",
        lambda h: MemoryReport(int(0.15 * 2_000_000_000), 2_000_000_000, 0.15),
    )

    # smoke_test FAILS
    monkeypatch.setattr(m, "smoke_test", lambda h, u: False)

    monkeypatch.setattr(m, "_read_state_file", lambda h, p: None)
    monkeypatch.setattr(m, "_read_state_history", lambda h, p: [])
    monkeypatch.setattr(m, "update_state_file", lambda *a, **k: None)

    argv = [
        "--source-host", "hermes",
        "--target-host", str(dirs["tmp_path"]),
        "--target-path", str(dirs["live_dir"]) + "/",
        "--state-file", str(dirs["state_file"]),
        "--public-smoke-url", "http://localhost",
        "--force",
    ]

    with pytest.raises(SystemExit) as exc:
        m.main(argv)

    assert exc.value.code == 1

    # live_dir must exist and contain the original content
    assert dirs["live_dir"].is_dir(), "live_dir must be restored after rollback"
    live_after: dict[str, bytes] = {}
    for f in sorted(dirs["live_dir"].rglob("*")):
        if f.is_file():
            live_after[f.name] = f.read_bytes()

    assert live_after == live_before, (
        "rollback must restore live_dir to pre-swap byte-for-byte contents"
    )

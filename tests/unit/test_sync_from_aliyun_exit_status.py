"""Offline exit-status regression tests for ``sync-from-aliyun.sh``."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "sync-from-aliyun.sh"


def _write_stub(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\nset -eu\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _run_sync(tmp_path: Path, failures_before_success: int) -> subprocess.CompletedProcess[str]:
    """Run the real script with every external command replaced by a temp stub."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_file = tmp_path / "stub.log"
    state_file = tmp_path / "rsync-attempts"
    state_file.write_text("0\n", encoding="utf-8")

    _write_stub(
        bin_dir / "rsync",
        """attempt=$(cat "$STATE_FILE")
attempt=$((attempt + 1))
printf '%s\\n' "$attempt" > "$STATE_FILE"
printf 'rsync %s\\n' "$attempt" >> "$STUB_LOG"
if [ "$attempt" -le "$RSYNC_FAILURES_BEFORE_SUCCESS" ]; then
  exit 23
fi""",
    )
    _write_stub(bin_dir / "ssh", "printf 'ssh\\n' >> \"$STUB_LOG\"\nexit 99")
    _write_stub(bin_dir / "sleep", "printf 'sleep %s\\n' \"$1\" >> \"$STUB_LOG\"")
    _write_stub(bin_dir / "rm", "printf 'rm\\n' >> \"$STUB_LOG\"")
    _write_stub(bin_dir / "touch", "printf 'touch\\n' >> \"$STUB_LOG\"")

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HERMES_DATA_DIR": str(tmp_path / "vault"),
        "ALIYUN_SSH_HOST": "stub@invalid",
        "ALIYUN_SSH_KEY": str(tmp_path / "stub-ssh-key"),
        "STATE_FILE": str(state_file),
        "STUB_LOG": str(log_file),
        "RSYNC_FAILURES_BEFORE_SUCCESS": str(failures_before_success),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert "ssh\n" not in log_file.read_text(encoding="utf-8"), "stub rsync must not invoke ssh"
    return result


@pytest.mark.unit
def test_continuous_rsync_failure_exits_nonzero_without_sync_ok(tmp_path: Path) -> None:
    """All four retry rounds failing must remain externally visible as failure."""
    result = _run_sync(tmp_path, failures_before_success=100)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "sync OK" not in result.stdout
    assert "exhausted 3 retries" in result.stderr


@pytest.mark.unit
@pytest.mark.parametrize("failures_before_success", [1, 4])
def test_rsync_retry_then_success_exits_zero_on_second_attempt(
    tmp_path: Path, failures_before_success: int
) -> None:
    """Any failed target in round one must lead to a second successful round."""
    result = _run_sync(tmp_path, failures_before_success=failures_before_success)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "sync OK on attempt 2" in result.stdout


@pytest.mark.unit
def test_immediate_rsync_success_exits_zero(tmp_path: Path) -> None:
    """An entirely successful sync keeps the script's original zero exit contract."""
    result = _run_sync(tmp_path, failures_before_success=0)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "sync OK on attempt 1" in result.stdout

"""Validate scripts/local_e2e.sh harness.

Verifies:
  1. `bash -n` syntax check passes
  2. shellcheck passes (skipped with warning if not in PATH)
  3. `help` mode → exit 0, prints "Modes:" usage block
  4. Invalid mode → exit 0 (falls through to help), prints "Modes:"
  5. All 6 documented case branches present in source

Tests run from repo root. They invoke bash directly (not pytest fixtures)
so they exercise the same shell environment a developer would.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "local_e2e.sh"


def _run_bash(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run scripts/local_e2e.sh via bash from repo root, capturing combined output.

    Forces UTF-8 decoding so em-dashes and CJK chars in the help block decode
    cleanly on Windows (default cp1252 chokes on `—`).
    """
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=env,
    )


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.is_file(), f"{SCRIPT} missing"
    # On Windows file mode bits aren't reliable; just assert it's a regular file.
    # bash itself doesn't require +x to source/run a script.


def test_bash_syntax_clean() -> None:
    """`bash -n` must parse without error."""
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, (
        f"bash -n failed (rc={result.returncode}):\n{result.stderr}"
    )


def test_shellcheck_clean() -> None:
    """shellcheck passes if available; skip otherwise."""
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not in PATH — skipping (install for stricter CI)")
    result = subprocess.run(
        ["shellcheck", str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, (
        f"shellcheck failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_help_mode_prints_usage_and_exits_zero() -> None:
    result = _run_bash("help")
    assert result.returncode == 0, f"rc={result.returncode}, stderr={result.stderr}"
    assert "Modes:" in result.stdout, f"'Modes:' not in stdout:\n{result.stdout}"
    assert "rss" in result.stdout
    assert "wechat" in result.stdout


def test_dash_h_alias_prints_usage() -> None:
    result = _run_bash("-h")
    assert result.returncode == 0
    assert "Modes:" in result.stdout


def test_invalid_mode_falls_through_to_help() -> None:
    """Unknown mode → prints error + usage, exits 0 (matches script *) branch)."""
    # Pre-flight (SA / DB) runs before mode dispatch, so this test requires the
    # local dev runtime layout. Skip cleanly if it's not set up.
    sa = REPO_ROOT / ".dev-runtime" / "gcp-paid-sa.json"
    db = REPO_ROOT / ".dev-runtime" / "data" / "kol_scan.db"
    if not sa.is_file() or not db.is_file():
        pytest.skip(".dev-runtime not provisioned — skipping invalid-mode test")

    result = _run_bash("invalid-mode-xyz")
    assert result.returncode == 0, (
        f"rc={result.returncode}, stdout={result.stdout}, stderr={result.stderr}"
    )
    assert "unknown mode" in result.stderr.lower() or "unknown mode" in result.stdout.lower()
    assert "Modes:" in result.stdout


def test_all_documented_modes_present_in_source() -> None:
    """Every documented mode must have a case branch in the dispatch."""
    source = SCRIPT.read_text(encoding="utf-8")
    expected_branches = ["rss)", "kol)", "wechat)", "layer1)", "layer2)", "cleanup)"]
    missing = [b for b in expected_branches if b not in source]
    assert not missing, f"Missing case branches: {missing}"


def test_help_short_circuits_before_preflight() -> None:
    """`help` must work even when SA / DB / BASE_DIR are missing."""
    env = os.environ.copy()
    env["GOOGLE_APPLICATION_CREDENTIALS"] = "/nonexistent/sa.json"
    env["OMNIGRAPH_BASE_DIR"] = "/nonexistent/base"
    result = _run_bash("help", env=env)
    assert result.returncode == 0, (
        f"help should exit 0 on broken env; got rc={result.returncode}, "
        f"stderr={result.stderr}"
    )
    assert "Modes:" in result.stdout


def test_default_env_vars_documented() -> None:
    """All env vars listed in usage block must have a default in the script body."""
    source = SCRIPT.read_text(encoding="utf-8")
    expected_defaults = [
        "NODE_EXTRA_CA_CERTS",
        "REQUESTS_CA_BUNDLE",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "OMNIGRAPH_LLM_PROVIDER",
        "OMNIGRAPH_LLM_MODEL",
        "OMNIGRAPH_BASE_DIR",
        "KOL_SCAN_DB_PATH",
        "PYTHONPATH",
        "DEEPSEEK_API_KEY",
        "SCRAPE_CASCADE",
    ]
    for var in expected_defaults:
        # Each var should appear in an `export VAR="${VAR:-...}"` line
        assert f'export {var}="${{{var}:-' in source, (
            f"Default for {var} missing or malformed"
        )

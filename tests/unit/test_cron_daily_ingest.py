"""Quick 260508-ev2 F2: structural tests for scripts/cron_daily_ingest.sh.

Verifies (no live tmux invocation):
  1. bash -n parses cleanly
  2. cleanup_stuck_docs.py --all-failed appears in script body
  3. cleanup invocation precedes batch_ingest invocation (line ordering)
  4. MAX_ARTICLES default is 10
  5. shellcheck passes when present (skipped if shellcheck not in PATH)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "cron_daily_ingest.sh"


def test_bash_n_passes():
    """bash -n returns 0 (syntax OK)."""
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT_PATH)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"bash -n failed: stderr={result.stderr!r}"
    )


def test_contains_cleanup_invocation():
    """Script body must invoke cleanup_stuck_docs.py --all-failed."""
    body = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "cleanup_stuck_docs.py --all-failed" in body, (
        "script must call cleanup_stuck_docs.py --all-failed before ingest"
    )


def test_cleanup_before_ingest():
    """cleanup_stuck_docs.py invocation must precede batch_ingest invocation.

    Skips lines starting with '#' (header comments may legally name either
    script in either order). Match only the executable command invocations.
    """
    lines = SCRIPT_PATH.read_text(encoding="utf-8").splitlines()

    def _first_invocation(needle: str) -> "int | None":
        for i, ln in enumerate(lines):
            stripped = ln.lstrip()
            if stripped.startswith("#"):
                continue
            if needle in ln:
                return i
        return None

    cleanup_idx = _first_invocation("cleanup_stuck_docs.py")
    ingest_idx = _first_invocation("batch_ingest_from_spider.py")
    assert cleanup_idx is not None, "cleanup invocation not found"
    assert ingest_idx is not None, "batch_ingest invocation not found"
    assert cleanup_idx < ingest_idx, (
        f"cleanup at L{cleanup_idx} must precede ingest at L{ingest_idx}"
    )


def test_max_articles_default_10():
    """MAX_ARTICLES parameter expansion must default to 10."""
    body = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "MAX_ARTICLES=\"${1:-10}\"" in body or "MAX_ARTICLES=${1:-10}" in body, (
        "expected MAX_ARTICLES default of 10 via parameter expansion"
    )


def test_shellcheck_passes_or_skips():
    """shellcheck (when present) must report 0 issues."""
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not in PATH")
    result = subprocess.run(
        ["shellcheck", str(SCRIPT_PATH)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"shellcheck failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )

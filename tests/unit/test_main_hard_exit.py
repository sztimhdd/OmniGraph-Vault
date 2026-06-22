"""ISSUES #45 behavior pin: batch_ingest_from_spider.py main() must exit
promptly after asyncio.run() returns — NOT hang for 50+ minutes waiting for a
third-party C-level thread join during Py_Finalize().

Pre-fix: subprocess hung 50+ minutes despite `Successfully finalized 12
storages` + `Metrics written` final journal lines (Hermes 6/8 PID 2623821,
Aliyun 6/9 PID 1826054, Aliyun 6/11 PID 1552490 — all platforms confirmed).

Post-fix: os._exit(0) bypasses Py_Finalize; process exits within ~1s of the
final logging.shutdown() call.

Both tests are corp-network-safe: `--help` is pure argparse and exits before
any LLM/Vertex/qdrant client construction, and the source grep touches no
network.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "batch_ingest_from_spider.py"
EXIT_BUDGET_S = 5.0


@pytest.mark.unit
def test_help_exits_within_5s() -> None:
    """`python batch_ingest_from_spider.py --help` must exit within 5s.

    Argparse is the cheapest end-to-end exercise of the module-import +
    main() entry path; if main() ever blocks at import-time on SDK init,
    this catches it. The hang's third-party-thread-join scenario only
    triggers after a real asyncio.run batch completes, so production cron
    is the ultimate verify — but this guards the cheap regression surface.
    """
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        timeout=EXIT_BUDGET_S * 6,  # outer 30s safety; inner budget asserted below
        cwd=str(REPO_ROOT),
    )
    elapsed = time.monotonic() - start

    assert result.returncode == 0, (
        f"--help should exit 0; got {result.returncode}\n"
        f"stderr: {result.stderr.decode('utf-8', errors='replace')[:2000]}"
    )
    assert elapsed <= EXIT_BUDGET_S, (
        f"--help took {elapsed:.2f}s, budget is {EXIT_BUDGET_S}s. "
        f"Possible ISSUES #45 regression (post-asyncio.run hang). "
        f"Check os._exit(0) fix is still in main()."
    )


@pytest.mark.unit
def test_main_has_os_exit_guard() -> None:
    """Source-level tripwire: os._exit(0) + flush + logging.shutdown() MUST
    remain in main(). If this fails, the #45 fix was silently removed and the
    cross-platform hang will recur on Hermes + Aliyun.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    assert "os._exit(0)" in source, (
        "ISSUES #45 fix missing: batch_ingest_from_spider.py no longer "
        "contains os._exit(0). Cross-platform post-completion hang will "
        "recur. See .planning/quick/260610-rgm-*-PLAN.md."
    )
    assert "sys.stdout.flush()" in source
    assert "logging.shutdown()" in source

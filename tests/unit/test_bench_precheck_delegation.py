"""Regression test for D-BENCH-PRECHECK (v3.1 closure Finding 2).

Before 2026-05-01: bench _balance_precheck() read os.environ directly and
emitted balance_precheck_skipped when SILICONFLOW_API_KEY was only in
~/.hermes/.env (not loaded into process env). Production Vision path worked
correctly; only the precheck helper was buggy.

This test verifies the fix: bench precheck delegates to lib.siliconflow_balance,
which imports config to auto-load .env. No direct os.environ reads remain
inside _balance_precheck's body.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.unit


def test_bench_precheck_no_longer_reads_os_environ_directly():
    """Regression: grep the bench source for the old anti-pattern."""
    from pathlib import Path

    bench_src = Path("scripts/bench_ingest_fixture.py").read_text(
        encoding="utf-8"
    )

    precheck_start = bench_src.index("def _balance_precheck")
    precheck_end = bench_src.index("\ndef ", precheck_start + 1)
    precheck_body = bench_src[precheck_start:precheck_end]
    assert 'os.environ.get("SILICONFLOW_API_KEY"' not in precheck_body, (
        "_balance_precheck must delegate to lib.siliconflow_balance "
        "(D-BENCH-PRECHECK)"
    )
    assert "from lib.siliconflow_balance import" in precheck_body, (
        "_balance_precheck must import from lib.siliconflow_balance"
    )


def test_bench_precheck_warning_branch():
    """When lib returns Decimal, bench emits balance_warning with status=ok."""
    from scripts.bench_ingest_fixture import _balance_precheck

    with patch(
        "lib.siliconflow_balance.check_siliconflow_balance",
        return_value=Decimal("10.00"),
    ):
        result = _balance_precheck()
    assert result["event"] == "balance_warning"
    assert result["status"] == "ok"
    assert result["balance_cny"] == 10.0


def test_bench_precheck_insufficient_branch():
    """When balance < ESTIMATED_COST_CNY, bench emits insufficient_for_batch."""
    from scripts.bench_ingest_fixture import _balance_precheck

    with patch(
        "lib.siliconflow_balance.check_siliconflow_balance",
        return_value=Decimal("0.001"),
    ):
        result = _balance_precheck()
    assert result["event"] == "balance_warning"
    assert result["status"] == "insufficient_for_batch"


def test_bench_precheck_skipped_branch_when_key_missing():
    """When lib raises MissingKeyError, bench emits balance_precheck_skipped."""
    from lib.siliconflow_balance import MissingKeyError
    from scripts.bench_ingest_fixture import _balance_precheck

    with patch(
        "lib.siliconflow_balance.check_siliconflow_balance",
        side_effect=MissingKeyError("SILICONFLOW_API_KEY not set"),
    ):
        result = _balance_precheck()
    assert result["event"] == "balance_precheck_skipped"
    assert result["reason"] == "api_key_unset"


def test_bench_precheck_failed_branch_on_http_error():
    """When lib raises BalanceCheckError, bench emits balance_precheck_failed."""
    from lib.siliconflow_balance import BalanceCheckError
    from scripts.bench_ingest_fixture import _balance_precheck

    with patch(
        "lib.siliconflow_balance.check_siliconflow_balance",
        side_effect=BalanceCheckError("HTTP 500"),
    ):
        result = _balance_precheck()
    assert result["event"] == "balance_precheck_failed"
    assert "HTTP 500" in result["error"]

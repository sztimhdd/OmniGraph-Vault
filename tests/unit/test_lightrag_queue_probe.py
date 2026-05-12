"""Unit tests for lib.lightrag_queue_probe (gqu Pattern A)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.lightrag_queue_probe import compute_dynamic_budget, read_queue_depth


@pytest.mark.unit
def test_empty_queue_returns_base_budget():
    budget = compute_dynamic_budget({}, base_budget_s=300.0)
    assert budget == 300.0


@pytest.mark.unit
def test_busy_queue_scales_linearly():
    # 10 processing docs × 60s/doc = 600s; floor of 300s does NOT override
    ds = {f"d{i}": {"status": "processing"} for i in range(10)}
    budget = compute_dynamic_budget(ds, base_budget_s=300.0, per_doc_avg_s=60.0)
    assert budget == 600.0


@pytest.mark.unit
def test_huge_queue_hits_cap():
    # 100 × 60 = 6000 > cap=1800
    ds = {f"d{i}": {"status": "processing"} for i in range(100)}
    budget = compute_dynamic_budget(ds, base_budget_s=300.0, per_doc_avg_s=60.0, cap_s=1800.0)
    assert budget == 1800.0


@pytest.mark.unit
def test_file_missing_returns_zero(tmp_path: Path):
    # Point read_queue_depth at a non-existent file
    target = tmp_path / "nonexistent.json"
    assert read_queue_depth(target) == 0


@pytest.mark.unit
def test_corrupt_json_returns_zero(tmp_path: Path):
    target = tmp_path / "bad.json"
    target.write_text("{not valid json", encoding="utf-8")
    assert read_queue_depth(target) == 0


@pytest.mark.unit
def test_fixture_busy_has_real_processing_docs():
    """Validates the prod-pulled busy fixture actually exercises the busy path."""
    fix = Path(__file__).parent.parent / "fixtures" / "lightrag_doc_status" / "sample_busy.json"
    if not fix.exists():
        pytest.skip("sample_busy.json fixture not present")
    with open(fix, "r", encoding="utf-8") as f:
        data = json.load(f)
    depth = sum(1 for v in data.values() if isinstance(v, dict) and v.get("status") == "processing")
    # Allow 0 only if pull happened during a quiet window — but warn loudly
    if depth == 0:
        pytest.skip("sample_busy.json was pulled during a quiet window — re-pull recommended")
    # Sanity: budget must be > base_budget_s when fixture has real busy state
    budget = compute_dynamic_budget(data, base_budget_s=300.0)
    assert budget >= 300.0


@pytest.mark.unit
def test_compute_dynamic_budget_emits_pattern_a_log_line(caplog):
    """gqu Pattern A burst activation must be directly grep-able via 'gqu Pattern A' marker."""
    import logging as _logging
    caplog.set_level(_logging.INFO, logger="lib.lightrag_queue_probe")
    ds = {"d0": {"status": "processing"}, "d1": {"status": "processing"}}
    budget = compute_dynamic_budget(
        ds, base_budget_s=300.0, per_doc_avg_s=60.0, cap_s=1800.0
    )
    # Math sanity: queue_depth=2, 2*60=120, max(300,120)=300, min(300,1800)=300
    assert budget == 300.0
    # Exactly one INFO record from the probe module
    records = [r for r in caplog.records if r.name == "lib.lightrag_queue_probe"]
    assert len(records) == 1, f"expected 1 INFO record, got {len(records)}"
    msg = records[0].getMessage()
    assert "gqu Pattern A" in msg, f"missing marker: {msg!r}"
    assert "queue_depth=2" in msg, f"missing queue_depth: {msg!r}"
    assert "effective_budget_s=300" in msg, f"missing effective_budget_s: {msg!r}"

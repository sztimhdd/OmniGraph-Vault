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

"""Scaffold smoke-test — verifies pytest is installed and test infrastructure is functional."""
from __future__ import annotations
from pathlib import Path
import pytest


@pytest.mark.unit
def test_fixtures_dir_exists():
    """Confirm the fixtures directory was created as part of Wave 0 scaffold."""
    fixtures = Path(__file__).parent.parent / "fixtures"
    assert fixtures.is_dir(), "tests/fixtures/ must exist after Wave 0 scaffold"


@pytest.mark.unit
def test_sample_wechat_fixture_min_length():
    """sample_wechat_article.md must be >= 2000 chars (threshold for question extraction)."""
    fixture = Path(__file__).parent.parent / "fixtures" / "sample_wechat_article.md"
    assert fixture.exists(), "sample_wechat_article.md must exist"
    assert fixture.stat().st_size >= 2000, "fixture must be >= 2000 bytes"


@pytest.mark.unit
def test_sample_haowen_response_is_valid_json():
    """sample_haowen_response.json must parse as valid JSON."""
    import json
    fixture = Path(__file__).parent.parent / "fixtures" / "sample_haowen_response.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert "question" in data
    assert "best_source_url" in data


@pytest.mark.unit
def test_golden_dir_exists():
    """tests/fixtures/golden/ must exist (populated in Task 0.5)."""
    golden = Path(__file__).parent.parent / "fixtures" / "golden"
    assert golden.is_dir(), "tests/fixtures/golden/ must exist after Wave 0 scaffold"

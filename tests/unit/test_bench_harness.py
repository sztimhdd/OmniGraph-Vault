"""Phase 11 Plan 11-00: benchmark harness unit tests (D-11.01, D-11.03, D-11.05, D-11.07).

Covers the PRD-exact schema, 5-stage timing scaffold, SiliconFlow balance
precheck branches, atomic JSON write, CLI arg parsing, and fixture reader
that performs no network I/O.

All tests mock HTTP calls so no live network, no LightRAG init, no real API calls.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Autouse fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    """DEEPSEEK_API_KEY=dummy to satisfy lib.__init__ eager import (Phase 5 FLAG 2)."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")


@pytest.fixture(autouse=True)
def _clear_siliconflow_key(monkeypatch):
    """Default: SILICONFLOW_API_KEY unset — individual tests re-set it as needed."""
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)


@pytest.fixture
def _synthetic_fixture(tmp_path: Path) -> Path:
    """Create a minimal synthetic fixture dir: article.md + metadata.json + images/."""
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    (fixture_dir / "article.md").write_text("# Hello\n\nBody text.", encoding="utf-8")
    (fixture_dir / "metadata.json").write_text(
        json.dumps({
            "title": "Test article",
            "url": "http://test.example/foo",
            "text_chars": 17,
            "total_images_raw": 3,
            "images_after_filter": 2,
        }),
        encoding="utf-8",
    )
    images_dir = fixture_dir / "images"
    images_dir.mkdir()
    (images_dir / "img_000.jpg").write_bytes(b"\xff\xd8\xff")  # tiny JPEG marker
    (images_dir / "img_001.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG marker
    return fixture_dir


# ---------------------------------------------------------------------------
# Import target under test
# ---------------------------------------------------------------------------


@pytest.fixture
def bench_module():
    """Import scripts/bench_ingest_fixture.py fresh each test."""
    # Add scripts/ to sys.path so we can import the module by name
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import importlib
    import bench_ingest_fixture  # type: ignore

    importlib.reload(bench_ingest_fixture)
    return bench_ingest_fixture


# ---------------------------------------------------------------------------
# Test 1 — CLI arg parsing (end-to-end via main(argv=...))
# ---------------------------------------------------------------------------


def test_main_runs_end_to_end_with_stub_text_ingest_returns_exit_1(
    bench_module, _synthetic_fixture, tmp_path
):
    """main() against the synthetic fixture with stub text_ingest → gate_pass=false → exit 1.

    Verifies the CLI entry point parses --fixture + --output, runs the 5-stage
    scaffold, writes benchmark_result.json with PRD-exact shape.
    """
    out_path = tmp_path / "benchmark_result.json"
    exit_code = bench_module.main([
        "--fixture", str(_synthetic_fixture),
        "--output", str(out_path),
    ])

    # Stub text_ingest → gate_pass=false → exit 1
    assert exit_code == 1, "stub harness should produce gate_pass=false → exit 1"
    assert out_path.exists(), "benchmark_result.json must be written"

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert set(data.keys()) == {
        "article_hash", "fixture_path", "timestamp_utc",
        "stage_timings_ms", "counters", "gate", "gate_pass",
        "warnings", "errors",
    }


def test_main_defaults_fixture_and_output_paths(bench_module):
    """main() constants expose default paths matching D-11.01 / D-11.07."""
    assert bench_module.DEFAULT_FIXTURE == Path("test/fixtures/gpt55_article")
    assert bench_module.DEFAULT_OUTPUT == Path(
        "test/fixtures/gpt55_article/benchmark_result.json"
    )


# ---------------------------------------------------------------------------
# Test 2 — Fixture reader (no network I/O)
# ---------------------------------------------------------------------------


def test_read_fixture_returns_expected_shape(bench_module, _synthetic_fixture):
    """_read_fixture() produces a clean dict from article.md + metadata.json + images/."""
    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("requests.get") as mock_requests_get:
        result = bench_module._read_fixture(_synthetic_fixture)

        # Zero network I/O — the fixture reader is pure disk
        mock_urlopen.assert_not_called()
        mock_requests_get.assert_not_called()

    assert result["title"] == "Test article"
    assert result["url"] == "http://test.example/foo"
    assert result["markdown"] == "# Hello\n\nBody text."
    assert result["text_chars"] == 17
    assert result["total_images_raw"] == 3
    assert result["images_after_filter"] == 2
    assert isinstance(result["image_paths"], list)
    assert len(result["image_paths"]) == 2
    assert all(isinstance(p, Path) for p in result["image_paths"])


# ---------------------------------------------------------------------------
# Test 3 — Article hash
# ---------------------------------------------------------------------------


def test_compute_article_hash_matches_ingest_wechat_shape(bench_module):
    """_compute_article_hash() returns md5(url)[:10] — matches ingest_wechat.py:689."""
    h = bench_module._compute_article_hash("http://test.example/foo")
    assert isinstance(h, str)
    assert len(h) == 10
    assert all(c in "0123456789abcdef" for c in h)


def test_compute_article_hash_deterministic(bench_module):
    """Same URL yields same hash (md5 is deterministic)."""
    h1 = bench_module._compute_article_hash("http://example.com/x")
    h2 = bench_module._compute_article_hash("http://example.com/x")
    assert h1 == h2


# ---------------------------------------------------------------------------
# Test 4 — Schema builder (PRD-exact shape)
# ---------------------------------------------------------------------------


def test_build_result_json_matches_prd_schema(bench_module):
    """_build_result_json() produces dict matching PRD schema key-for-key, type-for-type."""
    timings = {
        "scrape": 10,
        "classify": 50,
        "image_download": 20,
        "text_ingest": 100,
        "async_vision_start": 1,
    }
    counters = {
        "images_input": 28,
        "images_kept": 28,
        "images_filtered": 0,
        "chunks_extracted": 15,
        "entities_ingested": 50,
    }
    gate_flags = {
        "text_ingest_under_2min": True,
        "aquery_returns_fixture_chunk": True,
        "zero_crashes": True,
    }
    warnings = [{"event": "balance_warning", "provider": "siliconflow"}]
    errors = []

    result = bench_module._build_result_json(
        article_hash="abcdef1234",
        fixture_path="test/fixtures/gpt55_article/",
        timings=timings,
        counters=counters,
        gate_flags=gate_flags,
        warnings=warnings,
        errors=errors,
    )

    assert set(result.keys()) == {
        "article_hash", "fixture_path", "timestamp_utc",
        "stage_timings_ms", "counters", "gate", "gate_pass",
        "warnings", "errors",
    }
    assert result["article_hash"] == "abcdef1234"
    assert result["fixture_path"] == "test/fixtures/gpt55_article/"
    # timestamp round-trips (ISO 8601 with Z suffix)
    assert result["timestamp_utc"].endswith("Z")
    dt = datetime.fromisoformat(result["timestamp_utc"].replace("Z", "+00:00"))
    assert dt is not None
    # Stage timings: all 5 keys, all int
    assert set(result["stage_timings_ms"].keys()) == {
        "scrape", "classify", "image_download", "text_ingest", "async_vision_start"
    }
    assert all(isinstance(v, int) for v in result["stage_timings_ms"].values())
    # Counters: all 5 keys
    assert set(result["counters"].keys()) == {
        "images_input", "images_kept", "images_filtered",
        "chunks_extracted", "entities_ingested"
    }
    # Gate: all 3 keys, all bool
    assert set(result["gate"].keys()) == {
        "text_ingest_under_2min", "aquery_returns_fixture_chunk", "zero_crashes"
    }
    assert all(isinstance(v, bool) for v in result["gate"].values())
    # gate_pass = all(gate_flags.values())
    assert result["gate_pass"] is True


def test_build_result_json_gate_pass_false_when_any_gate_false(bench_module):
    """gate_pass = all(gate_flags.values()) — any False → gate_pass=false."""
    timings = dict.fromkeys(
        ["scrape", "classify", "image_download", "text_ingest", "async_vision_start"], 0
    )
    counters = dict.fromkeys(
        ["images_input", "images_kept", "images_filtered",
         "chunks_extracted", "entities_ingested"], 0
    )
    gate_flags = {
        "text_ingest_under_2min": True,
        "aquery_returns_fixture_chunk": False,  # one flag false
        "zero_crashes": True,
    }

    result = bench_module._build_result_json(
        article_hash="x", fixture_path="x/", timings=timings,
        counters=counters, gate_flags=gate_flags, warnings=[], errors=[],
    )
    assert result["gate_pass"] is False


# ---------------------------------------------------------------------------
# Test 5 — Atomic write
# ---------------------------------------------------------------------------


def test_write_result_atomic_tmp_rename(bench_module, tmp_path):
    """_write_result() writes to <path>.tmp, then os.rename to final path."""
    out = tmp_path / "out.json"
    bench_module._write_result(out, {"hello": "world"})

    assert out.exists()
    assert not (tmp_path / "out.json.tmp").exists(), "tmp file must be cleaned up on success"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"hello": "world"}


def test_write_result_cleans_tmp_on_failure(bench_module, tmp_path, monkeypatch):
    """On mid-write exception, tmp file is cleaned up AND final path is NOT modified."""
    out = tmp_path / "out.json"
    out.write_text('{"original": true}', encoding="utf-8")

    # Patch os.rename to raise
    def _raising_rename(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr("os.rename", _raising_rename)

    with pytest.raises(OSError):
        bench_module._write_result(out, {"new": "data"})

    # Original untouched
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"original": True}
    # tmp is cleaned up
    assert not (tmp_path / "out.json.tmp").exists()


# ---------------------------------------------------------------------------
# Test 6 — SiliconFlow balance precheck (4 branches)
# ---------------------------------------------------------------------------


def test_balance_precheck_api_key_unset(bench_module, monkeypatch):
    """Branch A: SILICONFLOW_API_KEY unset → event=balance_precheck_skipped."""
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    result = bench_module._balance_precheck()
    assert result["event"] == "balance_precheck_skipped"
    assert result["provider"] == "siliconflow"
    assert result["reason"] == "api_key_unset"


def test_balance_precheck_ok_branch(bench_module, monkeypatch):
    """Branch B: balance >= estimated cost → status=ok."""
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"data": {"balance": "5.43"}}).encode("utf-8")
    fake_resp.__enter__ = lambda self: self
    fake_resp.__exit__ = lambda self, *a: False

    with patch("urllib.request.urlopen", return_value=fake_resp):
        result = bench_module._balance_precheck()

    assert result["event"] == "balance_warning"
    assert result["provider"] == "siliconflow"
    assert result["balance_cny"] == pytest.approx(5.43)
    assert result["estimated_cost_cny"] == 0.036
    assert result["status"] == "ok"


def test_balance_precheck_insufficient_branch(bench_module, monkeypatch):
    """Branch C: balance < estimated cost → status=insufficient_for_batch."""
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"data": {"balance": 0.001}}).encode("utf-8")
    fake_resp.__enter__ = lambda self: self
    fake_resp.__exit__ = lambda self, *a: False

    with patch("urllib.request.urlopen", return_value=fake_resp):
        result = bench_module._balance_precheck()

    assert result["event"] == "balance_warning"
    assert result["status"] == "insufficient_for_batch"
    assert result["balance_cny"] == pytest.approx(0.001)


def test_balance_precheck_url_error_branch(bench_module, monkeypatch):
    """Branch D: urlopen raises URLError → event=balance_precheck_failed."""
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("boom"),
    ):
        result = bench_module._balance_precheck()

    assert result["event"] == "balance_precheck_failed"
    assert result["provider"] == "siliconflow"
    assert "boom" in result["error"]


def test_balance_precheck_json_decode_error(bench_module, monkeypatch):
    """Branch D variant: non-JSON response → event=balance_precheck_failed."""
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    fake_resp = MagicMock()
    fake_resp.read.return_value = b"not json"
    fake_resp.__enter__ = lambda self: self
    fake_resp.__exit__ = lambda self, *a: False

    with patch("urllib.request.urlopen", return_value=fake_resp):
        result = bench_module._balance_precheck()

    assert result["event"] == "balance_precheck_failed"
    assert result["provider"] == "siliconflow"


# ---------------------------------------------------------------------------
# Test 7 — Stage timing scaffold produces all 5 keys
# ---------------------------------------------------------------------------


def test_stage_timing_context_manager_records_ms(bench_module):
    """_time_stage context manager records elapsed ms into timings dict as int."""
    timings: dict[str, int] = {}
    with bench_module._time_stage("test_stage", timings):
        pass  # no-op
    assert "test_stage" in timings
    assert isinstance(timings["test_stage"], int)
    assert timings["test_stage"] >= 0


# ---------------------------------------------------------------------------
# Test 8 — UTC timestamp helper produces ISO 8601 Z suffix
# ---------------------------------------------------------------------------


def test_utc_now_iso_ends_with_z(bench_module):
    """_utc_now_iso() returns ISO 8601 with 'Z' suffix (not '+00:00')."""
    ts = bench_module._utc_now_iso()
    assert ts.endswith("Z")
    assert "+00:00" not in ts
    # Round-trips
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt is not None

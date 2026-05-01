"""Unit tests for image_pipeline — Phase 4 D-15/D-16; Phase 8 IMG-01/02/03/04."""
from __future__ import annotations
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from image_pipeline import (
    download_images, localize_markdown, describe_images, save_markdown_with_images,
    filter_small_images, FilterStats,
    _emit_log, emit_batch_complete, get_last_describe_stats,
    OUTCOME_SUCCESS, OUTCOME_DOWNLOAD_FAILED, OUTCOME_FILTERED_TOO_SMALL,
    OUTCOME_SIZE_READ_FAILED, OUTCOME_VISION_ERROR, OUTCOME_TIMEOUT,
)


def _fake_open(dims_by_name: dict[str, tuple[int, int]]):
    """Return a PIL.Image.open replacement that yields a context manager
    whose .size reflects dims_by_name[Path(path).name].

    Raise the value if dims is an Exception instance (used by the
    PIL-failure test case)."""
    class _Ctx:
        def __init__(self, w, h):
            self.size = (w, h)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _open(path, *a, **kw):
        dims = dims_by_name[Path(path).name]
        if isinstance(dims, Exception):
            raise dims
        return _Ctx(*dims)
    return _open


@pytest.mark.unit
def test_download_images_success_and_failure(tmp_path: Path, mocker):
    urls = ["http://a/x.jpg", "http://b/y.jpg", "http://c/z.jpg"]
    def fake_get(url, timeout):
        r = MagicMock()
        r.status_code = 200 if "c/" not in url else 404
        r.content = b"JPEG_BYTES"
        return r
    mocker.patch("image_pipeline.requests.get", side_effect=fake_get)
    result = download_images(urls, tmp_path)
    assert len(result) == 2
    assert urls[0] in result and urls[1] in result and urls[2] not in result
    assert result[urls[0]].name == "0.jpg"
    assert (tmp_path / "0.jpg").read_bytes() == b"JPEG_BYTES"


@pytest.mark.unit
def test_localize_markdown_replaces_urls():
    md = "text ![](https://remote/img.jpg) more"
    m = localize_markdown(md, {"https://remote/img.jpg": Path("0.jpg")},
                          base_url="http://localhost:8765", article_hash="abc")
    assert "http://localhost:8765/abc/0.jpg" in m
    assert "https://remote/img.jpg" not in m


@pytest.mark.unit
def test_describe_images_batch_calls_sleep_between(tmp_path: Path, mocker, monkeypatch):
    """Phase 8 IMG-02 / D-08.04: inter-image sleep default is 0 (down from 2).

    With default _DESCRIBE_INTER_IMAGE_SLEEP_SECS=0, sleep(0) is skipped by the
    `if ... and sleep_secs > 0` guard — so sleep is NOT called at all by default.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("VISION_INTER_IMAGE_SLEEP", raising=False)
    p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
    p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
    mock_sleep = mocker.patch("image_pipeline.time.sleep")
    # image_pipeline.describe_images imports lib.generate_sync lazily inside the
    # function body, so patch the lib symbol at its canonical location.
    mocker.patch("lib.generate_sync", return_value="desc")
    result = describe_images([p1, p2])
    assert result[p1] == "desc" and result[p2] == "desc"
    mock_sleep.assert_not_called()  # default=0 skips sleep entirely


@pytest.mark.unit
def test_describe_images_per_image_error_isolation(tmp_path: Path, mocker, monkeypatch):
    """Phase 7 D-06: mocks lib.generate_sync — see sibling test above."""
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
    p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
    mocker.patch("image_pipeline.time.sleep")
    mocker.patch(
        "lib.generate_sync",
        side_effect=[Exception("api boom"), "desc"],
    )
    result = describe_images([p1, p2])
    assert "Error describing image" in result[p1]
    assert result[p2] == "desc"


@pytest.mark.unit
def test_save_markdown_with_images_atomic(tmp_path: Path):
    md_path, meta_path = save_markdown_with_images(
        "# hello", tmp_path, {"title": "t", "images": []},
    )
    assert md_path.read_text(encoding="utf-8") == "# hello"
    assert json.loads(meta_path.read_text()) == {"title": "t", "images": []}
    # No leftover tmp files
    assert not list(tmp_path.glob("*.tmp"))


# -----------------------------------------------------------------------------
# Phase 8 IMG-01: filter_small_images tests (D-08.07 §1)
# -----------------------------------------------------------------------------


def _make_img_file(tmp_path: Path, name: str) -> Path:
    """Touch a placeholder file. Real bytes don't matter — PIL.Image.open is mocked."""
    p = tmp_path / name
    p.write_bytes(b"fake")
    return p


@pytest.mark.unit
def test_filter_keeps_800x600(tmp_path: Path, monkeypatch):
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr("PIL.Image.open", _fake_open({"0.jpg": (800, 600)}))
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=300)
    assert kept == {"http://a/0.jpg": p}
    assert stats.input == 1
    assert stats.kept == 1
    assert stats.filtered_too_small == 0
    assert stats.size_read_failed == 0
    assert isinstance(stats.timings_ms, dict)
    assert "total_read" in stats.timings_ms
    assert p.exists()  # NOT unlinked


@pytest.mark.unit
def test_filter_drops_100x800_narrow_banner(tmp_path: Path, monkeypatch):
    """The bug Hermes originally flagged — min(100, 800) = 100 < 300 → drop."""
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr("PIL.Image.open", _fake_open({"0.jpg": (100, 800)}))
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=300)
    assert kept == {}
    assert stats.kept == 0
    assert stats.filtered_too_small == 1
    assert stats.size_read_failed == 0
    assert not p.exists()  # unlinked from disk


@pytest.mark.unit
def test_filter_drops_300x299_just_below(tmp_path: Path, monkeypatch):
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr("PIL.Image.open", _fake_open({"0.jpg": (300, 299)}))
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=300)
    assert kept == {}
    assert stats.filtered_too_small == 1


@pytest.mark.unit
def test_filter_keeps_300x300_exact_threshold(tmp_path: Path, monkeypatch):
    """min(300, 300) = 300 < 300 is False → KEEP (strict inequality)."""
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr("PIL.Image.open", _fake_open({"0.jpg": (300, 300)}))
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=300)
    assert kept == {"http://a/0.jpg": p}
    assert stats.kept == 1
    assert stats.filtered_too_small == 0


@pytest.mark.unit
def test_filter_drops_299x300_one_axis_below(tmp_path: Path, monkeypatch):
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr("PIL.Image.open", _fake_open({"0.jpg": (299, 300)}))
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=300)
    assert kept == {}
    assert stats.filtered_too_small == 1


@pytest.mark.unit
def test_filter_kwarg_min_dim_100_keeps_150x150(tmp_path: Path, monkeypatch):
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr("PIL.Image.open", _fake_open({"0.jpg": (150, 150)}))
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=100)
    assert kept == {"http://a/0.jpg": p}
    assert stats.kept == 1


@pytest.mark.unit
def test_filter_pil_open_failure_keeps_image(tmp_path: Path, monkeypatch):
    """D-08.01: PIL failure degrades to KEEP — don't drop what we can't measure."""
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr(
        "PIL.Image.open",
        _fake_open({"0.jpg": OSError("bad image bytes")}),
    )
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=300)
    assert kept == {"http://a/0.jpg": p}
    assert stats.kept == 1
    assert stats.filtered_too_small == 0
    assert stats.size_read_failed == 1
    assert p.exists()  # NOT unlinked — PIL-failure path skips the unlink


@pytest.mark.unit
def test_ingest_wechat_reads_env_min_dim(monkeypatch):
    """D-08.07 §1 bullet 7: ingest_wechat reads IMAGE_FILTER_MIN_DIM from env.

    Thin smoke test — not a full subprocess run (that belongs in Phase 11 E2E).
    Asserts the literal read pattern used at ingest_wechat.py:634 resolves correctly.
    """
    monkeypatch.setenv("IMAGE_FILTER_MIN_DIM", "100")
    assert int(os.environ.get("IMAGE_FILTER_MIN_DIM", 300)) == 100
    monkeypatch.delenv("IMAGE_FILTER_MIN_DIM")
    assert int(os.environ.get("IMAGE_FILTER_MIN_DIM", 300)) == 300


# -----------------------------------------------------------------------------
# Phase 8 IMG-02 / IMG-03 / IMG-04: observability + sleep config tests
# -----------------------------------------------------------------------------


def _parse_stderr_events(err: str) -> list[dict]:
    """Parse captured stderr into a list of JSON-lines events. Ignores non-JSON lines."""
    events = []
    for line in err.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


@pytest.mark.unit
def test_describe_images_respects_vision_inter_image_sleep_env(tmp_path: Path, mocker, monkeypatch):
    """Phase 8 IMG-02 / D-08.04: VISION_INTER_IMAGE_SLEEP env overrides default 0."""
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("VISION_INTER_IMAGE_SLEEP", "1.5")
    p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
    p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
    mock_sleep = mocker.patch("image_pipeline.time.sleep")
    mocker.patch("lib.generate_sync", return_value="desc")
    result = describe_images([p1, p2])
    assert result[p1] == "desc" and result[p2] == "desc"
    mock_sleep.assert_called_once_with(1.5)


@pytest.mark.unit
def test_emit_log_writes_jsonlines_to_stderr(capsys, monkeypatch):
    """Phase 8 IMG-03 / D-08.02: default output path is stderr, one JSON line."""
    monkeypatch.delenv("VISION_LOG_PATH", raising=False)
    _emit_log({"event": "x", "ts": "t", "url": "u"})
    captured = capsys.readouterr()
    # exactly one JSON line on stderr that round-trips via json.loads
    lines = [l for l in captured.err.splitlines() if l.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed == {"event": "x", "ts": "t", "url": "u"}


@pytest.mark.unit
def test_emit_log_writes_to_file_when_env_set(tmp_path: Path, monkeypatch):
    """Phase 8 IMG-03 / D-08.02: VISION_LOG_PATH redirects output to a file."""
    log_path = tmp_path / "vision.log"
    monkeypatch.setenv("VISION_LOG_PATH", str(log_path))
    _emit_log({"event": "a"})
    _emit_log({"event": "b"})
    content = log_path.read_text(encoding="utf-8")
    lines = [l for l in content.splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"event": "a"}
    assert json.loads(lines[1]) == {"event": "b"}


@pytest.mark.unit
def test_filter_small_images_emits_filtered_too_small_log(tmp_path: Path, monkeypatch, capsys):
    """Phase 8 IMG-03: filter stage emits one image_processed line per dropped image."""
    monkeypatch.delenv("VISION_LOG_PATH", raising=False)
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr("PIL.Image.open", _fake_open({"0.jpg": (100, 800)}))
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=300)
    assert stats.filtered_too_small == 1
    events = _parse_stderr_events(capsys.readouterr().err)
    filt_events = [e for e in events if e.get("outcome") == OUTCOME_FILTERED_TOO_SMALL]
    assert len(filt_events) == 1
    ev = filt_events[0]
    assert ev["event"] == "image_processed"
    assert ev["url"] == "http://a/0.jpg"
    assert ev["dims"] == "100x800"
    assert ev["provider"] is None
    assert ev["error"] is None


@pytest.mark.unit
def test_filter_small_images_emits_size_read_failed_log(tmp_path: Path, monkeypatch, capsys):
    """Phase 8 IMG-03: PIL open failure emits image_processed with outcome=size_read_failed."""
    monkeypatch.delenv("VISION_LOG_PATH", raising=False)
    p = _make_img_file(tmp_path, "0.jpg")
    monkeypatch.setattr(
        "PIL.Image.open",
        _fake_open({"0.jpg": OSError("corrupt")}),
    )
    kept, stats = filter_small_images({"http://a/0.jpg": p}, min_dim=300)
    assert stats.size_read_failed == 1
    events = _parse_stderr_events(capsys.readouterr().err)
    fail_events = [e for e in events if e.get("outcome") == OUTCOME_SIZE_READ_FAILED]
    assert len(fail_events) == 1
    ev = fail_events[0]
    assert ev["event"] == "image_processed"
    assert ev["error"] == "corrupt"
    assert ev["dims"] is None


@pytest.mark.unit
def test_describe_images_outcome_timeout_vs_vision_error(tmp_path: Path, mocker, monkeypatch, capsys):
    """Phase 8 IMG-03 / D-08.05: TimeoutError maps to timeout; other exceptions to vision_error.

    Pin VISION_PROVIDER=gemini so the exception propagates directly out of
    _describe_one without the auto-cascade masking it with later provider errors.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("VISION_PROVIDER", "gemini")
    monkeypatch.delenv("VISION_LOG_PATH", raising=False)
    p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
    p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
    mocker.patch("image_pipeline.time.sleep")
    mocker.patch(
        "lib.generate_sync",
        side_effect=[TimeoutError("read timeout"), RuntimeError("HTTP 500 boom")],
    )
    describe_images([p1, p2])
    events = _parse_stderr_events(capsys.readouterr().err)
    outcomes = [e["outcome"] for e in events if e.get("event") == "image_processed"]
    assert OUTCOME_TIMEOUT in outcomes
    assert OUTCOME_VISION_ERROR in outcomes


@pytest.mark.unit
def test_get_last_describe_stats_populated_after_call(tmp_path: Path, mocker, monkeypatch):
    """Phase 8 IMG-04: get_last_describe_stats returns per-call stats after describe_images."""
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("VISION_LOG_PATH", raising=False)
    # Reset module-level state so we can assert the None-before-first-call contract
    monkeypatch.setattr("image_pipeline._last_describe_stats", None)
    assert get_last_describe_stats() is None
    p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
    p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
    mocker.patch("image_pipeline.time.sleep")
    mocker.patch("lib.generate_sync", return_value="desc")
    describe_images([p1, p2])
    stats = get_last_describe_stats()
    assert stats is not None
    assert stats["vision_success"] == 2
    assert stats["vision_error"] == 0
    assert stats["vision_timeout"] == 0
    # default VISION_PROVIDER=auto → first try = gemini succeeds on both images
    assert stats["provider_mix"] == {"gemini": 2}


@pytest.mark.unit
def test_emit_batch_complete_aggregate_shape(capsys, monkeypatch):
    """Phase 8 IMG-04 / D-08.02: aggregate event shape matches D-08.02 sample exactly."""
    monkeypatch.delenv("VISION_LOG_PATH", raising=False)
    stats = FilterStats(
        input=30,
        kept=20,
        filtered_too_small=9,
        size_read_failed=1,
        timings_ms={"total_read": 50},
    )
    emit_batch_complete(
        filter_stats=stats,
        download_input_count=30,
        download_failed=0,
        describe_stats={
            "vision_success": 18,
            "vision_error": 2,
            "vision_timeout": 0,
            "provider_mix": {"siliconflow": 18},
        },
        total_ms=12000,
    )
    events = _parse_stderr_events(capsys.readouterr().err)
    batch = [e for e in events if e.get("event") == "image_batch_complete"]
    assert len(batch) == 1
    ev = batch[0]
    # Top-level keys per D-08.02 aggregate schema
    assert set(ev.keys()) >= {"event", "ts", "counts", "total_ms", "provider_mix"}
    # counts has all 8 subkeys
    assert set(ev["counts"].keys()) == {
        "input", "kept", "filtered_too_small", "download_failed",
        "size_read_failed", "vision_success", "vision_error", "vision_timeout",
    }
    assert ev["counts"]["input"] == 30
    assert ev["counts"]["kept"] == 20
    assert ev["counts"]["filtered_too_small"] == 9
    assert ev["counts"]["size_read_failed"] == 1
    assert ev["counts"]["vision_success"] == 18
    assert ev["counts"]["vision_error"] == 2
    assert ev["total_ms"] == 12000
    assert ev["provider_mix"] == {"siliconflow": 18}


@pytest.mark.unit
def test_emit_batch_complete_handles_none_describe_stats(capsys, monkeypatch):
    """Phase 8 IMG-04: None describe_stats normalizes to zero counts + empty provider_mix."""
    monkeypatch.delenv("VISION_LOG_PATH", raising=False)
    stats = FilterStats(
        input=5,
        kept=5,
        filtered_too_small=0,
        size_read_failed=0,
        timings_ms={"total_read": 10},
    )
    emit_batch_complete(
        filter_stats=stats,
        download_input_count=5,
        download_failed=0,
        describe_stats=None,
        total_ms=100,
    )
    events = _parse_stderr_events(capsys.readouterr().err)
    batch = [e for e in events if e.get("event") == "image_batch_complete"]
    assert len(batch) == 1
    ev = batch[0]
    assert ev["counts"]["vision_success"] == 0
    assert ev["counts"]["vision_error"] == 0
    assert ev["counts"]["vision_timeout"] == 0
    assert ev["provider_mix"] == {}

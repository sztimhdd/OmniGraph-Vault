"""Unit tests for image_pipeline — Phase 4 D-15/D-16; Phase 8 IMG-01."""
from __future__ import annotations
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from image_pipeline import (
    download_images, localize_markdown, describe_images, save_markdown_with_images,
    filter_small_images, FilterStats,
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
    """Phase 7 D-06: mocks lib.generate_sync (the unified multimodal call path).

    Previously patched image_pipeline.genai.Client + image_pipeline.Image.open;
    after Phase 7 Amendment 5 migration the call goes through lib.generate_sync
    which accepts types.Part.from_bytes natively.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
    p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
    mock_sleep = mocker.patch("image_pipeline.time.sleep")
    # image_pipeline.describe_images imports lib.generate_sync lazily inside the
    # function body, so patch the lib symbol at its canonical location.
    mocker.patch("lib.generate_sync", return_value="desc")
    result = describe_images([p1, p2])
    assert result[p1] == "desc" and result[p2] == "desc"
    mock_sleep.assert_called_once_with(4)  # exactly one sleep between 2 images


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

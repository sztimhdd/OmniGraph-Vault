"""Unit tests for image_pipeline — Phase 4 D-15/D-16."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from image_pipeline import (
    download_images, localize_markdown, describe_images, save_markdown_with_images,
)


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
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
    p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
    mock_sleep = mocker.patch("image_pipeline.time.sleep")
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value.text = "desc"
    mocker.patch("image_pipeline.genai.Client", return_value=mock_client)
    mocker.patch("image_pipeline.Image.open", return_value=MagicMock())
    result = describe_images([p1, p2])
    assert result[p1] == "desc" and result[p2] == "desc"
    mock_sleep.assert_called_once_with(4)  # exactly one sleep between 2 images


@pytest.mark.unit
def test_describe_images_per_image_error_isolation(tmp_path: Path, mocker, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
    p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
    mocker.patch("image_pipeline.time.sleep")
    client = MagicMock()
    r_ok = MagicMock(); r_ok.text = "desc"
    client.models.generate_content.side_effect = [Exception("api boom"), r_ok]
    mocker.patch("image_pipeline.genai.Client", return_value=client)
    mocker.patch("image_pipeline.Image.open", return_value=MagicMock())
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

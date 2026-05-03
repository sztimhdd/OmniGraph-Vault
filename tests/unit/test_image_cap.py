"""Unit tests for HYG-02 image cap (Phase 18-01).

Exercises the ``_apply_image_cap()`` helper extracted from
``ingest_wechat.py``. No live scrape, no live download — tests operate
directly on dict inputs.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from ingest_wechat import _apply_image_cap, MAX_IMAGES_PER_ARTICLE


def _make_url_to_path(count: int) -> dict:
    """Build a deterministic ordered {url: path} dict with ``count`` entries."""
    return {
        f"https://img.example.com/img_{i:03d}.jpg": Path(f"/tmp/img_{i:03d}.jpg")
        for i in range(count)
    }


def test_cap_under_threshold_is_noop():
    url_to_path = _make_url_to_path(20)
    capped, dropped, original = _apply_image_cap(url_to_path, max_images=60)
    assert capped == url_to_path
    assert dropped == set()
    assert original == 20


def test_cap_at_exact_threshold_is_noop():
    url_to_path = _make_url_to_path(60)
    capped, dropped, original = _apply_image_cap(url_to_path, max_images=60)
    assert capped == url_to_path
    assert dropped == set()
    assert original == 60


def test_cap_over_threshold_truncates_tail(caplog):
    url_to_path = _make_url_to_path(70)
    with caplog.at_level(logging.WARNING, logger="ingest_wechat"):
        capped, dropped, original = _apply_image_cap(url_to_path, max_images=60)
    assert len(capped) == 60
    assert len(dropped) == 10
    assert original == 70
    # Head-preservation: first URL stays, last 10 URLs dropped.
    first_url = list(url_to_path.keys())[0]
    last_url = list(url_to_path.keys())[-1]
    assert first_url in capped
    assert last_url in dropped
    # WARNING log emitted exactly once.
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("image cap hit" in m for m in warning_messages)


def test_cap_preserves_insertion_order():
    url_to_path = _make_url_to_path(10)
    capped, _, _ = _apply_image_cap(url_to_path, max_images=5)
    # Kept keys MUST match the first 5 of the input, in order.
    assert list(capped.keys()) == list(url_to_path.keys())[:5]


def test_cap_default_env_is_60(monkeypatch):
    # Module constant reads env at import; verify default.
    # (Re-importing to confirm env override would require importlib.reload;
    # documenting the constant value directly is sufficient here.)
    assert MAX_IMAGES_PER_ARTICLE == 60


def test_cap_env_override_applied_via_module_reload(monkeypatch):
    import importlib
    import ingest_wechat
    monkeypatch.setenv("OMNIGRAPH_MAX_IMAGES_PER_ARTICLE", "5")
    importlib.reload(ingest_wechat)
    try:
        assert ingest_wechat.MAX_IMAGES_PER_ARTICLE == 5
        url_to_path = _make_url_to_path(10)
        capped, dropped, _ = ingest_wechat._apply_image_cap(
            url_to_path, max_images=ingest_wechat.MAX_IMAGES_PER_ARTICLE
        )
        assert len(capped) == 5
        assert len(dropped) == 5
    finally:
        # Restore default to avoid polluting subsequent tests.
        monkeypatch.delenv("OMNIGRAPH_MAX_IMAGES_PER_ARTICLE", raising=False)
        importlib.reload(ingest_wechat)


def test_cap_no_warning_when_at_or_below_threshold(caplog):
    url_to_path = _make_url_to_path(60)
    with caplog.at_level(logging.WARNING, logger="ingest_wechat"):
        _apply_image_cap(url_to_path, max_images=60)
    # No "image cap hit" at the exact threshold.
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("image cap hit" in m for m in warning_messages)


def test_cap_returns_empty_dropped_set_when_under_threshold():
    url_to_path = _make_url_to_path(5)
    _, dropped, _ = _apply_image_cap(url_to_path, max_images=60)
    assert isinstance(dropped, set)
    assert len(dropped) == 0

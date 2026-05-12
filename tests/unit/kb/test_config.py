"""Tests for kb.config — env-driven configuration constants (CONFIG-01).

Each test reloads `kb.config` after monkeypatching the relevant env var so
that the module-level constants are recomputed for the test scope. This
mirrors the pattern documented in the plan's behavior section and confirms
that callers can override defaults at any time via `importlib.reload`.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _reload_config():
    """Import then reload kb.config so that env var changes take effect."""
    import kb.config as cfg

    return importlib.reload(cfg)


def test_kb_db_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_DB_PATH", raising=False)
    cfg = _reload_config()
    assert cfg.KB_DB_PATH == Path.home() / ".hermes" / "data" / "kol_scan.db"


def test_kb_db_path_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "custom.db"
    monkeypatch.setenv("KB_DB_PATH", str(target))
    cfg = _reload_config()
    assert cfg.KB_DB_PATH == target


def test_kb_images_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_IMAGES_DIR", raising=False)
    cfg = _reload_config()
    # 'omonigraph' typo is canonical per CLAUDE.md — do not "fix" it.
    assert cfg.KB_IMAGES_DIR == Path.home() / ".hermes" / "omonigraph-vault" / "images"


def test_kb_output_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_OUTPUT_DIR", raising=False)
    cfg = _reload_config()
    assert cfg.KB_OUTPUT_DIR == Path("kb/output")


def test_kb_port_default_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_PORT", raising=False)
    cfg = _reload_config()
    assert cfg.KB_PORT == 8766
    assert isinstance(cfg.KB_PORT, int)

    monkeypatch.setenv("KB_PORT", "9999")
    cfg = _reload_config()
    assert cfg.KB_PORT == 9999
    assert isinstance(cfg.KB_PORT, int)


def test_kb_default_lang_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_DEFAULT_LANG", raising=False)
    cfg = _reload_config()
    assert cfg.KB_DEFAULT_LANG == "zh-CN"


def test_kb_synthesize_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KB_SYNTHESIZE_TIMEOUT", raising=False)
    cfg = _reload_config()
    assert cfg.KB_SYNTHESIZE_TIMEOUT == 60
    assert isinstance(cfg.KB_SYNTHESIZE_TIMEOUT, int)


def test_all_constants_re_read_env_on_reload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """All 6 constants must be re-read on `importlib.reload(kb.config)` —
    confirms no module-load-time caching that would prevent env override
    after first import.
    """
    db = tmp_path / "alt.db"
    images = tmp_path / "alt-images"
    output = tmp_path / "alt-output"
    monkeypatch.setenv("KB_DB_PATH", str(db))
    monkeypatch.setenv("KB_IMAGES_DIR", str(images))
    monkeypatch.setenv("KB_OUTPUT_DIR", str(output))
    monkeypatch.setenv("KB_PORT", "7000")
    monkeypatch.setenv("KB_DEFAULT_LANG", "en")
    monkeypatch.setenv("KB_SYNTHESIZE_TIMEOUT", "120")

    cfg = _reload_config()
    assert cfg.KB_DB_PATH == db
    assert cfg.KB_IMAGES_DIR == images
    assert cfg.KB_OUTPUT_DIR == output
    assert cfg.KB_PORT == 7000
    assert cfg.KB_DEFAULT_LANG == "en"
    assert cfg.KB_SYNTHESIZE_TIMEOUT == 120

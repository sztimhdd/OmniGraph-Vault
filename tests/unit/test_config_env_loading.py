"""Regression tests for the opt-out of config.py's Hermes env-file loading."""
from __future__ import annotations

import builtins
import os
import runpy
from pathlib import Path

import pytest


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.py"


def _write_env(home: Path, contents: str) -> None:
    env_path = home / ".hermes" / ".env"
    env_path.parent.mkdir()
    env_path.write_text(contents, encoding="utf-8")


def _load_config(monkeypatch: pytest.MonkeyPatch, home: Path) -> dict[str, object]:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return runpy.run_path(str(CONFIG_PATH))


def test_default_loads_env_file_from_isolated_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Removing the switch preserves the legacy env-file load at module import."""
    sentinel = "VX004_DEFAULT_ENV_SENTINEL"
    monkeypatch.delenv("OMNIGRAPH_LOAD_ENV", raising=False)
    monkeypatch.delenv(sentinel, raising=False)
    _write_env(tmp_path, f"{sentinel}=loaded-from-fake-env\n")

    _load_config(monkeypatch, tmp_path)

    assert os.environ[sentinel] == "loaded-from-fake-env"


def test_zero_disables_env_file_checks_for_import_and_explicit_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A disabled switch must prevent both import and later load_env() file access."""
    monkeypatch.setenv("OMNIGRAPH_LOAD_ENV", "0")

    def fail_file_access(*args: object, **kwargs: object) -> object:
        raise AssertionError("env file access must be disabled")

    monkeypatch.setattr(os.path, "exists", fail_file_access)
    monkeypatch.setattr(builtins, "open", fail_file_access)

    namespace = _load_config(monkeypatch, tmp_path)
    namespace["load_env"]()


def test_existing_environment_value_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The env file remains a fallback and cannot replace a caller's value."""
    sentinel = "VX004_EXISTING_ENV_SENTINEL"
    monkeypatch.delenv("OMNIGRAPH_LOAD_ENV", raising=False)
    monkeypatch.setenv(sentinel, "caller-value")
    _write_env(tmp_path, f"{sentinel}=file-value\n")

    _load_config(monkeypatch, tmp_path)

    assert os.environ[sentinel] == "caller-value"


def test_invalid_env_loading_switch_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Misspelled switch values fail before config can consult an env file."""
    monkeypatch.setenv("OMNIGRAPH_LOAD_ENV", "disabled")

    def fail_file_access(*args: object, **kwargs: object) -> object:
        raise AssertionError("invalid switch must fail before env file access")

    monkeypatch.setattr(os.path, "exists", fail_file_access)
    monkeypatch.setattr(builtins, "open", fail_file_access)

    with pytest.raises(ValueError, match="OMNIGRAPH_LOAD_ENV.*'0'.*'1'"):
        _load_config(monkeypatch, tmp_path)

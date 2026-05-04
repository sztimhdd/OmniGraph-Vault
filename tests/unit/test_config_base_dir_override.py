"""Unit tests for config.BASE_DIR with OMNIGRAPH_BASE_DIR override (LDEV-05).

Uses a subprocess per test so config.py is re-imported cleanly without
cross-test pollution — config has module-level env-loading side effects.
No network, no filesystem writes outside the current repo.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_config_print(extra_env: dict[str, str], attr: str = "BASE_DIR") -> str:
    """Run ``python -c 'import config; print(config.<attr>)'`` in a fresh
    subprocess with the given env overlay and return the printed line.

    The subprocess inherits the parent's env EXCEPT for keys listed in
    extra_env with value ``""`` — those are treated as "unset" and popped.
    DEEPSEEK_API_KEY=dummy is always set so lib imports don't fail.
    """
    env = dict(os.environ)
    env.setdefault("DEEPSEEK_API_KEY", "dummy-for-tests")
    for k, v in extra_env.items():
        if v == "__UNSET__":
            env.pop(k, None)
        else:
            env[k] = v
    # Force stdout to utf-8 so the paths print cleanly on Windows.
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", f"import config; print(config.{attr})"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_env_unset_defaults_to_hermes() -> None:
    """OMNIGRAPH_BASE_DIR unset → path ends with .hermes/omonigraph-vault."""
    out = _run_config_print({"OMNIGRAPH_BASE_DIR": "__UNSET__"})
    # Accept both native path separators — use forward-slash normalization.
    normalized = out.replace("\\", "/")
    assert normalized.endswith(".hermes/omonigraph-vault"), out


def test_env_empty_string_falls_back_to_default() -> None:
    """OMNIGRAPH_BASE_DIR='' treats empty as unset; Hermes default is used."""
    out = _run_config_print({"OMNIGRAPH_BASE_DIR": ""})
    normalized = out.replace("\\", "/")
    assert normalized.endswith(".hermes/omonigraph-vault"), out


def test_env_set_absolute_path_wins(tmp_path: Path) -> None:
    """OMNIGRAPH_BASE_DIR=<abs-path> → BASE_DIR equals that path."""
    target = tmp_path / "fake-runtime"
    target.mkdir()
    out = _run_config_print({"OMNIGRAPH_BASE_DIR": str(target)})
    assert out == str(target), (out, str(target))


def test_dependent_paths_inherit(tmp_path: Path) -> None:
    """BASE_IMAGE_DIR and CANONICAL_MAP_FILE derive from the overridden BASE_DIR."""
    target = tmp_path / "inherit-root"
    target.mkdir()
    env = {"OMNIGRAPH_BASE_DIR": str(target)}

    img = _run_config_print(env, attr="BASE_IMAGE_DIR")
    canon = _run_config_print(env, attr="CANONICAL_MAP_FILE")

    # BASE_IMAGE_DIR = BASE_DIR / "images"
    assert Path(img) == target / "images", (img, target / "images")
    # CANONICAL_MAP_FILE = BASE_DIR / "canonical_map.json"
    assert Path(canon) == target / "canonical_map.json", (canon, target / "canonical_map.json")

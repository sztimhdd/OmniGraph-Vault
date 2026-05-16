"""Shared pytest fixtures for databricks-deploy unit tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_volume_root(tmp_path: Path) -> Path:
    """Synthetic VOLUME_ROOT fixture.

    Returns a tmp_path-rooted directory with a `lightrag_storage/` sub-dir
    pre-created (mirrors the kdb-1 STORAGE-DBX-03 layout).
    """
    vol = tmp_path / "vol"
    (vol / "lightrag_storage").mkdir(parents=True)
    return vol


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """Synthetic TMP_ROOT fixture (writable destination)."""
    return tmp_path / "tmp_omnigraph_vault"

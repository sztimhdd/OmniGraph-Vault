"""Unit tests for databricks-deploy/startup_adapter.py.

Tests follow the Testing Trophy: these are unit tests with monkeypatched
filesystem boundaries (NOT integration tests). The Databricks SDK is mocked
via unittest.mock.MagicMock so the test suite does not require databricks-sdk
to be installed in the dev venv.

Coverage:
    1. test_hydrate_skipped_when_source_empty
    2. test_hydrate_copies_via_fuse_when_source_populated
    3. test_hydrate_idempotent_skip_on_repeat
    4. test_hydrate_falls_back_to_sdk_when_fuse_unavailable
    5. test_raises_when_tmp_not_writable
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make the databricks-deploy/ dir importable so `import startup_adapter` works
# regardless of how pytest is invoked.
_DEPLOY_DIR = Path(__file__).resolve().parent.parent
if str(_DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOY_DIR))

import startup_adapter  # noqa: E402  -- import after sys.path mutation


def _write_file(path: Path, n_bytes: int) -> None:
    """Write `n_bytes` of fixed content to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * n_bytes)


# ---------------------------------------------------------------------------
# Test 1 — empty-source pre-seed case
# ---------------------------------------------------------------------------


def test_hydrate_skipped_when_source_empty(
    tmp_volume_root: Path,
    tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """src/lightrag_storage exists but is empty -> source_empty_pre_seed skip."""
    # source `lightrag_storage/` already created by fixture, no files inside
    result = startup_adapter.hydrate_lightrag_storage_from_volume(
        volume_root=str(tmp_volume_root),
        tmp_root=str(tmp_root),
    )

    assert isinstance(result, startup_adapter.CopyResult)
    assert result.status == "skipped"
    assert result.reason == "source_empty_pre_seed"
    assert result.method is None
    # dst dir was created (mkdir parents=True, exist_ok=True succeeded)
    assert (tmp_root / "lightrag_storage").exists()
    # but no files inside dst
    assert list((tmp_root / "lightrag_storage").iterdir()) == []


# ---------------------------------------------------------------------------
# Test 2 — FUSE primary copy path
# ---------------------------------------------------------------------------


def test_hydrate_copies_via_fuse_when_source_populated(
    tmp_volume_root: Path,
    tmp_root: Path,
) -> None:
    """src non-empty -> shutil.copytree FUSE path; CopyResult records bytes."""
    src = tmp_volume_root / "lightrag_storage"
    _write_file(src / "vdb_chunks.json", 1024)
    _write_file(src / "graph_chunk_entity_relation.graphml", 2048)
    _write_file(src / "kv_store_full_docs.json", 3072)

    result = startup_adapter.hydrate_lightrag_storage_from_volume(
        volume_root=str(tmp_volume_root),
        tmp_root=str(tmp_root),
    )

    assert result.status == "copied"
    assert result.method == "fuse"
    assert result.elapsed_s is not None
    assert result.elapsed_s >= 0.0
    assert result.bytes_copied == 1024 + 2048 + 3072

    dst = tmp_root / "lightrag_storage"
    assert (dst / "vdb_chunks.json").read_bytes() == b"x" * 1024
    assert (dst / "graph_chunk_entity_relation.graphml").read_bytes() == b"x" * 2048
    assert (dst / "kv_store_full_docs.json").read_bytes() == b"x" * 3072


# ---------------------------------------------------------------------------
# Test 3 — idempotency on second call
# ---------------------------------------------------------------------------


def test_hydrate_idempotent_skip_on_repeat(
    tmp_volume_root: Path,
    tmp_root: Path,
) -> None:
    """Second call to hydrate skips because dst is already populated."""
    src = tmp_volume_root / "lightrag_storage"
    _write_file(src / "vdb_chunks.json", 512)

    first = startup_adapter.hydrate_lightrag_storage_from_volume(
        volume_root=str(tmp_volume_root),
        tmp_root=str(tmp_root),
    )
    assert first.status == "copied"

    second = startup_adapter.hydrate_lightrag_storage_from_volume(
        volume_root=str(tmp_volume_root),
        tmp_root=str(tmp_root),
    )
    assert second.status == "skipped"
    assert second.reason == "already_hydrated"
    assert second.method is None


# ---------------------------------------------------------------------------
# Test 4 — SDK fallback when FUSE unavailable
# ---------------------------------------------------------------------------


def test_hydrate_falls_back_to_sdk_when_fuse_unavailable(
    tmp_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Volume not mounted, src does not exist locally -> SDK fallback path."""
    # volume_root that does not exist locally and is not a mount point
    fake_volume = tmp_path / "no-such-volume"

    # Simulate mock SDK module: WorkspaceClient().files.download_directory(src, dst)
    # writes a fake file into dst so the bytes_copied compute path has data.
    def fake_download_directory(src_str: str, dst_str: str, overwrite: bool = True) -> None:
        dst_p = Path(dst_str)
        dst_p.mkdir(parents=True, exist_ok=True)
        (dst_p / "sdk_marker.json").write_bytes(b"sdk-payload")

    mock_files = MagicMock()
    mock_files.download_directory.side_effect = fake_download_directory
    mock_client = MagicMock()
    mock_client.files = mock_files
    mock_workspace_client_cls = MagicMock(return_value=mock_client)

    # Inject a fake `databricks.sdk` module so the lazy `from databricks.sdk
    # import WorkspaceClient` inside the adapter resolves to our mock.
    fake_sdk_module = MagicMock()
    fake_sdk_module.WorkspaceClient = mock_workspace_client_cls
    fake_databricks_pkg = MagicMock()
    fake_databricks_pkg.sdk = fake_sdk_module
    monkeypatch.setitem(sys.modules, "databricks", fake_databricks_pkg)
    monkeypatch.setitem(sys.modules, "databricks.sdk", fake_sdk_module)

    # Force ismount False so the FUSE branch's `or src.exists()` is the only gate;
    # since src doesn't exist locally, the FUSE branch will be skipped.
    monkeypatch.setattr(os.path, "ismount", lambda _p: False)

    result = startup_adapter.hydrate_lightrag_storage_from_volume(
        volume_root=str(fake_volume),
        tmp_root=str(tmp_root),
    )

    assert result.status == "copied"
    assert result.method == "sdk"
    assert result.elapsed_s is not None
    assert result.bytes_copied == len(b"sdk-payload")
    mock_workspace_client_cls.assert_called_once()
    mock_files.download_directory.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5 — defensive raise when /tmp is not writable
# ---------------------------------------------------------------------------


def test_raises_when_tmp_not_writable(
    tmp_volume_root: Path,
    tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If /tmp is not writable, adapter raises RuntimeError per RESEARCH Risk 5."""

    def fake_access(path: str, mode: int) -> bool:
        if path == "/tmp" and mode == os.W_OK:
            return False
        # other access checks unaffected
        return True

    monkeypatch.setattr(os, "access", fake_access)

    with pytest.raises(RuntimeError, match="/tmp"):
        startup_adapter.hydrate_lightrag_storage_from_volume(
            volume_root=str(tmp_volume_root),
            tmp_root=str(tmp_root),
        )

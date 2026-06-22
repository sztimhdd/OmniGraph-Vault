"""ISSUES #48 behavior pin: aliyun-backup-260610.sh PHASE 0 quiesce probe must
distinguish a hung-but-quiesced ingest service (safe to back up) from a
genuinely-active one (must keep waiting).

The script exposes a `__quiesce_probe <fd_dir> <storage_dir>` seam that runs ONLY
the 3-probe gate (0 real-file fds + 0 *.tmp orphans + parseable graphml) and
exits with its status — no systemctl / Aliyun dependency. These tests drive it
with tmp dirs.

Requires bash (Git Bash on Windows) + networkx (already a venv dependency).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Tracked copy under scripts/ — the .scratch/ original is gitignored and never
# reaches Aliyun via `git pull`, so the deployable quiesce gate lives here.
SCRIPT = REPO_ROOT / "scripts" / "aliyun-backup-260610.sh"

_BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available")


def _write_graphml(storage_dir: Path) -> None:
    """Write a real, parseable graphml at the path the probe checks."""
    import networkx as nx

    g = nx.Graph()
    g.add_node("a")
    g.add_node("b")
    g.add_edge("a", "b")
    nx.write_graphml(g, str(storage_dir / "graph_chunk_entity_relation.graphml"))


def _run_probe(fd_dir: Path, storage_dir: Path) -> int:
    """Invoke the script's __quiesce_probe seam; return its exit status."""
    env = dict(os.environ)
    env["QUIESCE_PY"] = sys.executable  # local venv python (has networkx)
    # POSIX-form paths: bash + the embedded `python -c` string literal both
    # need forward slashes. str(WindowsPath) emits backslashes which break the
    # glob and trip `\U`-style escape errors in the python literal. On Aliyun
    # (Linux) str() == as_posix(), so this is test-harness-only.
    result = subprocess.run(
        [_BASH, str(SCRIPT), "__quiesce_probe", fd_dir.as_posix(), storage_dir.as_posix()],
        capture_output=True,
        timeout=30,
        env=env,
    )
    return result.returncode


@pytest.mark.unit
def test_quiesced_state_passes_gate(tmp_path: Path) -> None:
    """No real-file fds + no .tmp + parseable graphml → probe exits 0 (proceed).

    Mirrors the 2026-06-11 03:48 deep-probe finding: PID 1552490 had 0 fds,
    0 .tmp, graphml parsed 30558/44030 — data safe, backup should proceed."""
    fd_dir = tmp_path / "fd"
    fd_dir.mkdir()  # empty → 0 real fds
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    _write_graphml(storage_dir)

    assert _run_probe(fd_dir, storage_dir) == 0, (
        "quiesced state (0 fds + 0 .tmp + parseable graphml) must pass the gate"
    )


@pytest.mark.unit
def test_active_with_open_fd_blocks_gate(tmp_path: Path) -> None:
    """A real-file fd present → probe exits non-zero (keep waiting)."""
    fd_dir = tmp_path / "fd"
    fd_dir.mkdir()
    (fd_dir / "7").write_text("open file handle")  # one real-file fd
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    _write_graphml(storage_dir)

    assert _run_probe(fd_dir, storage_dir) != 0, (
        "an open real-file fd means I/O may be in flight — must keep waiting"
    )


@pytest.mark.unit
def test_tmp_orphan_blocks_gate(tmp_path: Path) -> None:
    """A .tmp orphan in the storage dir → probe exits non-zero (atomic-write
    rename may be mid-flight; backing up now risks a torn capture)."""
    fd_dir = tmp_path / "fd"
    fd_dir.mkdir()  # 0 real fds
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    _write_graphml(storage_dir)
    (storage_dir / "graph_chunk_entity_relation.graphml.tmp").write_text("partial")

    assert _run_probe(fd_dir, storage_dir) != 0, (
        ".tmp orphan means a write/rename may be in flight — must keep waiting"
    )

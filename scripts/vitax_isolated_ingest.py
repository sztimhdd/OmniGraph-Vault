#!/usr/bin/env python3
"""Create a VX004 offline preflight for one existing fixture.

This module deliberately does not import ``ingest_wechat``, construct a RAG
client, or invoke a model.  It only creates an empty, owned layout and records
the environment and gates a later, separately authorized live exercise needs.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class IsolationError(ValueError):
    """The requested layout could overlap a broad or unowned destination."""


@dataclass(frozen=True)
class OfflineIngestPlan:
    fixture_dir: Path
    run_dir: Path
    base_dir: Path
    rag_dir: Path
    environment: Mapping[str, str]
    execution_mode: str
    required_live_gates: str


def _validated_fixture(fixture_dir: Path) -> Path:
    if fixture_dir.is_symlink():
        raise IsolationError(f"fixture must not be a symlink: {fixture_dir}")
    fixture = fixture_dir.resolve(strict=True)
    if not fixture.is_dir():
        raise IsolationError(f"fixture must be a real directory: {fixture_dir}")
    for required in ("article.md", "metadata.json"):
        required_path = fixture / required
        if required_path.is_symlink():
            raise IsolationError(
                f"fixture required file must not be a symlink: {required_path}"
            )
        if not required_path.is_file():
            raise IsolationError(f"fixture missing {required}: {fixture}")
    return fixture


def _symlink_ancestor(path: Path) -> Path | None:
    """Return a symlink in the supplied path, without resolving it first."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.is_symlink():
            return current
    return None


def _validated_parent(parent_dir: Path) -> Path:
    if ".." in parent_dir.parts:
        raise IsolationError(f"unsafe parent path traversal: {parent_dir}")
    symlink = _symlink_ancestor(parent_dir)
    if symlink is not None:
        raise IsolationError(f"unsafe parent symlink ancestor: {symlink}")
    parent = parent_dir.resolve(strict=True)
    unsafe = {Path("/"), Path.home().resolve(), Path(tempfile.gettempdir()).resolve()}
    if parent in unsafe:
        raise IsolationError(f"unsafe parent directory: {parent}")
    if not parent.is_dir():
        raise IsolationError(f"parent is not a directory: {parent}")
    return parent


def _offline_environment(base_dir: Path, rag_dir: Path) -> dict[str, str]:
    """Return a fresh allowlist, never a copy of the caller's environment."""
    return {
        "OMNIGRAPH_LOAD_ENV": "0",
        "OMNIGRAPH_BASE_DIR": str(base_dir),
        "RAG_WORKING_DIR": str(rag_dir),
        "OMNIGRAPH_CHECKPOINT_BASE_DIR": str(base_dir),
        "KOL_SCAN_DB_PATH": str(base_dir / "kol_scan.db"),
        "OMNIGRAPH_VECTOR_STORAGE": "nanovectordb",
        "ENRICHMENT_ENABLED": "0",
    }


def create_offline_plan(*, fixture_dir: Path, parent_dir: Path) -> OfflineIngestPlan:
    """Create empty controlled paths for a single fixture without executing it."""
    fixture = _validated_fixture(fixture_dir)
    parent = _validated_parent(parent_dir)
    run_dir = Path(tempfile.mkdtemp(prefix="vitax-vx004-", dir=parent)).resolve()
    if run_dir.parent != parent or run_dir.is_symlink():
        raise IsolationError(f"unsafe generated run directory: {run_dir}")

    base_dir = run_dir / "base"
    rag_dir = run_dir / "rag"
    base_dir.mkdir()
    rag_dir.mkdir()
    return OfflineIngestPlan(
        fixture_dir=fixture,
        run_dir=run_dir,
        base_dir=base_dir,
        rag_dir=rag_dir,
        environment=_offline_environment(base_dir, rag_dir),
        execution_mode="preflight-only",
        required_live_gates=(
            "explicit LLM callback; explicit embedding callback; explicit storage "
            "backend; independent network/process isolation evidence; authorized "
            "ingest_article execution and finalize_storages verification"
        ),
    )


def write_manifest(plan: OfflineIngestPlan) -> Path:
    """Persist the plan only; this is not an ingestion receipt."""
    manifest_path = plan.run_dir / "VX004_OFFLINE_PREFLIGHT.json"
    payload = {
        "fixture_dir": str(plan.fixture_dir),
        "run_dir": str(plan.run_dir),
        "base_dir": str(plan.base_dir),
        "rag_dir": str(plan.rag_dir),
        "environment": dict(plan.environment),
        "execution_mode": plan.execution_mode,
        "network_or_model_execution": "not attempted",
        "storage_backend": "nanovectordb",
        "qdrant_status": "not validated by this preflight",
        "required_live_gates": plan.required_live_gates,
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a VX004 offline preflight manifest.")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = create_offline_plan(fixture_dir=args.fixture, parent_dir=args.parent)
    except IsolationError as exc:
        parser.error(str(exc))
    print(write_manifest(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

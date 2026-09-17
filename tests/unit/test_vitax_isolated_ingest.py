"""Offline contract tests for the VX004 single-fixture preflight."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_harness():
    script = Path(__file__).resolve().parents[2] / "scripts" / "vitax_isolated_ingest.py"
    spec = importlib.util.spec_from_file_location("vitax_isolated_ingest", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture(root: Path) -> Path:
    fixture = root / "one_article"
    fixture.mkdir()
    (fixture / "article.md").write_text("# One article\n", encoding="utf-8")
    (fixture / "metadata.json").write_text(
        json.dumps({"url": "https://example.invalid/article"}), encoding="utf-8"
    )
    return fixture


def test_creates_an_empty_nanovectordb_plan_with_a_credential_free_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    parent = tmp_path / "runs"
    parent.mkdir()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-be-in-plan")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/secret.json")

    plan = harness.create_offline_plan(fixture_dir=fixture, parent_dir=parent)

    assert plan.run_dir.is_dir()
    assert plan.base_dir.is_dir()
    assert plan.rag_dir.is_dir()
    assert plan.run_dir.parent == parent.resolve()
    assert plan.environment["OMNIGRAPH_LOAD_ENV"] == "0"
    assert plan.environment["OMNIGRAPH_VECTOR_STORAGE"] == "nanovectordb"
    assert plan.environment["OMNIGRAPH_BASE_DIR"] == str(plan.base_dir)
    assert plan.environment["RAG_WORKING_DIR"] == str(plan.rag_dir)
    assert plan.environment["OMNIGRAPH_CHECKPOINT_BASE_DIR"] == str(plan.base_dir)
    assert "OMNIGRAPH_OFFLINE_PREFLIGHT" not in plan.environment
    assert "DEEPSEEK_API_KEY" not in plan.environment
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in plan.environment
    assert plan.execution_mode == "preflight-only"
    assert "explicit LLM callback" in plan.required_live_gates


@pytest.mark.parametrize("unsafe", [Path("/"), Path.home(), Path(__import__("tempfile").gettempdir())])
def test_rejects_broad_or_shared_parent_directories(tmp_path: Path, unsafe: Path) -> None:
    harness = _load_harness()

    with pytest.raises(harness.IsolationError, match="unsafe parent"):
        harness.create_offline_plan(fixture_dir=_fixture(tmp_path), parent_dir=unsafe)


def test_rejects_parent_path_traversal(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    parent = tmp_path / "runs"
    parent.mkdir()

    with pytest.raises(harness.IsolationError, match="path traversal"):
        harness.create_offline_plan(
            fixture_dir=fixture, parent_dir=parent / ".." / parent.name
        )


def test_rejects_symlink_required_fixture_file_before_creating_a_run(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    parent = tmp_path / "runs"
    parent.mkdir()
    metadata_target = tmp_path / "external-metadata.json"
    metadata_target.write_text("{}", encoding="utf-8")
    (fixture / "metadata.json").unlink()
    (fixture / "metadata.json").symlink_to(metadata_target)

    with pytest.raises(harness.IsolationError, match="required file must not be a symlink"):
        harness.create_offline_plan(fixture_dir=fixture, parent_dir=parent)

    assert list(parent.iterdir()) == []


def test_rejects_parent_with_a_symlink_ancestor_before_creating_a_run(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    safe_root = tmp_path / "safe-root"
    (safe_root / "runs").mkdir(parents=True)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(safe_root, target_is_directory=True)

    with pytest.raises(harness.IsolationError, match="symlink ancestor"):
        harness.create_offline_plan(fixture_dir=fixture, parent_dir=linked_root / "runs")

    assert list(safe_root.joinpath("runs").iterdir()) == []


def test_rejects_symlink_parent_and_writes_a_preflight_only_manifest(tmp_path: Path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    safe_parent = tmp_path / "safe-runs"
    safe_parent.mkdir()
    symlink_parent = tmp_path / "linked-runs"
    symlink_parent.symlink_to(safe_parent, target_is_directory=True)

    with pytest.raises(harness.IsolationError, match="symlink"):
        harness.create_offline_plan(fixture_dir=fixture, parent_dir=symlink_parent)

    plan = harness.create_offline_plan(fixture_dir=fixture, parent_dir=safe_parent)
    manifest_path = harness.write_manifest(plan)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["execution_mode"] == "preflight-only"
    assert manifest["network_or_model_execution"] == "not attempted"
    assert manifest["storage_backend"] == "nanovectordb"
    assert manifest["qdrant_status"] == "not validated by this preflight"

"""Offline contracts for the fail-closed single-article probe runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_probe():
    script = Path(__file__).resolve().parents[2] / "scripts" / "vitax_single_article_probe.py"
    spec = importlib.util.spec_from_file_location("vitax_single_article_probe", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_builds_unique_four_path_plan_with_only_explicit_runtime_environment(tmp_path: Path) -> None:
    probe = _load_probe()
    parent = tmp_path / "controlled-runs"
    parent.mkdir()

    plan = probe.create_probe_plan(
        parent_dir=parent,
        hermes_bin=Path("/opt/hermes/bin/hermes"),
        embedding_url="http://127.0.0.1:17997/embeddings",
    )

    assert plan.run_dir.parent == parent.resolve()
    assert plan.base_dir == plan.run_dir / "base"
    assert plan.rag_dir == plan.run_dir / "rag"
    assert plan.checkpoint_dir == plan.base_dir
    assert plan.sqlite_path == plan.base_dir / "kol_scan.db"
    assert plan.environment == {
        "OMNIGRAPH_LOAD_ENV": "0",
        "OMNIGRAPH_BASE_DIR": str(plan.base_dir),
        "RAG_WORKING_DIR": str(plan.rag_dir),
        "OMNIGRAPH_CHECKPOINT_BASE_DIR": str(plan.checkpoint_dir),
        "KOL_SCAN_DB_PATH": str(plan.sqlite_path),
        "OMNIGRAPH_VECTOR_STORAGE": "nanovectordb",
        "OMNIGRAPH_LLM_PROVIDER": "hermes",
        "OMNIGRAPH_HERMES_BIN": "/opt/hermes/bin/hermes",
        "OMNIGRAPH_LOCAL_EMBED": "1",
        "OMNIGRAPH_LOCAL_EMBED_URL": "http://127.0.0.1:17997/embeddings",
        "ENRICHMENT_ENABLED": "0",
    }
    assert "DEEPSEEK_API_KEY" not in plan.environment
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in plan.environment


def test_offline_mode_refuses_to_import_or_execute_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe()
    parent = tmp_path / "controlled-runs"
    parent.mkdir()
    plan = probe.create_probe_plan(
        parent_dir=parent, hermes_bin=Path("/opt/hermes/bin/hermes"), embedding_url="http://127.0.0.1:17997/embeddings"
    )
    imported = False

    def fake_runtime(*_args, **_kwargs):
        nonlocal imported
        imported = True
        raise AssertionError("runtime must not load in offline mode")

    monkeypatch.setattr(probe, "_execute_runtime", fake_runtime)

    receipt = probe.run_probe(plan, execute=False)

    assert imported is False
    assert receipt["status"] == "OFFLINE_ONLY"
    assert receipt["network_or_model_execution"] == "not attempted"
    assert receipt["request_budget"] == {"entity_canonicalization": 0, "lightrag_extraction": 0}


def test_execute_uses_injected_runtime_seam_and_requires_two_independent_verifications(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _load_probe()
    parent = tmp_path / "controlled-runs"
    parent.mkdir()
    plan = probe.create_probe_plan(
        parent_dir=parent, hermes_bin=Path("/opt/hermes/bin/hermes"), embedding_url="http://127.0.0.1:17997/embeddings"
    )
    calls: list[str] = []

    def fake_runtime(received_plan, *, reopen_reader):
        assert received_plan == plan
        calls.append("runtime")
        first = reopen_reader("first")
        second = reopen_reader("rerun")
        return {"first": first, "rerun": second, "request_budget": {"entity_canonicalization": 2, "lightrag_extraction": 3}}

    def fake_reader(label: str):
        calls.append(f"reader:{label}")
        return {"processed": True, "graph_entities": 2, "graph_relationships": 1, "body_marker": True}

    monkeypatch.setattr(probe, "_execute_runtime", fake_runtime)
    receipt = probe.run_probe(plan, execute=True, reopen_reader=fake_reader)

    assert calls == ["runtime", "reader:first", "reader:rerun"]
    assert receipt["status"] == "READY_FOR_REVIEW"
    assert receipt["first"]["processed"] is True
    assert receipt["rerun"]["graph_relationships"] == 1
    assert receipt["request_budget"] == {"entity_canonicalization": 2, "lightrag_extraction": 3}


def test_rejects_unowned_parent_before_creating_a_probe_directory(tmp_path: Path) -> None:
    probe = _load_probe()

    with pytest.raises(probe.IsolationError, match="unsafe parent"):
        probe.create_probe_plan(
            parent_dir=Path("/"), hermes_bin=Path("/opt/hermes/bin/hermes"), embedding_url="http://127.0.0.1:17997/embeddings"
        )

    assert list(tmp_path.iterdir()) == []


def test_verify_rejects_arbitrary_or_symlinked_run_directories(tmp_path: Path) -> None:
    probe = _load_probe()
    arbitrary = tmp_path / "arbitrary"
    arbitrary.mkdir()
    (arbitrary / "base").mkdir()
    (arbitrary / "rag").mkdir()

    with pytest.raises(probe.IsolationError, match="owned"):
        probe._plan_from_run_dir(
            arbitrary, Path("/opt/hermes/bin/hermes"), "http://127.0.0.1:17997/embeddings"
        )

    parent = tmp_path / "controlled-runs"
    parent.mkdir()
    plan = probe.create_probe_plan(
        parent_dir=parent, hermes_bin=Path("/opt/hermes/bin/hermes"), embedding_url="http://127.0.0.1:17997/embeddings"
    )
    linked = tmp_path / "linked-run"
    linked.symlink_to(plan.run_dir, target_is_directory=True)
    with pytest.raises(probe.IsolationError, match="symlink"):
        probe._plan_from_run_dir(
            linked, Path("/opt/hermes/bin/hermes"), "http://127.0.0.1:17997/embeddings"
        )


def test_fresh_reader_failure_never_returns_raw_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe()
    parent = tmp_path / "controlled-runs"
    parent.mkdir()
    plan = probe.create_probe_plan(
        parent_dir=parent, hermes_bin=Path("/opt/hermes/bin/hermes"), embedding_url="http://127.0.0.1:17997/embeddings"
    )
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=21, stdout="", stderr="credential=must-not-return"),
    )

    with pytest.raises(probe.ProbeError) as exc_info:
        probe._reopen_reader(plan, "first")

    assert exc_info.value.code == "FRESH_READER_FAILED"
    assert "credential" not in str(exc_info.value)
    assert exc_info.value.log_path == plan.run_dir / "fresh-reader.log"


def test_execute_failure_persists_a_redacted_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe()
    parent = tmp_path / "controlled-runs"
    parent.mkdir()
    plan = probe.create_probe_plan(
        parent_dir=parent, hermes_bin=Path("/opt/hermes/bin/hermes"), embedding_url="http://127.0.0.1:17997/embeddings"
    )

    def fail_runtime(*_args, **_kwargs):
        raise probe.ProbeError("RUNTIME_FAILED", plan.run_dir / "runtime.log")

    monkeypatch.setattr(probe, "_execute_runtime", fail_runtime)
    receipt = probe.run_probe(plan, execute=True)

    assert receipt["status"] == "FAILED"
    assert receipt["error"] == {
        "type": "ProbeError", "code": "RUNTIME_FAILED", "log_path": str(plan.run_dir / "runtime.log")
    }
    assert (plan.run_dir / "VITAX_SINGLE_ARTICLE_PROBE.json").is_file()


def test_rejects_embedding_url_credentials_and_noncanonical_parts(tmp_path: Path) -> None:
    probe = _load_probe()
    parent = tmp_path / "controlled-runs"
    parent.mkdir()

    for bad_url in (
        "http://token@127.0.0.1:17997/embeddings",
        "http://127.0.0.1:17997/embeddings?token=secret",
        "http://127.0.0.1:17997/embeddings#fragment",
    ):
        with pytest.raises(probe.IsolationError):
            probe.create_probe_plan(parent_dir=parent, hermes_bin=Path("/opt/hermes/bin/hermes"), embedding_url=bad_url)


def test_execute_rejects_preimported_runtime_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe()
    parent = tmp_path / "controlled-runs"
    parent.mkdir()
    plan = probe.create_probe_plan(
        parent_dir=parent, hermes_bin=Path("/opt/hermes/bin/hermes"), embedding_url="http://127.0.0.1:17997/embeddings"
    )
    monkeypatch.setitem(sys.modules, "lib.checkpoint", object())

    with pytest.raises(probe.ProbeError, match="RUNTIME_MODULES_ALREADY_IMPORTED"):
        probe._execute_runtime(plan, reopen_reader=lambda _label: {})

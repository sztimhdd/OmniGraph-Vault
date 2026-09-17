"""Offline contracts for the isolated VitaX Wiki candidate probe."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import socket
import sys
from pathlib import Path

import pytest


def _load_probe():
    script = Path(__file__).resolve().parents[2] / "scripts" / "vitax_wiki_candidate_probe.py"
    spec = importlib.util.spec_from_file_location("vitax_wiki_candidate_probe", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _accepted_run(
    parent: Path, *, status: str = "processed", summary: str = "Accepted synthetic source."
) -> Path:
    run = parent / "vitax-single-article-accepted"
    (run / "rag").mkdir(parents=True)
    (run / "base" / "entity_buffer").mkdir(parents=True)
    (run / ".vitax-single-article-owned.json").write_text(
        json.dumps({"schema": 1, "run_dir": str(run.resolve())}) + "\n",
        encoding="utf-8",
    )
    (run / "rag" / "kv_store_full_docs.json").write_text(
        json.dumps({"doc-accepted": {"content": f"# Synthetic\n\nURL: https://vitax.invalid/single-article-probe\n\n{summary}\n"}}),
        encoding="utf-8",
    )
    (run / "rag" / "kv_store_doc_status.json").write_text(
        json.dumps({"doc-accepted": {"status": status}}), encoding="utf-8"
    )
    (run / "base" / "entity_buffer" / "9955937e7a_entities.json").write_text(
        json.dumps({"raw_entities": [{"name": "VitaX"}]}), encoding="utf-8"
    )
    return run


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _no_socket(*_args, **_kwargs):
    raise AssertionError("network call attempted during Wiki candidate probe")


def test_persists_isolated_applied_page_linked_to_processed_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches a probe that applies outside its owned root or loses source ref."""
    pytest.importorskip("frontmatter")
    probe = _load_probe()
    runs = tmp_path / "runs"
    runs.mkdir()
    accepted = _accepted_run(runs)
    accepted_before = _file_hashes(accepted)
    repo_wiki = Path(__file__).resolve().parents[2] / "kb" / "wiki"
    repo_wiki_before = _file_hashes(repo_wiki)
    monkeypatch.setattr(socket, "socket", _no_socket)

    receipt = probe.create_wiki_candidate(
        accepted_run=accepted,
        output_parent=runs,
        today="2026-09-09",
    )

    candidate = Path(receipt["candidate_dir"])
    page = candidate / "wiki" / "entities" / "vitax.md"
    assert receipt["status"] == "APPLIED"
    assert receipt["source"] == "synthetic"
    assert receipt["processed_doc_id"] == "doc-accepted"
    assert receipt["source_url"] == "https://vitax.invalid/single-article-probe"
    assert receipt["source_ref"] == "9955937e7a"
    assert candidate.parent == runs.resolve()
    assert page.is_file()
    assert "9955937e7a (w3-entity-buffer)" in page.read_text(encoding="utf-8")
    assert "Synthetic" in page.read_text(encoding="utf-8")
    assert "Accepted synthetic source." in page.read_text(encoding="utf-8")
    assert receipt["artifact_hashes"]["wiki/entities/vitax.md"] == hashlib.sha256(page.read_bytes()).hexdigest()
    assert any(path.startswith("wiki/.locks/") for path in receipt["artifact_hashes"])
    assert _file_hashes(accepted) == accepted_before
    assert _file_hashes(repo_wiki) == repo_wiki_before
    assert receipt["source_input_hashes"] == accepted_before


def test_rejects_nonprocessed_source_before_creating_candidate(tmp_path: Path) -> None:
    """Catches accepting a stale or failed LightRAG document as Wiki evidence."""
    probe = _load_probe()
    runs = tmp_path / "runs"
    runs.mkdir()
    accepted = _accepted_run(runs, status="failed")

    with pytest.raises(probe.ProbeError, match="SOURCE_NOT_PROCESSED"):
        probe.create_wiki_candidate(
            accepted_run=accepted,
            output_parent=runs,
            today="2026-09-09",
        )

    assert [path.name for path in runs.iterdir()] == ["vitax-single-article-accepted"]


def test_compiler_rejection_writes_only_candidate_local_diagnostics(tmp_path: Path) -> None:
    """Catches rejection routing through the repository Error Book."""
    pytest.importorskip("frontmatter")
    probe = _load_probe()
    runs = tmp_path / "runs"
    runs.mkdir()
    accepted = _accepted_run(runs, summary="Rejected candidate[^2].")
    accepted_before = _file_hashes(accepted)
    repo_wiki = Path(__file__).resolve().parents[2] / "kb" / "wiki"
    repo_wiki_before = _file_hashes(repo_wiki)

    with pytest.raises(probe.ProbeError, match="WIKI_CANDIDATE_NOT_APPLIED"):
        probe.create_wiki_candidate(accepted_run=accepted, output_parent=runs, today="2026-09-09")

    candidates = list(runs.glob("vitax-wiki-candidate-*"))
    assert len(candidates) == 1
    assert (candidates[0] / "compiler_failures.jsonl").is_file()
    rejection_receipt = json.loads((candidates[0] / "VITAX_WIKI_CANDIDATE_PROBE.json").read_text())
    assert rejection_receipt["status"] == "REJECTED"
    assert "compiler_failures.jsonl" in rejection_receipt["artifact_hashes"]
    assert _file_hashes(accepted) == accepted_before
    assert _file_hashes(repo_wiki) == repo_wiki_before

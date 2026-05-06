"""Mock-only unit tests for `scripts/cleanup_stuck_docs.py`.

LightRAG instance + RAG_WORKING_DIR are both monkeypatched per test —
no .dev-runtime/ mutation. STK-01 verified `adelete_by_doc_id` is residue-free
on the production backend; this suite locks down the CLI argparse contract,
JSON report schema, and exit-code semantics.
"""
from __future__ import annotations

import json
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import cleanup_stuck_docs  # noqa: E402


def _make_storage(tmp_path, status_map):
    storage = tmp_path / "lightrag_storage"
    storage.mkdir()
    (storage / "kv_store_doc_status.json").write_text(
        json.dumps(status_map), encoding="utf-8")
    return storage


@pytest.fixture
def fake_doc_status(tmp_path, monkeypatch):
    storage = _make_storage(tmp_path, {
        "doc_a_failed":     {"status": "failed",     "chunks_count": 1},
        "doc_b_processing": {"status": "processing", "chunks_count": 0},
        "doc_c_processed":  {"status": "processed",  "chunks_count": 3},
    })
    monkeypatch.setattr(cleanup_stuck_docs, "RAG_WORKING_DIR", storage)
    return storage


@pytest.fixture
def empty_doc_status(tmp_path, monkeypatch):
    storage = _make_storage(tmp_path, {})
    monkeypatch.setattr(cleanup_stuck_docs, "RAG_WORKING_DIR", storage)
    return storage


@pytest.fixture
def mock_rag(monkeypatch):
    rag = MagicMock()
    rag.adelete_by_doc_id = AsyncMock(return_value=SimpleNamespace(
        status="success", doc_id="x", message="ok", status_code=200))

    async def fake_build_rag():
        return rag

    monkeypatch.setattr(cleanup_stuck_docs, "_build_rag", fake_build_rag)
    monkeypatch.setattr(
        cleanup_stuck_docs, "_emit_pipeline_busy_warning", lambda _: None)
    return rag


# --- Task 1: dry-run + schema -------------------------------------------------


def test_dry_run_lists_candidates_only(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--dry-run"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_identified"] == 2
    assert report["docs_deleted"] == 0
    assert mock_rag.adelete_by_doc_id.call_count == 0


def test_processed_doc_excluded_from_candidates(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "doc_c_processed" not in captured.out
    assert "doc_c_processed" not in captured.err


def test_no_flag_prints_help_exits_0(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.lower().startswith("usage:")
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.out)


def test_json_schema_complete(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--dry-run"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report.keys()) == {
        "docs_identified", "docs_deleted", "docs_skipped",
        "skipped_reasons", "elapsed_ms",
    }
    assert isinstance(report["docs_identified"], int)
    assert isinstance(report["docs_deleted"], int)
    assert isinstance(report["docs_skipped"], int)
    assert isinstance(report["skipped_reasons"], list)
    assert isinstance(report["elapsed_ms"], int)


def test_dry_run_with_all_failed_combined_is_dry_run(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--dry-run", "--all-failed"])
    assert rc == 0
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_deleted"] == 0


# --- Task 2: --all-failed / --hash / advisory / exception ---------------------


def test_all_failed_calls_delete_once_per_failed_doc(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--all-failed"])
    assert rc == 0
    assert mock_rag.adelete_by_doc_id.call_count == 2
    called_ids = {c.args[0] for c in mock_rag.adelete_by_doc_id.call_args_list}
    assert called_ids == {"doc_a_failed", "doc_b_processing"}
    report = json.loads(capsys.readouterr().out)
    assert report["docs_deleted"] == 2
    assert report["docs_identified"] == 2


def test_all_failed_zero_candidates_exits_0(empty_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--all-failed"])
    assert rc == 0
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_identified"] == 0
    assert report["docs_deleted"] == 0
    assert report["skipped_reasons"] == []


def test_hash_deletes_one_doc(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--hash", "doc_a_failed"])
    assert rc == 0
    assert mock_rag.adelete_by_doc_id.call_count == 1
    assert mock_rag.adelete_by_doc_id.call_args.args[0] == "doc_a_failed"
    report = json.loads(capsys.readouterr().out)
    assert report["docs_identified"] == 1
    assert report["docs_deleted"] == 1


def test_hash_refuses_processed_doc(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--hash", "doc_c_processed"])
    assert rc == 1
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_deleted"] == 0
    assert len(report["skipped_reasons"]) == 1
    assert report["skipped_reasons"][0]["reason"] == "not_failed_status"
    assert report["skipped_reasons"][0]["doc_id"] == "doc_c_processed"


def test_hash_missing_doc_is_idempotent_exit_0(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--hash", "totally_unknown_doc"])
    assert rc == 0
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_identified"] == 0
    assert report["docs_deleted"] == 0
    assert report["skipped_reasons"][0]["reason"] == "doc_not_found"


def test_delete_returning_error_is_recorded_as_skip(fake_doc_status, monkeypatch, capsys):
    rag = MagicMock()
    rag.adelete_by_doc_id = AsyncMock(return_value=SimpleNamespace(
        status="error", status_code=500, message="kuzu lock", doc_id="doc_a_failed"))

    async def fake_build_rag():
        return rag

    monkeypatch.setattr(cleanup_stuck_docs, "_build_rag", fake_build_rag)
    monkeypatch.setattr(cleanup_stuck_docs, "_emit_pipeline_busy_warning", lambda _: None)
    rc = cleanup_stuck_docs.main(["--all-failed"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_deleted"] == 0
    reasons = {e["reason"] for e in report["skipped_reasons"]}
    assert "delete_returned_error" in reasons


def test_pipeline_busy_advisory_emits_stderr_does_not_block(
    fake_doc_status, monkeypatch, capsys
):
    rag = MagicMock()
    rag.adelete_by_doc_id = AsyncMock(return_value=SimpleNamespace(
        status="success", doc_id="x", message="ok", status_code=200))

    async def fake_build_rag():
        return rag

    monkeypatch.setattr(cleanup_stuck_docs, "_build_rag", fake_build_rag)
    monkeypatch.setattr(cleanup_stuck_docs, "_emit_pipeline_busy_warning",
                        lambda _: sys.stderr.write("WARNING: pipeline busy advisory\n"))
    rc = cleanup_stuck_docs.main(["--all-failed"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARNING: pipeline busy advisory" in captured.err
    assert rag.adelete_by_doc_id.call_count == 2


def test_unexpected_exception_returns_exit_1(fake_doc_status, monkeypatch, capsys):
    rag = MagicMock()
    rag.adelete_by_doc_id = AsyncMock(side_effect=RuntimeError("boom"))

    async def fake_build_rag():
        return rag

    monkeypatch.setattr(cleanup_stuck_docs, "_build_rag", fake_build_rag)
    monkeypatch.setattr(cleanup_stuck_docs, "_emit_pipeline_busy_warning", lambda _: None)
    rc = cleanup_stuck_docs.main(["--all-failed"])
    assert rc == 1

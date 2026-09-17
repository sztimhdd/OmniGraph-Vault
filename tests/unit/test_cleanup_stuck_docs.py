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


def test_write_flag_help_states_that_cleanup_fails_closed():
    help_text = cleanup_stuck_docs._build_parser().format_help()
    assert "delete every doc" not in help_text
    assert "report failed docs" in help_text


def test_dry_run_help_states_that_it_counts_candidates():
    help_text = cleanup_stuck_docs._build_parser().format_help()
    assert "count candidates only" in help_text
    assert "list candidates" not in help_text


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


def test_all_failed_fails_closed_without_a_shared_pipeline_lock(
    fake_doc_status, mock_rag, capsys
):
    rc = cleanup_stuck_docs.main(["--all-failed"])
    assert rc == 1
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_deleted"] == 0
    assert report["docs_identified"] == 1
    assert report["skipped_reasons"] == [{
        "doc_id": "doc_b_processing",
        "status": "processing",
        "reason": "processing_not_eligible",
    }, {
        "doc_id": "doc_a_failed",
        "status": "failed",
        "reason": "pipeline_lock_unshared",
    }]


def test_dry_run_keeps_processing_visible_for_diagnostics(
    fake_doc_status, mock_rag, capsys
):
    rc = cleanup_stuck_docs.main(["--dry-run"])
    assert rc == 0
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_identified"] == 2


def test_all_failed_with_only_processing_is_no_eligible_exit_0(
    empty_doc_status, mock_rag, capsys
):
    (empty_doc_status / "kv_store_doc_status.json").write_text(
        json.dumps({"only_processing": {"status": "processing"}}),
        encoding="utf-8",
    )
    rc = cleanup_stuck_docs.main(["--all-failed"])
    assert rc == 0
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_identified"] == 0
    assert report["docs_deleted"] == 0
    assert report["skipped_reasons"] == [{
        "doc_id": "only_processing",
        "status": "processing",
        "reason": "processing_not_eligible",
    }]


def test_hash_fails_closed_without_a_shared_pipeline_lock(
    fake_doc_status, mock_rag, capsys
):
    rc = cleanup_stuck_docs.main(["--hash", "doc_a_failed"])
    assert rc == 1
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_identified"] == 1
    assert report["docs_deleted"] == 0
    assert report["skipped_reasons"] == [{
        "doc_id": "doc_a_failed",
        "status": "failed",
        "reason": "pipeline_lock_unshared",
    }]


def test_hash_refuses_processed_doc(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--hash", "doc_c_processed"])
    assert rc == 1
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_deleted"] == 0
    assert len(report["skipped_reasons"]) == 1
    assert report["skipped_reasons"][0]["reason"] == "not_failed_status"
    assert report["skipped_reasons"][0]["doc_id"] == "doc_c_processed"


def test_hash_refuses_processing_doc(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--hash", "doc_b_processing"])
    assert rc == 1
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_deleted"] == 0
    assert report["skipped_reasons"] == [{
        "doc_id": "doc_b_processing",
        "status": "processing",
        "reason": "processing_not_eligible",
    }]


def test_hash_missing_doc_is_idempotent_exit_0(fake_doc_status, mock_rag, capsys):
    rc = cleanup_stuck_docs.main(["--hash", "totally_unknown_doc"])
    assert rc == 0
    assert mock_rag.adelete_by_doc_id.call_count == 0
    report = json.loads(capsys.readouterr().out)
    assert report["docs_identified"] == 0
    assert report["docs_deleted"] == 0
    assert report["skipped_reasons"][0]["reason"] == "doc_not_found"


def test_hash_rejects_invalid_status_entry_without_echoing_value(
    empty_doc_status, mock_rag, capsys
):
    (empty_doc_status / "kv_store_doc_status.json").write_text(
        json.dumps({"bad_entry": ["untrusted", "value"]}), encoding="utf-8"
    )

    rc = cleanup_stuck_docs.main(["--hash", "bad_entry"])

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert rc == 1
    assert mock_rag.adelete_by_doc_id.call_count == 0
    assert report["docs_deleted"] == 0
    assert report["skipped_reasons"] == [{
        "doc_id": "bad_entry",
        "status": "invalid",
        "reason": "invalid_status_entry",
    }]
    assert "untrusted" not in captured.out
    assert "untrusted" not in captured.err

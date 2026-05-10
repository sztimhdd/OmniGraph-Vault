"""Unit tests for HYG-03 JSONL query history (Phase 18-02).

Tests ``_read_recent_query_history`` + ``_append_query_history`` in
``kg_synthesize.py``. Uses ``tmp_path`` + monkeypatch of the
``QUERY_HISTORY_FILE`` module constant to avoid touching real
``~/.hermes/omonigraph-vault/``.

Also includes a regression-guard grep test: Cognee must stay OUT of
kg_synthesize.py (per Wave 0 commit 0109c02 + 2026-05-10 quick 260510-gfg
full Cognee retirement).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import kg_synthesize


@pytest.fixture
def history_file(tmp_path, monkeypatch):
    """Redirect QUERY_HISTORY_FILE to a tmp_path location."""
    target = tmp_path / "omonigraph-vault" / "query_history.jsonl"
    monkeypatch.setattr(kg_synthesize, "QUERY_HISTORY_FILE", target)
    return target


def test_read_empty_file_returns_empty_list(history_file):
    # File does not exist — read is no-op, returns [].
    assert not history_file.exists()
    result = kg_synthesize._read_recent_query_history(limit=10)
    assert result == []


def test_append_then_read_roundtrip(history_file):
    kg_synthesize._append_query_history("query one", "hybrid", 100)
    kg_synthesize._append_query_history("query two", "local", 250)
    kg_synthesize._append_query_history("query three", "global", 500)

    assert history_file.exists()
    lines = history_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3

    result = kg_synthesize._read_recent_query_history(limit=10)
    # Newest first.
    assert result == ["query three", "query two", "query one"]


def test_read_limit_truncates_to_n(history_file):
    for i in range(15):
        kg_synthesize._append_query_history(f"query {i}", "hybrid", 100)
    result = kg_synthesize._read_recent_query_history(limit=5)
    assert len(result) == 5
    # Newest first.
    assert result[0] == "query 14"
    assert result[4] == "query 10"


def test_read_skips_malformed_lines(history_file):
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        json.dumps({"ts": "t1", "query": "valid 1", "mode": "h", "response_len": 100}) + "\n"
        + "this is not json\n"
        + json.dumps({"ts": "t2", "query": "valid 2", "mode": "h", "response_len": 200}) + "\n"
        + "\n"
        + "{\"broken\": \"no-query-key\"}\n",
        encoding="utf-8",
    )
    result = kg_synthesize._read_recent_query_history(limit=10)
    # Newest first; 2 valid entries returned; "no-query-key" entry dropped; malformed line dropped.
    assert result == ["valid 2", "valid 1"]


def test_append_survives_missing_parent_dir(history_file):
    parent = history_file.parent
    if parent.exists():
        shutil.rmtree(parent)
    assert not parent.exists()
    kg_synthesize._append_query_history("post-mkdir query", "hybrid", 100)
    assert history_file.exists()
    result = kg_synthesize._read_recent_query_history(limit=10)
    assert result == ["post-mkdir query"]


def test_append_jsonl_shape(history_file):
    kg_synthesize._append_query_history("my query", "hybrid", 1234)
    line = history_file.read_text(encoding="utf-8").strip()
    entry = json.loads(line)
    assert set(entry.keys()) == {"ts", "query", "mode", "response_len"}
    assert entry["query"] == "my query"
    assert entry["mode"] == "hybrid"
    assert entry["response_len"] == 1234
    # ts ends with Z (UTC marker).
    assert entry["ts"].endswith("Z")


def test_cognee_regression_guard_kg_synthesize():
    """HYG-03 lock: Cognee must stay removed from kg_synthesize.py.

    Wave 0 commit 0109c02 removed `import cognee` and its call sites
    because Cognee's module-level import blocked the asyncio event loop.
    Quick 260510-gfg (2026-05-10) retired Cognee from the entire repo.
    This test protects against accidental re-introduction.
    """
    source_path = Path(kg_synthesize.__file__)
    source = source_path.read_text(encoding="utf-8")
    lines_wo_comments = [
        line for line in source.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    body = "\n".join(lines_wo_comments)
    assert "import cognee" not in body
    assert "recall_previous_context" not in body
    assert "remember_synthesis" not in body

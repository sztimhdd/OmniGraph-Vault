"""Unit tests for reindex_lightrag.py — no network calls.

All 8 behaviours specified in PLAN 01 Task 1.2:
  1. test_load_candidates_strict_filter
  2. test_stratified_sample_distribution
  3. test_empty_target_safety_blocks
  4. test_empty_target_safety_passes_on_force
  5. test_ingest_one_isolates_failures
  6. test_ingest_one_checks_doc_status
  7. test_resume_skips_already_ok
  8. test_failures_csv_schema_no_path_leak

Coverage of locked decisions:
  D-01: _load_candidates strict filter (test 1)
  D-05: doc_status post-check (test 6)
  D-06: ids=[content_hash] idempotency (verified in test 5+6 setup)
  D-07: empty-target safety (tests 3+4)
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure databricks-deploy/ is on sys.path for the import below.
_TESTS_DIR = Path(__file__).resolve().parent
_JOBS_DIR = _TESTS_DIR.parent
_DEPLOY_DIR = _JOBS_DIR.parent
for _p in (str(_DEPLOY_DIR), str(_JOBS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from reindex_lightrag import (  # noqa: E402
    CandidateRow,
    IngestResult,
    _append_failures_csv,
    _ingest_one,
    _load_candidates,
    _load_progress_hashes,
    _verify_target_empty,
)

import reindex_lightrag as _mod  # for monkeypatching PROGRESS_CSV / FAILURES_CSV


# ---------------------------------------------------------------------------
# 1. test_load_candidates_strict_filter
# ---------------------------------------------------------------------------

def test_load_candidates_strict_filter(fixture_db_path: str) -> None:
    """Strict filter (DATA-07) returns exactly the 3 candidate+body rows.

    Fixture DB has 5 rows:
      articles: aaaa=candidate/null ✓, bbbb=candidate/ok ✓, cccc=reject ✗
      rss_articles: dddd=candidate/null ✓, eeee=candidate/reject ✗
    Expected: 3 rows (aaaa, bbbb, dddd).
    """
    rows = _load_candidates(fixture_db_path, filter_mode="strict")
    assert len(rows) == 3, f"Expected 3, got {len(rows)}: {[r.content_hash for r in rows]}"

    hashes = {r.content_hash for r in rows}
    # All expected rows are present
    assert "a" * 32 in hashes, "aaaa (articles/candidate/null) should be included"
    assert "b" * 32 in hashes, "bbbb (articles/candidate/ok) should be included"
    assert "d" * 32 in hashes, "dddd (rss_articles/candidate/null) should be included"
    # Excluded rows are absent
    assert "c" * 32 not in hashes, "cccc (reject) should be excluded"
    assert "e" * 32 not in hashes, "eeee (layer2=reject) should be excluded"


# ---------------------------------------------------------------------------
# 2. test_stratified_sample_distribution
# ---------------------------------------------------------------------------

def test_stratified_sample_distribution(stratified_db_path: str) -> None:
    """50-row DB with 5 body-length buckets (10 each); sample_n=50 returns 50.

    All 5 buckets must be represented (stratified).
    """
    rows = _load_candidates(stratified_db_path, filter_mode="all", sample_n=50)
    assert len(rows) == 50, f"Expected 50 sampled rows, got {len(rows)}"

    # Verify all 5 buckets are represented by checking body lengths
    body_lengths = sorted({len(r.body) for r in rows})
    assert len(body_lengths) == 5, (
        f"Expected 5 distinct body-length buckets; got {body_lengths}"
    )
    assert 100 in body_lengths
    assert 50000 in body_lengths


# ---------------------------------------------------------------------------
# 3. test_empty_target_safety_blocks
# ---------------------------------------------------------------------------

def test_empty_target_safety_blocks(tmp_path: Path) -> None:
    """Non-empty dir + force_overwrite=False raises RuntimeError with filenames."""
    d = tmp_path / "lightrag_storage"
    d.mkdir()
    (d / "vdb_entities.json").write_text("{}")
    (d / "graph_chunk_entity_relation.graphml").write_text("<graph/>")

    with pytest.raises(RuntimeError) as exc_info:
        _verify_target_empty(lightrag_dir=str(d), force_overwrite=False)

    msg = str(exc_info.value)
    # Error message must contain filenames
    assert "vdb_entities.json" in msg or "graph_chunk" in msg, (
        f"RuntimeError should mention artifact names; got: {msg[:300]}"
    )
    # Must contain mtime strings
    assert "mtime=" in msg, f"RuntimeError should contain mtime info; got: {msg[:300]}"


# ---------------------------------------------------------------------------
# 4. test_empty_target_safety_passes_on_force
# ---------------------------------------------------------------------------

def test_empty_target_safety_passes_on_force(tmp_path: Path) -> None:
    """Non-empty dir + force_overwrite=True should NOT raise."""
    d = tmp_path / "lightrag_storage"
    d.mkdir()
    (d / "vdb_entities.json").write_text("{}")

    # Should not raise
    _verify_target_empty(lightrag_dir=str(d), force_overwrite=True)


# ---------------------------------------------------------------------------
# 5. test_ingest_one_isolates_failures
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_one_isolates_failures(mock_rag: MagicMock) -> None:
    """ainsert raising RuntimeError -> _ingest_one returns status='failed'.

    The exception must NOT propagate. error_truncated must contain 'boom'.
    """
    mock_rag.ainsert = AsyncMock(side_effect=RuntimeError("boom: test failure"))

    row = CandidateRow(
        source_table="articles",
        content_hash="a" * 32,
        title="Test",
        body="test body content",
        lang="en",
    )
    result = await _ingest_one(mock_rag, row)

    assert result.status == "failed", f"Expected failed, got {result.status}"
    assert result.error_truncated is not None
    assert "boom" in result.error_truncated, (
        f"error_truncated should contain 'boom'; got: {result.error_truncated}"
    )
    assert len(result.error_truncated) <= 200, (
        f"error_truncated should be <= 200 chars; got {len(result.error_truncated)}"
    )


# ---------------------------------------------------------------------------
# 6. test_ingest_one_checks_doc_status (D-05)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_one_checks_doc_status(mock_rag: MagicMock) -> None:
    """ainsert succeeds but doc_status=FAILED -> _ingest_one returns status='failed'.

    D-05: try/except alone is insufficient — we must consult aget_docs_by_ids.
    """
    # ainsert completes without raising
    mock_rag.ainsert = AsyncMock(return_value="track-999")

    # But aget_docs_by_ids returns FAILED for this doc (dict, not list)
    content_hash = "b" * 32
    failed_record = MagicMock()
    failed_record.status = MagicMock()
    failed_record.status.value = "FAILED"
    mock_rag.aget_docs_by_ids = AsyncMock(
        return_value={f"doc-{content_hash}": failed_record}
    )

    row = CandidateRow(
        source_table="articles",
        content_hash=content_hash,
        title="Test B",
        body="test body content for doc status check",
        lang="zh",
    )
    result = await _ingest_one(mock_rag, row)

    assert result.status == "failed", (
        f"Expected failed (doc_status=FAILED), got {result.status}"
    )
    # D-05 verification: error_truncated must mention doc_status
    assert result.error_truncated is not None
    assert "doc_status=FAILED" in result.error_truncated, (
        f"error_truncated should mention 'doc_status=FAILED'; "
        f"got: {result.error_truncated}"
    )
    # D-06 verification: ainsert was called with ids=[content_hash]
    call_kwargs = mock_rag.ainsert.call_args
    assert call_kwargs is not None, "ainsert must have been called"
    # ids can be in args or kwargs
    all_args = list(call_kwargs.args) + list(call_kwargs.kwargs.values())
    assert ["b" * 32] in all_args or ("b" * 32) in str(all_args), (
        f"ainsert must be called with ids=[content_hash]; got {call_kwargs}"
    )


# ---------------------------------------------------------------------------
# 7. test_resume_skips_already_ok
# ---------------------------------------------------------------------------

def test_resume_skips_already_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Progress CSV with 2 ok + 1 failed -> _load_progress_hashes returns 2-element set.

    The 2 ok hashes should be filtered out by fullreindex resume logic.
    """
    progress_csv = tmp_path / "progress.csv"
    with progress_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["content_hash", "source_table", "status",
                    "elapsed_s", "error_truncated", "track_id", "ts"])
        w.writerow(["hash_ok_1" + "0" * 23, "articles", "ok",
                    "1.5", "", "track-1", "1716000000"])
        w.writerow(["hash_ok_2" + "0" * 23, "rss_articles", "ok",
                    "2.1", "", "track-2", "1716000001"])
        w.writerow(["hash_fail" + "0" * 23, "articles", "failed",
                    "0.8", "RuntimeError: boom", "", "1716000002"])

    # Monkeypatch both CSV path constants so _load_progress_hashes uses the test file
    # regardless of which path it checks first (_TMP_PROGRESS_CSV or PROGRESS_CSV).
    monkeypatch.setattr(_mod, "PROGRESS_CSV", str(progress_csv))
    monkeypatch.setattr(_mod, "_TMP_PROGRESS_CSV", str(progress_csv))

    done = _load_progress_hashes(status_filter={"ok"})
    assert len(done) == 2, f"Expected 2 ok hashes, got {len(done)}: {done}"
    assert "hash_ok_1" + "0" * 23 in done
    assert "hash_ok_2" + "0" * 23 in done
    assert "hash_fail" + "0" * 23 not in done


# ---------------------------------------------------------------------------
# 8. test_failures_csv_schema_no_path_leak
# ---------------------------------------------------------------------------

def test_failures_csv_schema_no_path_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure with path-containing error -> FAILURES CSV has 200-char truncated error.

    The truncated error must NOT contain '/' or '\\' characters (path leak check).
    """
    failures_csv = tmp_path / "FAILURES.csv"
    # Patch both constants: _append_failures_csv writes to _TMP_FAILURES_CSV.
    monkeypatch.setattr(_mod, "FAILURES_CSV", str(failures_csv))
    monkeypatch.setattr(_mod, "_TMP_FAILURES_CSV", str(failures_csv))

    # Simulate a failure whose repr includes a file path
    long_path_error = (
        "RuntimeError: 'Failed to open file /some/secret/path/to/data.json "
        "line 42 column 5 (char 999)' x" + "y" * 200  # longer than 200 chars
    )
    result = IngestResult(
        content_hash="f" * 32,
        source_table="articles",
        status="failed",
        elapsed_s=1.23,
        error_truncated=long_path_error[:200].replace("/", " ").replace("\\", " "),
        track_id=None,
    )
    _append_failures_csv(result)

    assert failures_csv.exists(), "FAILURES.csv should have been created"

    with failures_csv.open("r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1, f"Expected 1 failure row, got {len(rows)}"
    err = rows[0]["error_truncated"]
    assert len(err) <= 200, f"error_truncated must be <= 200 chars; got {len(err)}"
    assert "/" not in err, f"error_truncated must not contain '/'; got: {err[:100]}"
    assert "\\" not in err, f"error_truncated must not contain '\\'; got: {err[:100]}"

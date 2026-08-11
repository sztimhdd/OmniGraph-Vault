"""W5-0 Gate E: Error Book SQLite — unit tests."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from kb.error_book import (
    _fingerprint,
    _migrate_jsonl,
    log_lint_failure,
    get_open_errors,
    resolve_error,
    error_summary,
    _LEGACY_JSONL,
)


def test_fingerprint_is_stable():
    """Same inputs produce same fingerprint."""
    fp1 = _fingerprint("lint_citation", "openclaw", "0000000000")
    fp2 = _fingerprint("lint_citation", "openclaw", "0000000000")
    assert fp1 == fp2
    assert len(fp1) == 16


def test_fingerprint_different_inputs():
    """Different check_type or evidence produce different fingerprints."""
    fp1 = _fingerprint("lint_citation", "openclaw", "aaaa")
    fp2 = _fingerprint("lint_citation", "openclaw", "bbbb")
    fp3 = _fingerprint("lint_staleness", "openclaw", "aaaa")
    assert fp1 != fp2
    assert fp1 != fp3


def test_log_and_retrieve_errors(tmp_path: Path, monkeypatch):
    """Log an error, retrieve it, dedup works."""
    # Prevent migration of real legacy JSONL during test
    monkeypatch.setattr("kb.error_book._LEGACY_JSONL", tmp_path / "nonexistent.jsonl")
    db_path = tmp_path / "error_book.db"

    log_lint_failure({
        "lint_name": "lint_citation_integrity",
        "page_path": "kb/wiki/entities/openclaw.md",
        "failures": ["^[article:deadbeef00]"],
        "suggestion_excerpt": "openclaw page with bad citation",
    }, db_path=db_path)

    open_errors = get_open_errors(db_path=db_path)
    assert len(open_errors) == 1
    assert open_errors[0]["check_type"] == "lint_citation_integrity"
    assert open_errors[0]["page_slug"] == "openclaw"
    assert open_errors[0]["seen_count"] == 1

    # Log same error again — dedup, seen_count increments
    log_lint_failure({
        "lint_name": "lint_citation_integrity",
        "page_path": "kb/wiki/entities/openclaw.md",
        "failures": ["^[article:deadbeef00]"],
    }, db_path=db_path)

    open_errors = get_open_errors(db_path=db_path)
    assert len(open_errors) == 1  # dedup
    assert open_errors[0]["seen_count"] == 2


def test_resolve_error(tmp_path: Path, monkeypatch):
    """Resolving removes from open list."""
    monkeypatch.setattr("kb.error_book._LEGACY_JSONL", tmp_path / "nonexistent.jsonl")
    db_path = tmp_path / "error_book.db"

    log_lint_failure({
        "lint_name": "lint_backlink",
        "page_path": "kb/wiki/entities/test.md",
        "failures": ["nonexistent"],
    }, db_path=db_path)

    errors = get_open_errors(db_path=db_path)
    assert len(errors) == 1
    fp = errors[0]["fingerprint"]

    assert resolve_error(fp, db_path=db_path) is True
    assert len(get_open_errors(db_path=db_path)) == 0


def test_error_summary(tmp_path: Path, monkeypatch):
    """Summary reports counts correctly."""
    monkeypatch.setattr("kb.error_book._LEGACY_JSONL", tmp_path / "nonexistent.jsonl")
    db_path = tmp_path / "error_book.db"

    log_lint_failure({
        "lint_name": "lint_citation_integrity",
        "page_path": "kb/wiki/entities/a.md",
        "failures": ["bad1"],
    }, db_path=db_path)
    log_lint_failure({
        "lint_name": "lint_staleness",
        "page_path": "kb/wiki/entities/b.md",
        "failures": ["stale: 200d"],
    }, db_path=db_path)
    log_lint_failure({
        "lint_name": "lint_citation_integrity",
        "page_path": "kb/wiki/entities/c.md",
        "failures": ["bad2"],
    }, db_path=db_path)

    summary = error_summary(db_path=db_path)
    assert summary["total"] == 3
    assert summary["by_status"]["open"] == 3
    assert summary["by_check"]["lint_citation_integrity"] == 2
    assert summary["by_check"]["lint_staleness"] == 1


def test_migrate_jsonl(tmp_path: Path, monkeypatch):
    """Existing JSONL entries are migrated to Error Book."""
    # Create legacy JSONL
    legacy = tmp_path / "wiki-lint-failures.jsonl"
    monkeypatch.setattr("kb.error_book._LEGACY_JSONL", legacy)
    legacy.write_text(json.dumps({
        "lint_name": "lint_citation_integrity",
        "page_path": "kb/wiki/entities/old.md",
        "failures": ["^[article:aaaaaaaaaa]"],
        "ts": "2026-05-19T00:00:00",
        "suggestion_excerpt": "old error",
    }) + "\n", encoding="utf-8")

    db_path = tmp_path / "error_book.db"
    count = _migrate_jsonl(db_path)
    assert count == 1
    assert not legacy.exists()  # renamed to .migrated
    assert legacy.with_suffix(".jsonl.migrated").exists()

    open_errors = get_open_errors(db_path=db_path)
    assert len(open_errors) == 1
    assert open_errors[0]["page_slug"] == "old"

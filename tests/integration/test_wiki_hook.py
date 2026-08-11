"""W3 hook integration tests: generate_wiki_suggestions + apply_suggestion_atomic."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from kb.wiki_update import apply_suggestion_atomic, generate_wiki_suggestions


def _seed_db(hashes: list[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE articles (content_hash TEXT PRIMARY KEY)")
    for h in hashes:
        conn.execute("INSERT INTO articles (content_hash) VALUES (?)", (h,))
    conn.commit()
    return conn


def _write_buffer(buf_dir: Path, h: str, names: list[str]) -> None:
    buf_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": f"http://example.com/{h}",
        "raw_entities": [{"name": n} for n in names],
        "timestamp": 0.0,
    }
    (buf_dir / f"{h}_entities.json").write_text(json.dumps(payload), encoding="utf-8")


def test_end_of_cron_fires(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kb.wiki_lint.JSONL_LOG_PATH", tmp_path / "fails.jsonl"
    )
    hashes = ["aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc"]
    conn = _seed_db(hashes)
    buf_dir = tmp_path / "entity_buffer"
    for h in hashes:
        _write_buffer(buf_dir, h, ["OpenClaw", "Hermes"])
    wiki_root = tmp_path / "wiki"
    (wiki_root / "entities").mkdir(parents=True)

    suggestions = generate_wiki_suggestions(
        hashes, wiki_root, conn, min_frequency=2, entity_buffer_dirs=[buf_dir]
    )
    assert len(suggestions) >= 1

    applied_count = 0
    for s in suggestions:
        if apply_suggestion_atomic(s, conn, wiki_root=wiki_root):
            applied_count += 1
    assert applied_count >= 1
    written = list((wiki_root / "entities").glob("*.md"))
    assert len(written) >= 1


def test_lint_blocks_unresolved_citation(tmp_path, monkeypatch):
    """Lint failure is recorded in Error Book (W5-0 Gate E), not JSONL.
    Unresolved citation blocks page creation — result is False, page not written."""
    db_path = tmp_path / "error_book.db"
    monkeypatch.setattr("kb.wiki_lint.JSONL_LOG_PATH", tmp_path / "unused.jsonl")
    # Prevent migration of real legacy JSONL
    monkeypatch.setattr("kb.error_book._LEGACY_JSONL", tmp_path / "nonexistent.jsonl")
    # Redirect Error Book to test path
    monkeypatch.setattr("kb.error_book._DEFAULT_DB_PATH", db_path)

    from kb.error_book import get_open_errors

    conn = _seed_db(["aaaaaaaaaa"])
    wiki_root = tmp_path / "wiki"
    (wiki_root / "entities").mkdir(parents=True)
    page_path = wiki_root / "entities" / "ghost.md"
    suggestion = {
        "type": "new",
        "entity_slug": "ghost",
        "page_path": str(page_path),
        "content": (
            "---\ntitle: Ghost\ncreated: 2026-05-19\nlast_updated: 2026-05-19\n"
            "sources:\n  - article:ffffffffff\nconfidence_level: low\n---\n\n"
            "# Ghost\n\nReferences ^[article:ffffffffff].\n"
        ),
        "source_articles": ["ffffffffff"],
    }
    result = apply_suggestion_atomic(suggestion, conn, wiki_root=wiki_root)
    assert result is False
    assert not page_path.exists()

    open_errors = get_open_errors(db_path=db_path)
    assert any(e["check_type"] == "lint_citation_integrity" for e in open_errors)

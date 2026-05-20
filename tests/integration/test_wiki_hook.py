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
    fails_path = tmp_path / "fails.jsonl"
    monkeypatch.setattr("kb.wiki_lint.JSONL_LOG_PATH", fails_path)
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
    assert fails_path.exists()
    lines = [json.loads(ln) for ln in fails_path.read_text(encoding="utf-8").splitlines()]
    assert any(e.get("lint_name") == "lint_citation_integrity" for e in lines)

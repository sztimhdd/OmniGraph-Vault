"""Verify classify→ingest bridge: classifications sync to articles.layer1_verdict.

Guards:
1. bridge promotes relevant>=min_depth articles to layer1_verdict='candidate'
2. bridge never demotes an existing candidate (promote-only)
3. bridge stamps layer1_prompt_version with PROMPT_VERSION_LAYER1
4. dry_run skips the bridge entirely
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from batch_classify_kol import run
from lib.article_filter import PROMPT_VERSION_LAYER1


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT, digest TEXT, account_id INTEGER,
            layer1_verdict TEXT, layer1_prompt_version TEXT, scanned_at TEXT
        );
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE classifications (
            article_id INTEGER, topic TEXT, depth_score INTEGER,
            relevant INTEGER, excluded INTEGER, reason TEXT,
            PRIMARY KEY (article_id, topic)
        );
        INSERT INTO accounts (id, name) VALUES (1, 'test-acc');
        -- reject article that should be promoted
        INSERT INTO articles (id, title, digest, account_id, layer1_verdict, layer1_prompt_version, scanned_at)
        VALUES (1, 'Agent Harness 工程实践', 'digest', 1, 'reject', 'old_v1', '2026-08-11');
        -- already-candidate article that must NOT be demoted
        INSERT INTO articles (id, title, digest, account_id, layer1_verdict, layer1_prompt_version, scanned_at)
        VALUES (2, 'already candidate', 'digest', 1, 'candidate', 'old_v1', '2026-08-11');
        -- NULL article
        INSERT INTO articles (id, title, digest, account_id, layer1_verdict, layer1_prompt_version, scanned_at)
        VALUES (3, 'null verdict article', 'digest', 1, NULL, NULL, '2026-08-11');
        """
    )
    conn.commit()
    conn.close()
    return db_path


def test_bridge_promotes_relevant_to_candidate(monkeypatch, db: Path) -> None:
    """relevant>=min_depth reject article becomes candidate; NULL too."""
    # Stub the classify LLM to return a relevant pass for article 1 & 3.
    monkeypatch.setattr(
        "batch_classify_kol._call_deepseek",
        lambda prompt, api_key: [
            {"index": 0, "depth": 2, "relevant": True, "reason": "ok"},
            {"index": 1, "depth": 2, "relevant": True, "reason": "ok"},
            {"index": 2, "depth": 2, "relevant": True, "reason": "ok"},
        ],
    )
    monkeypatch.setattr("batch_classify_kol.DB_PATH", db)
    # make init_db() open our file
    monkeypatch.setattr("batch_classify_kol.init_db", lambda: sqlite3.connect(str(db)))

    run("Harness", 2, "deepseek", dry_run=False)

    conn = sqlite3.connect(db)
    rows = {
        row[0]: (row[1], row[2])
        for row in conn.execute("SELECT id, layer1_verdict, layer1_prompt_version FROM articles")
    }
    conn.close()
    # article 1 (reject) promoted
    assert rows[1][0] == "candidate"
    assert rows[1][1] == PROMPT_VERSION_LAYER1
    # article 3 (NULL) promoted
    assert rows[3][0] == "candidate"
    # article 2 (already candidate) untouched — no demote
    assert rows[2][0] == "candidate"
    assert rows[2][1] == "old_v1"


def test_bridge_dry_run_skips_update(monkeypatch, db: Path) -> None:
    """dry_run=True must not write verdicts."""
    monkeypatch.setattr(
        "batch_classify_kol._call_deepseek",
        lambda prompt, api_key: [
            {"index": 0, "depth": 2, "relevant": True, "reason": "ok"},
        ],
    )
    monkeypatch.setattr("batch_classify_kol.DB_PATH", db)
    monkeypatch.setattr("batch_classify_kol.init_db", lambda: sqlite3.connect(str(db)))

    run("Harness", 2, "deepseek", dry_run=True)

    conn = sqlite3.connect(db)
    verdict = conn.execute("SELECT layer1_verdict FROM articles WHERE id=1").fetchone()[0]
    conn.close()
    assert verdict == "reject"  # untouched

"""Integration test for reindex_lightrag.py — requires Model Serving auth.

Gated behind @pytest.mark.dryrun — run only in CI with real credentials.
Verify with:
    pytest databricks-deploy/jobs/tests/test_reindex_integration.py -v -m dryrun

Estimated cost: $0.10-$1.00 per run (5 articles x LightRAG entity extraction).
"""
from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_JOBS_DIR = _TESTS_DIR.parent
_DEPLOY_DIR = _JOBS_DIR.parent
for _p in (str(_DEPLOY_DIR), str(_JOBS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from reindex_lightrag import _run_smallbatch  # noqa: E402

_CREATE_ARTICLES_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    content_hash TEXT,
    title TEXT,
    body TEXT,
    lang TEXT,
    layer1_verdict TEXT,
    layer2_verdict TEXT
)
"""
_CREATE_RSS_SQL = """
CREATE TABLE IF NOT EXISTS rss_articles (
    id INTEGER PRIMARY KEY,
    content_hash TEXT,
    title TEXT,
    body TEXT,
    lang TEXT,
    layer1_verdict TEXT,
    layer2_verdict TEXT
)
"""


@pytest.mark.dryrun
def test_smallbatch_against_fixture_db(tmp_path: Path) -> None:
    """Run _run_smallbatch with 5-article fixture DB against a tmp lightrag_dir.

    Acceptance:
      - Return value is 0 or 2 (NEVER unhandled exception)
      - kdb-2.5-smallbatch-stats.json is created under tmp output/ dir
    Cost: $0.10-$1.00 — only run with real Databricks credentials.
    """
    # Build a 5-article fixture DB
    db_path = tmp_path / "fixture.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(_CREATE_ARTICLES_SQL)
    conn.execute(_CREATE_RSS_SQL)

    articles = [
        ("a" * 32, "Article short",   "x" * 100,   "en"),
        ("b" * 32, "Article medium",  "y" * 500,   "zh"),
        ("c" * 32, "Article long",    "z" * 1000,  "en"),
        ("d" * 32, "Article vlong",   "w" * 5000,  "zh"),
        ("e" * 32, "Article longest", "v" * 10000, "en"),
    ]
    for i, (h, title, body, lang) in enumerate(articles, start=1):
        conn.execute(
            "INSERT INTO articles VALUES (?, ?, ?, ?, ?, 'candidate', NULL)",
            (i, h, title, body, lang),
        )
    conn.commit()
    conn.close()

    # Configure args to point to tmp paths
    lightrag_dir = str(tmp_path / "lightrag_storage")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    args = argparse.Namespace(
        db_path=str(db_path),
        lightrag_dir=lightrag_dir,
        filter_mode="strict",
        max_articles=5,
        force_overwrite=True,    # tmp dir — no safety concern
        shutdown_lightrag=True,
    )

    # Monkeypatch PROGRESS_CSV + FAILURES_CSV to tmp paths
    import reindex_lightrag as _mod
    orig_progress = _mod.PROGRESS_CSV
    orig_failures = _mod.FAILURES_CSV
    orig_volume_root = _mod.VOLUME_ROOT
    orig_step1 = _mod._STEP1_BASELINE_PATH

    try:
        _mod.PROGRESS_CSV = str(output_dir / "progress.csv")
        _mod.FAILURES_CSV = str(output_dir / "FAILURES.csv")
        _mod.VOLUME_ROOT = str(tmp_path)
        _mod._STEP1_BASELINE_PATH = str(output_dir / "kdb-2.5-smallbatch-stats.json")

        return_code = asyncio.run(_run_smallbatch(args))
    finally:
        _mod.PROGRESS_CSV = orig_progress
        _mod.FAILURES_CSV = orig_failures
        _mod.VOLUME_ROOT = orig_volume_root
        _mod._STEP1_BASELINE_PATH = orig_step1

    # Return 0 or 2 — never an unhandled exception
    assert return_code in (0, 2), (
        f"Expected return code 0 or 2, got {return_code}"
    )

    # Stats JSON must exist at tmp output path
    stats_path = tmp_path / "output" / "kdb-2.5-smallbatch-stats.json"
    assert stats_path.exists(), (
        f"kdb-2.5-smallbatch-stats.json should exist at {stats_path}"
    )

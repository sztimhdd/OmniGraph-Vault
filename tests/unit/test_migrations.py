"""Phase 4 SQLite migration tests — D-07 enriched state, enrichment_id, content_hash drift."""
from __future__ import annotations
import sqlite3
from pathlib import Path
import pytest
from batch_scan_kol import init_db


@pytest.mark.unit
def test_init_db_creates_enriched_column(tmp_path: Path):
    db = tmp_path / "k.db"
    conn = init_db(db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    assert "enriched" in cols
    assert "content_hash" in cols
    conn.close()


@pytest.mark.unit
def test_init_db_creates_enrichment_id_column(tmp_path: Path):
    db = tmp_path / "k.db"
    conn = init_db(db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ingestions)")}
    assert "enrichment_id" in cols
    conn.close()


@pytest.mark.unit
def test_init_db_is_idempotent(tmp_path: Path):
    db = tmp_path / "k.db"
    conn1 = init_db(db); conn1.close()
    # Second call must not raise (ALTER TABLE on existing column would error without guard)
    conn2 = init_db(db)
    cols = {row[1] for row in conn2.execute("PRAGMA table_info(articles)")}
    assert "enriched" in cols and "content_hash" in cols
    conn2.close()


@pytest.mark.unit
def test_enriched_default_is_zero(tmp_path: Path):
    db = tmp_path / "k.db"
    conn = init_db(db)
    conn.execute("INSERT INTO accounts (name, fakeid) VALUES ('X', 'fx1')")
    conn.execute(
        "INSERT INTO articles (account_id, title, url) VALUES (1, 't', 'http://example.com/1')"
    )
    row = conn.execute("SELECT enriched FROM articles WHERE url='http://example.com/1'").fetchone()
    assert row[0] == 0
    conn.close()

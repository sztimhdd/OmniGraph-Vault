"""DATA-02 v2: integration tests for kb.scripts.detect_article_lang backfill.

Tests idempotency and no-op behaviour for the detect_for_table driver
against a real SQLite DB using tmp_path fixture. Does NOT touch
.dev-runtime/data/kol_scan.db.

Skill(skill="writing-tests") — Testing Trophy: integration because the caller
updates SQL state; real SQLite via tmp_path; no mocks; both tests assert on
Counter return AND post-state SELECT.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kb.scripts.detect_article_lang import detect_for_table


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> tuple[Path, sqlite3.Connection]:
    """Create a tmp DB with articles table (id, title, body, lang)."""
    db_path = tmp_path / "test_backfill.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE articles "
        "(id INTEGER PRIMARY KEY, title TEXT, body TEXT, lang TEXT)"
    )
    conn.commit()
    return db_path, conn


# Fixture rows for mixed detection scenario
_CN_TITLE = "如何用 LightRAG 构建知识图谱"   # CJK in title → zh-CN
_EN_TITLE_EN_BODY = "LightRAG Tutorial"         # no CJK title, no CJK body
_EN_BODY_LONG = "word " * 30                    # 150 chars, no CJK → en
_KANA_TITLE = "カタカナのテスト"                # pure kana → NOT zh-CN


# ---------------------------------------------------------------------------
# Test 1: idempotency — second invocation produces zero UPDATEs
# ---------------------------------------------------------------------------


def test_detect_article_lang_script_idempotent_on_tmp_db(tmp_path: Path):
    """Run detect_for_table twice; second run returns empty Counter (idempotent).

    Seeds articles with:
    - Row 1: Chinese title, English body → expect zh-CN
    - Row 2: English title, English body (>50 chars) → expect en
    - Row 3: Kana title, English body → expect en (NOT zh-CN)
    """
    _, conn = _make_db(tmp_path)
    conn.execute(
        "INSERT INTO articles (id, title, body, lang) VALUES (1, ?, ?, NULL)",
        (_CN_TITLE, _EN_BODY_LONG),
    )
    conn.execute(
        "INSERT INTO articles (id, title, body, lang) VALUES (2, ?, ?, NULL)",
        (_EN_TITLE_EN_BODY, _EN_BODY_LONG),
    )
    conn.execute(
        "INSERT INTO articles (id, title, body, lang) VALUES (3, ?, ?, NULL)",
        (_KANA_TITLE, _EN_BODY_LONG),
    )
    conn.commit()

    # First run — classifies all 3 rows
    first = detect_for_table(conn, "articles")
    assert first["zh-CN"] == 1
    assert first["en"] == 2
    assert sum(first.values()) == 3

    # Verify post-state
    rows = {r[0]: r[1] for r in conn.execute("SELECT id, lang FROM articles")}
    assert rows[1] == "zh-CN"
    assert rows[2] == "en"
    assert rows[3] == "en"   # kana title → en, not zh-CN

    # Second run — idempotent (WHERE lang IS NULL matches nothing)
    second = detect_for_table(conn, "articles")
    assert second == {}

    conn.close()


# ---------------------------------------------------------------------------
# Test 2: pre-classified row not overwritten (no-op on already-correct rows)
# ---------------------------------------------------------------------------


def test_backfill_does_not_change_already_correct_lang(tmp_path: Path):
    """Row with lang already set is skipped (WHERE lang IS NULL does not match).

    Seeds:
    - Row 1: Chinese title, lang='zh-CN' (already classified) → must NOT change
    - Row 2: English title, lang=NULL → must be classified to 'en'
    """
    _, conn = _make_db(tmp_path)
    conn.execute(
        "INSERT INTO articles (id, title, body, lang) VALUES (1, ?, ?, 'zh-CN')",
        (_CN_TITLE, _EN_BODY_LONG),
    )
    conn.execute(
        "INSERT INTO articles (id, title, body, lang) VALUES (2, ?, ?, NULL)",
        (_EN_TITLE_EN_BODY, _EN_BODY_LONG),
    )
    conn.commit()

    result = detect_for_table(conn, "articles")

    # Only 1 UPDATE issued (row 2); row 1 was pre-classified and skipped
    assert result == {"en": 1}

    rows = {r[0]: r[1] for r in conn.execute("SELECT id, lang FROM articles")}
    assert rows[1] == "zh-CN"   # unchanged
    assert rows[2] == "en"

    conn.close()

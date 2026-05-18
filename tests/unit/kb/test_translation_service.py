"""Unit tests for kb.services.translation — kb-v2.2-2 F1'.

Coverage:
  1. TranslateResult dataclass properties
  2. translate_article: not_found → error
  3. translate_article: not_eligible (layer1_verdict != candidate) → error
  4. translate_article: same_lang → error
  5. translate_article: idempotent (already translated) → ok, no LLM call
  6. translate_article: success → stores translation in DB
  7. translate_article: NULL content_hash fallback (runtime md5 path)
  8. _strip_llm_wrapper: prefix + quote removal

Real SQLite in-memory; LLM mocked via monkeypatch on lib.llm_complete.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock

import pytest

from kb.services.translation import TranslateResult, _strip_llm_wrapper, translate_article


# ---- Helpers ----------------------------------------------------------------


def _make_articles_db(tmp_path: Path, *, article_id: int = 1) -> Path:
    """Minimal SQLite with articles table + translation columns.

    Returns db_path pointing at a file with one eligible KOL article.
    """
    db_path = tmp_path / "test.db"
    body = "# 人工智能进展\n\n大语言模型的最新发展趋势和应用场景。"
    content_hash = hashlib.md5(body.encode("utf-8")).hexdigest()[:10]
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT,
            body TEXT,
            content_hash TEXT,
            lang TEXT,
            update_time INTEGER,
            layer1_verdict TEXT,
            layer2_verdict TEXT,
            body_translated TEXT,
            title_translated TEXT,
            translated_lang VARCHAR(5),
            translated_at DATETIME
        );
        """
    )
    conn.execute(
        "INSERT INTO articles (id,title,url,body,content_hash,lang,update_time,layer1_verdict,layer2_verdict) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            article_id,
            "人工智能进展",
            "https://mp.weixin.qq.com/s/test1",
            body,
            content_hash,
            "zh-CN",
            1778270400,
            "candidate",
            "ok",
        ),
    )
    conn.commit()
    conn.close()
    return db_path


def _add_reject_article(db_path: Path, article_id: int = 2) -> str:
    """Insert a layer1_verdict='reject' article; returns its content_hash."""
    body = "Short rejected content."
    content_hash = hashlib.md5(body.encode("utf-8")).hexdigest()[:10]
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO articles (id,title,url,body,content_hash,lang,update_time,layer1_verdict) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (article_id, "Rejected Article", "https://mp.weixin.qq.com/s/reject", body, content_hash, "zh-CN", 1000, "reject"),
    )
    conn.commit()
    conn.close()
    return content_hash


def _get_translation_row(db_path: Path, article_id: int) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT body_translated, title_translated, translated_lang, translated_at FROM articles WHERE id=?",
        (article_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _article_hash(db_path: Path, article_id: int) -> str:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT content_hash, body FROM articles WHERE id=?", (article_id,)).fetchone()
    conn.close()
    if row[0]:
        return row[0]
    return hashlib.md5((row[1] or "").encode("utf-8")).hexdigest()[:10]


# ---- Tests ------------------------------------------------------------------


def test_translate_result_ok_fields() -> None:
    r = TranslateResult(ok=True, translated_lang="en")
    assert r.ok is True
    assert r.translated_lang == "en"
    assert r.error is None


def test_translate_result_error_fields() -> None:
    r = TranslateResult(ok=False, translated_lang="en", error="not_found")
    assert r.ok is False
    assert r.error == "not_found"


@pytest.mark.asyncio
async def test_translate_article_not_found(tmp_path: Path) -> None:
    db_path = _make_articles_db(tmp_path)
    result = await translate_article("nonexistent0", "en", db_path=str(db_path))
    assert result.ok is False
    assert result.error == "not_found"


@pytest.mark.asyncio
async def test_translate_article_not_eligible(tmp_path: Path) -> None:
    db_path = _make_articles_db(tmp_path)
    reject_hash = _add_reject_article(db_path)
    result = await translate_article(reject_hash, "en", db_path=str(db_path))
    assert result.ok is False
    assert "not_eligible" in (result.error or "")


@pytest.mark.asyncio
async def test_translate_article_same_lang(tmp_path: Path) -> None:
    db_path = _make_articles_db(tmp_path)
    article_hash = _article_hash(db_path, 1)
    result = await translate_article(article_hash, "zh-CN", db_path=str(db_path))
    assert result.ok is False
    assert result.error == "same_lang"


@pytest.mark.asyncio
async def test_translate_article_idempotent_no_llm_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _make_articles_db(tmp_path)
    article_hash = _article_hash(db_path, 1)

    # Pre-seed translation into DB
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE articles SET body_translated=?, title_translated=?, translated_lang=?, translated_at=? WHERE id=1",
        ("AI Progress", "Existing title translation", "en", "2026-01-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()

    # LLM mock should NOT be called
    llm_called = False

    async def fake_llm(prompt: str, **_) -> str:
        nonlocal llm_called
        llm_called = True
        return "should not be called"

    monkeypatch.setattr("lib.llm_complete.get_llm_func", lambda: fake_llm)

    result = await translate_article(article_hash, "en", db_path=str(db_path))
    assert result.ok is True
    assert llm_called is False


@pytest.mark.asyncio
async def test_translate_article_success_stores_to_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _make_articles_db(tmp_path)
    article_hash = _article_hash(db_path, 1)

    async def fake_llm(prompt: str, **_) -> str:
        if "title" in prompt.lower():
            return "AI Advances"
        return "The latest developments in large language models and their applications."

    monkeypatch.setattr("lib.llm_complete.get_llm_func", lambda: fake_llm)

    result = await translate_article(article_hash, "en", db_path=str(db_path))
    assert result.ok is True
    assert result.translated_lang == "en"

    row = _get_translation_row(db_path, 1)
    assert row is not None
    assert row["translated_lang"] == "en"
    assert row["body_translated"] and len(row["body_translated"]) > 0
    assert row["title_translated"] and len(row["title_translated"]) > 0
    assert row["translated_at"] is not None


@pytest.mark.asyncio
async def test_translate_article_null_hash_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Article with NULL content_hash is matched via runtime md5(body)[:10]."""
    db_path = _make_articles_db(tmp_path)
    # Blank out content_hash to force NULL-hash code path
    body = "# 人工智能进展\n\n大语言模型的最新发展趋势和应用场景。"
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE articles SET content_hash=NULL WHERE id=1")
    conn.commit()
    conn.close()

    runtime_hash = hashlib.md5(body.encode("utf-8")).hexdigest()[:10]

    async def fake_llm(prompt: str, **_) -> str:
        return "translated text"

    monkeypatch.setattr("lib.llm_complete.get_llm_func", lambda: fake_llm)

    result = await translate_article(runtime_hash, "en", db_path=str(db_path))
    assert result.ok is True


def test_strip_llm_wrapper_removes_translation_prefix() -> None:
    assert _strip_llm_wrapper("Translation: 人工智能进展") == "人工智能进展"
    assert _strip_llm_wrapper("Translated title: AI Advances") == "AI Advances"


def test_strip_llm_wrapper_removes_surrounding_quotes() -> None:
    assert _strip_llm_wrapper('"AI Advances"') == "AI Advances"
    assert _strip_llm_wrapper("'AI Advances'") == "AI Advances"


def test_strip_llm_wrapper_passthrough() -> None:
    assert _strip_llm_wrapper("AI Advances") == "AI Advances"
    assert _strip_llm_wrapper("  AI Advances  ") == "AI Advances"

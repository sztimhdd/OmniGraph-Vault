"""FTS5 search index helpers — SEARCH-01, SEARCH-03, DATA-07.

The `articles_fts` virtual table uses SQLite's built-in trigram tokenizer
(D-18 — works for both Chinese and English without jieba). UNION-fed from
`articles` (KOL) and `rss_articles`. Nightly rebuild script lives in kb-3-07.

Per kb-3-CONTENT-QUALITY-DECISIONS.md "Open question — search results filtering":
    Decision: apply DATA-07 filter to FTS5 hits by default; expose
    `KB_SEARCH_BYPASS_QUALITY=on` env override for power users / admin debugging.
    Same pattern as KB_CONTENT_QUALITY_FILTER but scoped to search.

Skill discipline (kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):

    Skill(skill="python-patterns", args="Two service modules: kb/services/search_index.py wraps the FTS5 virtual-table operations (ensure_fts_table, fts_query). Use sqlite3 with parameterized queries — `tokenize='trigram'` is the locked tokenizer per D-18. fts_query MUST honor SEARCH-03 lang filter via WHERE clause + DATA-07 conditional via KB_SEARCH_BYPASS_QUALITY env. snippet() function used for highlighted excerpt — trim to 200 chars max with explicit Python slicing. NO new env vars except KB_SEARCH_BYPASS_QUALITY (per kb-3-CONTENT-QUALITY-DECISIONS.md decision).")

    Skill(skill="writing-tests", args="Unit tests use in-memory sqlite3 + manual articles + rss_articles + extracted articles_fts; verifies index creation idempotent, query returns hits with snippet, lang filter, DATA-07 default + bypass.")
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional

# ---- Constants -------------------------------------------------------------

FTS_TABLE_NAME = "articles_fts"

# Read once per process at import time (cheap; matches kb.data.article_query
# QUALITY_FILTER_ENABLED pattern). Tests reload this module to flip the value.
SEARCH_BYPASS_QUALITY: bool = (
    os.environ.get("KB_SEARCH_BYPASS_QUALITY", "off").lower() == "on"
)


# ---- Public API ------------------------------------------------------------


def ensure_fts_table(conn: sqlite3.Connection) -> None:
    """Create the `articles_fts` virtual table if absent (idempotent).

    Schema:
        - hash    (UNINDEXED — md5[:10] used by /api/article/{hash})
        - title   (indexed)
        - body    (indexed)
        - lang    (UNINDEXED — for lang filter)
        - source  (UNINDEXED — 'wechat' | 'rss')
        - tokenize='trigram' (D-18: works for zh + en without jieba)
    """
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE_NAME} USING fts5("
        "hash UNINDEXED, title, body, lang UNINDEXED, source UNINDEXED, "
        "tokenize='trigram')"
    )


def fts_query(
    q: str,
    lang: Optional[str] = None,
    limit: int = 20,
    conn: Optional[sqlite3.Connection] = None,
) -> list[tuple[str, str, str, Optional[str], str]]:
    """SEARCH-01: FTS5 trigram query against `articles_fts`.

    Args:
        q: search query (FTS5 syntax — trigram tokenizer handles substrings)
        lang: optional content-language filter ('zh-CN' | 'en' | 'unknown')
        limit: max rows returned
        conn: optional injected connection (for tests); else opens read-only
              against `kb.config.KB_DB_PATH`.

    Returns:
        List of (hash, title, snippet, lang, source) tuples.
        `snippet` is the FTS5 ``snippet()`` output trimmed to 200 chars.

    Behavior:
        - SEARCH-03: when ``lang`` is non-None, excludes rows whose lang differs
        - DATA-07: applies content-quality filter to hits unless
          ``KB_SEARCH_BYPASS_QUALITY=on`` (read at import time)
    """
    own = False
    if conn is None:
        from kb import config

        conn = sqlite3.connect(f"file:{config.KB_DB_PATH}?mode=ro", uri=True)
        own = True
    try:
        # snippet(table, col_idx, prefix, suffix, ellipsis, max_tokens)
        # col_idx = -1 means "match in any indexed column".
        sql = (
            f"SELECT f.hash, f.title, "
            f"snippet({FTS_TABLE_NAME}, -1, '<b>', '</b>', '…', 32) AS snippet, "
            f"f.lang, f.source "
            f"FROM {FTS_TABLE_NAME} f "
            f"WHERE {FTS_TABLE_NAME} MATCH ? "
        )
        params: list = [q]
        if lang is not None:
            sql += "AND f.lang = ? "
            params.append(lang)
        if not SEARCH_BYPASS_QUALITY:
            # DATA-07: hash matches articles.content_hash (KOL) OR
            # substr(rss_articles.content_hash, 1, 10) (RSS).
            sql += (
                "AND ((f.source = 'wechat' AND EXISTS ("
                "  SELECT 1 FROM articles a WHERE a.content_hash = f.hash "
                "  AND a.body IS NOT NULL AND a.body != '' "
                "  AND a.layer1_verdict = 'candidate' "
                "  AND (a.layer2_verdict IS NULL OR a.layer2_verdict != 'reject')"
                ")) "
                "OR (f.source = 'rss' AND EXISTS ("
                "  SELECT 1 FROM rss_articles r WHERE substr(r.content_hash, 1, 10) = f.hash "
                "  AND r.body IS NOT NULL AND r.body != '' "
                "  AND r.layer1_verdict = 'candidate' "
                "  AND (r.layer2_verdict IS NULL OR r.layer2_verdict != 'reject')"
                "))) "
            )
        sql += "ORDER BY rank LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        # Trim FTS5 snippet (up to 32 tokens) to 200 chars per API-CONTRACT §5.3.
        return [
            (r[0], r[1] or "", (r[2] or "")[:200], r[3], r[4])
            for r in rows
        ]
    finally:
        if own:
            conn.close()

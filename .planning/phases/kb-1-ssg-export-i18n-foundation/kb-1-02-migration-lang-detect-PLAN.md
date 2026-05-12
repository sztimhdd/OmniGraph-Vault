---
phase: kb-1-ssg-export-i18n-foundation
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/scripts/migrate_lang_column.py
  - kb/data/lang_detect.py
  - tests/unit/kb/test_lang_detect.py
  - tests/unit/kb/test_migrate_lang_column.py
autonomous: true
requirements:
  - DATA-01
  - DATA-02

must_haves:
  truths:
    - "Running `python -m kb.scripts.migrate_lang_column` adds nullable `lang TEXT` column to both `articles` and `rss_articles`"
    - "Re-running the migration is a no-op (zero ALTER TABLE statements issued, exits 0)"
    - "`detect_lang(text)` returns 'zh-CN' for >30% Chinese chars, 'en' otherwise, 'unknown' for text < 200 chars"
    - "Both schema-extending changes are NON-BREAKING per C3 contract"
  artifacts:
    - path: "kb/scripts/migrate_lang_column.py"
      provides: "Idempotent SQLite migration adding `lang TEXT` to articles + rss_articles"
      contains: "PRAGMA table_info"
    - path: "kb/data/lang_detect.py"
      provides: "detect_lang(text: str) -> Literal['zh-CN', 'en', 'unknown']"
      exports: ["detect_lang", "chinese_char_ratio"]
  key_links:
    - from: "kb/scripts/migrate_lang_column.py"
      to: "kb.config.KB_DB_PATH"
      via: "from kb import config"
      pattern: "from kb import config|config.KB_DB_PATH"
    - from: "kb/data/lang_detect.py"
      to: "(stdlib only — no DB, no network)"
      via: "pure function"
---

<objective>
Deliver the schema migration (`articles.lang` + `rss_articles.lang` nullable TEXT columns) and the language-detection helper. These are independent of CONFIG-01's runtime values for unit testing (the migration script reads `KB_DB_PATH` from config; the detector is pure Python).

Purpose: Without populated `lang` columns, the article query layer (DATA-04..06) cannot filter by content language, and the i18n badge (I18N-05/06) has no source data. DATA-01 is C3-additive non-breaking; DATA-02 is the algorithm only — the driver script that walks the DB lives in plan kb-1-04.

Output: Two source files (migration + detector lib) + their unit tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@enrichment/rss_schema.py
@CLAUDE.md

<interfaces>
**Pattern to mirror — `enrichment/rss_schema.py:_ensure_rss_columns` (the canonical idempotent ALTER pattern in this codebase):**

```python
# Existing pattern (DO NOT modify; mirror it):
def _ensure_rss_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(rss_articles)")}
    for col_name, col_type in _PHASE19_RSS_ARTICLES_ADDITIONS:
        if col_name not in existing:
            conn.execute(
                f"ALTER TABLE rss_articles ADD COLUMN {col_name} {col_type}"
            )
    conn.commit()
```

The migration script in this plan must use the same `PRAGMA table_info` pre-check + per-column ALTER style.

**SQLite schema fact (from kb/docs/09-AGENT-QA-HANDBOOK.md verified against live data/kol_scan.db):**
- Table `articles` exists with primary KOL article rows (~756 rows)
- Table `rss_articles` exists (~1687 rows) with full md5 in `content_hash`
- Neither currently has a `lang` column

**Detector algorithm (from CONTEXT.md § "Lang detection algorithm (DATA-02)"):**
- Chinese char range: `'一' <= c <= '鿿'` (CJK Unified Ideographs basic — covers 99% of zh corpus)
- Threshold: ratio > 0.30 → `zh-CN`, else `en`
- Insufficient sample: `len(text) < 200` → `unknown`
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write kb/data/lang_detect.py with detect_lang() + chinese_char_ratio() + tests</name>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md § "Lang detection algorithm (DATA-02)"
    - .planning/REQUIREMENTS-KB-v2.md § DATA-02 (exact REQ wording)
    - .claude/rules/python/coding-style.md (PEP 8 + type annotations required)
  </read_first>
  <files>kb/data/lang_detect.py, tests/unit/kb/test_lang_detect.py</files>
  <behavior>
    - Test 1: `chinese_char_ratio("人工智能 Agent 框架对比 LangChain CrewAI")` returns float in (0.3, 0.6) range
    - Test 2: `chinese_char_ratio("LangGraph and CrewAI compared")` returns 0.0
    - Test 3: `chinese_char_ratio("")` returns 0.0 (empty string, no division-by-zero)
    - Test 4: `chinese_char_ratio("纯中文文章" * 100)` returns 1.0 (all Chinese chars)
    - Test 5: `detect_lang("LangGraph framework architecture deep dive ..." * 20)` returns `"en"` (long English text)
    - Test 6: `detect_lang("人工智能 Agent 框架解析 ..." * 30)` returns `"zh-CN"` (long Chinese text)
    - Test 7: `detect_lang("short text")` returns `"unknown"` (< 200 chars)
    - Test 8: `detect_lang("")` returns `"unknown"` (empty)
    - Test 9: `detect_lang("a" * 250)` returns `"en"` (long enough, 0% Chinese)
    - Test 10: `detect_lang("中" * 250)` returns `"zh-CN"` (long enough, 100% Chinese)
  </behavior>
  <action>
    Create `kb/data/lang_detect.py` with this exact content:

    ```python
    """DATA-02: Chinese vs English language detection by char ratio.

    Algorithm (locked in CONTEXT.md):
    - Chinese char ratio > 30% → 'zh-CN'
    - Chinese char ratio <= 30% → 'en'
    - Text length < 200 chars → 'unknown' (insufficient sample)

    Pure function, no DB, no network. The driver script that walks the DB
    and updates rows lives in kb/scripts/detect_article_lang.py (plan kb-1-04).
    """
    from __future__ import annotations

    from typing import Literal

    LangCode = Literal["zh-CN", "en", "unknown"]

    # CJK Unified Ideographs basic block. 0x4e00-0x9fff covers 99% of modern
    # Chinese articles in this corpus. Extension blocks (3400-4dbf, 20000-2a6df)
    # are rare in tech KOL writing — accept the ~1% false-negative rate over
    # adding `unicodedata` import + slower per-char lookup.
    _CJK_LO = "一"
    _CJK_HI = "鿿"

    MIN_TEXT_LEN: int = 200
    ZH_THRESHOLD: float = 0.30


    def chinese_char_ratio(text: str) -> float:
        """Return ratio of Chinese chars in text. Empty string → 0.0 (no div-by-zero)."""
        if not text:
            return 0.0
        cjk_count = sum(1 for c in text if _CJK_LO <= c <= _CJK_HI)
        return cjk_count / len(text)


    def detect_lang(text: str) -> LangCode:
        """Detect language by Chinese char ratio.

        Returns:
            'zh-CN' if Chinese char ratio > 30% AND len(text) >= 200
            'en' if Chinese char ratio <= 30% AND len(text) >= 200
            'unknown' if len(text) < 200
        """
        if len(text) < MIN_TEXT_LEN:
            return "unknown"
        return "zh-CN" if chinese_char_ratio(text) > ZH_THRESHOLD else "en"
    ```

    Then create `tests/unit/kb/test_lang_detect.py` with all 10 behaviors above using pytest.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_lang_detect.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `kb/data/lang_detect.py` exists; `python -c "from kb.data.lang_detect import detect_lang; print(detect_lang('a'*300))"` outputs `en`
    - `python -c "from kb.data.lang_detect import detect_lang; print(detect_lang('中'*300))"` outputs `zh-CN`
    - `python -c "from kb.data.lang_detect import detect_lang; print(detect_lang('short'))"` outputs `unknown`
    - `pytest tests/unit/kb/test_lang_detect.py -v` exits 0 with 10 tests passing
    - File contains exact strings: `"一"`, `"鿿"`, `MIN_TEXT_LEN: int = 200`, `ZH_THRESHOLD: float = 0.30`
    - No `import sqlite3`, no `import requests`, no `os.environ` calls (pure function module)
  </acceptance_criteria>
  <done>10 tests pass, detect_lang is pure-function and importable.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write kb/scripts/migrate_lang_column.py — idempotent ALTER for both tables + tests</name>
  <read_first>
    - enrichment/rss_schema.py (lines 60-95 — the `_ensure_rss_columns` pattern this script must mirror exactly)
    - kb/config.py (already created in plan kb-1-01 — to read KB_DB_PATH)
    - .planning/REQUIREMENTS-KB-v2.md § DATA-01 (idempotency requirement)
  </read_first>
  <files>kb/scripts/migrate_lang_column.py, tests/unit/kb/test_migrate_lang_column.py</files>
  <behavior>
    - Test 1: On a fresh in-memory SQLite with `articles` (id, title, body) and `rss_articles` (id, title, body) created — running `migrate_lang_column(conn)` adds `lang TEXT` to BOTH tables. After: `PRAGMA table_info(articles)` shows `lang` column.
    - Test 2: Running `migrate_lang_column(conn)` a second time on the same DB executes ZERO `ALTER TABLE` statements. Verified by spying on `conn.execute` calls (count of ALTER statements stays at 2 after first run, stays at 2 after second run).
    - Test 3: When ONLY one of the two tables already has `lang` (asymmetric pre-state), the migration adds `lang` to the other table only. (Edge case: a partial prior run.)
    - Test 4: When neither `articles` nor `rss_articles` table exists in the DB, the function exits cleanly without error (returns silently — there's nothing to migrate; this is the "fresh empty DB" case).
    - Test 5: CLI invocation `python -m kb.scripts.migrate_lang_column` with monkeypatched `KB_DB_PATH` pointing at a temp DB exits 0 and leaves both tables migrated.
  </behavior>
  <action>
    Create `kb/scripts/migrate_lang_column.py` with this exact content:

    ```python
    """DATA-01: One-time SQLite migration adding nullable `lang TEXT` column to
    `articles` and `rss_articles` tables.

    Idempotent: re-running issues zero ALTER TABLE statements (uses PRAGMA table_info
    pre-check, mirrors the pattern in enrichment/rss_schema.py:_ensure_rss_columns).

    Schema-extending non-breaking (C3 contract preserved).
    """
    from __future__ import annotations

    import sqlite3
    import sys
    from pathlib import Path

    from kb import config

    _TARGETS: tuple[tuple[str, str, str], ...] = (
        ("articles", "lang", "TEXT"),
        ("rss_articles", "lang", "TEXT"),
    )


    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return row is not None


    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        return column in cols


    def migrate_lang_column(conn: sqlite3.Connection) -> dict[str, str]:
        """Add `lang TEXT` to articles + rss_articles if absent. Idempotent.

        Returns:
            dict mapping table name → action ('added' | 'already_present' | 'table_missing')
        """
        results: dict[str, str] = {}
        for table, col, col_type in _TARGETS:
            if not _table_exists(conn, table):
                results[table] = "table_missing"
                continue
            if _column_exists(conn, table, col):
                results[table] = "already_present"
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            results[table] = "added"
        conn.commit()
        return results


    def main() -> int:
        db_path: Path = config.KB_DB_PATH
        if not db_path.exists():
            print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
            return 1
        with sqlite3.connect(db_path) as conn:
            results = migrate_lang_column(conn)
        for table, action in results.items():
            print(f"  {table}: {action}")
        print(f"Migration complete (DB: {db_path})")
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```

    Then create `tests/unit/kb/test_migrate_lang_column.py` with the 5 behaviors above. Use `sqlite3.connect(":memory:")` for tests 1-4. For test 5, use `tmp_path` fixture to create a real file DB and monkeypatch `kb.config.KB_DB_PATH`. Use `subprocess.run` or call `main()` directly with monkeypatched env.

    Per CLAUDE.md: use `print()` only in CLI scripts (this is one) — `migrate_lang_column()` is a library function, no print. The `main()` function may print operational status.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/unit/kb/test_migrate_lang_column.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `kb/scripts/migrate_lang_column.py` exists; imports without error
    - `pytest tests/unit/kb/test_migrate_lang_column.py -v` exits 0 with 5 tests passing
    - File contains string `PRAGMA table_info` (verifies pattern adopted from rss_schema.py)
    - File contains string `ALTER TABLE` exactly twice (one for each target table — visible in the loop) — count check via `grep -c "ALTER TABLE" kb/scripts/migrate_lang_column.py` returns 1 (it appears once textually inside the f-string)
    - `python -m kb.scripts.migrate_lang_column` runs against a missing DB and exits 1 with `ERROR: DB not found` on stderr (negative-path acceptance)
    - When run against a populated test DB, second invocation produces output `articles: already_present` and `rss_articles: already_present` (idempotency proven via output)
  </acceptance_criteria>
  <done>Migration script idempotent, 5 tests pass, mirrors rss_schema.py pattern.</done>
</task>

</tasks>

<verification>
- `pytest tests/unit/kb/test_lang_detect.py tests/unit/kb/test_migrate_lang_column.py -v` exits 0 with 15 tests passing
- Module `kb.scripts.migrate_lang_column` runnable as `-m` script
- Module `kb.data.lang_detect` is a pure function module (no DB, no I/O)
</verification>

<success_criteria>
- DATA-01 satisfied: idempotent migration script for both tables
- DATA-02 satisfied (algorithm only — driver in kb-1-04): pure detector function with documented thresholds
- 15 unit tests pass
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-02-SUMMARY.md` documenting:
- Files created
- Test count + pass status
- Idempotency proof (re-run output)
- Pattern reference: confirms mirroring of `enrichment/rss_schema.py`
</output>

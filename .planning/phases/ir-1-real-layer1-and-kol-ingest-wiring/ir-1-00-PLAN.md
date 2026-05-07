---
phase: ir-1-real-layer1-and-kol-ingest-wiring
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/article_filter.py
  - migrations/006_layer1_columns.sql
  - migrations/006_layer1_columns.py
autonomous: true
requirements:
  - LF-1.1
  - LF-1.2
  - LF-1.3
  - LF-1.4
  - LF-1.5
  - LF-1.6
  - LF-1.7
  - LF-1.8

must_haves:
  truths:
    - "lib/article_filter.py exposes a NEW batch contract: layer1_pre_filter(articles: list[ArticleMeta]) -> list[FilterResult] is async, takes up to 30 articles, returns 1:1 with input order"
    - "FilterResult has 3 fields: verdict (Literal['candidate','reject'] | None), reason (str), prompt_version (str). The placeholder's 2-field passed/reason shape is REMOVED — Foundation Quick docstring's 'do not change these signatures' is overruled by REQ LF-1.1"
    - "ArticleMeta is a frozen dataclass: id (int), source (Literal['wechat','rss']), title (str), summary (str | None), content_length (int | None)"
    - "Layer 1 prompt body is the verbatim text from PROJECT-v3.5-Ingest-Refactor.md § 'Layer 1 v0 Prompt' — not a paraphrase, not a refactor; the 30-article spike at .scratch/layer1-validation-20260507-151608.md is invalidated if the prompt is edited"
    - "PROMPT_VERSION_LAYER1 = 'layer1_v0_20260507' is a module-level constant in lib/article_filter.py — every persisted row carries this value in articles.layer1_prompt_version / rss_articles.layer1_prompt_version"
    - "Layer 1 LLM call is routed through lib.vertex_gemini_complete.vertex_gemini_model_complete when OMNIGRAPH_LLM_PROVIDER='vertex_gemini', else through lib.gemini_model_complete (legacy free-tier API key path) — no new env var introduced (LF-1.3 verbatim)"
    - "Per-call timeout for Layer 1 is 30s (validated spike: 8s wall-clock; 30s = 2× safety + 503-retry budget). Implementation: temporarily set OMNIGRAPH_LLM_TIMEOUT_SEC=30 in os.environ around the call OR pass timeout via genai config; do NOT introduce OMNIGRAPH_LAYER1_TIMEOUT_SEC env var"
    - "Failure modes (LF-1.5): timeout / non-JSON / partial JSON / row-count-mismatch all return FilterResult(verdict=None, reason=<error_class>, prompt_version=PROMPT_VERSION_LAYER1) for EVERY article in the batch — no partial-batch persistence"
    - "Persistence helper persist_layer1_verdicts(conn, articles, results) groups by source (wechat → articles, rss → rss_articles), executes ONE UPDATE per source-table inside ONE transaction, rolls back on any error. Only the 4 layer1_* columns are written; other columns untouched (LF-1.7)"
    - "Migration 006 (.sql + .py runner) is additive and idempotent: PRAGMA table_info guard before each ALTER TABLE ADD COLUMN. Adds 4 columns × 2 tables = 8 columns. Existing rows: all four columns NULL. Migration runs cleanly on a fresh DB and on a previously-migrated DB"
  artifacts:
    - path: "lib/article_filter.py"
      provides: "Real Layer 1 (batch async LLM call) + ArticleMeta + new FilterResult shape + PROMPT_VERSION_LAYER1 constant + persist_layer1_verdicts helper. Layer 2 stub stays in place but its FilterResult contract migrates to the new 3-field shape (verdict='candidate' as placeholder always-pass returning candidate verdict to keep ingest loop's downstream Layer 2 wiring happy until ir-2)"
      contains: "PROMPT_VERSION_LAYER1 = \"layer1_v0_20260507\""
      exports: ["ArticleMeta", "FilterResult", "layer1_pre_filter", "layer2_full_body_score", "persist_layer1_verdicts", "PROMPT_VERSION_LAYER1"]
    - path: "migrations/006_layer1_columns.sql"
      provides: "ALTER TABLE statements (idempotent via PRAGMA guard) adding 8 layer1_* columns across articles + rss_articles"
      min_lines: 25
      contains: "ALTER TABLE articles ADD COLUMN layer1_verdict TEXT"
    - path: "migrations/006_layer1_columns.py"
      provides: "Idempotent runner mirroring 002/003 pattern. PRAGMA-guards each ALTER. CLI: python migrations/006_layer1_columns.py [db_path]"
      min_lines: 60
      contains: "def migrate(db_path: str) -> bool"
  key_links:
    - from: "lib/article_filter.layer1_pre_filter"
      to: "lib.vertex_gemini_complete.vertex_gemini_model_complete"
      via: "import + await"
      pattern: "from lib.vertex_gemini_complete import vertex_gemini_model_complete"
    - from: "lib/article_filter.persist_layer1_verdicts"
      to: "articles.layer1_* / rss_articles.layer1_* columns"
      via: "UPDATE statement grouped by source"
      pattern: "UPDATE articles SET layer1_verdict = ?, layer1_reason = ?, layer1_at = ?, layer1_prompt_version = ? WHERE id = ?"
    - from: "migrations/006_layer1_columns.py"
      to: "data/kol_scan.db schema"
      via: "ALTER TABLE ADD COLUMN with PRAGMA table_info guard"
      pattern: "PRAGMA table_info(articles)"
---

<objective>
Wave 1: replace the always-pass Layer 1 placeholder with a real Gemini Flash Lite batch call against the validated v0 prompt; persist verdicts atomically on `articles.layer1_*` / `rss_articles.layer1_*`; ship migration 006 (.sql + idempotent .py runner).

This plan deliberately also rewrites `FilterResult`'s shape and `layer1_pre_filter`'s signature to match REQ LF-1.1 — Foundation Quick's placeholder shape is discarded. ir-1-01 (ingest loop refactor) and ir-1-02 (unit tests) depend on this new shape.

Output: `lib/article_filter.py` carries real Layer 1 + new contract; `migrations/006_*` lands schema additions; layer 2 placeholder stays always-pass but adopts the new 3-field FilterResult shape so downstream Layer 2 wiring works in ir-1-01 (real Layer 2 ships in ir-2).
</objective>

<execution_context>
@.planning/PROJECT-v3.5-Ingest-Refactor.md
@.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md
@.planning/ROADMAP-v3.5-Ingest-Refactor.md
</execution_context>

<context>
@.planning/STATE-v3.5-Ingest-Refactor.md
@CLAUDE.md
</context>

<interfaces>
<!-- Existing symbols this plan REUSES (read-only). -->

From `lib/vertex_gemini_complete.py`:
```python
async def vertex_gemini_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    keyword_extraction: bool = False,
    **kwargs: Any,
) -> str: ...
```
- Reads `OMNIGRAPH_LLM_MODEL` (default `gemini-3.1-flash-lite-preview` per `_DEFAULT_MODEL`)
- Reads `OMNIGRAPH_LLM_TIMEOUT_SEC` (default 600)
- Built-in 503 retry × 4 with backoff; non-503 ServerError propagates immediately
- Returns plain string — caller parses JSON

From `lib.gemini_model_complete` (legacy path; symbol path `from lib import gemini_model_complete`):
- Same signature shape (LightRAG-compatible) — used when `OMNIGRAPH_LLM_PROVIDER` is not `vertex_gemini`
- Wired through Gemini API key (`OMNIGRAPH_GEMINI_KEY` / `GEMINI_API_KEY`)

From SQLite (data/kol_scan.db):
- `articles` table: existing columns include `id, account_id, title, url, body, digest, ...`
- `rss_articles` table: existing columns include `id, feed_id, title, url, body, summary, fetched_at, depth, topics, classify_rationale, body_scraped_at, ...`
- Migration runner pattern: `migrations/002_*.py` and `003_*.py` — PRAGMA-guarded, idempotent, CLI takes optional `[db_path]` arg defaulting to `data/kol_scan.db`

<!-- Symbols this plan EXPORTS (write). -->

```python
# lib/article_filter.py — NEW shape (replaces the V35-FOUND-01 placeholder shape)

PROMPT_VERSION_LAYER1: str = "layer1_v0_20260507"
PROMPT_VERSION_LAYER2: str = "layer2_placeholder_20260507"  # bumped in ir-2 to layer2_v0_<ts>

LAYER1_BATCH_SIZE: int = 30
LAYER1_TIMEOUT_SEC: int = 30

@dataclass(frozen=True)
class ArticleMeta:
    id: int
    source: Literal["wechat", "rss"]
    title: str
    summary: str | None  # WeChat: digest; RSS: feed summary; None when missing
    content_length: int | None  # RSS only; None for WeChat (length unknown pre-scrape)

@dataclass(frozen=True)
class ArticleWithBody:
    id: int
    source: Literal["wechat", "rss"]
    title: str
    body: str  # full scraped markdown

@dataclass(frozen=True)
class FilterResult:
    verdict: Literal["candidate", "reject"] | None  # None = LLM error / re-evaluate next run
    reason: str  # ≤30 中文 chars on success; error class name on failure
    prompt_version: str  # = PROMPT_VERSION_LAYER1 or PROMPT_VERSION_LAYER2 at call time

async def layer1_pre_filter(
    articles: list[ArticleMeta],
) -> list[FilterResult]:
    """Real Gemini Flash Lite batch call. Up to LAYER1_BATCH_SIZE articles per call.

    On any error (timeout / non-JSON / partial JSON / row-count-mismatch),
    every result in the returned list has verdict=None and reason set to
    the error class. Caller persists None-verdict rows as layer1_verdict=NULL
    so the next ingest tick re-evaluates them.
    """

def layer2_full_body_score(
    articles: list[ArticleWithBody],
) -> list[FilterResult]:
    """Placeholder — always-pass with new 3-field FilterResult shape.

    Real implementation lands in ir-2. This stub returns
    [FilterResult(verdict='candidate', reason='placeholder: layer2 always-pass',
                  prompt_version=PROMPT_VERSION_LAYER2)
     for _ in articles].

    Note: 'candidate' verdict is used (not 'ok'); ir-2 introduces 'ok'/'reject'
    semantics on the SAME column. ir-1's ingest-loop wiring treats any
    non-'reject' verdict (including 'candidate' and 'ok') as pass-to-ainsert
    so this placeholder remains compatible until ir-2 lands.
    """

def persist_layer1_verdicts(
    conn: sqlite3.Connection,
    articles: list[ArticleMeta],
    results: list[FilterResult],
) -> None:
    """Atomically persist layer1_verdict + reason + at + prompt_version on
    each article's source table. Groups articles by source, issues one
    UPDATE per source-table inside one transaction. Raises on any DB error
    (caller is expected to roll back its own state).

    Per LF-1.7: all 30 succeed together or zero are persisted.
    Per LF-1.5: when result.verdict is None for the entire batch, this
    helper is NOT called — caller skips persistence so rows stay NULL.
    """
```
</interfaces>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1.1: Rewrite lib/article_filter.py — new contract + real Layer 1</name>
  <read_first>
    - lib/article_filter.py (current 117-line placeholder)
    - lib/vertex_gemini_complete.py (full file — understand timeout / retry / config plumbing)
    - lib/__init__.py (export surface — confirm `gemini_model_complete` legacy path symbol)
    - .planning/PROJECT-v3.5-Ingest-Refactor.md § "Layer 1 v0 Prompt" (verbatim text)
    - .scratch/layer1-validation-20260507-151608.md (spike report — confirm prompt version + result shape)
  </read_first>
  <files>lib/article_filter.py</files>
  <behavior>
    - Module exports new symbols: ArticleMeta, ArticleWithBody, FilterResult (3-field), PROMPT_VERSION_LAYER1, PROMPT_VERSION_LAYER2, LAYER1_BATCH_SIZE, LAYER1_TIMEOUT_SEC, layer1_pre_filter (async), layer2_full_body_score (sync placeholder), persist_layer1_verdicts
    - Old symbol shape (`passed: bool` FilterResult, single-article layer1_pre_filter / layer2_full_body_score) is REMOVED — there is no back-compat shim. Callers (`batch_ingest_from_spider.py:1491,1526`) are rewired in ir-1-01-PLAN
    - layer1_pre_filter implementation:
      1. If `articles` is empty → return []
      2. If `len(articles) > LAYER1_BATCH_SIZE` → raise ValueError (caller's job to chunk)
      3. Build prompt: prepend the verbatim Layer 1 v0 prompt text + JSON-format input instruction; append articles serialized as JSON list of {id, source, title, summary or "", content_length or null}
      4. Call LLM with 30s timeout: temporarily override `os.environ["OMNIGRAPH_LLM_TIMEOUT_SEC"]` for the call duration (save+restore pattern; or use a context manager) — do NOT introduce a new env var
      5. Route via `vertex_gemini_model_complete` if `os.environ.get("OMNIGRAPH_LLM_PROVIDER") == "vertex_gemini"`, else `lib.gemini_model_complete` legacy path
      6. Parse response as strict JSON array. On any parse error / wrong array length / missing fields → return [FilterResult(verdict=None, reason=<error_class>, prompt_version=PROMPT_VERSION_LAYER1) for _ in articles]
      7. On success: 1:1 zip articles with parsed entries, validate each entry's verdict ∈ {"candidate", "reject"}, return list[FilterResult]
      8. Wrap whole-call try/except: catch asyncio.TimeoutError, ValueError (parse), KeyError (missing fields), generic Exception last → all map to whole-batch NULL with corresponding error_class string ("timeout" | "non_json" | "partial_json" | "row_count_mismatch" | "exception:<ClassName>")
    - layer2_full_body_score (sync placeholder): return [FilterResult(verdict="candidate", reason="placeholder: layer2 always-pass", prompt_version=PROMPT_VERSION_LAYER2) for _ in articles]
    - persist_layer1_verdicts: dispatch on source ('wechat' → 'articles' table; 'rss' → 'rss_articles' table); single transaction; UPDATE per row; commit on success; rollback + re-raise on error
    - The verbatim Layer 1 v0 prompt text MUST be the exact body from PROJECT-v3.5-Ingest-Refactor.md § "Layer 1 v0 Prompt" — no whitespace edits, no rephrasing, no truncation
  </behavior>
  <action>
**Concrete edit instructions for `lib/article_filter.py`:**

1. **REWRITE** the entire module (it is 117 lines; the new shape is incompatible with the old). Preserve the module-level docstring header but UPDATE its body to describe the new ir-1 contract (mention ir-2 will replace layer2 placeholder).

2. **NEW imports:**
```python
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Literal
```

3. **Module-level constants:**
```python
PROMPT_VERSION_LAYER1: str = "layer1_v0_20260507"
PROMPT_VERSION_LAYER2: str = "layer2_placeholder_20260507"  # ir-2 bumps to layer2_v0_<ts>

LAYER1_BATCH_SIZE: int = 30
LAYER1_TIMEOUT_SEC: int = 30

logger = logging.getLogger(__name__)
```

4. **Define dataclasses** (frozen, exact field order):
```python
@dataclass(frozen=True)
class ArticleMeta:
    id: int
    source: Literal["wechat", "rss"]
    title: str
    summary: str | None
    content_length: int | None

@dataclass(frozen=True)
class ArticleWithBody:
    id: int
    source: Literal["wechat", "rss"]
    title: str
    body: str

@dataclass(frozen=True)
class FilterResult:
    verdict: Literal["candidate", "reject"] | None
    reason: str
    prompt_version: str
```

5. **Define the verbatim Layer 1 v0 prompt** as a module-level string constant `_LAYER1_V0_PROMPT_BODY`. Copy the exact text from PROJECT-v3.5-Ingest-Refactor.md § "Layer 1 v0 Prompt" — character-for-character. Triple-quoted Python raw string, preserve all CJK and emoji.

6. **Define a context manager for timeout override:**
```python
@contextmanager
def _layer1_timeout_env() -> Iterator[None]:
    """Temporarily set OMNIGRAPH_LLM_TIMEOUT_SEC=30 for Layer 1 call duration."""
    prior = os.environ.get("OMNIGRAPH_LLM_TIMEOUT_SEC")
    os.environ["OMNIGRAPH_LLM_TIMEOUT_SEC"] = str(LAYER1_TIMEOUT_SEC)
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("OMNIGRAPH_LLM_TIMEOUT_SEC", None)
        else:
            os.environ["OMNIGRAPH_LLM_TIMEOUT_SEC"] = prior
```

7. **Define `layer1_pre_filter` (async)** — implementation per `<behavior>` above. Key fragments:

```python
async def layer1_pre_filter(
    articles: list[ArticleMeta],
) -> list[FilterResult]:
    if not articles:
        return []
    if len(articles) > LAYER1_BATCH_SIZE:
        raise ValueError(
            f"Layer 1 batch size > {LAYER1_BATCH_SIZE}; got {len(articles)}. "
            "Caller must chunk."
        )

    payload = [
        {
            "id": a.id,
            "source": a.source,
            "title": a.title,
            "summary": a.summary or "",
            "content_length": a.content_length,
        }
        for a in articles
    ]
    prompt = (
        _LAYER1_V0_PROMPT_BODY
        + "\n\n输入文章 metadata 列表(JSON):\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    def _all_null(reason: str) -> list[FilterResult]:
        return [
            FilterResult(verdict=None, reason=reason, prompt_version=PROMPT_VERSION_LAYER1)
            for _ in articles
        ]

    try:
        with _layer1_timeout_env():
            if os.environ.get("OMNIGRAPH_LLM_PROVIDER") == "vertex_gemini":
                from lib.vertex_gemini_complete import vertex_gemini_model_complete as _llm
            else:
                from lib import gemini_model_complete as _llm
            raw = await _llm(prompt)
    except asyncio.TimeoutError:
        logger.warning("[layer1] timeout for batch of %d", len(articles))
        return _all_null("timeout")
    except Exception as exc:  # noqa: BLE001 — whole-batch fail per LF-1.5
        logger.warning("[layer1] LLM error %s: %s", type(exc).__name__, exc)
        return _all_null(f"exception:{type(exc).__name__}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[layer1] non-JSON response: %r", raw[:200])
        return _all_null("non_json")

    if not isinstance(parsed, list):
        return _all_null("non_json")
    if len(parsed) != len(articles):
        logger.warning(
            "[layer1] row_count_mismatch: expected %d got %d",
            len(articles), len(parsed),
        )
        return _all_null("row_count_mismatch")

    out: list[FilterResult] = []
    for i, entry in enumerate(parsed):
        try:
            verdict = entry["verdict"]
            reason = str(entry.get("reason", ""))[:60]  # ≤30 中文 chars (UTF-8 ~60 bytes)
        except (KeyError, TypeError):
            return _all_null("partial_json")
        if verdict not in ("candidate", "reject"):
            return _all_null("partial_json")
        out.append(
            FilterResult(
                verdict=verdict,
                reason=reason,
                prompt_version=PROMPT_VERSION_LAYER1,
            )
        )
    return out
```

8. **Define `layer2_full_body_score` (sync placeholder, new shape):**
```python
def layer2_full_body_score(
    articles: list[ArticleWithBody],
) -> list[FilterResult]:
    """Placeholder always-pass; ir-2 ships real DeepSeek call."""
    return [
        FilterResult(
            verdict="candidate",  # ir-2 will switch to "ok" / "reject"
            reason="placeholder: layer2 always-pass",
            prompt_version=PROMPT_VERSION_LAYER2,
        )
        for _ in articles
    ]
```

9. **Define `persist_layer1_verdicts`:**
```python
def persist_layer1_verdicts(
    conn: sqlite3.Connection,
    articles: list[ArticleMeta],
    results: list[FilterResult],
) -> None:
    """Atomic per-source UPDATE. Caller MUST NOT call this when verdict=None
    for the entire batch (LF-1.5: leave rows NULL, picked up next run)."""
    if len(articles) != len(results):
        raise ValueError("articles and results must have equal length")

    now = datetime.now(timezone.utc).isoformat()
    by_source: dict[str, list[tuple[str | None, str, str, str, int]]] = {
        "wechat": [],
        "rss": [],
    }
    for a, r in zip(articles, results):
        by_source[a.source].append(
            (r.verdict, r.reason, now, r.prompt_version, a.id)
        )

    table_for: dict[str, str] = {"wechat": "articles", "rss": "rss_articles"}

    try:
        conn.execute("BEGIN")
        for source, rows in by_source.items():
            if not rows:
                continue
            tbl = table_for[source]
            conn.executemany(
                f"UPDATE {tbl} SET "
                f"layer1_verdict = ?, layer1_reason = ?, layer1_at = ?, "
                f"layer1_prompt_version = ? "
                f"WHERE id = ?",
                rows,
            )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
```

10. **Verify** locally:
```bash
python -c "from lib.article_filter import (
    ArticleMeta, ArticleWithBody, FilterResult,
    PROMPT_VERSION_LAYER1, LAYER1_BATCH_SIZE,
    layer1_pre_filter, layer2_full_body_score, persist_layer1_verdicts,
)
print('OK', PROMPT_VERSION_LAYER1, LAYER1_BATCH_SIZE)"
```
Expect `OK layer1_v0_20260507 30`.

**HARD CONSTRAINTS:**
- DO NOT keep the old `passed: bool` FilterResult shape — it must be fully replaced. If you find yourself adding a back-compat property, stop: ir-1-01 will fix the only two callers
- DO NOT edit Layer 1 prompt text — character-for-character verbatim from PROJECT § "Layer 1 v0 Prompt"
- DO NOT add LLM-call retry logic at the Layer 1 layer — `vertex_gemini_model_complete` already retries 503 × 4; LF-1.5 + D-LF-4 forbid Layer-1-level retry
- DO NOT introduce a new env var (e.g. `OMNIGRAPH_LAYER1_TIMEOUT_SEC`) — LF-1.3 forbids
- DO NOT touch `tests/unit/test_article_filter.py` — ir-1-02 owns it (will delete + replace)
- DO NOT touch `batch_ingest_from_spider.py` — ir-1-01 owns the call site rewire
- Per CLAUDE.md "Surgical Changes": every changed line traces to LF-1.1..1.8; no opportunistic refactors
  </action>
  <verify>
    <automated>python -c "from lib.article_filter import ArticleMeta, FilterResult, layer1_pre_filter, layer2_full_body_score, persist_layer1_verdicts, PROMPT_VERSION_LAYER1, LAYER1_BATCH_SIZE; print('imports ok')"</automated>
    <automated>python -c "from lib.article_filter import FilterResult; r = FilterResult(verdict='candidate', reason='x', prompt_version='v'); assert r.verdict == 'candidate' and r.reason == 'x' and r.prompt_version == 'v'; print('FilterResult shape ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `python -c "from lib.article_filter import FilterResult; FilterResult(passed=True, reason='x')"` raises TypeError (old shape removed)
    - `python -c "from lib.article_filter import FilterResult; FilterResult(verdict='candidate', reason='x', prompt_version='v')"` succeeds
    - `lib/article_filter.py` contains literal: `PROMPT_VERSION_LAYER1: str = "layer1_v0_20260507"`
    - `lib/article_filter.py` contains literal: `LAYER1_BATCH_SIZE: int = 30`
    - `lib/article_filter.py` contains literal: `LAYER1_TIMEOUT_SEC: int = 30`
    - `lib/article_filter.py` contains literal: `async def layer1_pre_filter(`
    - `lib/article_filter.py` contains the verbatim Chinese phrase from the v0 prompt: `多模态 / 视觉 / 视频 / 语音 模型本身`
    - `lib/article_filter.py` does NOT contain literal `passed: bool` (old field removed)
    - `lib/article_filter.py` does NOT contain literal `placeholder: layer1 always-pass` (old reason removed; layer2 placeholder reason is preserved)
    - Module imports cleanly: `python -c "import lib.article_filter; print('ok')"`
  </acceptance_criteria>
  <done>LF-1.1, LF-1.2, LF-1.3, LF-1.4, LF-1.5, LF-1.7, LF-1.8 satisfied at function level (LF-1.6 / 1.7 DB layer covered by Task 1.2 + 1.3; LF-1.9 tests by ir-1-02). Foundation Quick contract is fully replaced.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 1.2: Migration 006 SQL — additive layer1_* columns × 2 tables</name>
  <read_first>
    - migrations/004_classifications_unique_article_id.sql (current SQL-style migration)
    - migrations/002_expand_ingestions_check.py and 002_expand_ingestions_check.sql (.py + .sql twin pattern)
    - data/kol_scan.db schema for `articles` + `rss_articles` (PRAGMA table_info via local python or `.dev-runtime/` snapshot)
  </read_first>
  <files>migrations/006_layer1_columns.sql</files>
  <behavior>
    - SQL-only file is human-readable migration, executable directly via sqlite3 CLI
    - Adds 4 columns to `articles`: layer1_verdict TEXT, layer1_reason TEXT, layer1_at TEXT, layer1_prompt_version TEXT (all nullable)
    - Adds same 4 columns to `rss_articles`
    - Existing rows: all four columns NULL (SQLite default-NULL on ADD COLUMN)
    - File header documents idempotency caveat: this raw SQL file is NOT itself idempotent (re-running will fail with "duplicate column name") — the `.py` runner (Task 1.3) provides idempotency via PRAGMA guard. Operator-runnable form is the `.py` runner; the `.sql` file is the human-readable spec
  </behavior>
  <action>
**Create `migrations/006_layer1_columns.sql`** with this content:

```sql
-- Migration 006: Layer 1 verdict columns (v3.5 Ingest Refactor)
-- Phase:   ir-1 (Real Layer 1 + KOL ingest wiring)
-- REQ:     LF-1.6
-- Date:    2026-05-07
--
-- Adds 4 columns × 2 tables = 8 total columns. All additive, no data touched.
-- Existing rows have all four layer1_* columns NULL (re-evaluated on next ingest).
--
-- ============================================================
-- OPERATOR: BACKUP THE DB FILE BEFORE RUNNING THIS MIGRATION
--   cp data/kol_scan.db data/kol_scan.db.backup-pre-mig006-$(date +%Y%m%d-%H%M%S)
-- (Per CLAUDE.md Lessons 2026-05-06 #2 — backup file before any schema change.)
-- ============================================================
--
-- This .sql file is NOT idempotent: re-running raises "duplicate column name".
-- For idempotent runs (e.g. CI / local dev re-applies), use the .py twin:
--   python migrations/006_layer1_columns.py [path/to/kol_scan.db]

ALTER TABLE articles      ADD COLUMN layer1_verdict        TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_reason         TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_at             TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer1_prompt_version TEXT NULL;

ALTER TABLE rss_articles  ADD COLUMN layer1_verdict        TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_reason         TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_at             TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer1_prompt_version TEXT NULL;
```
  </action>
  <verify>
    <automated>test -f migrations/006_layer1_columns.sql && grep -c "ALTER TABLE" migrations/006_layer1_columns.sql | grep -q "^8$" && echo OK</automated>
  </verify>
  <acceptance_criteria>
    - File exists at `migrations/006_layer1_columns.sql`
    - Contains exactly 8 `ALTER TABLE` statements (4 per source table)
    - Contains backup-warning comment header (matches Lesson 2026-05-06 #2 pattern)
    - References Task 1.3 .py twin for idempotency
  </acceptance_criteria>
  <done>LF-1.6 SQL form ready. Idempotent runner is Task 1.3.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 1.3: Migration 006 Python runner — PRAGMA-guarded idempotent</name>
  <read_first>
    - migrations/003_expand_ingestions_status_graded.py (full file — pattern source)
    - migrations/006_layer1_columns.sql (Task 1.2 output — column list source of truth)
  </read_first>
  <files>migrations/006_layer1_columns.py</files>
  <behavior>
    - CLI: `python migrations/006_layer1_columns.py [optional db_path]`
    - Default db_path: `data/kol_scan.db` relative to repo root
    - For each table in (`articles`, `rss_articles`): for each column in (`layer1_verdict`, `layer1_reason`, `layer1_at`, `layer1_prompt_version`): if PRAGMA table_info(<table>) shows column missing → ALTER TABLE <table> ADD COLUMN <col> TEXT NULL; else log SKIP
    - Print summary at end: `migration 006: applied N column(s); skipped M (already present)`
    - Idempotent: re-running on a fully-migrated DB prints `migration 006: applied 0 column(s); skipped 8 (already present)` and exits 0
    - Returns boolean from `migrate(db_path) -> bool` mirror to 002/003 pattern; sys.exit(0 if ok else 1) at module level
  </behavior>
  <action>
**Create `migrations/006_layer1_columns.py`** modeled on `003_expand_ingestions_status_graded.py`:

```python
#!/usr/bin/env python3
"""Apply migration 006: add layer1_* columns to articles + rss_articles.

Usage:  python3 migrations/006_layer1_columns.py [path/to/kol_scan.db]
Default: data/kol_scan.db (relative to repo root)

REQ: LF-1.6 (v3.5 Ingest Refactor — Phase ir-1)
Idempotent via PRAGMA table_info guard. Safe to run multiple times.
"""
from __future__ import annotations

import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, "data", "kol_scan.db")

LAYER1_COLUMNS: tuple[str, ...] = (
    "layer1_verdict",
    "layer1_reason",
    "layer1_at",
    "layer1_prompt_version",
)
TABLES: tuple[str, ...] = ("articles", "rss_articles")


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(db_path: str) -> bool:
    if not os.path.exists(db_path):
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return False

    applied = 0
    skipped = 0
    conn = sqlite3.connect(db_path)
    try:
        for table in TABLES:
            existing = _existing_columns(conn, table)
            if not existing:
                print(f"ERROR: '{table}' table not found in {db_path}", file=sys.stderr)
                return False
            for col in LAYER1_COLUMNS:
                if col in existing:
                    print(f"SKIP {table}.{col} (already present)")
                    skipped += 1
                else:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT NULL")
                    print(f"ADD  {table}.{col}")
                    applied += 1
        conn.commit()
    finally:
        conn.close()

    print(f"\nmigration 006: applied {applied} column(s); skipped {skipped} (already present)")
    return True


if __name__ == "__main__":
    ok = migrate(DB_PATH)
    sys.exit(0 if ok else 1)
```
  </action>
  <verify>
    <automated>python migrations/006_layer1_columns.py "$(mktemp -t test-006-XXXX.db)" 2>&1 | grep -q "ERROR: db not found"</automated>
    <automated>python -c "
import os, sqlite3, tempfile, subprocess, sys
fd, p = tempfile.mkstemp(suffix='.db'); os.close(fd)
conn = sqlite3.connect(p)
conn.executescript('CREATE TABLE articles(id INTEGER PRIMARY KEY); CREATE TABLE rss_articles(id INTEGER PRIMARY KEY);')
conn.close()
r1 = subprocess.run([sys.executable, 'migrations/006_layer1_columns.py', p], capture_output=True, text=True)
assert r1.returncode == 0
assert 'applied 8' in r1.stdout, r1.stdout
r2 = subprocess.run([sys.executable, 'migrations/006_layer1_columns.py', p], capture_output=True, text=True)
assert r2.returncode == 0
assert 'applied 0' in r2.stdout, r2.stdout
print('idempotent ok')
os.unlink(p)
"</automated>
  </verify>
  <acceptance_criteria>
    - File exists at `migrations/006_layer1_columns.py`, has shebang, is executable as `python migrations/006_layer1_columns.py`
    - First run on empty schema applies 8 columns; second run applies 0 (PRAGMA guard works)
    - Missing DB path prints `ERROR: db not found` to stderr, exits 1
    - Module-level `migrate(db_path: str) -> bool` callable from import
  </acceptance_criteria>
  <done>LF-1.6 idempotent runner ready. Combined with Task 1.2 .sql, migration 006 is fully delivered.</done>
</task>

</tasks>

<verification>
After Tasks 1.1, 1.2, 1.3 land:

```bash
# Module imports + symbol surface
python -c "from lib.article_filter import (
    ArticleMeta, ArticleWithBody, FilterResult,
    PROMPT_VERSION_LAYER1, PROMPT_VERSION_LAYER2,
    LAYER1_BATCH_SIZE, LAYER1_TIMEOUT_SEC,
    layer1_pre_filter, layer2_full_body_score, persist_layer1_verdicts,
)
print('imports ok')"

# Migration 006 idempotency on a temp DB
python migrations/006_layer1_columns.py /tmp/test_mig006.db || true
sqlite3 /tmp/test_mig006.db < migrations/006_layer1_columns.sql 2>&1 | head

# CLAUDE.md regression bar — ir-1-02 owns the Layer 1 unit tests; expect existing
# Foundation Quick tests to FAIL after this plan (they pin the old shape).
# That is INTENTIONAL — ir-1-02 deletes + replaces them. DO NOT run pytest as a gate
# for this plan; it is a gate for ir-1-02.
```

Plan-level OUT-OF-SCOPE verification:
- Ingest loop call sites (`batch_ingest_from_spider.py:1491,1526`) are NOT updated by this plan; they will produce ImportError at runtime (broken FilterResult shape). **This is expected** — ir-1-01 fixes them. Do NOT run `python batch_ingest_from_spider.py` between this plan and ir-1-01.
</verification>

<commit_message>
feat(ir-1): real Layer 1 LLM impl + persistence + migration 006

Replace V35-FOUND-01 always-pass placeholder in lib/article_filter.py with
real Gemini Flash Lite batch call against the validated v0 prompt. New
3-field FilterResult (verdict / reason / prompt_version) supersedes the
2-field placeholder shape. Migration 006 (.sql + idempotent .py runner)
adds layer1_verdict / layer1_reason / layer1_at / layer1_prompt_version to
both articles and rss_articles. Layer 2 placeholder retained at always-pass
returning the new shape so ir-1-01 ingest loop wiring stays viable until
ir-2 ships real Layer 2.

REQs: LF-1.1, LF-1.2, LF-1.3, LF-1.4, LF-1.5, LF-1.6, LF-1.7, LF-1.8
Phase: v3.5-Ingest-Refactor / ir-1 / plan 00
</commit_message>

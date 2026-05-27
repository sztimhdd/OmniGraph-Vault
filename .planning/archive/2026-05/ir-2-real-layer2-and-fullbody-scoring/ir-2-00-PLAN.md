---
phase: ir-2-real-layer2-and-fullbody-scoring
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/article_filter.py
  - migrations/007_layer2_columns.sql
  - migrations/007_layer2_columns.py
autonomous: true
requirements:
  - LF-2.1
  - LF-2.2
  - LF-2.3
  - LF-2.5
  - LF-2.6
  - LF-2.7

must_haves:
  truths:
    - "lib/article_filter.layer2_full_body_score is async and batched: layer2_full_body_score(articles: list[ArticleWithBody]) -> list[FilterResult]. Replaces the sync placeholder shipped in ir-1-00 (commit cf79840)."
    - "PROMPT_VERSION_LAYER2 bumps from 'layer2_placeholder_20260507' to 'layer2_v0_20260507'. The bump triggers automatic re-evaluation of any existing rows tagged with the placeholder version (LF-2.7 prompt-bump pattern, mirroring LF-1.8)."
    - "Layer 2 v0 prompt body is the verbatim text from .scratch/layer2-validation-20260507-210423.md § 'Final prompt' (lines 43-118 of the report). Editing the prompt requires re-running the spike + bumping prompt_version."
    - "LAYER2_BATCH_SIZE = 5 (LF-2.2 lower bound chosen — sweet spot per spike report § Recommendation)."
    - "LAYER2_TIMEOUT_SEC = 60 (LF-2.2 wall-clock budget). Implementation: temporary override of DEEPSEEK_REQUEST_TIMEOUT or pass timeout via openai client; do NOT introduce a new env var."
    - "LAYER2_BODY_TRUNCATION_CHARS = 8000 (validated by spike — max prompt 23.7K tokens well under DeepSeek 64K context for batch=5)."
    - "Layer 2 LLM routing: lib.llm_deepseek.deepseek_model_complete (the only DeepSeek path in lib/). Does NOT route through Vertex regardless of OMNIGRAPH_LLM_PROVIDER — Layer 2 is contract-pinned to DeepSeek per LF-2.3."
    - "Failure modes (LF-2.6): timeout / non-JSON / partial JSON / row-count-mismatch all return FilterResult(verdict=None, reason=<error_class>, prompt_version=PROMPT_VERSION_LAYER2) for EVERY article in the batch — no partial-batch persistence. Same shape as Layer 1 _all_null."
    - "persist_layer2_verdicts(conn, articles, results) groups by source ('wechat' → articles, 'rss' → rss_articles), one UPDATE per source-table inside one transaction, only the 4 layer2_* columns written. Mirror of persist_layer1_verdicts."
    - "Migration 007 (.sql + .py runner) is additive and idempotent: PRAGMA table_info guard before each ALTER TABLE ADD COLUMN. Adds 4 columns × 2 tables = 8 columns. Same shape as migration 006."
    - "Verdict semantics for Layer 2 (LF-2.5): NULL = not yet evaluated; 'ok' = passed (proceed to ainsert); 'reject' = full body off-scope (skip ainsert). Note: Layer 1 uses 'candidate'/'reject'; Layer 2 uses 'ok'/'reject' — different verdict alphabets per LF-2.5 wording. The placeholder in ir-1-00 returned 'candidate' (compat shim); ir-2-00 replaces with 'ok' / 'reject'."
  artifacts:
    - path: "lib/article_filter.py"
      provides: "Real Layer 2 (batch async DeepSeek call) + bumped PROMPT_VERSION_LAYER2 + new constants (LAYER2_BATCH_SIZE, LAYER2_TIMEOUT_SEC, LAYER2_BODY_TRUNCATION_CHARS) + persist_layer2_verdicts helper. Module exports updated __all__."
      contains: "PROMPT_VERSION_LAYER2: str = \"layer2_v0_20260507\""
      exports: ["ArticleMeta", "ArticleWithBody", "FilterResult", "PROMPT_VERSION_LAYER1", "PROMPT_VERSION_LAYER2", "LAYER1_BATCH_SIZE", "LAYER1_TIMEOUT_SEC", "LAYER2_BATCH_SIZE", "LAYER2_TIMEOUT_SEC", "LAYER2_BODY_TRUNCATION_CHARS", "layer1_pre_filter", "layer2_full_body_score", "persist_layer1_verdicts", "persist_layer2_verdicts"]
    - path: "migrations/007_layer2_columns.sql"
      provides: "8 ALTER TABLE statements (idempotent via PRAGMA guard at .py twin) adding layer2_verdict / layer2_reason / layer2_at / layer2_prompt_version on articles + rss_articles."
      min_lines: 25
      contains: "ALTER TABLE articles ADD COLUMN layer2_verdict TEXT"
    - path: "migrations/007_layer2_columns.py"
      provides: "Idempotent runner mirroring 006 pattern. PRAGMA-guards each ALTER. CLI: python migrations/007_layer2_columns.py [db_path]."
      min_lines: 60
      contains: "def migrate(db_path: str) -> bool"
  key_links:
    - from: "lib/article_filter.layer2_full_body_score"
      to: "lib.llm_deepseek.deepseek_model_complete"
      via: "import + await"
      pattern: "from lib.llm_deepseek import deepseek_model_complete"
    - from: "lib/article_filter.persist_layer2_verdicts"
      to: "articles.layer2_* / rss_articles.layer2_* columns (migration 007)"
      via: "UPDATE statement grouped by source"
      pattern: "UPDATE articles SET layer2_verdict = ?, layer2_reason = ?, layer2_at = ?, layer2_prompt_version = ? WHERE id = ?"
    - from: "migrations/007_layer2_columns.py"
      to: "data/kol_scan.db schema"
      via: "ALTER TABLE ADD COLUMN with PRAGMA table_info guard"
      pattern: "PRAGMA table_info(articles)"
---

<objective>
Wave 1: replace the always-pass Layer 2 placeholder with a real DeepSeek batch call against the spike-validated v0 prompt; persist verdicts atomically on `articles.layer2_*` / `rss_articles.layer2_*`; ship migration 007 (.sql + idempotent .py runner). Same structural pattern as ir-1-00, scaled to Layer 2's 5-article batch + DeepSeek routing.

Output: `lib/article_filter.py` carries real Layer 2 + bumped prompt_version; `migrations/007_*` lands schema additions. Layer 2 verdict alphabet shifts from placeholder 'candidate' to spec-compliant 'ok' / 'reject' (LF-2.5). The ingest loop still calls `layer2_full_body_score` per chunk — wiring restructure happens in ir-2-01.
</objective>

<execution_context>
@.planning/PROJECT-v3.5-Ingest-Refactor.md
@.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md
@.planning/ROADMAP-v3.5-Ingest-Refactor.md
@.scratch/layer2-validation-20260507-210423.md
</execution_context>

<context>
@.planning/STATE-v3.5-Ingest-Refactor.md
@CLAUDE.md
</context>

<interfaces>
<!-- Existing symbols this plan REUSES (read-only). -->

From `lib/llm_deepseek.py` (post-ir-1; unchanged):
```python
async def deepseek_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict] | None = None,
    **kwargs,
) -> str: ...
```
- Reads `DEEPSEEK_API_KEY` at module-import time (raises RuntimeError if absent).
- Reads `DEEPSEEK_MODEL` env, default `deepseek-v4-flash` (note: REQ LF-2.3 names `deepseek-chat` — see plan deviation note below).
- Built-in 120s request timeout.
- API endpoint: `https://api.deepseek.com/v1` (OpenAI-compatible).

From `lib/article_filter.py` post-ir-1 (commit cf79840):
- `ArticleMeta`, `ArticleWithBody`, `FilterResult` (3-field) — REUSED.
- `PROMPT_VERSION_LAYER1` constant — REUSED unchanged.
- `_LAYER1_V0_PROMPT_BODY`, `_layer1_timeout_env`, `layer1_pre_filter`, `persist_layer1_verdicts` — UNCHANGED.
- `PROMPT_VERSION_LAYER2 = "layer2_placeholder_20260507"` (line 75) — BUMP to `"layer2_v0_20260507"`.
- `def layer2_full_body_score(articles)` (line ~343, sync placeholder returning verdict='candidate') — REPLACE with real async DeepSeek impl returning verdict='ok'/'reject'.

From `.scratch/layer2-validation-20260507-210423.md`:
- The verbatim Layer 2 v0 prompt at lines 43-118 of the report. Copy character-for-character into `_LAYER2_V0_PROMPT_BODY`.
- Failure-mode mapping at report lines 195-203:
  - timeout → "timeout"
  - non-JSON → "non_json"
  - partial JSON → "partial_json"
  - row count mismatch → "row_count_mismatch"

<!-- Plan deviation re LF-2.3 model pinning. -->

> **LF-2.3 deviation note (must surface in commit message):** REQ LF-2.3 names
> `deepseek-chat` as the Layer 2 model. The actual `lib/llm_deepseek.py` module
> default is `deepseek-v4-flash` (configurable via `DEEPSEEK_MODEL` env). The
> v3.5 spike at `.scratch/layer2-validation-20260507-210423.md` ran on Vertex
> Gemini Flash Lite (substitute), not DeepSeek at all. ir-2-00 calls
> `deepseek_model_complete` which honors the project-wide `DEEPSEEK_MODEL`
> env — so production uses whatever the operator has set. Layer 2 does NOT
> introduce a Layer-2-specific model env var. If LF-2.3 strictly requires
> `deepseek-chat`, the operator-side fix is to set `DEEPSEEK_MODEL=deepseek-chat`
> in `~/.hermes/.env` before deploy; ir-2 does not enforce that at code level.

<!-- New symbols this plan EXPORTS. -->

```python
# lib/article_filter.py — additions for ir-2

PROMPT_VERSION_LAYER2: str = "layer2_v0_20260507"  # bumped from placeholder

LAYER2_BATCH_SIZE: int = 5
LAYER2_TIMEOUT_SEC: int = 60
LAYER2_BODY_TRUNCATION_CHARS: int = 8000

# Verbatim from spike report § "Final prompt"
_LAYER2_V0_PROMPT_BODY: str = """\
你是一个 AI/LLM 文章 Layer 2 深度过滤器。任务是在 Layer 1...
... (full text, ~70 lines) ...
输入文章列表 (JSON):
"""

@contextmanager
def _layer2_timeout_env() -> Iterator[None]:
    """Mirror of _layer1_timeout_env. The DeepSeek wrapper does NOT honor
    OMNIGRAPH_LLM_TIMEOUT_SEC (it has its own _DEEPSEEK_TIMEOUT_S=120 module
    constant), so this context manager is a NO-OP placeholder for symmetry —
    the per-call 60s budget is enforced via asyncio.wait_for in the caller.
    Kept as a stub so future timeout-tunability has a hook to land in."""
    yield

async def layer2_full_body_score(
    articles: list[ArticleWithBody],
) -> list[FilterResult]:
    """Real DeepSeek batch full-body filter. Up to LAYER2_BATCH_SIZE articles
    per call; bodies truncated to LAYER2_BODY_TRUNCATION_CHARS each.

    Verdict alphabet: 'ok' / 'reject' (LF-2.5). 'reject' on (relevant=false)
    OR (depth_score < 2). 'ok' otherwise. Caller should treat any non-'reject'
    verdict (including the legacy 'candidate' from layer1) as pass-to-ainsert.

    On any error (timeout / non-JSON / partial JSON / row-count-mismatch),
    every result has verdict=None and reason set to the error class. Caller
    persists None-verdict rows as layer2_verdict=NULL so the next ingest tick
    re-evaluates them.
    """

def persist_layer2_verdicts(
    conn: sqlite3.Connection,
    articles: list[ArticleWithBody],
    results: list[FilterResult],
) -> None:
    """Atomically persist layer2_verdict + reason + at + prompt_version on
    each article's source table. Mirror of persist_layer1_verdicts."""
```
</interfaces>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1.1: Extend lib/article_filter.py with real Layer 2 + persistence helper</name>
  <read_first>
    - lib/article_filter.py (full file — current ir-1 shape, ~430 lines)
    - lib/llm_deepseek.py (full file — DeepSeek wrapper contract)
    - .scratch/layer2-validation-20260507-210423.md (spike report — prompt + failure modes + sample shape)
  </read_first>
  <files>lib/article_filter.py</files>
  <behavior>
    - New constants block AFTER existing Layer 1 constants: PROMPT_VERSION_LAYER2 (bumped), LAYER2_BATCH_SIZE, LAYER2_TIMEOUT_SEC, LAYER2_BODY_TRUNCATION_CHARS.
    - New `_LAYER2_V0_PROMPT_BODY` string constant (verbatim from spike report).
    - The existing sync `layer2_full_body_score` placeholder (line ~343) is REPLACED by an async batch impl. Old placeholder logic is removed.
    - Layer 2 implementation pattern (mirror layer1):
      1. If `articles` is empty → return []
      2. If `len(articles) > LAYER2_BATCH_SIZE` → raise ValueError
      3. Build prompt: prepend the verbatim Layer 2 v0 prompt + JSON-format hint; serialize articles as `[{id, title, body}]` with body truncated to LAYER2_BODY_TRUNCATION_CHARS
      4. Wrap LLM call in `asyncio.wait_for(..., timeout=LAYER2_TIMEOUT_SEC)` to enforce per-batch wall-clock cap
      5. Catch `asyncio.TimeoutError` → all-NULL with reason="timeout"
      6. Catch generic `Exception` → all-NULL with reason="exception:<ClassName>"
      7. Strip markdown code fences if present (DeepSeek may wrap JSON despite instruction)
      8. Parse JSON; on `json.JSONDecodeError` → all-NULL reason="non_json"
      9. Validate is list of correct length → row_count_mismatch on len mismatch
      10. Per-entry validation: `depth_score` ∈ {1,2,3}, `relevant` is bool, `reason` is str. KeyError/TypeError → partial_json all-NULL
      11. Apply decision rule: `relevant=True AND depth_score>=2 → 'ok'`; else `'reject'`. Reason field carries the LLM-supplied reason (truncated to 60 bytes ≈ 30 中文 chars).
    - New `persist_layer2_verdicts` mirroring `persist_layer1_verdicts` (group by source, one UPDATE per source-table inside ONE transaction, only 4 layer2_* columns written).
    - `_layer2_timeout_env` is a NO-OP context manager (kept for symmetry; per-batch timeout is enforced by `asyncio.wait_for`).
    - Update module-level docstring to mention Layer 2 is now real DeepSeek.
    - Update `__all__` to include the new exports.
  </behavior>
  <action>
**Concrete edit instructions for `lib/article_filter.py`:**

1. **Update module docstring** at the top: replace the description of layer2 placeholder with "real DeepSeek batch call against the v0 prompt validated 2026-05-07 spike (.scratch/layer2-validation-20260507-210423.md). Verdict alphabet: 'ok' / 'reject' per LF-2.5."

2. **Bump constant** at line 75:
```python
PROMPT_VERSION_LAYER2: str = "layer2_v0_20260507"  # ir-2: real DeepSeek wired
```

3. **Add new Layer 2 constants** AFTER the existing `LAYER1_TIMEOUT_SEC` block:
```python
LAYER2_BATCH_SIZE: int = 5
"""LF-2.2 lower bound — sweet spot per spike § Recommendation."""

LAYER2_TIMEOUT_SEC: int = 60
"""LF-2.2 wall-clock budget. Enforced by asyncio.wait_for around the
DeepSeek call; the wrapper's own _DEEPSEEK_TIMEOUT_S=120 is the inner
limit. 60s outer budget = 2× spike measurement (max 7.22s)."""

LAYER2_BODY_TRUNCATION_CHARS: int = 8000
"""Validated by spike (max prompt 23.7K tokens, well under DeepSeek 64K)."""
```

4. **Add `_LAYER2_V0_PROMPT_BODY`** AFTER `_LAYER1_V0_PROMPT_BODY` (verbatim from spike report § "Final prompt", lines 43-118 of `.scratch/layer2-validation-20260507-210423.md`):

```python
_LAYER2_V0_PROMPT_BODY: str = """\
你是一个 AI/LLM 文章 Layer 2 深度过滤器。任务是在 Layer 1(基于 title+summary)之后,基于完整正文,判断每篇文章是否值得进入知识库。Layer 1 已 reject 大量明显跑偏文章,Layer 2 是 second-line filter — 主要 catch "AI 招牌但实质浅 / 软文" 这一 Layer 1 难以判断的类别。

知识库核心兴趣:agent / LLM / RAG / prompt 工程 / Claude Code / DeepSeek / Gemini / Hermes / OpenClaw / Harness / 智能体 / 大模型架构 / 推理优化 / Agent 框架 / 工程实践。

每篇文章给出 3 个判断:

## 1. depth_score (1 / 2 / 3)
... (paste full prompt body verbatim from spike report) ...

输入文章列表 (JSON):
"""
```

The implementer MUST paste the full prompt verbatim — do NOT paraphrase. The spike report's reject-rate metrics are invalidated if the prompt drifts.

5. **Add `_layer2_timeout_env` no-op context manager** AFTER `_layer1_timeout_env`:
```python
@contextmanager
def _layer2_timeout_env() -> Iterator[None]:
    """No-op placeholder for symmetry with _layer1_timeout_env. Layer 2's
    per-batch wall-clock cap is enforced by asyncio.wait_for in the caller;
    the lib.llm_deepseek wrapper has its own internal 120s timeout."""
    yield
```

6. **REPLACE the sync placeholder `layer2_full_body_score`** (current lines ~343-360) with the new async impl:

```python
async def layer2_full_body_score(
    articles: list[ArticleWithBody],
) -> list[FilterResult]:
    """Real DeepSeek batch full-body filter (LF-2.1 / LF-2.2 / LF-2.3)..."""
    if not articles:
        return []
    if len(articles) > LAYER2_BATCH_SIZE:
        raise ValueError(
            f"Layer 2 batch size > {LAYER2_BATCH_SIZE}; got {len(articles)}. "
            "Caller must chunk."
        )

    payload = [
        {
            "id": a.id,
            "title": a.title,
            "body": (a.body or "")[:LAYER2_BODY_TRUNCATION_CHARS],
        }
        for a in articles
    ]
    prompt = (
        _LAYER2_V0_PROMPT_BODY
        + "\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    def _all_null(reason: str) -> list[FilterResult]:
        return [
            FilterResult(
                verdict=None,
                reason=reason,
                prompt_version=PROMPT_VERSION_LAYER2,
            )
            for _ in articles
        ]

    try:
        from lib.llm_deepseek import deepseek_model_complete
        raw = await asyncio.wait_for(
            deepseek_model_complete(prompt),
            timeout=LAYER2_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning("[layer2] timeout for batch of %d", len(articles))
        return _all_null("timeout")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[layer2] LLM error %s: %s",
            type(exc).__name__,
            str(exc)[:200],
        )
        return _all_null(f"exception:{type(exc).__name__}")

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("[layer2] non-JSON response: %r", raw[:200])
        return _all_null("non_json")

    if not isinstance(parsed, list):
        return _all_null("non_json")
    if len(parsed) != len(articles):
        logger.warning(
            "[layer2] row_count_mismatch: expected %d got %d",
            len(articles), len(parsed),
        )
        return _all_null("row_count_mismatch")

    out: list[FilterResult] = []
    for entry in parsed:
        try:
            depth_score = int(entry["depth_score"])
            relevant = bool(entry["relevant"])
            reason = str(entry.get("reason", ""))[:60]
        except (KeyError, TypeError, ValueError):
            return _all_null("partial_json")
        if depth_score not in (1, 2, 3):
            return _all_null("partial_json")
        # Decision rule: keep iff relevant AND depth >= 2 (LF-2.5 + spike § "Decision rule")
        verdict = "ok" if (relevant and depth_score >= 2) else "reject"
        out.append(
            FilterResult(
                verdict=verdict,
                reason=reason,
                prompt_version=PROMPT_VERSION_LAYER2,
            )
        )
    return out
```

7. **Add `persist_layer2_verdicts`** AFTER `persist_layer1_verdicts`. Function body is identical structurally to `persist_layer1_verdicts` except column names:

```python
def persist_layer2_verdicts(
    conn: sqlite3.Connection,
    articles: list[ArticleWithBody],
    results: list[FilterResult],
) -> None:
    """Atomic per-source UPDATE of layer2_* columns. Mirror of
    persist_layer1_verdicts."""
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
                f"layer2_verdict = ?, layer2_reason = ?, layer2_at = ?, "
                f"layer2_prompt_version = ? "
                f"WHERE id = ?",
                rows,
            )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
```

8. **Update `__all__`** at module bottom to include new exports:
```python
__all__ = [
    "ArticleMeta", "ArticleWithBody", "FilterResult",
    "PROMPT_VERSION_LAYER1", "PROMPT_VERSION_LAYER2",
    "LAYER1_BATCH_SIZE", "LAYER1_TIMEOUT_SEC",
    "LAYER2_BATCH_SIZE", "LAYER2_TIMEOUT_SEC", "LAYER2_BODY_TRUNCATION_CHARS",
    "layer1_pre_filter", "layer2_full_body_score",
    "persist_layer1_verdicts", "persist_layer2_verdicts",
]
```

**HARD CONSTRAINTS:**
- DO NOT keep the sync placeholder shape — fully replace with async batch impl.
- DO NOT edit the Layer 2 prompt text from the spike report — character-for-character verbatim.
- DO NOT add Layer-2-specific retry logic. The DeepSeek wrapper has its own 120s timeout; LF-2.6 + D-LF-4 forbid Layer-2-level retry.
- DO NOT introduce new env vars. Operator may set `DEEPSEEK_MODEL=deepseek-chat` to satisfy LF-2.3 strictness; that is operator config, not code.
- DO NOT touch `tests/unit/test_article_filter.py` — ir-2-02 owns it.
- DO NOT touch `batch_ingest_from_spider.py` — ir-2-01 owns the call site rewire.
- Per CLAUDE.md "Surgical Changes": every changed line traces to LF-2.x; no opportunistic refactors.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy python -c "from lib.article_filter import (ArticleMeta, ArticleWithBody, FilterResult, PROMPT_VERSION_LAYER2, LAYER2_BATCH_SIZE, LAYER2_TIMEOUT_SEC, LAYER2_BODY_TRUNCATION_CHARS, layer2_full_body_score, persist_layer2_verdicts); import inspect; assert inspect.iscoroutinefunction(layer2_full_body_score); print('ok', PROMPT_VERSION_LAYER2, LAYER2_BATCH_SIZE)"</automated>
  </verify>
  <acceptance_criteria>
    - Imports succeed: ArticleMeta, ArticleWithBody, FilterResult, PROMPT_VERSION_LAYER2, LAYER2_BATCH_SIZE, LAYER2_TIMEOUT_SEC, LAYER2_BODY_TRUNCATION_CHARS, layer2_full_body_score (async), persist_layer2_verdicts.
    - `PROMPT_VERSION_LAYER2 == "layer2_v0_20260507"`.
    - `LAYER2_BATCH_SIZE == 5`, `LAYER2_TIMEOUT_SEC == 60`, `LAYER2_BODY_TRUNCATION_CHARS == 8000`.
    - `inspect.iscoroutinefunction(layer2_full_body_score) is True`.
    - `lib/article_filter.py` contains literal Chinese phrase from the v0 prompt: `Layer 2 是 second-line filter`.
    - Old placeholder reason "placeholder: layer2 always-pass" is REMOVED from the file.
  </acceptance_criteria>
  <done>LF-2.1, LF-2.2, LF-2.3, LF-2.6, LF-2.7 satisfied at function level. LF-2.5 partially: column shape requires migration 007 (Task 1.2 + 1.3). LF-2.8 unit tests in ir-2-02. LF-2.4 spike re-validation (real DeepSeek) in ir-2-03 close-out smoke.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 1.2: Migration 007 SQL — additive layer2_* columns × 2 tables</name>
  <read_first>
    - migrations/006_layer1_columns.sql (template)
  </read_first>
  <files>migrations/007_layer2_columns.sql</files>
  <behavior>
    - Mirror of 006: 8 ALTER TABLE statements, additive, NOT idempotent at SQL level (use .py twin for that).
    - Same operator-backup warning header per CLAUDE.md Lessons 2026-05-06 #2.
  </behavior>
  <action>
**Create `migrations/007_layer2_columns.sql`** with this content:

```sql
-- Migration 007: Layer 2 verdict columns (v3.5 Ingest Refactor)
-- Phase:   ir-2 (Real Layer 2 + full-body scoring)
-- REQ:     LF-2.5
-- Date:    2026-05-07
--
-- Adds 4 columns × 2 tables = 8 total columns. All additive, no data touched.
-- Existing rows have all four layer2_* columns NULL (re-evaluated by next ingest).
--
-- ============================================================
-- OPERATOR: BACKUP THE DB FILE BEFORE RUNNING THIS MIGRATION
--   cp data/kol_scan.db data/kol_scan.db.backup-pre-mig007-$(date +%Y%m%d-%H%M%S)
-- (Per CLAUDE.md Lessons 2026-05-06 #2.)
-- ============================================================
--
-- This .sql file is NOT idempotent: re-running raises "duplicate column name".
-- For idempotent runs use the .py twin:
--   python migrations/007_layer2_columns.py [path/to/kol_scan.db]

ALTER TABLE articles      ADD COLUMN layer2_verdict        TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer2_reason         TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer2_at             TEXT NULL;
ALTER TABLE articles      ADD COLUMN layer2_prompt_version TEXT NULL;

ALTER TABLE rss_articles  ADD COLUMN layer2_verdict        TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer2_reason         TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer2_at             TEXT NULL;
ALTER TABLE rss_articles  ADD COLUMN layer2_prompt_version TEXT NULL;
```
  </action>
  <verify>
    <automated>test -f migrations/007_layer2_columns.sql && grep -c "ALTER TABLE" migrations/007_layer2_columns.sql | grep -q "^8$" && echo OK</automated>
  </verify>
  <acceptance_criteria>
    - File exists at `migrations/007_layer2_columns.sql`, ≥25 lines.
    - Contains exactly 8 `ALTER TABLE` statements (4 per source table).
    - Contains backup-warning comment header.
  </acceptance_criteria>
  <done>LF-2.5 SQL form ready.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 1.3: Migration 007 Python runner — idempotent</name>
  <read_first>
    - migrations/006_layer1_columns.py (template)
  </read_first>
  <files>migrations/007_layer2_columns.py</files>
  <behavior>
    - Mirror of 006_layer1_columns.py with column tuple swapped.
    - Same CLI shape, same PRAGMA table_info guard, same applied/skipped reporting.
  </behavior>
  <action>
**Create `migrations/007_layer2_columns.py`** as a near-clone of the 006 runner:

```python
#!/usr/bin/env python3
"""Apply migration 007: add layer2_* columns to articles + rss_articles.

Usage:  python3 migrations/007_layer2_columns.py [path/to/kol_scan.db]
Default: data/kol_scan.db (relative to repo root)

REQ: LF-2.5 (v3.5 Ingest Refactor — Phase ir-2)
Idempotent via PRAGMA table_info guard. Safe to run multiple times.
"""
from __future__ import annotations

import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, "data", "kol_scan.db")

LAYER2_COLUMNS: tuple[str, ...] = (
    "layer2_verdict",
    "layer2_reason",
    "layer2_at",
    "layer2_prompt_version",
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
                print(
                    f"ERROR: '{table}' table not found in {db_path}",
                    file=sys.stderr,
                )
                return False
            for col in LAYER2_COLUMNS:
                if col in existing:
                    print(f"SKIP {table}.{col} (already present)")
                    skipped += 1
                else:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col} TEXT NULL"
                    )
                    print(f"ADD  {table}.{col}")
                    applied += 1
        conn.commit()
    finally:
        conn.close()

    print(
        f"\nmigration 007: applied {applied} column(s); "
        f"skipped {skipped} (already present)"
    )
    return True


if __name__ == "__main__":
    ok = migrate(DB_PATH)
    sys.exit(0 if ok else 1)
```
  </action>
  <verify>
    <automated>python -c "
import os, sqlite3, tempfile, subprocess, sys
fd, p = tempfile.mkstemp(suffix='.db'); os.close(fd)
conn = sqlite3.connect(p); conn.executescript('CREATE TABLE articles(id INTEGER PRIMARY KEY); CREATE TABLE rss_articles(id INTEGER PRIMARY KEY);'); conn.close()
r1 = subprocess.run([sys.executable, 'migrations/007_layer2_columns.py', p], capture_output=True, text=True); assert r1.returncode == 0; assert 'applied 8' in r1.stdout, r1.stdout
r2 = subprocess.run([sys.executable, 'migrations/007_layer2_columns.py', p], capture_output=True, text=True); assert r2.returncode == 0; assert 'applied 0' in r2.stdout, r2.stdout
print('idempotent ok'); os.unlink(p)
"</automated>
  </verify>
  <acceptance_criteria>
    - File exists at `migrations/007_layer2_columns.py`.
    - First run on empty schema applies 8; second run applies 0.
    - Module-level `migrate(db_path: str) -> bool` callable.
  </acceptance_criteria>
  <done>LF-2.5 idempotent runner ready. Migration 007 fully delivered.</done>
</task>

</tasks>

<verification>
After Tasks 1.1, 1.2, 1.3 land:

```bash
# Module imports + symbol surface
DEEPSEEK_API_KEY=dummy python -c "
from lib.article_filter import (
    ArticleMeta, ArticleWithBody, FilterResult,
    PROMPT_VERSION_LAYER1, PROMPT_VERSION_LAYER2,
    LAYER1_BATCH_SIZE, LAYER2_BATCH_SIZE, LAYER2_TIMEOUT_SEC, LAYER2_BODY_TRUNCATION_CHARS,
    layer1_pre_filter, layer2_full_body_score,
    persist_layer1_verdicts, persist_layer2_verdicts,
)
import inspect
assert inspect.iscoroutinefunction(layer2_full_body_score)
print('imports ok')
"

# Migration 007 idempotency on a temp DB
python -c "import tempfile, sqlite3, subprocess, sys, os
fd, p = tempfile.mkstemp(suffix='.db'); os.close(fd)
sqlite3.connect(p).executescript('CREATE TABLE articles(id INTEGER PRIMARY KEY); CREATE TABLE rss_articles(id INTEGER PRIMARY KEY);')
subprocess.run([sys.executable, 'migrations/007_layer2_columns.py', p], check=True)
subprocess.run([sys.executable, 'migrations/007_layer2_columns.py', p], check=True)
os.unlink(p)
"
```

Plan-level OUT-OF-SCOPE verification:
- ir-2-01 owns ingest loop wiring; this plan does NOT update `batch_ingest_from_spider.py`.
- ir-2-02 owns unit tests; the existing layer1 tests should keep passing because the new shape is additive (no Layer 1 surface changed).
</verification>

<commit_message>
feat(ir-2): real Layer 2 DeepSeek impl + persistence + migration 007

Replace V35-FOUND-01 always-pass Layer 2 placeholder in lib/article_filter.py
with real DeepSeek batch call against the v0 prompt validated 2026-05-07
spike (.scratch/layer2-validation-20260507-210423.md). Verdict alphabet
shifts from placeholder 'candidate' to spec-compliant 'ok' / 'reject'
(LF-2.5: relevant=true AND depth_score>=2 → 'ok', else 'reject').

PROMPT_VERSION_LAYER2 bumps from 'layer2_placeholder_20260507' to
'layer2_v0_20260507'. Migration 007 (.sql + idempotent .py runner) adds
layer2_verdict / layer2_reason / layer2_at / layer2_prompt_version to both
articles and rss_articles. New persist_layer2_verdicts mirrors persist_layer1.

Plan deviation (LF-2.3): REQ names deepseek-chat as the Layer 2 model;
lib/llm_deepseek module default is deepseek-v4-flash (configurable via
DEEPSEEK_MODEL env). ir-2-00 calls deepseek_model_complete which honors
the project-wide DEEPSEEK_MODEL — operator sets the model name in
~/.hermes/.env, no Layer-2-specific env var introduced.

REQs: LF-2.1, LF-2.2, LF-2.3 (operator-config gated), LF-2.5, LF-2.6, LF-2.7
Phase: v3.5-Ingest-Refactor / ir-2 / plan 00
</commit_message>

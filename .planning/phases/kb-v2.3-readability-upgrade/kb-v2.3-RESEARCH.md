# Phase kb-v2.3: KB Article Readability Upgrade — Research

**Researched:** 2026-07-02
**Domain:** SQLite schema migration, async Python cron (DeepSeek), D-14 read-path, conftest fixture parity, Fork-X translation wiring
**Confidence:** HIGH (all findings from direct code reads with file:line evidence)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Rewrite output is DISPLAY-LAYER ONLY (`body_rewritten` column). LightRAG KG always runs on original `body`.
- Fork X: rewrite emits source-language clean version into `body_rewritten`; existing translation cron reads `body_rewritten` (falling back to `body`), produces clean `body_translated`. Do NOT make the rewrite emit both languages directly.
- No regex / hand-rolled cleaning. Single LLM semantic rewrite pass.
- Storage slot: NEW `body_rewritten` column (migration 009), added to BOTH `articles` AND `rss_articles`. TEXT NULL, additive/non-breaking.
- `get_article_body()` MUST check `body_rewritten` FIRST, ABOVE filesystem `final_content.enriched.md`/`final_content.md`. (70% of articles have `final_content.md` on disk — filling the pre-wired `body_cleaned` would be silently shadowed.)
- `body_cleaned` is NOT usable as the storage slot (0-populated, shadowed by filesystem sources).
- Image URLs `http://localhost:8765/{hash}/{name}` MUST be pinned verbatim by the rewrite LLM.
- Cron host: ALIYUN (co-located with DB + translation cron, DeepSeek CN egress).
- Full backfill: ~572 displayed articles (KOL 463 + RSS 109).
- One-time backfill model: recommend Opus-tier. Steady-state: TBD (plan decision).

### Claude's Discretion
- Exact rewrite prompt wording and few-shot structure (subject to Task-1 validation gate).
- Checkpoint/stage integration detail for the rewrite cron (idempotency mechanism).
- Batch size + pacing for the backfill.
- Light-mode yes/no and specific CSS token values (ui-ux-pro-max design decision).
- Whether the steady-state (new-article) rewrite is a separate timer or folded into an existing one.

### Deferred Ideas (OUT OF SCOPE)
- Steady-state incremental rewrite automation beyond the backfill — wire the cron timer, but ongoing tuning is post-phase.
- Deleting now-moot SSG regex transforms (Surgical Changes).
- Light mode — plan may include or defer per ui-ux-pro-max recommendation.
</user_constraints>

---

## Summary

This phase adds a new `body_rewritten` column to both `articles` and `rss_articles` (migration 009), writes a new `rewrite_body_cron.py` that mirrors `translate_body_cron.py` in structure, inserts `body_rewritten` at the TOP of the D-14 fallback chain in `get_article_body()`, updates the translation cron's SELECT to read `body_rewritten` (falling back to `body`) for the Fork-X wiring, and keeps conftest.py in sync to prevent fixture-drift failures.

**The highest-risk unknown is Fork-X wiring (#7):** the current translation cron reads the raw `body` column directly. After the rewrite cron populates `body_rewritten`, the translation cron must be modified to read `COALESCE(body_rewritten, body)` instead of `body` so the clean rewritten text is what gets translated. This is a surgical 3-line change to `_select_candidate_rows` in `translate_body_cron.py`.

**Primary recommendation:** copy `translate_body_cron.py` as the skeleton for `rewrite_body_cron.py` (imports, DB resolve, logging, argparse, async run loop, per-row idempotency, error handling) — it is already the correct pattern. The only structural differences are: the WHERE guard changes from `body_translated IS NULL` to `body_rewritten IS NULL`, and the per-row call invokes a new `rewrite_body_with_deepseek` function (new in `lib/rewrite.py` or inline) instead of `translate_body_with_deepseek_tavily`.

---

## Finding 1: translate_body_cron.py — Complete Skeleton

**File:** `scripts/translate_body_cron.py` (307 lines)

### CLI shape (lines 284-296)
```python
p.add_argument("--dry-run", action="store_true", ...)
p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, ...)  # DEFAULT_LIMIT = 10
```
Invocation: `venv/bin/python scripts/translate_body_cron.py [--dry-run] [--limit N]`

### DEEPSEEK_API_KEY guard (lines 48-49) — MUST copy verbatim
```python
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
```
This must appear BEFORE any `lib.*` import. `lib/__init__.py` eagerly imports `lib.llm_deepseek`, which raises at import if the key is unset (`lib/llm_deepseek.py:56-62`).

### sys.path bootstrap (lines 52-54)
```python
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
```

### DB resolution (lines 62-78) — copy unchanged
```python
def _resolve_db_path() -> Path:
    base = Path(BASE_DIR)
    nested = base / "data" / "kol_scan.db"
    if nested.exists():
        return nested
    return base / "kol_scan.db"
```
Tries `BASE_DIR/data/kol_scan.db` (local dev layout) first, falls back to `BASE_DIR/kol_scan.db` (Hermes prod layout).

### Logging setup (lines 81-103) — copy unchanged
- Dual sink: `logging.StreamHandler(sys.stdout)` + `logging.FileHandler(log_path)`
- Log file: `.scratch/translate-body-cron-YYYYMMDD.log` — rewrite cron should use `.scratch/rewrite-body-cron-YYYYMMDD.log`
- UTF-8 reconfigure on stdout (handles Chinese titles on Windows)
- `force=True` on `basicConfig` (essential — prevents silently swallowed logs when another module called basicConfig first)

### Idempotent SELECT (lines 106-141) — the most critical structural element

Current translation cron SELECT includes both tables via UNION ALL with this WHERE pattern per table:
```sql
WHERE layer1_verdict = 'candidate'
  AND layer2_verdict = 'ok'
  AND body IS NOT NULL AND body != ''
  AND (body_translated IS NULL OR title_translated IS NULL)
```
The idempotency guard is the final AND clause. The **rewrite cron** version becomes:
```sql
WHERE layer1_verdict = 'candidate'
  AND layer2_verdict = 'ok'
  AND body IS NOT NULL AND body != ''
  AND body_rewritten IS NULL
```
Tuple shape returned: `(id, table_name, title, body, ...)` — the `table_name` literal (`'articles'` or `'rss_articles'`) is injected by the SELECT, not a real column.

ORDER BY: `layer2_at ASC, id ASC` (processes oldest-approved articles first).

### Per-row async loop (lines 251-280) — copy structure, not content

```python
async def _run(args, logger):
    conn = sqlite3.connect(str(db_path))
    try:
        rows = _select_candidate_rows(conn, args.limit)
        if not rows:
            logger.info("0 candidates — nothing to translate")
            return 0
        tally = {"ok": 0, "fail": 0, "dry_run": 0}
        for row in rows:
            outcome = await _translate_one_row(row, conn, args.dry_run, logger)
            tally[outcome] = tally.get(outcome, 0) + 1
        ...
    finally:
        conn.close()
```
The loop is SERIAL (not concurrent) — one `await` per row, no `asyncio.gather`. This is intentional: DeepSeek rate-limit safety. Rewrite cron must also be serial.

### Per-row idempotency + UPDATE pattern (lines 144-248)

Per-row function returns `"ok"` / `"fail"` / `"dry_run"`. Lazy import of `lib.translate` inside the per-row function (lines 172-177) so `--dry-run` never imports the DeepSeek chain. The rewrite cron should do the same lazy import of the rewrite function.

UPDATE statement pattern (lines 195-206):
```python
conn.execute(
    f"UPDATE {table} SET body_translated = ?, translated_lang = ?, translated_at = ? WHERE id = ?",
    (body_result["body_translated"], body_result["lang"],
     datetime.now(timezone.utc).isoformat(), art_id),
)
conn.commit()
```
The `table` variable is a literal string from the SELECT (`'articles'` or `'rss_articles'`) — not user input. The `# noqa: S608` comment acknowledges the f-string-in-SQL but documents why it is safe.

For the rewrite cron the UPDATE becomes:
```python
conn.execute(
    f"UPDATE {table} SET body_rewritten = ?, rewritten_at = ? WHERE id = ?",
    (rewritten_body, datetime.now(timezone.utc).isoformat(), art_id),
)
conn.commit()
```
This requires a `rewritten_at DATETIME` column in migration 009 (see Finding 4).

### Entry point (lines 299-306)
```python
def main(argv=None):
    args = _parse_args(argv)
    logger = _setup_logging()
    return asyncio.run(_run(args, logger))

if __name__ == "__main__":
    raise SystemExit(main())
```

---

## Finding 2: get_article_body() D-14 Chain — Exact Edit Required

**File:** `kb/data/article_query.py`, lines 587-619

### Current chain (measured, not from docs)

```python
def get_article_body(rec: ArticleRecord) -> tuple[str, BodySource]:
    base_path = config.KB_BASE_PATH
    url_hash = resolve_url_hash(rec)
    images_dir = Path(config.KB_IMAGES_DIR)
    for fname in ("final_content.enriched.md", "final_content.md"):  # line 605
        p = images_dir / url_hash / fname
        if p.exists():
            md = p.read_text(encoding="utf-8")
            md = _strip_hermes_metadata_prefix(md)
            md = _strip_external_wechat_images(md)
            md = _rewrite_image_paths(md, base_path)
            md = _rewrite_image_text_refs_to_html(md)
            return md, "vision_enriched"               # line 613
    # 260522-clt Pass 1: prefer regex-stripped body_cleaned over raw body
    body = rec.body_cleaned or rec.body or ""          # line 615
    body = _strip_external_wechat_images(body)
    body = _rewrite_image_paths(body, base_path)
    body = _rewrite_image_text_refs_to_html(body)
    return body, "raw_markdown"                        # line 619
```

**Current precedence:** `final_content.enriched.md` (fs) → `final_content.md` (fs) → `body_cleaned` (db) → `body` (db)

### Required change (minimal surgical edit)

Insert `body_rewritten` check BEFORE the filesystem loop. Change lines 587-619 to:

```python
def get_article_body(rec: ArticleRecord) -> tuple[str, BodySource]:
    base_path = config.KB_BASE_PATH
    url_hash = resolve_url_hash(rec)
    images_dir = Path(config.KB_IMAGES_DIR)
    # kb-v2.3: body_rewritten wins over ALL filesystem sources (display-only column)
    if rec.body_rewritten:                              # NEW LINES
        body = rec.body_rewritten
        body = _strip_external_wechat_images(body)
        body = _rewrite_image_paths(body, base_path)
        body = _rewrite_image_text_refs_to_html(body)
        return body, "raw_markdown"
    for fname in ("final_content.enriched.md", "final_content.md"):
        ...  # unchanged
```

**Why "raw_markdown" source tag:** `body_rewritten` is a DB column, not a filesystem enriched file. Using `"raw_markdown"` avoids a new BodySource literal and keeps callers that branch on `"vision_enriched"` unaffected.

**New `BodySource` value option:** A third literal `"rewritten"` could be added to the `BodySource = Literal[...]` type at line 27. This is a "Claude's Discretion" call — the planner may choose either approach. Using `"raw_markdown"` is the zero-new-type-change option.

---

## Finding 3: ArticleRecord Dataclass + SELECT Columns to Update

**File:** `kb/data/article_query.py`, lines 97-131 (dataclass), 313-315 (KOL SELECT), 330-332 (RSS SELECT), 237-274 (row-to-record converters)

### Dataclass — add one field (line 131, after body_repositioned)

Current last field (line 131):
```python
body_repositioned: Optional[str] = None
```

Add after it:
```python
body_rewritten: Optional[str] = None    # kb-v2.3 display-only LLM rewrite
```

**Frozen dataclass (line 97):** `@dataclass(frozen=True)` — the field addition is append-only, no structural change.

### KOL SELECT (list_articles, lines 313-315) — add column

Current:
```python
"SELECT id, title, url, body, content_hash, lang, update_time, "
"title_translated, body_translated, translated_lang, "
"body_cleaned, body_repositioned "
"FROM articles"
```

Add `body_rewritten` to the SELECT list (append after `body_repositioned`):
```python
"body_cleaned, body_repositioned, body_rewritten "
```

### RSS SELECT (list_articles, lines 330-332) — add column

Current:
```python
"SELECT id, title, url, body, content_hash, lang, "
"published_at, fetched_at, "
"title_translated, body_translated, translated_lang, "
"body_cleaned "
"FROM rss_articles"
```

Add `body_rewritten`:
```python
"body_cleaned, body_rewritten "
```

### get_article_by_hash — THREE independent SELECT statements to update

There are 3 separate SELECTs inside `get_article_by_hash` that must each add `body_rewritten`:

1. **KOL direct match** (line 379-384):
   ```python
   "SELECT id, title, url, body, content_hash, lang, update_time, "
   "title_translated, body_translated, translated_lang, "
   "body_cleaned, body_repositioned "
   "FROM articles WHERE content_hash = ?"
   ```

2. **RSS direct match** (line 389-394):
   ```python
   "SELECT id, title, url, body, content_hash, lang, "
   "published_at, fetched_at, "
   "title_translated, body_translated, translated_lang, "
   "body_cleaned "
   "FROM rss_articles WHERE substr(content_hash, 1, 10) = ?"
   ```

3. **KOL NULL hash fallback** (lines 400-404):
   ```python
   "SELECT id, title, url, body, content_hash, lang, update_time, "
   "title_translated, body_translated, translated_lang, "
   "body_cleaned, body_repositioned "
   "FROM articles WHERE content_hash IS NULL"
   ```

All three must add `body_rewritten` to avoid `_row_get()` returning `None` silently.

### Row-to-record converters — add body_rewritten

`_row_to_record_kol` (lines 237-253): add `body_rewritten=_row_get(row, "body_rewritten")` after `body_repositioned`.

`_row_to_record_rss` (lines 256-274): add `body_rewritten=_row_get(row, "body_rewritten")` after `body_cleaned`.

**Note:** `_row_get()` (line 225-233) already provides safe column access — returns `None` if the column is absent. This means the code is safe to deploy before the migration runs (graceful degradation to `None`). But the migration must run before the cron populates data.

---

## Finding 4: Migration 009 Shape

**Reference:** `kb/data/migrations/008_add_body_cleaned_columns.sql`

**Migration 008 pattern (exact SQL):**
```sql
ALTER TABLE articles ADD COLUMN body_cleaned TEXT;
ALTER TABLE articles ADD COLUMN body_repositioned TEXT;
ALTER TABLE rss_articles ADD COLUMN body_cleaned TEXT;
```

**Migration 009 must follow the same additive pattern:**

```sql
-- 009: Add body_rewritten column for kb-v2.3 display-only LLM rewrite.
-- Additive, non-breaking, idempotent (run_migrations.py guards via PRAGMA table_info).
--
-- Context: rewrite_body_cron.py (mirroring translate_body_cron.py) writes
-- LLM-rewritten clean article bodies here. get_article_body() D-14 chain
-- checks body_rewritten FIRST, above filesystem final_content.md sources.
-- KG (LightRAG) always uses original body column; body_rewritten is display-only.
--
-- body_cleaned NOT used (0-populated; shadowed by final_content.md for 70% of corpus).
-- See decision_rewrite_display_only_kg_uses_original.md for full rationale.
--
-- No backfill required (NULL is correct initial state).
-- Rollback: ALTER TABLE <t> DROP COLUMN body_rewritten (SQLite >= 3.35).

ALTER TABLE articles ADD COLUMN body_rewritten TEXT;
ALTER TABLE articles ADD COLUMN rewritten_at DATETIME;
ALTER TABLE rss_articles ADD COLUMN body_rewritten TEXT;
ALTER TABLE rss_articles ADD COLUMN rewritten_at DATETIME;
```

**Why `rewritten_at`:** mirrors `translated_at DATETIME` in migration 008 / schema. The cron UPDATE statement needs an audit timestamp column. Without it, there is no way to track when the rewrite ran or detect stale rewrites.

**Note on `rss_articles.body_repositioned`:** migration 008 did NOT add `body_repositioned` to `rss_articles` — only to `articles` (lines 19-20 of 008). The `_row_to_record_rss` function (line 274) does NOT include `body_repositioned`. Migration 009 must NOT add `body_repositioned` to `rss_articles` (stays KOL-only). Only `body_rewritten` and `rewritten_at` go to both tables.

---

## Finding 5: conftest.py CREATE TABLE — Columns to Add

**File:** `tests/integration/kb/conftest.py`, lines 79-115

### Current `articles` CREATE TABLE (lines 80-96)
```sql
CREATE TABLE articles (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    body TEXT,
    content_hash TEXT,
    lang TEXT,
    update_time INTEGER,
    layer1_verdict TEXT,
    layer2_verdict TEXT,
    body_translated TEXT,
    title_translated TEXT,
    translated_lang VARCHAR(5),
    translated_at DATETIME,
    body_cleaned TEXT,
    body_repositioned TEXT
);
```

**Must add:**
```sql
    body_rewritten TEXT,
    rewritten_at DATETIME
```

### Current `rss_articles` CREATE TABLE (lines 97-115)
```sql
CREATE TABLE rss_articles (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    body TEXT,
    content_hash TEXT,
    lang TEXT,
    published_at TEXT,
    fetched_at TEXT,
    topics TEXT,
    depth INTEGER,
    layer1_verdict TEXT,
    layer2_verdict TEXT,
    body_translated TEXT,
    title_translated TEXT,
    translated_lang VARCHAR(5),
    translated_at DATETIME,
    body_cleaned TEXT
);
```

**Must add:**
```sql
    body_rewritten TEXT,
    rewritten_at DATETIME
```

**Note:** `rss_articles` does NOT have `body_repositioned` (KOL-only). The fixture correctly reflects this. Maintain that asymmetry — do NOT add `body_repositioned` to `rss_articles`.

**Fixture-drift failure mode (documented in CLAUDE.md behavior-anchor section):** 2026-05-15 lesson: "test fixture CREATE TABLE not synced with migration silently masks the downstream bug." If conftest.py fixtures are not updated in sync with migration 009, `_row_get(row, "body_rewritten")` will return `None` in tests because the column does not exist in the in-memory fixture DB — but this will look like "column not populated" rather than "column missing", hiding schema-drift bugs.

---

## Finding 6: lib/translate.py — DeepSeek Wrapper Patterns to Reuse

**File:** `lib/translate.py` (307 lines)

### Key constants (lines 35-41)
```python
TRANSLATE_TITLE_TIMEOUT_S: float = 15.0
TRANSLATE_BODY_TIMEOUT_S: float = 300.0
_BAKE_MODEL: str = "deepseek-v4-pro"
```

The body translation uses `deepseek-v4-pro` hardcoded (line 40), overriding the module-level `_MODEL` env var. The rewrite function should do the same — pin the model explicitly rather than reading an env var, since Opus-tier rewrite quality is the explicit goal.

### DeepSeek call pattern (lines 274-285)
```python
translated = await asyncio.wait_for(
    deepseek_model_complete(prompt, model=_BAKE_MODEL),
    timeout=TRANSLATE_BODY_TIMEOUT_S,
)
cleaned = (translated or "").strip()
if not cleaned:
    return None
return {"body_translated": cleaned, "lang": tgt}
```

For the rewrite function the pattern is identical but simpler (no `lang` output, no Tavily, no `tgt` language):
```python
rewritten = await asyncio.wait_for(
    deepseek_model_complete(prompt, model=_REWRITE_MODEL),
    timeout=REWRITE_BODY_TIMEOUT_S,
)
cleaned = (rewritten or "").strip()
if not cleaned:
    return None
return cleaned
```

### Tavily (lines 90-121) — NOT needed for rewrite

Tavily is used in translation to look up terminology equivalents in the target language. The rewrite task is within the source language — no cross-language terminology lookup needed. The rewrite function does NOT need to call `_tavily_search`. This simplifies the rewrite function relative to the translate function.

### Boilerplate strip prompts (lines 149-195) — REUSE as starting point

The translate body prompt already covers the critical stripping behaviors needed by the rewrite:
- Line 170-173: WeChat boilerplate strip (关注公众号, 点赞, 在看, 扫码, 转载声明, 作者简介)
- Line 176-179: Lead filler strip (今天我们来聊, 大家好, 本文将介绍)
- Line 180-184: Image reference preservation at exact positions, URL verbatim

The rewrite prompt must carry the same rules but WITHOUT the "translate to {target_lang}" instruction. The task is: clean and reformat WITHIN the source language. Add the image URL pinning constraint explicitly (CONTEXT.md requirement):

> Image URLs of the form `http://localhost:8765/{hash}/{filename}` MUST appear VERBATIM in the output — do not modify, shorten, or reformat them.

### `detect_source_lang` (lines 70-82) — reuse unchanged

The rewrite cron needs to know the source lang to include it in the prompt system context (e.g., "clean this Chinese markdown"). Import and reuse `detect_source_lang` from `lib.translate`.

### Lazy import pattern (translate_body_cron.py lines 172-177) — MUST replicate

The translation cron imports `lib.translate` lazily inside the per-row function so `--dry-run` never loads the DeepSeek chain. The rewrite cron must do the same:

```python
if dry_run:
    ...
    return "dry_run"

from lib.rewrite import rewrite_body_with_deepseek  # lazy import here
```

---

## Finding 7 (CRITICAL): Fork-X Translation-Wiring — What Must Change in translate_body_cron.py

**This is the highest-risk finding. The current translation cron reads dirty `body` from the DB; after the rewrite cron runs, it must read `body_rewritten` (clean) instead.**

### Current translate_body_cron.py SELECT (lines 119-141)

```python
sql = """
    SELECT id, table_name, title, body, body_translated, title_translated
      FROM (
        SELECT id, 'articles' AS table_name, title, body,
               body_translated, title_translated, layer2_at
          FROM articles
         WHERE layer1_verdict = 'candidate'
           AND layer2_verdict = 'ok'
           AND body IS NOT NULL AND body != ''
           AND (body_translated IS NULL OR title_translated IS NULL)
        UNION ALL
        SELECT id, 'rss_articles' AS table_name, title, body,
               body_translated, title_translated, layer2_at
          FROM rss_articles
         WHERE layer1_verdict = 'candidate'
           AND layer2_verdict = 'ok'
           AND body IS NOT NULL AND body != ''
           AND (body_translated IS NULL OR title_translated IS NULL)
      )
     ORDER BY layer2_at ASC, id ASC
     LIMIT ?
"""
```

The SELECT fetches `body` (line: `title, body, body_translated`) and passes it raw to `translate_body_with_deepseek_tavily(title, body, ...)` at line 184. There is NO fallback to `body_rewritten` — it reads the raw dirty body column unconditionally.

### Required change to translate_body_cron.py

Replace `body` in the SELECT with `COALESCE(body_rewritten, body) AS body` in BOTH subqueries:

```sql
SELECT id, 'articles' AS table_name, title,
       COALESCE(body_rewritten, body) AS body,
       body_translated, title_translated, layer2_at
  FROM articles
 WHERE ...
UNION ALL
SELECT id, 'rss_articles' AS table_name, title,
       COALESCE(body_rewritten, body) AS body,
       body_translated, title_translated, layer2_at
  FROM rss_articles
 WHERE ...
```

**Why COALESCE not a conditional:** the cron will continue to run on articles where `body_rewritten` is not yet populated (e.g., newly ingested articles that haven't been rewritten yet). `COALESCE(body_rewritten, body)` gives the clean version when available and falls back to dirty `body` transparently. The column alias `AS body` means the rest of the function (`_translate_one_row`, `translate_body_with_deepseek_tavily`) needs zero changes — the variable named `body` in the tuple unpacking at line 157 receives the coalesced value automatically.

**Impact scope of this change:** 3 lines in `_select_candidate_rows` (add COALESCE wrapping in both subqueries). No other change to `translate_body_cron.py`. The per-row function, the UPDATE, and `lib/translate.py` are all unaffected.

**Ordering dependency:** the translate cron must NOT run a batch on an article until that article's `body_rewritten` is populated. The COALESCE fallback handles the interim state correctly — it will translate the dirty body for articles that haven't been rewritten yet, and then the rewrite cron will later populate `body_rewritten`. This creates an ordering issue: if translate runs first on a newly-ingested article, it may produce a dirty `body_translated` that was derived from the dirty `body`. Post-rewrite, the `body_translated` won't be re-generated automatically (it's already non-NULL).

**Mitigation option (planner decision):** after backfill completes, run a one-shot re-translation pass: `WHERE body_rewritten IS NOT NULL AND body_translated IS NOT NULL AND ...` to clear `body_translated` for all 572 articles and let the translation cron regenerate from the clean `body_rewritten`. This is a "Claude's Discretion" planning decision.

**Alternatively (simpler):** backfill the rewrite first, then run the translation cron. Since ~94% of articles are already translated, the new `body_rewritten` column being the translation source only matters for the ~6% not yet translated + all future articles. For the 94% already translated, a re-translation pass from clean body would improve quality but is optional. Flag this tradeoff explicitly in the plan.

---

## Finding 8: Behavior-Anchor Test Discipline — Rewrite Cron Qualification

**Reference:** CLAUDE.md "Behavior-Anchor Harness for Hot Orchestration Code" section

### Three signals checklist for rewrite_body_cron.py

| Signal | Rewrite cron | Qualifies? |
|--------|--------------|-----------|
| (a) >300 LOC nested batches | The cron is ~150 LOC (translating from the 307-line translate cron); shorter due to no title/dual-field handling | BORDERLINE |
| (b) Silent broad except handlers around external calls | Yes — per-row try/except wraps DeepSeek call; failures logged + skipped silently | YES |
| (c) Cost-or-correctness consequences | Yes — bad rewrite overwrites display bodies for 572 articles; DeepSeek API spend is modest but real | YES |

**Conclusion:** The rewrite cron meets signals (b) and (c). Signal (a) is borderline but the other two are sufficient. The behavior-anchor harness should be applied. The existing model is `tests/unit/test_ingest_from_db_orchestration.py` (anchors on observable post-conditions in seeded in-memory DB + mocked callables).

### Existing test precedent for a similar cron

- `tests/unit/test_translate.py` — tests `lib/translate.py` functions (mock LLM + Tavily). File exists, 60+ lines.
- No test file exists for `translate_body_cron.py` itself (no `tests/unit/test_translate_body_cron.py` found).

### Recommended test file

**`tests/unit/test_rewrite_body_cron.py`** — behavior-anchor tests anchored on post-conditions:

| Anchor ID | Behavior | Test Pattern |
|-----------|---------|--------------|
| RW-1 | `--dry-run` flag: SELECT runs but no LLM call and no UPDATE to DB | seed 3 rows `body_rewritten IS NULL`; mock LLM not called; assert all 3 rows still have `body_rewritten IS NULL` post-run |
| RW-2 | Idempotency: rows with `body_rewritten IS NOT NULL` are skipped by the WHERE guard | seed 2 rows — 1 with `body_rewritten` populated, 1 NULL; assert only 1 LLM call; populated row unchanged |
| RW-3 | Per-row failure is logged + skipped; remaining rows continue | mock LLM to raise on row 1, return string on row 2; assert `body_rewritten` NULL on row 1, populated on row 2 |
| RW-4 | `--limit N` respected | seed 5 eligible rows, run with `--limit 2`; assert exactly 2 LLM calls |
| RW-5 | UPDATE persists `body_rewritten` AND `rewritten_at` | run on 1 row; assert both columns non-NULL post-run |

**In-memory DB fixture** for these tests must include the `body_rewritten TEXT, rewritten_at DATETIME` columns (mirrors the conftest.py update in Finding 5).

---

## Finding 9: Additional SELECT Sites (Complete Audit)

Beyond `list_articles` and `get_article_by_hash`, every SELECT that builds an `ArticleRecord` must include `body_rewritten`. Full audit of SELECT sites in `article_query.py`:

| Function | Lines | Tables | Needs update |
|----------|-------|--------|-------------|
| `list_articles` — KOL path | 313-315 | articles | YES |
| `list_articles` — RSS path | 330-332 | rss_articles | YES |
| `get_article_by_hash` — KOL direct | 379-384 | articles | YES |
| `get_article_by_hash` — RSS direct | 389-394 | rss_articles | YES |
| `get_article_by_hash` — KOL NULL hash fallback | 400-404 | articles | YES |
| `topic_articles_query` — KOL path | 841-844 (`a.body_cleaned, a.body_repositioned` at 844) | articles (alias `a`) | YES |
| `topic_articles_query` — RSS path | 861-865 (`r.body_cleaned` at 865) | rss_articles (alias `r`) | YES |
| `entity_articles_query` — KOL path | 916-919 (`a.body_cleaned, a.body_repositioned` at 919) | articles (alias `a`) | YES |

**CORRECTED 2026-07-02 (plan-checker Blocker 1):** the original audit listed only 5 sites and missed the 3 topic/entity-browse SELECTs. There are **8 ArticleRecord-building SELECT sites total** (confirmed by grepping the `_row_to_record_*` call sites: lines 326, 343, 386, 398, 406, 853, 873, 927 = 8). `entity_articles_query` has NO RSS branch (`extracted_entities` is KOL-only per prod schema — RSS entity extraction does not exist in v1.0), so only the KOL entity SELECT at 916-919 exists. The topic/entity SELECTs use table ALIASES (`a.` / `r.`), so the added column must be `a.body_rewritten` / `r.body_rewritten` respectively.

Total: **8 SELECT statements** to update. All follow the same pattern: append `body_rewritten` (alias-qualified where the SELECT uses `a.`/`r.`) to the column list. The `_row_get()` helper at line 225 provides safe access — if a test runs against a fixture without the column, it returns `None` gracefully rather than raising `KeyError`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async DeepSeek call with timeout | Custom OpenAI wrapper | `deepseek_model_complete(prompt, model=...) + asyncio.wait_for(...)` from `lib/llm_deepseek.py` | Already handles client reuse, timeout config via `OMNIGRAPH_DEEPSEEK_TIMEOUT`, lazy key check |
| Language detection | Regex or langdetect | `detect_source_lang()` from `lib/translate.py:70` | Already tuned for Chinese-character ratio, handles empty string |
| DB path resolution | Hardcoded path | `_resolve_db_path()` from `translate_body_cron.py:62` | Handles both local dev (`data/kol_scan.db`) and Aliyun prod layouts |
| Logging dual-sink | Manual handlers | `_setup_logging()` from `translate_body_cron.py:81` | UTF-8 reconfigure, force=True, daily log file naming already correct |
| Idempotent UPDATE | Custom dedup logic | `WHERE body_rewritten IS NULL` in SELECT guard + commit-per-row | Pattern proven in translate cron; commit-per-row ensures no all-or-nothing batch loss |

---

## Common Pitfalls

### Pitfall 1: body_cleaned vs body_rewritten confusion
**What goes wrong:** Developer writes to `body_cleaned` (already exists from migration 008, `body_cleaned` = 0 rows) instead of the new `body_rewritten`. The D-14 chain checks `body_cleaned` AFTER filesystem sources — filling it would be silently shadowed for 70% of articles.
**How to avoid:** Migration 009 adds `body_rewritten`. The rewrite cron UPDATE targets `body_rewritten`. The D-14 chain inserts the `body_rewritten` check BEFORE the filesystem loop.

### Pitfall 2: DEEPSEEK_API_KEY import-time raise
**What goes wrong:** `import lib.translate` (which imports `lib.llm_deepseek` which imports `lib/__init__.py` which eagerly imports `deepseek_model_complete`) raises `RuntimeError: DEEPSEEK_API_KEY is not set` at script import time, before `config.load_env()` runs.
**How to avoid:** `os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")` BEFORE any `lib.*` import. See `translate_body_cron.py:48-49` — copy verbatim.

### Pitfall 3: conftest.py fixture drift
**What goes wrong:** `migration 009` adds `body_rewritten` to prod schema but `conftest.py` CREATE TABLE is not updated. Tests pass because `_row_get()` gracefully returns `None` — but the D-14 `if rec.body_rewritten:` branch never exercises in tests, masking bugs.
**How to avoid:** Update both `articles` and `rss_articles` CREATE TABLE in `conftest.py:79-115` in the SAME commit as migration 009.

### Pitfall 4: Fork-X translation cron reads dirty body after rewrite
**What goes wrong:** Rewrite cron backfills `body_rewritten` for 572 articles. Translation cron still reads raw `body` (line 121: `title, body, body_translated`). Result: 572 clean rewritten articles but their English translation (`body_translated`) was generated from the dirty source.
**How to avoid:** Apply the COALESCE change to `translate_body_cron.py` as part of this phase (Finding 7). Deploy before running the backfill so the translation cron immediately benefits from clean bodies on any new articles.

### Pitfall 5: get_article_by_hash has 3 independent SELECTs
**What goes wrong:** Only `list_articles` is updated; `get_article_by_hash` (which is the primary path for the KB API `/api/article/{hash}`) still returns `ArticleRecord` with `body_rewritten=None` because its 3 SELECTs don't include the column. The D-14 fix has zero effect for SSG export and live API.
**How to avoid:** Update all 5 SELECT statements identified in Finding 9.

### Pitfall 6: Image URL mangling by the rewrite LLM
**What goes wrong:** DeepSeek rewrites `http://localhost:8765/abc/0.jpg` to a relative path or shortens it. `_rewrite_image_paths()` regex (`r"http://localhost:8765/"`) no longer matches. Images disappear silently.
**How to avoid:** Rewrite prompt must include an explicit verbatim-URL constraint (see CONTEXT.md image URL section). Prompt validation gate (CONTEXT.md success criterion) must grep-diff URL sets between input and output before batch.

### Pitfall 7: Rewrite cron uses asyncio.gather instead of serial loop
**What goes wrong:** Concurrent DeepSeek calls hit rate limits; a single failure causes the gather to fail all pending tasks.
**How to avoid:** Mirror translate cron exactly — serial `for row in rows: outcome = await _translate_one_row(...)`. No `asyncio.gather`.

---

## Architecture Patterns

### Recommended file layout for new code

```
scripts/
└── rewrite_body_cron.py          # mirrors translate_body_cron.py

lib/
└── rewrite.py                    # new: rewrite_body_with_deepseek() function
                                  # (OR inline in rewrite_body_cron.py — planner decision)

kb/data/migrations/
└── 009_add_body_rewritten_columns.sql   # new migration

tests/unit/
└── test_rewrite_body_cron.py     # behavior-anchor tests (see Finding 8)

tests/integration/kb/
└── conftest.py                   # update existing CREATE TABLE (Finding 5)
```

### rewrite_body_cron.py skeleton (derived from translate_body_cron.py)

```python
"""Nightly body-rewrite cron (kb-v2.3).

Rewrites ~N article bodies per run using DeepSeek (source-language clean
display version) for articles that passed Layer 1 + Layer 2 but lack
body_rewritten. Runs on Aliyun only (co-located with DB + translate cron).

CLI:
    venv/bin/python scripts/rewrite_body_cron.py                # production
    venv/bin/python scripts/rewrite_body_cron.py --dry-run      # SELECT only
    venv/bin/python scripts/rewrite_body_cron.py --limit 50     # backfill batch
"""
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")  # BEFORE any lib.* import

# [sys.path bootstrap — identical to translate_body_cron.py:52-54]
# [from config import BASE_DIR — identical]

DEFAULT_LIMIT = 10

# DB resolution: copy _resolve_db_path() from translate_body_cron.py unchanged

# Logging: copy _setup_logging() from translate_body_cron.py, change log filename
#          to "rewrite-body-cron-YYYYMMDD.log"

def _select_candidate_rows(conn, limit):
    sql = """
        SELECT id, table_name, title, body
          FROM (
            SELECT id, 'articles' AS table_name, title, body, layer2_at
              FROM articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND body_rewritten IS NULL
            UNION ALL
            SELECT id, 'rss_articles' AS table_name, title, body, layer2_at
              FROM rss_articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND body_rewritten IS NULL
          )
         ORDER BY layer2_at ASC, id ASC
         LIMIT ?
    """
    return list(conn.execute(sql, (limit,)))

async def _rewrite_one_row(row, conn, dry_run, logger):
    art_id, table, title, body = row
    if dry_run:
        logger.info("[dry-run] WOULD rewrite id=%s table=%s ...", art_id, table)
        return "dry_run"
    from lib.rewrite import rewrite_body_with_deepseek  # lazy import
    try:
        result = await rewrite_body_with_deepseek(title or "", body)
    except Exception as e:
        logger.warning("rewrite raised (id=%s table=%s): %s — leaving NULL", art_id, table, e)
        result = None
    if result:
        conn.execute(
            f"UPDATE {table} SET body_rewritten = ?, rewritten_at = ? WHERE id = ?",
            (result, datetime.now(timezone.utc).isoformat(), art_id),
        )
        conn.commit()
        logger.info("rewrite ok id=%s table=%s in=%d out=%d", art_id, table, len(body), len(result))
        return "ok"
    return "fail"

# _run(), _parse_args(), main() — mirror translate_body_cron.py structure exactly
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `body_cleaned` as display slot | New `body_rewritten` column | kb-v2.3 (this phase) | Avoids filesystem shadowing for 70% of articles |
| `get_article_body` checks filesystem first | `body_rewritten` wins before filesystem | kb-v2.3 (this phase) | Clean display body always wins when available |
| Translate cron reads raw `body` | Translate cron reads `COALESCE(body_rewritten, body)` | kb-v2.3 (this phase) | Clean source for English translation |

---

## Open Questions

1. **Re-translation of already-translated articles**
   - What we know: ~94% of 572 articles already have `body_translated` (derived from dirty `body`). After rewrite backfill, these translations are "dirty-sourced."
   - What's unclear: Is a second translation pass (re-generate `body_translated` from clean `body_rewritten`) in scope for this phase?
   - Recommendation: Include a one-shot re-translation mechanism in the plan ("clear `body_translated` for `body_rewritten IS NOT NULL` rows, let translate cron regenerate") but gate it behind a cost/quality assessment. Cost: 572 articles × 8.6K avg chars = ~4.9M tokens at DeepSeek body-translate rates. Mark as Phase 1 optional/bonus task.

2. **Rewrite model for steady-state (new articles)**
   - What we know: Opus-tier locked for one-time backfill. Post-backfill, new articles need rewriting too.
   - What's unclear: Whether steady-state uses the same Opus model or a cheaper Flash model.
   - Recommendation: Plan should wire the cron timer for steady-state but default to the same `deepseek-v4-pro` model used for body translation (already proven in translate cron). Document as "match translate cron model selection unless user specifies otherwise."

3. **Chunking for max-154K-char articles**
   - What we know: Max body is 154,372 chars (CONTEXT.md specifics). DeepSeek context window is large but output truncation can occur.
   - What's unclear: Whether 154K chars exceeds safe rewrite capacity.
   - Recommendation: Mirror the approach mentioned in CONTEXT.md for the translate_kb.py 15KB threshold — add a per-row body-length guard: if `len(body) > 30_000` (configurable), skip with a `logger.warning` and leave `body_rewritten NULL` rather than risk truncation. Flag the oversized articles in the log for manual review. This is a "Claude's Discretion" plan decision.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | `pytest.ini` or `setup.cfg` (existing) |
| Quick run command | `venv/Scripts/python.exe -m pytest tests/unit/test_rewrite_body_cron.py -v` |
| Full suite command | `venv/Scripts/python.exe -m pytest tests/unit/ tests/integration/kb/ -v` |

### Phase Requirements → Test Map

| Gate (from CONTEXT.md) | Behavior | Test Type | Automated Command | File Exists? |
|------------------------|----------|-----------|-------------------|-------------|
| Schema: migration 009 adds `body_rewritten` | Migration runs; both tables gain column | integration | `pytest tests/integration/kb/ -v` | Existing (needs fixture update) |
| Read path: `body_rewritten` wins over filesystem | `get_article_body()` returns `body_rewritten` when non-NULL | unit | `pytest tests/unit/kb/test_article_query.py -v` | Check if exists |
| Cron idempotency | `WHERE body_rewritten IS NULL` guard skips already-rewritten rows | unit | `pytest tests/unit/test_rewrite_body_cron.py::test_idempotency -v` | NO — Wave 0 gap |
| Cron dry-run | No LLM call, no UPDATE | unit | `pytest tests/unit/test_rewrite_body_cron.py::test_dry_run -v` | NO — Wave 0 gap |
| Prompt validation gate | 0 mangled URLs, 0 HTML leakage, markdownlint clean | manual + grep | `grep -c 'http://localhost:8765/' input.md && grep -c 'http://localhost:8765/' output.md` | Manual |
| conftest.py parity | Fixtures include `body_rewritten` column | unit | `pytest tests/integration/kb/ -v` | YES (needs update) |

### Wave 0 Gaps
- [ ] `tests/unit/test_rewrite_body_cron.py` — covers RW-1 through RW-5 behavior anchors (see Finding 8)
- [ ] `tests/unit/kb/test_article_query_body_rewritten.py` — covers the D-14 chain priority change (body_rewritten wins over filesystem)

*(Existing tests for translate cron: none. Existing tests for lib/translate.py: `tests/unit/test_translate.py` — only covers the translate functions, not the cron orchestrator.)*

---

## Sources

### Primary (HIGH confidence — direct code reads)
- `scripts/translate_body_cron.py` (307 lines) — complete skeleton, SELECT pattern, loop structure, per-row error handling
- `lib/translate.py` (307 lines) — DeepSeek call pattern, timeout constants, prompt structure, lazy import pattern
- `kb/data/article_query.py` (lines 1-419, 575-685) — D-14 chain, ArticleRecord dataclass, all 5 SELECT sites, _row_to_record converters
- `kb/data/migrations/008_add_body_cleaned_columns.sql` — migration pattern, additive ALTER TABLE style
- `tests/integration/kb/conftest.py` (285 lines) — exact CREATE TABLE for both tables
- `lib/llm_deepseek.py` (136 lines) — client construction, model override parameter, timeout config
- `lib/checkpoint.py` (lines 30-90) — STAGE_FILES map, _STAGE_ORDER (6 stages); rewrite cron does NOT use checkpoint.py — it is DB-only with `body_rewritten IS NULL` as the idempotency guard
- `tests/unit/test_run_kol_scan_orchestration.py` (preamble) — behavior-anchor harness documentation + qualification signals
- `tests/unit/test_translate.py` (60+ lines) — existing translate test pattern (lazy import, `os.environ.setdefault`, mock pattern)
- `CLAUDE.md` — Behavior-Anchor Harness section, Principle #6, #9, fixture-drift lesson

### Secondary (MEDIUM confidence)
- CONTEXT.md `<specifics>` section — corpus sizes (572, 463 KOL + 109 RSS), avg body 8.6K chars, max 154K chars, translation coverage 94%
- Memory `decision_rewrite_display_only_kg_uses_original.md` — all locked decisions + discovered facts

---

## Metadata

**Confidence breakdown:**
- Cron skeleton (Finding 1): HIGH — complete direct read of the 307-line file
- D-14 chain edit (Finding 2): HIGH — direct read of lines 587-619
- SELECT sites audit (Findings 3 + 9): HIGH — read all 5 SELECT statements
- Migration 009 shape (Finding 4): HIGH — directly mirrors 008 pattern
- conftest.py fixture columns (Finding 5): HIGH — direct read of CREATE TABLE
- lib/translate.py patterns (Finding 6): HIGH — complete direct read
- Fork-X translation wiring (Finding 7): HIGH — traced the SELECT column fetch through to the per-row call
- Behavior-anchor qualification (Finding 8): HIGH — applied the three-signal checklist from CLAUDE.md

**Research date:** 2026-07-02
**Valid until:** Stable — codebase-internal research does not expire until the files change

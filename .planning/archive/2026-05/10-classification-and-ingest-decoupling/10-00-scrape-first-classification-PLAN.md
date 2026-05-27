---
phase: 10-classification-and-ingest-decoupling
plan: 00
type: execute
wave: 1
depends_on: []
files_modified:
  - batch_ingest_from_spider.py
  - batch_classify_kol.py
  - tests/unit/test_scrape_first_classify.py
autonomous: true
requirements: [CLASS-01, CLASS-02, CLASS-03, CLASS-04]

must_haves:
  truths:
    - "Scrape-first flow: for each pending article, the full body is scraped and held before the classifier is called (the WeChat digest field is never consulted as classifier input)"
    - "DeepSeek receives the full article body and returns {depth: 1-3, topics: [...], rationale: str}"
    - "A classifications row with (article_id, depth, topics, rationale, classified_at) is written to SQLite BEFORE the ingest decision is made"
    - "Scrape phase reuses existing spiders/wechat_spider.py rate-limit constants (no new params introduced)"
    - "DeepSeek API failure on the scrape-first path SKIPS the article (no fail-open) — distinguishes from batch-scan fail-open"
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "Scrape-first pre-flight: article.body check → scrape-on-demand → classify_full_body → persist classifications row → gated ingest"
      contains: "def _classify_full_body"
    - path: "batch_classify_kol.py"
      provides: "Full-body prompt builder + DeepSeek call that returns the new {depth, topics, rationale} schema"
      contains: "def _build_fullbody_prompt"
    - path: "tests/unit/test_scrape_first_classify.py"
      provides: "5+ unit tests gating D-10.01 through D-10.04"
      min_lines: 150
  key_links:
    - from: "batch_ingest_from_spider.ingest_from_db"
      to: "batch_classify_kol._build_fullbody_prompt + _call_deepseek"
      via: "module-level import; called once per pending article after scrape-on-demand"
      pattern: "from batch_classify_kol import _build_fullbody_prompt"
    - from: "batch_ingest_from_spider._classify_full_body"
      to: "SQLite classifications table"
      via: "sqlite3 INSERT before ingest decision"
      pattern: "INSERT.*INTO classifications.*\\(article_id, (?:depth|topic).*"
    - from: "batch_ingest_from_spider (scrape-on-demand)"
      to: "ingest_wechat.scrape_wechat_ua"
      via: "direct reuse of existing UA-rotating scraper + _ua_cooldown"
      pattern: "ingest_wechat\\.scrape_wechat_ua"
---

<objective>
Rework classification from digest-based (unreliable) to full-body-based (accurate) by scraping
article bodies BEFORE classify, calling DeepSeek with the full text, and persisting the result
to SQLite before the ingest decision.

Purpose: unblock Phase 10 REQs CLASS-01/02/03/04. Empirically the fixture article has
`digest=N/A` which the current classifier interprets as depth=3 news (wrong). Scrape-first +
full-body classification is the root fix.

Output: batch_ingest_from_spider.py with a new pre-flight `_classify_full_body` helper, a new
prompt builder in batch_classify_kol.py, a schema-additive `classifications` table (depth,
topics, rationale columns added idempotently), and 5+ unit tests gating all four REQs.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/10-classification-and-ingest-decoupling/10-CONTEXT.md
@.planning/phases/10-classification-and-ingest-decoupling/10-PRD.md
@.planning/phases/09-timeout-state-management/09-01-SUMMARY.md
@batch_ingest_from_spider.py
@batch_classify_kol.py
@spiders/wechat_spider.py

<interfaces>
<!-- Contracts the executor needs; no codebase exploration required. -->

From `batch_ingest_from_spider.py` (current state):
```python
# Existing helpers already in place — reuse, do not duplicate
def _build_filter_prompt(titles: list[str], topic_filter, exclude_topics, digests) -> str: ...
def _call_deepseek(prompt: str, api_key: str) -> list[dict] | None: ...
def batch_classify_articles(articles: list[dict], ...) -> tuple[list[dict], list[dict]]: ...
async def ingest_article(url: str, dry_run: bool, rag) -> bool: ...  # Phase 9 wrapper — has rollback
async def ingest_from_db(topic: str | list[str], min_depth: int, dry_run: bool) -> None: ...
# Rate limit constants already imported from spiders.wechat_spider:
from spiders.wechat_spider import list_articles_with_digest as list_articles
from spiders.wechat_spider import RATE_LIMIT_SLEEP_ACCOUNTS, RATE_LIMIT_COOLDOWN
```

From `ingest_wechat.py` (Phase 9 state — do not modify this file in this plan):
```python
async def scrape_wechat_ua(url: str) -> dict | None:
    # Returns {"title", "content_html", "img_urls", "url", "publish_time", "method": "ua"}
    # Has _ua_cooldown() built-in (D-10.03 reuse target)
```

From `batch_classify_kol.py` (current state — extend, don't break):
```python
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
def _build_prompt(titles, topic_filter, min_depth, digests) -> str: ...  # KEEP as-is for batch-scan
def _call_deepseek(prompt: str, api_key: str) -> list[dict] | None: ...  # KEEP — reuse for new prompt
def run(topic, min_depth, classifier, dry_run) -> None: ...  # KEEP
```

Existing `classifications` table schema (from batch_classify_kol.init_db, lines 100-110):
```sql
CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    topic TEXT NOT NULL,
    depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
    relevant INTEGER DEFAULT 0,
    excluded INTEGER DEFAULT 0,
    reason TEXT,
    classified_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(article_id, topic)
);
```

Additive migration (D-10.04 picks (a)) — execute once at the top of scrape-first flow:
```python
# Add columns idempotently; old columns stay for batch-scan backward-compat
conn.execute("ALTER TABLE classifications ADD COLUMN IF NOT EXISTS depth INTEGER")
conn.execute("ALTER TABLE classifications ADD COLUMN IF NOT EXISTS topics TEXT")      # JSON-serialized list
conn.execute("ALTER TABLE classifications ADD COLUMN IF NOT EXISTS rationale TEXT")
# NOTE: SQLite before 3.35 did NOT support "ADD COLUMN IF NOT EXISTS". Planner MUST
# implement this as a try/except ALTER (each column individually) and swallow the
# "duplicate column" error. See _ensure_column pattern in batch_scan_kol.init_db.
# The articles.body column needs the same treatment (D-10.01).
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Full-body DeepSeek prompt builder + schema-additive migration</name>
  <files>batch_classify_kol.py, batch_ingest_from_spider.py, tests/unit/test_scrape_first_classify.py</files>
  <behavior>
    Unit tests (RED first) in tests/unit/test_scrape_first_classify.py:
    - test_fullbody_prompt_includes_body_not_digest: stub article dict with body="long text about GPT-5.5 benchmark" and digest="N/A" → _build_fullbody_prompt returns a string containing "long text about GPT-5.5" AND NOT containing "[digest: N/A]"
    - test_fullbody_prompt_schema_requires_topics_list: prompt string includes "topics" key instruction AND includes the phrase "JSON array" or "JSON object"
    - test_call_deepseek_returns_new_schema: mock requests.post to return {"choices":[{"message":{"content":'{"depth":1,"topics":["news"],"rationale":"shallow"}'}}]} → _call_deepseek_fullbody returns {"depth": 1, "topics": ["news"], "rationale": "shallow"}
    - test_schema_migration_idempotent: with an in-memory sqlite3 conn + batch_classify_kol.init_db (creates old schema) → calling ensure_fullbody_columns(conn) twice in a row succeeds (no "duplicate column" crash on second call)
  </behavior>
  <action>
    1. In `batch_classify_kol.py`, ADD a new function `_build_fullbody_prompt(title: str, body: str, topic_filter: list[str] | None = None) -> str` that produces a DeepSeek prompt instructing the model to return ONE JSON OBJECT (not array) with keys `depth` (int 1-3), `topics` (list of string — key concepts/domains from the article), `rationale` (str). The prompt MUST include the article body (truncated to 8000 chars — the D-10.02 budget) verbatim, NOT a digest preview. Example body:
    ```
    "Classify the following article by depth (1=shallow news, 2=moderate, 3=deep technical) and extract its top 3-5 topics.\n\nTitle: {title}\n\nBody:\n{body[:8000]}\n\nReturn ONLY a JSON object: {\"depth\": <1-3>, \"topics\": [...], \"rationale\": \"...\"}. No other text."
    ```
    Do NOT delete or modify `_build_prompt` — it stays for batch-scan path.

    2. In `batch_classify_kol.py`, ADD `_call_deepseek_fullbody(prompt: str, api_key: str) -> dict | None`. Reuses the existing `requests.post` pattern from `_call_deepseek` but parses a single JSON OBJECT (not array). Return None on any error. Per D-10.04: this function does NOT fail-open — the orchestrator skips the article on None return.

    3. In `batch_ingest_from_spider.py`, ADD a helper `_ensure_fullbody_columns(conn: sqlite3.Connection) -> None` that adds `depth INTEGER`, `topics TEXT`, `rationale TEXT` to `classifications` AND `body TEXT` to `articles` via individual `try/except sqlite3.OperationalError` ALTER TABLE statements (pattern reuse from batch_scan_kol's `_ensure_column`). Must be idempotent (D-10.04, D-10.01).

    4. Write the 4 behavior tests above. All use `DEEPSEEK_API_KEY=dummy` (via monkeypatch env var on the test module). Mock `requests.post` via `unittest.mock.patch`. Use in-memory `sqlite3.connect(":memory:")` for the schema migration test, with `batch_classify_kol.init_db` adapted to accept a connection (or re-create the classifications table manually in the test fixture).

    Per D-10.02, D-10.04, D-10.10.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_scrape_first_classify.py -v -k "fullbody_prompt or call_deepseek or migration"</automated>
  </verify>
  <done>4 new unit tests pass. `_build_fullbody_prompt` + `_call_deepseek_fullbody` exist in batch_classify_kol.py. `_ensure_fullbody_columns` exists in batch_ingest_from_spider.py and is idempotent.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Scrape-first pre-flight + SQLite persistence + gated ingest</name>
  <files>batch_ingest_from_spider.py, tests/unit/test_scrape_first_classify.py</files>
  <behavior>
    Unit tests (RED first) in tests/unit/test_scrape_first_classify.py:
    - test_scrape_on_demand_when_body_empty: mock `ingest_wechat.scrape_wechat_ua` to return {"content_html":"<p>long gpt-5.5 body</p>", "title":"t", "url":"u", "img_urls":[], "publish_time":"", "method":"ua"}; mock DeepSeek to return valid JSON; with an in-memory DB seeded with an article (body=None), call the scrape-first pre-flight → assert scrape_wechat_ua was called, articles.body was updated, classifications row has the new columns populated
    - test_classifier_persistence_before_ingest_decision: with mocked scrape + mocked DeepSeek → assert the classifications INSERT happens BEFORE the ingest_wechat.ingest_article call (use MagicMock call order check, or a side_effect spy list)
    - test_deepseek_failure_skips_ingest: mock DeepSeek to return None → assert ingest_wechat.ingest_article was NOT called (no fail-open per D-10.04), and that no `ingestions` row is written for this article
    - test_rate_limit_constants_reused: source-grep assertion — open batch_ingest_from_spider.py, assert it imports `RATE_LIMIT_SLEEP_ACCOUNTS`, `RATE_LIMIT_COOLDOWN` from spiders.wechat_spider (D-10.03); assert no NEW rate limit constants are introduced (no regex match for e.g. `SCRAPE_ON_DEMAND_SLEEP`, `PER_ARTICLE_DELAY`)
  </behavior>
  <action>
    1. In `batch_ingest_from_spider.py`, ADD an async helper:
    ```python
    async def _classify_full_body(
        conn: sqlite3.Connection,
        article_id: int,
        url: str,
        title: str,
        body: str | None,
        api_key: str,
    ) -> dict | None:
        """Scrape-first classify (D-10.01/02/04). Returns the classification dict or None on skip.

        On None return, caller MUST NOT proceed to ingest (D-10.04 strict ordering).
        """
        # 1. Scrape on demand if body absent (D-10.01); reuses existing UA-rotating scraper + _ua_cooldown
        if not body:
            import ingest_wechat  # late import — avoids LightRAG init at module load
            scraped = await ingest_wechat.scrape_wechat_ua(url)
            if not scraped or not scraped.get("content_html"):
                logger.warning("scrape-on-demand failed for %s — skipping classify", url[:80])
                return None
            # Convert HTML → markdown via the same process_content helper ingest_wechat uses
            body, _ = ingest_wechat.process_content(scraped["content_html"])
            # Persist body for reuse
            conn.execute("UPDATE articles SET body = ? WHERE id = ?", (body, article_id))
            conn.commit()

        # 2. Build prompt + call DeepSeek with full body (D-10.02)
        from batch_classify_kol import _build_fullbody_prompt, _call_deepseek_fullbody
        prompt = _build_fullbody_prompt(title, body)
        result = _call_deepseek_fullbody(prompt, api_key)
        if result is None:
            logger.warning("DeepSeek classify failed for %s — skipping (no fail-open, D-10.04)", url[:80])
            return None

        # 3. Persist classifications row BEFORE ingest decision (D-10.04)
        import json
        conn.execute(
            """INSERT OR REPLACE INTO classifications
               (article_id, topic, depth_score, depth, topics, rationale, relevant)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (
                article_id,
                (result.get("topics") or ["unknown"])[0],  # old topic column — first topic for back-compat
                result.get("depth", 2),                     # old depth_score column
                result.get("depth"),                        # new depth column
                json.dumps(result.get("topics", []), ensure_ascii=False),  # new topics JSON
                result.get("rationale", ""),
            ),
        )
        conn.commit()
        return result
    ```

    2. Modify `ingest_from_db` in `batch_ingest_from_spider.py`:
       - At the top (after `_load_hermes_env`), call `_ensure_fullbody_columns(conn)` before the query.
       - Change the SELECT query to include `a.body`:
       ```sql
       SELECT a.id, a.title, a.url, acc.name, c.depth_score, a.body
       FROM articles a
       JOIN accounts acc ON a.account_id = acc.id
       LEFT JOIN classifications c ON a.id = c.article_id
       WHERE (c.topic IS NULL OR c.topic IN ({placeholders}))
         AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
       ORDER BY a.id
       ```
       (We no longer pre-filter by `c.depth_score >= ?` because unclassified articles have NULL c.depth_score; classification happens per-article now.)
       - Inside the `for i, (art_id, title, url, account, depth, body) in enumerate(rows, 1):` loop, BEFORE the existing `await ingest_article(url, dry_run, rag)` call, insert:
       ```python
       api_key = get_deepseek_api_key()
       if not dry_run and api_key:
           cls_result = await _classify_full_body(conn, art_id, url, title, body, api_key)
           if cls_result is None:
               conn.execute("INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')", (art_id,))
               conn.commit()
               continue  # D-10.04: no fail-open
           if cls_result.get("depth", 0) < min_depth:
               logger.info("  depth=%d < min_depth=%d — skipping ingest", cls_result.get("depth"), min_depth)
               conn.execute("INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')", (art_id,))
               conn.commit()
               continue
       ```
       Keep the existing `success = await ingest_article(url, dry_run, rag)` call unchanged — Phase 10-01 will modify that. The gate above simply prevents the call for classify-failed or shallow-depth articles.

    3. Do NOT modify the `run()` function's batch-scan path (`run` without `--from-db`). That path still uses `batch_classify_articles` on titles — it is outside the scrape-first scope per D-10.10 (planner resolves: scrape-first is `--from-db` only for Phase 10; batch-scan title-based classify stays for Phase 5 compat).

    4. Write the 4 behavior tests above. Use an in-memory SQLite fixture with `accounts` + `articles` + `classifications` + `ingestions` tables pre-seeded. Mock `ingest_wechat.scrape_wechat_ua` and `ingest_wechat.process_content` via `unittest.mock.patch`. Mock the Phase 9 `ingest_wechat.ingest_article` (don't let it actually call ainsert) — or patch `batch_ingest_from_spider.ingest_article` wrapper. Use `AsyncMock` for coroutines.

    Per D-10.01, D-10.03, D-10.04, D-10.10.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_scrape_first_classify.py -v</automated>
  </verify>
  <done>All 8 tests in test_scrape_first_classify.py pass. `_classify_full_body` exists. `ingest_from_db` calls it per article BEFORE `ingest_article`. No new rate-limit constants introduced. Phase 8 (22 tests) + Phase 9 (12 tests) regression suites stay green.</done>
</task>

<task type="auto">
  <name>Task 3: Phase 8 + Phase 9 regression verification + smoke imports</name>
  <files>(no source changes — verification only)</files>
  <action>
    1. Run Phase 8 regression (MUST stay 22/22 green):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py -v
    ```
    2. Run Phase 9 regression (MUST stay 12/12 green):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_get_rag_contract.py tests/unit/test_rollback_on_timeout.py tests/unit/test_prebatch_flush.py -v
    ```
    3. Smoke imports (both modules must import cleanly post-edit):
    ```
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"
    DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_classify_kol; print('OK')"
    ```
    4. If any regression fails OR import fails → STOP and fix in place (Rule 1 auto-fix). Do not proceed to plan 10-01 until green.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_image_pipeline.py tests/unit/test_get_rag_contract.py tests/unit/test_rollback_on_timeout.py tests/unit/test_prebatch_flush.py tests/unit/test_scrape_first_classify.py -v</automated>
  </verify>
  <done>All of: 22 image_pipeline + 12 Phase-9 + 8 new Phase-10 = 42 tests pass. Both smoke imports succeed.</done>
</task>

</tasks>

<verification>
Phase 10 plan 10-00 acceptance (D-10.01 through D-10.04):

1. **D-10.01 verified by:** test_scrape_on_demand_when_body_empty asserts scrape_wechat_ua was called and articles.body was written before classify.
2. **D-10.02 verified by:** test_fullbody_prompt_includes_body_not_digest + test_call_deepseek_returns_new_schema assert the prompt uses full body (not digest) and parses the new {depth, topics, rationale} schema.
3. **D-10.03 verified by:** test_rate_limit_constants_reused source-greps the module for existing RATE_LIMIT_* imports and absence of new constants.
4. **D-10.04 verified by:** test_classifier_persistence_before_ingest_decision (order check) + test_deepseek_failure_skips_ingest (no fail-open) + test_schema_migration_idempotent (additive ALTER TABLE works twice).

Phase 8 + Phase 9 regression (22 + 12 tests) stays GREEN — no modifications to image_pipeline.py or ingest_wechat.py in this plan.
</verification>

<success_criteria>
- `ingest_from_db` scrapes body on-demand when articles.body is empty, writes body back, classifies on full body, persists to classifications, and gates ingest (D-10.01–04)
- `_build_fullbody_prompt` + `_call_deepseek_fullbody` live in batch_classify_kol.py and return the new {depth, topics, rationale} shape (D-10.02)
- No new rate-limit constants introduced (D-10.03 — source-grep test)
- 8 new unit tests pass, 22 Phase-8 tests pass, 12 Phase-9 tests pass
- `DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -v` reports no regressions
</success_criteria>

<output>
After completion, create `.planning/phases/10-classification-and-ingest-decoupling/10-00-SUMMARY.md` per the standard SUMMARY template. Document the schema-additive migration (ALTER TABLE columns added), the new prompt schema shape, and any deviation from the plan (Rule 1 auto-fixes). Commit SUMMARY separately from source changes per the Phase 9 pattern.
</output>

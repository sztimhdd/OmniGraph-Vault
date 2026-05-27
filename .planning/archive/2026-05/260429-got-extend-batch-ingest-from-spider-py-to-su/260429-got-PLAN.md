---
phase: quick-260429
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - batch_ingest_from_spider.py
autonomous: true
requirements: [D-11]
must_haves:
  truths:
    - "--topic-filter 'openclaw,hermes,agent,harness' matches any article containing ANY of the 4 keywords"
    - "--topic-filter 'openclaw' (single keyword, no comma) still works identically to before"
    - "Whitespace around commas is stripped: 'a, b, c' becomes ['a','b','c']"
    - "Trailing commas are ignored: 'a,b,' becomes ['a','b']"
    - "--from-db with multiple keywords queries the DB with OR across all keywords"
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "multi-keyword --topic-filter support"
      contains: "list[str] | None"
  key_links:
    - from: "main() argparse"
      to: "ingest_from_db / run"
      via: "split(',') + strip() + filter('')"
      pattern: "args\\.topic_filter\\.split"
---

<objective>
Extend `batch_ingest_from_spider.py` so `--topic-filter` accepts a comma-separated
list of keywords matching ANY of them, per D-11 of 05-CONTEXT.

Purpose: The KOL catch-up run (Plan 05-00b) needs
`--topic-filter "openclaw,hermes,agent,harness"` to match all 4 keywords in one
pass. Currently only a single keyword is supported.
Output: Modified `batch_ingest_from_spider.py` — no new files.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@batch_ingest_from_spider.py

<!-- Key signatures the executor needs — extracted from current source -->
<interfaces>
From batch_ingest_from_spider.py:

```python
# Line 177-182 (current)
def _build_filter_prompt(
    titles: list[str],
    topic_filter: str | None,        # CHANGE TO: list[str] | None
    exclude_topics: str | None,
    digests: list[str] | None = None,
) -> str: ...

# Line 286-292 (current)
def batch_classify_articles(
    articles: list[dict],
    topic_filter: str | None,        # CHANGE TO: list[str] | None
    exclude_topics: str | None,
    min_depth: int,
    classifier: str = "deepseek",
) -> tuple[list[dict], list[dict]]: ...

# Line 543 (current)
def ingest_from_db(topic: str, min_depth: int, dry_run: bool) -> None:
    # Line 561-568: SQL uses `WHERE c.topic = ? AND c.relevant = 1`
    # CHANGE: accept list[str], build OR clause per keyword

# Line 607 (current)
parser.add_argument("--topic-filter", type=str, default=None, ...)
# Keep type=str; split in main() after parsing
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Extend --topic-filter to accept comma-separated keywords</name>
  <files>batch_ingest_from_spider.py</files>
  <action>
Make the following SURGICAL changes — touch only these lines, nothing else.

**1. `main()` — parse and split (lines ~617-621)**

After `args = parser.parse_args()`, add a split step that converts the raw string
into a list before passing to `ingest_from_db` or `run`. Leave `argparse` line 607
unchanged (keep `type=str`).

```python
# Convert comma-separated string to list; strip whitespace; drop empty strings
topic_keywords: list[str] | None = None
if args.topic_filter:
    topic_keywords = [k.strip() for k in args.topic_filter.split(",") if k.strip()]
    if not topic_keywords:
        topic_keywords = None
```

Then pass `topic_keywords` (not `args.topic_filter`) to both `ingest_from_db` and
`run(topic_filter=topic_keywords, ...)`.

**2. `ingest_from_db` signature and SQL (line 543)**

Change signature: `def ingest_from_db(topic: str | list[str], min_depth: int, dry_run: bool) -> None:`

Normalise at the top of the function:
```python
topics = [topic] if isinstance(topic, str) else topic
```

Replace the single-topic SQL with a multi-topic OR query. Build the WHERE fragment
dynamically:
```python
placeholders = ",".join("?" for _ in topics)
rows = conn.execute(f"""
    SELECT a.id, a.title, a.url, acc.name, c.depth_score
    FROM articles a
    JOIN accounts acc ON a.account_id = acc.id
    JOIN classifications c ON a.id = c.article_id
    WHERE c.topic IN ({placeholders}) AND c.relevant = 1 AND c.depth_score >= ?
      AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
    ORDER BY c.depth_score DESC, a.id
""", (*topics, min_depth)).fetchall()
```

Update the log line to show the list: `logger.info("%d articles to ingest for topics %s", len(rows), topics)`

**3. `_build_filter_prompt` — update signature and prompt text (lines 177-196)**

Change type annotation: `topic_filter: list[str] | None`

Change the prompt string for topic_filter (line 191):
```python
if topic_filter:
    keywords_quoted = ", ".join(f'"{k}"' for k in topic_filter)
    topic_instruction = (
        f"- relevant: true/false — is this article substantially about ANY of: {keywords_quoted}?\n"
    )
```

**4. `batch_classify_articles` — update type annotation only (line 288)**

Change: `topic_filter: list[str] | None`
No logic change needed; value is passed straight through to `_build_filter_prompt`.

**5. `run()` — update type annotation in kwargs comment only (line 424)**

The function reads `topic_filter = kwargs.get("topic_filter")` — this still works
with a list. Add inline comment: `# list[str] | None after main() split`

**6. `scanning_active` and filter_reason (lines 361-362 and 471)**

`scanning_active = bool(topic_filter or exclude_topics)` — already list-truthy, no
change needed.

For the filter reason message (line 362):
```python
if topic_filter and not relevant:
    keywords_str = ", ".join(topic_filter)
    filter_reasons.append(f"off-topic (not about any of: {keywords_str})")
```

Do NOT modify: ingest_article(), argparse help text, SLEEP_BETWEEN_ARTICLES,
batch_scan_kol usage, or any other function.
  </action>
  <verify>
    <automated>
cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" && python batch_ingest_from_spider.py --from-db --topic-filter "openclaw,hermes,agent,harness" --min-depth 2 --dry-run 2>&1 | head -30
    </automated>
  </verify>
  <done>
- `--topic-filter "openclaw,hermes,agent,harness" --dry-run` runs without error and
  logs "articles to ingest for topics ['openclaw', 'hermes', 'agent', 'harness']"
- `--topic-filter "openclaw" --dry-run` (single keyword) still works (back-compat)
- `python -c "import batch_ingest_from_spider"` imports cleanly (no syntax errors)
  </done>
</task>

</tasks>

<verification>
Run these in order:

```bash
# 1. Import check
python batch_ingest_from_spider.py --help

# 2. Multi-keyword dry-run (primary use case per D-11)
python batch_ingest_from_spider.py --from-db --topic-filter "openclaw,hermes,agent,harness" --min-depth 2 --dry-run

# 3. Single-keyword back-compat
python batch_ingest_from_spider.py --from-db --topic-filter "agent" --min-depth 2 --dry-run

# 4. Whitespace/trailing-comma edge cases (inspect source only — not runnable without DB)
# Confirm in code: "a, b, " splits to ["a", "b"] (strip + filter)
```
</verification>

<success_criteria>
- Multi-keyword invocation executes without error; DB query runs with `IN (...)` OR semantics
- Single-keyword invocation unchanged in output/behaviour
- No files other than `batch_ingest_from_spider.py` modified
- No argparse interface changes visible in `--help`
</success_criteria>

<output>
After completion, create `.planning/quick/260429-got-extend-batch-ingest-from-spider-py-to-su/260429-got-SUMMARY.md`
</output>

---
phase: ir-1-real-layer1-and-kol-ingest-wiring
plan: 01
type: execute
wave: 2
depends_on:
  - "ir-1-00"
files_modified:
  - batch_ingest_from_spider.py
autonomous: true
requirements:
  - LF-3.1
  - LF-3.4
  - LF-3.5
  - LF-3.6

must_haves:
  truths:
    - "Ingest loop control flow is restructured: fetch up-to-30 candidate batch → call layer1_pre_filter (async) → persist_layer1_verdicts → split candidate/reject → drain candidate sub-batch through the existing per-article scrape+layer2+ainsert loop. Reject rows write ingestions(status='skipped', reason='layer1_reject:<verdict.reason>')"
    - "_build_topic_filter_query candidate SELECT additionally filters: WHERE layer1_verdict IS NULL OR layer1_prompt_version != ?  bound to lib.article_filter.PROMPT_VERSION_LAYER1. Existing predicates (NOT IN ingestions WHERE status='ok' / ORDER BY a.id) preserved"
    - "--topic-filter and --min-depth CLI flags continue to be silently accepted (back-compat per Foundation Quick) but no longer drive any logic — they are dead arguments"
    - "[layer1] log tag is added to every Layer 1 verdict line (per article: id, source, verdict, reason); [layer1] batch summary line per call: count_total, count_candidate, count_reject, wall_clock_ms, error_class (if NULL whole-batch)"
    - "--dry-run continues to invoke real layer1_pre_filter + persist_layer1_verdicts (LF-3.6: dry-run validates the filter pipeline) but skips scrape, skips layer2 call, skips ainsert, skips ingestions writes"
    - "Regression: 5-article smoke (--max-articles 5 --dry-run) on a populated .dev-runtime DB completes without exception, reaches Layer 1 batch call, persists verdicts to layer1_* columns"
  artifacts:
    - path: "batch_ingest_from_spider.py"
      provides: "Batched Layer 1 wiring; per-article inline call sites at lines ~1491 and ~1526 are removed; new batch-then-drain control flow inside ingest_from_db()"
      contains: "from lib.article_filter import"
      contains_must_not: "from lib.article_filter import layer1_pre_filter, layer2_full_body_score\n"
  key_links:
    - from: "batch_ingest_from_spider.ingest_from_db"
      to: "lib.article_filter.layer1_pre_filter"
      via: "await call on batch of ≤30 ArticleMeta"
      pattern: "await layer1_pre_filter("
    - from: "batch_ingest_from_spider._build_topic_filter_query"
      to: "articles.layer1_verdict + layer1_prompt_version columns (migration 006)"
      via: "SQL predicate"
      pattern: "layer1_verdict IS NULL"
---

<objective>
Wave 2 (parallel-able with ir-1-02): rewire `batch_ingest_from_spider.py` ingest loop from per-article placeholder calls to batched Layer 1. The Layer 1 batch happens BEFORE scrape; rejects are persisted + skipped without paying scrape cost; candidates drain through the existing per-article scrape→layer2→ainsert loop unchanged.

Output: `batch_ingest_from_spider.py` consumes ir-1-00's new contract; candidate SQL filters by `layer1_verdict IS NULL OR layer1_prompt_version != ?`; --dry-run continues end-to-end through Layer 1; logs gain `[layer1]` tags; --topic-filter / --min-depth remain silent no-ops.
</objective>

<execution_context>
@.planning/PROJECT-v3.5-Ingest-Refactor.md
@.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md
@.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/ir-1-00-PLAN.md
</execution_context>

<context>
@.planning/STATE-v3.5-Ingest-Refactor.md
@CLAUDE.md
</context>

<interfaces>
<!-- New symbols this plan CONSUMES (from ir-1-00 output). -->

```python
# lib/article_filter.py (post ir-1-00):
PROMPT_VERSION_LAYER1: str = "layer1_v0_20260507"
LAYER1_BATCH_SIZE: int = 30

@dataclass(frozen=True)
class ArticleMeta:
    id: int
    source: Literal["wechat", "rss"]
    title: str
    summary: str | None
    content_length: int | None

@dataclass(frozen=True)
class FilterResult:
    verdict: Literal["candidate", "reject"] | None
    reason: str
    prompt_version: str

async def layer1_pre_filter(articles: list[ArticleMeta]) -> list[FilterResult]: ...
def layer2_full_body_score(articles: list[ArticleWithBody]) -> list[FilterResult]: ...
def persist_layer1_verdicts(conn, articles, results) -> None: ...
```

<!-- Existing batch_ingest_from_spider.py shape this plan modifies. -->

```python
# Current import (line 63):
from lib.article_filter import layer1_pre_filter, layer2_full_body_score
# CHANGES TO: include FilterResult, ArticleMeta, persist_layer1_verdicts, PROMPT_VERSION_LAYER1, LAYER1_BATCH_SIZE

# Current candidate SQL (lines ~1294-1324, _build_topic_filter_query):
sql = """
    SELECT a.id, a.title, a.url, acc.name, a.body, a.digest
    FROM articles a
    JOIN accounts acc ON a.account_id = acc.id
    WHERE a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
    ORDER BY a.id
"""
# CHANGES: add ` AND (a.layer1_verdict IS NULL OR a.layer1_prompt_version IS NOT ?) ` predicate
#          and bind PROMPT_VERSION_LAYER1 as the parameter

# Current per-article Layer 1 call (lines ~1491-1506):
if not dry_run:
    layer1 = layer1_pre_filter(title=title, summary=digest or "", content_length=None)
    if not layer1.passed:  # OLD shape — broken after ir-1-00
        ...
# CHANGES: this inline call is REMOVED. Layer 1 happens at batch boundary
#          ~30 articles before the per-article loop body.

# Current per-article Layer 2 call (lines ~1525-1541):
layer2 = layer2_full_body_score(article_id=art_id, title=title, body=body or "")
if not layer2.passed:  # OLD shape
    ...
# CHANGES: rewire to new sig — call as layer2_full_body_score([ArticleWithBody(...)])[0],
#          treat verdict == "reject" as skip, anything else (candidate / ok) as pass
```
</interfaces>

<tasks>

<task type="auto" tdd="false">
  <name>Task 2.1: Update import + candidate SQL predicate</name>
  <read_first>
    - batch_ingest_from_spider.py lines 60-70 (imports)
    - batch_ingest_from_spider.py lines 1294-1325 (`_build_topic_filter_query`)
    - lib/article_filter.py post ir-1-00 (the new exports list)
  </read_first>
  <files>batch_ingest_from_spider.py</files>
  <behavior>
    - Import surface for `lib.article_filter` becomes the ir-1-00 contract
    - `_build_topic_filter_query` adds prompt-version-aware Layer 1 predicate; topics arg still silently accepted
    - Returned tuple is now `(sql, (PROMPT_VERSION_LAYER1,))` — params has 1 element instead of 0
  </behavior>
  <action>
1. **Update import at line 63**:
```python
from lib.article_filter import (
    ArticleMeta,
    ArticleWithBody,
    FilterResult,
    LAYER1_BATCH_SIZE,
    PROMPT_VERSION_LAYER1,
    layer1_pre_filter,
    layer2_full_body_score,
    persist_layer1_verdicts,
)
```

2. **Rewrite `_build_topic_filter_query`** (lines ~1294-1324). Update the docstring to reflect the new predicate; the body becomes:

```python
def _build_topic_filter_query(topics: list[str]) -> tuple[str, tuple[str, ...]]:
    """Build the --from-db candidate SELECT as (sql, params).

    v3.5 ir-1: adds Layer 1 predicate. Rows are candidates when:
      - they are NOT in ingestions WHERE status='ok' (anti-join, already there)
      - AND (layer1_verdict IS NULL OR layer1_prompt_version IS NOT current)
        — the OR clause re-evaluates rows under a bumped prompt_version
        (LF-1.8 prompt-bump pattern)

    `topics` parameter is retained for API compat (--topic-filter CLI flag)
    but is NOT used in SQL — Layer 1 LLM call replaces topic filtering.
    """
    sql = """
        SELECT a.id, a.title, a.url, acc.name, a.body, a.digest
        FROM articles a
        JOIN accounts acc ON a.account_id = acc.id
        WHERE a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
          AND (a.layer1_verdict IS NULL OR a.layer1_prompt_version IS NOT ?)
        ORDER BY a.id
    """
    return sql, (PROMPT_VERSION_LAYER1,)
```

3. **Audit all callers** of `_build_topic_filter_query`. Use grep to confirm caller(s) destructure `(sql, params)` correctly and pass `params` to `cursor.execute()`. Existing call site at line ~1376 already does `sql, params = _build_topic_filter_query(topics)` — no change needed downstream.
  </action>
  <verify>
    <automated>python -c "
from batch_ingest_from_spider import _build_topic_filter_query
sql, params = _build_topic_filter_query(['agent'])
assert 'layer1_verdict IS NULL' in sql, sql
assert len(params) == 1, params
assert params[0] == 'layer1_v0_20260507', params
print('SQL predicate ok')
"</automated>
  </verify>
  <acceptance_criteria>
    - Import block at lines ~63 includes `ArticleMeta, ArticleWithBody, FilterResult, LAYER1_BATCH_SIZE, PROMPT_VERSION_LAYER1, layer1_pre_filter, layer2_full_body_score, persist_layer1_verdicts`
    - `_build_topic_filter_query` returned SQL contains literal `layer1_verdict IS NULL OR a.layer1_prompt_version IS NOT ?`
    - Returned params tuple has length 1, value `PROMPT_VERSION_LAYER1`
    - File still parses + imports cleanly: `python -c "import batch_ingest_from_spider"` exits 0
  </acceptance_criteria>
  <done>LF-3.4 (candidate SQL predicate) delivered for KOL articles. RSS-side `_build_topic_filter_query` equivalent is ir-4 scope.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2.2: Restructure ingest loop to batched Layer 1</name>
  <read_first>
    - batch_ingest_from_spider.py lines 1327-1700 (`ingest_from_db` body — the for-loop over candidates)
    - Specifically lines ~1430-1542 (the per-article preamble: checkpoint skip, body presence, graded probe, layer1, scrape, layer2, ingest_article)
    - lib/article_filter.py post ir-1-00 (verify behavior of layer1_pre_filter on empty input + ValueError on >30)
  </read_first>
  <files>batch_ingest_from_spider.py</files>
  <behavior>
    - Inside `ingest_from_db`, after the candidate cursor is fetched (line ~1380 area), introduce a chunking layer: split rows into chunks of LAYER1_BATCH_SIZE
    - For each chunk:
      1. Build `articles_meta: list[ArticleMeta]` from chunk rows (source='wechat'; summary=row.digest; content_length=None)
      2. `results = await layer1_pre_filter(articles_meta)`
      3. Log `[layer1] batch n=X candidate=Y reject=Z wall_ms=N`
      4. If all results have `verdict is None` (whole-batch error): log `[layer1] batch NULL reason=<error_class> — rows stay NULL, retry next run`; SKIP persist; continue to next chunk WITHOUT processing rows (they will be picked up by next ingest tick)
      5. Else: call `persist_layer1_verdicts(conn, articles_meta, results)` to persist atomically
      6. For rows where `result.verdict == "reject"`: log `[layer1] reject id=X reason=<r>`; INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped'); continue (do NOT enter per-article body)
      7. For rows where `result.verdict == "candidate"`: enter the existing per-article processing body (checkpoint check, scrape, layer2, ingest_article) — UNCHANGED control flow except the inline Layer 1 + Layer 2 calls at lines ~1491 and ~1526 are REMOVED (Layer 1 already done; Layer 2 inline call gets refactored in step below)
    - Refactor the inline Layer 2 call (lines ~1525-1541): keep it inline (Layer 2 is per-article in v3.5; batching is ir-2's option). Update to new shape:
      ```python
      layer2_results = layer2_full_body_score([ArticleWithBody(
          id=art_id, source="wechat", title=title, body=body or "",
      )])
      layer2 = layer2_results[0]
      if layer2.verdict == "reject":
          logger.info("  [layer2] reject id=%s reason=%s", art_id, layer2.reason)
          conn.execute(
              "INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')",
              (art_id,),
          )
          conn.commit()
          continue
      ```
    - Reason field on ingestions(status='skipped') for layer1/layer2 rejects: the existing schema does NOT have a `reason` column on `ingestions` (verify via `PRAGMA table_info(ingestions)`). REQ LF-3.1 / LF-3.3 say "reason 'layer1_reject:<verdict.reason>'" — but if the schema lacks the column, log the reason at INFO level (already done via logger.info) and accept that the persisted ingestions row only has status='skipped'. Do NOT add a schema migration for an `ingestions.reason` column in this plan; that is a follow-up if operator-grep needs it
    - --dry-run flow: still call layer1_pre_filter + persist_layer1_verdicts (real LLM cost intentional per LF-3.6), but for rows with verdict='candidate' SKIP the per-article body (no scrape, no layer2, no ainsert, no ingestions writes). Continue logging as if a dry run completed
  </behavior>
  <action>
**Concrete edit instructions for `batch_ingest_from_spider.py` ingest_from_db body:**

1. Locate `ingest_from_db` async function (line ~1327). After the candidate-cursor fetch (around lines 1376-1410) but BEFORE the `for art_id, ... in cursor:` loop, insert the chunking + batch Layer 1 layer.

2. **Pseudocode shape** (literal Python — implement against the actual current loop body, preserve all existing checkpoint / graded probe / body persist / scrape / layer2 / ingest_article logic for candidate rows):

```python
sql, params = _build_topic_filter_query(topics)
candidate_rows = list(conn.execute(sql, params))
# v3.5 ir-1 LF-3.1: chunk by LAYER1_BATCH_SIZE; layer1 batch BEFORE per-article work
chunks = [
    candidate_rows[i:i + LAYER1_BATCH_SIZE]
    for i in range(0, len(candidate_rows), LAYER1_BATCH_SIZE)
]

for chunk_idx, chunk in enumerate(chunks):
    articles_meta = [
        ArticleMeta(
            id=row[0],            # a.id
            source="wechat",
            title=row[1] or "",
            summary=row[5] or None,  # a.digest
            content_length=None,
        )
        for row in chunk
    ]

    t0 = time.monotonic()
    layer1_results = await layer1_pre_filter(articles_meta)
    wall_ms = int((time.monotonic() - t0) * 1000)

    cand_count = sum(1 for r in layer1_results if r.verdict == "candidate")
    rej_count  = sum(1 for r in layer1_results if r.verdict == "reject")
    null_count = sum(1 for r in layer1_results if r.verdict is None)

    if null_count == len(layer1_results):
        # whole-batch error — leave rows NULL, retry next tick
        err_class = layer1_results[0].reason if layer1_results else "empty_batch"
        logger.warning(
            "[layer1] batch %d NULL reason=%s n=%d wall_ms=%d — rows stay NULL",
            chunk_idx, err_class, len(chunk), wall_ms,
        )
        continue

    logger.info(
        "[layer1] batch %d n=%d candidate=%d reject=%d null=%d wall_ms=%d",
        chunk_idx, len(chunk), cand_count, rej_count, null_count, wall_ms,
    )

    persist_layer1_verdicts(conn, articles_meta, layer1_results)

    # Persist reject rows as skipped, without scrape
    for meta, result in zip(articles_meta, layer1_results):
        if result.verdict == "reject":
            logger.info(
                "[layer1] reject id=%s reason=%s",
                meta.id, result.reason,
            )
            conn.execute(
                "INSERT OR REPLACE INTO ingestions(article_id, status) "
                "VALUES (?, 'skipped')",
                (meta.id,),
            )
    conn.commit()

    # Candidates flow into the per-article scrape→layer2→ainsert loop
    candidate_rows_in_chunk = [
        row for row, result in zip(chunk, layer1_results)
        if result.verdict == "candidate"
    ]
    for row in candidate_rows_in_chunk:
        art_id, title, url, account, body, digest = row
        # ... existing per-article body resumes here ...
        # Important: REMOVE the inline `layer1_pre_filter(...)` call at line ~1491.
        # KEEP the inline `layer2_full_body_score(...)` call but REWRITE per behavior.
```

3. **Remove** the inline Layer 1 call at lines ~1484-1506. The if-block that wrapped `layer1 = layer1_pre_filter(...)` and the per-article reject-write should be deleted; Layer 1 is now done at the chunk boundary above.

4. **Rewrite** the inline Layer 2 call at lines ~1525-1541 to consume the new sig:
```python
# v3.5 Layer 2 (placeholder always-pass; ir-2 ships real DeepSeek call).
if not dry_run:
    layer2_results = layer2_full_body_score([ArticleWithBody(
        id=art_id, source="wechat", title=title, body=body or "",
    )])
    layer2 = layer2_results[0]
    if layer2.verdict == "reject":
        logger.info(
            "  [layer2] reject id=%s reason=%s",
            art_id, layer2.reason,
        )
        conn.execute(
            "INSERT OR REPLACE INTO ingestions(article_id, status) VALUES (?, 'skipped')",
            (art_id,),
        )
        conn.commit()
        continue
```

5. **Dry-run handling**: confirm the existing `if not dry_run:` guard around the inline body covers Layer 2 + scrape + ainsert correctly. Layer 1 is OUTSIDE the dry-run guard (always runs). Add a dry-run short-circuit inside the candidate per-article loop:

```python
for row in candidate_rows_in_chunk:
    art_id, title, url, account, body, digest = row
    if dry_run:
        logger.info("[dry-run] would-process candidate id=%d url=%s", art_id, url[:60])
        continue
    # ... existing scrape→layer2→ainsert body ...
```

6. **Verify `ingestions.reason` column does not exist** (which is expected). Run:
```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/kol_scan.db' if __import__('os').path.exists('data/kol_scan.db') else ':memory:')
print({row[1] for row in conn.execute('PRAGMA table_info(ingestions)')})"
```
If `reason` is in the set, do NOT add it now — it is a v3.5 follow-up if operator visibility is needed. The verdict.reason value is recorded in articles.layer1_reason already, so the data is preserved.

**HARD CONSTRAINTS:**
- DO NOT change function signatures of `ingest_from_db`, `_build_topic_filter_query`, or `ingest_article` — orchestrate_daily and other callers depend on them
- DO NOT add a `reason` column to `ingestions` schema in this plan
- DO NOT remove the `--topic-filter` / `--min-depth` CLI flags or their argparse entries — they are silent no-ops per LF-3.4
- DO NOT batch Layer 2 in this plan — Layer 2 stays per-article (placeholder always-pass anyway). ir-2 may batch it
- DO NOT touch `enrichment/rss_ingest.py` — RSS path is ir-4 scope per D-LF-6
- DO NOT remove the existing graded-classify probe block (`OMNIGRAPH_GRADED_CLASSIFY` env-gated) — it is feature-flagged off by default and out-of-scope per PROJECT § Out of Scope. Order: graded probe runs INSIDE the per-article candidate loop, AFTER Layer 1 has already approved the row (graded probe is a free-tier extra reject gate; cheap to keep)
- Per CLAUDE.md "Surgical Changes": every changed line traces to LF-3.1 / LF-3.4 / LF-3.5 / LF-3.6
  </action>
  <verify>
    <automated>python -c "import batch_ingest_from_spider; print('imports ok')"</automated>
    <automated>python -c "
from batch_ingest_from_spider import _build_topic_filter_query
import inspect
sig = inspect.signature(_build_topic_filter_query)
assert list(sig.parameters) == ['topics']
sql, params = _build_topic_filter_query([])
assert 'layer1_verdict IS NULL' in sql
assert params == ('layer1_v0_20260507',)
print('SQL ok')"</automated>
  </verify>
  <acceptance_criteria>
    - File `batch_ingest_from_spider.py` parses + imports cleanly
    - File contains literal `await layer1_pre_filter(`
    - File contains literal `persist_layer1_verdicts(conn, articles_meta, layer1_results)`
    - File contains literal `[layer1] batch` (log tag)
    - File contains literal `[layer2] reject id=` (log tag)
    - File no longer contains literal `if not layer1.passed:` (old shape removed)
    - File no longer contains literal `if not layer2.passed:` (old shape removed)
    - File still contains `--topic-filter` and `--min-depth` argparse entries (back-compat)
    - 5-article dry-run smoke completes without exception (manual gate, executed by operator):
      `OMNIGRAPH_BASE_DIR=$(pwd)/.dev-runtime python batch_ingest_from_spider.py --from-db --max-articles 5 --dry-run` exits 0 AND log contains `[layer1] batch`
  </acceptance_criteria>
  <done>LF-3.1 (Layer 1 batch wiring + skipped-row persistence) + LF-3.4 (candidate SQL predicate) + LF-3.5 (log tags) + LF-3.6 (dry-run) all delivered.</done>
</task>

</tasks>

<verification>
After Tasks 2.1 + 2.2 land:

```bash
# Import + SQL shape regressions
python -c "
import batch_ingest_from_spider
sql, params = batch_ingest_from_spider._build_topic_filter_query(['agent'])
assert 'layer1_verdict IS NULL' in sql
assert params[0] == 'layer1_v0_20260507'
print('ok')
"

# Existing pytest suite — ir-1-02 owns layer1 unit tests; this plan should
# leave the pytest suite minus tests/unit/test_article_filter.py at the
# same pass/fail count as the v3.4 baseline. test_article_filter.py is
# expected to FAIL for shape mismatches (intentional; ir-1-02 fixes).
python -m pytest tests/unit/ --ignore=tests/unit/test_article_filter.py -q 2>&1 | tail -5

# Local 5-article dry-run smoke (manual; operator runs):
OMNIGRAPH_BASE_DIR=$(pwd)/.dev-runtime \
  python batch_ingest_from_spider.py --from-db --max-articles 5 --dry-run \
  2>&1 | tee .scratch/ir-1-01-smoke-$(date +%s).log
# Expect log lines: [layer1] batch ... candidate=N reject=M ...
```
</verification>

<commit_message>
feat(ir-1): rewire ingest loop to batched Layer 1

batch_ingest_from_spider.py: replace per-article Layer 1 call with batch-of-30
async call at chunk boundary; persist verdicts atomically via
persist_layer1_verdicts; reject rows write ingestions(status='skipped') without
scrape; candidates drain through existing scrape→layer2→ainsert loop.

Candidate SQL gains layer1_verdict IS NULL OR layer1_prompt_version != ?
predicate; PROMPT_VERSION_LAYER1 binds the parameter. --topic-filter /
--min-depth flags retained but silent (LF-3.4 back-compat). Layer 2 inline
call updated to new 3-field FilterResult shape; placeholder always-pass
returning verdict='candidate' until ir-2 ships real DeepSeek call.

REQs: LF-3.1, LF-3.4, LF-3.5, LF-3.6
Phase: v3.5-Ingest-Refactor / ir-1 / plan 01
Depends-on: ir-1-00 (lib/article_filter contract)
</commit_message>

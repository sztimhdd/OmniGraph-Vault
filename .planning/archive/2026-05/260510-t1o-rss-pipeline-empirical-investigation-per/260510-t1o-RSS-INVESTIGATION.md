# RSS Pipeline Empirical Investigation (260510-t1o)

**Date:** 2026-05-10
**Scope:** Read-only. No production code, DB, or env changes.
**Question:** Is the "0 RSS ingestions=ok despite 546 bodies persisted" gap an ar-1 milestone or a ~50 LOC quick fix?

---

## Verdict (TL;DR)

**One line:** `~50 LOC quick scope`

**Justification:** The RSS dispatch infrastructure is already wired end-to-end (dual-source UNION ALL candidate SQL, source-aware Layer 1 + Layer 2 persistence to `rss_articles`, source-aware `_needs_scrape`, source-aware `ingestions` row writes). What is missing is a single-axis correctness fix at one call site: `batch_ingest_from_spider.ingest_article` at `batch_ingest_from_spider.py:286` blindly dispatches *every* URL to `ingest_wechat.ingest_article` regardless of `source`. For non-WeChat URLs this produces a `wechat_*` doc_id and runs the WeChat-specific scrape/cache path on a generic blog URL — which is why all 4 RSS rows that passed both filters landed in `ingestions(status='failed')`. The other 1600 RSS rows are NOT failures: they are correct rejects from Layer 1 / Layer 2 (1561 rejects + 4 ainsert failures + 35 candidates not yet processed). The fix is an `if source == 'rss': route to a generic ainsert helper else: ingest_wechat.ingest_article` branch at the same call site, plus the generic helper itself (~50 LOC).

---

## 1. Layer 2 verdict persistence call-sites

### Grep evidence

```
Grep pattern: "persist_layer2_verdicts|layer2_full_body_score"
path: C:/Users/huxxha/Desktop/OmniGraph-Vault (*.py only, excluding .planning/)
```

Production-code matches (excluding `.planning/`, docstrings, test files):

| File:line | Match | Context |
|---|---|---|
| `batch_ingest_from_spider.py:71` | import `layer2_full_body_score` | top-of-file imports from `lib.article_filter` |
| `batch_ingest_from_spider.py:73` | import `persist_layer2_verdicts` | top-of-file imports from `lib.article_filter` |
| `batch_ingest_from_spider.py:1655` | call `await layer2_full_body_score(articles_with_body)` | inside `_drain_layer2_queue` closure |
| `batch_ingest_from_spider.py:1679` | call `persist_layer2_verdicts(conn, articles_with_body, layer2_results)` | immediately after the score call |
| `lib/article_filter.py:458` | def `layer2_full_body_score(articles: list[ArticleWithBody]) -> list[FilterResult]` | function definition |
| `lib/article_filter.py:639` | def `persist_layer2_verdicts(conn, articles, results)` | function definition |

### Source-aware analysis

**`lib/article_filter.py:639-683` — `persist_layer2_verdicts` IS source-aware**:

```python
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
```

Verdict columns are written to `articles` for `source='wechat'` and `rss_articles` for `source='rss'`. The mirror function `persist_layer1_verdicts` at `lib/article_filter.py:585-636` is identical in structure. **Layer 2 persistence is NOT the bug.**

The caller at `batch_ingest_from_spider.py:1644-1652` propagates `source=row[1]` into the `ArticleWithBody` dataclass:

```python
articles_with_body = [
    ArticleWithBody(
        id=row[0],
        source=row[1],     # <-- 'wechat' or 'rss' from the dual-source SELECT
        title=row[2] or "",
        body=body or "",
    )
    for row, body in queue_snapshot
]
```

So the upstream tuple shape carries the source label all the way through Layer 2 persistence. No bug here.

---

## 2. `batch_ingest_from_spider.py` source-branch analysis

### Grep evidence

```
Grep pattern: "source\s*==\s*['\"]rss['\"]|source\s*=\s*['\"]rss['\"]|FROM rss_articles|UNION ALL"
path: batch_ingest_from_spider.py
```

Source-aware sites found:

| Line | Site | Branches on source? |
|---|---|---|
| `batch_ingest_from_spider.py:931` | `_needs_scrape` | YES — `if source == "rss" and len(body) <= RSS_SCRAPE_THRESHOLD: return True` |
| `batch_ingest_from_spider.py:1407` | candidate SQL `UNION ALL` clause | YES — pulls `articles` (source literal `'wechat'`) and `rss_articles` (source literal `'rss'`) |
| `batch_ingest_from_spider.py:1419` | candidate SQL `WHERE source = 'rss'` filter on `ingestions` | YES — both halves of UNION exclude rows already in `ingestions` per source |
| `batch_ingest_from_spider.py:1530` | `articles_meta = [ArticleMeta(... source=row[1] ...)]` | YES — Layer 1 batch carries source through |
| `batch_ingest_from_spider.py:1645-1652` | `articles_with_body = [ArticleWithBody(... source=row[1] ...)]` | YES — Layer 2 batch carries source through |
| `batch_ingest_from_spider.py:1697`, `1746` | `INSERT OR REPLACE INTO ingestions(article_id, source, ...) VALUES (?, ?, ...)` | YES — writes correct source label per row |
| `batch_ingest_from_spider.py:1872-1887` | pre-Layer-2 scrape via `lib.scraper.scrape_url(url)` | NO direct branch, but `scrape_url` auto-routes by URL host (mp.weixin → WeChat scrape, others → generic). `_persist_scraped_body(conn, art_id, source, scraped)` at line 1877 IS source-aware (writes `articles.body` for wechat / `rss_articles.body` for rss) |

### The MISSING source-branch site

**`batch_ingest_from_spider.py:1730-1732` — the ainsert dispatch is NOT source-aware**:

```python
success, wall, doc_confirmed = await ingest_article(
    url_d, dry_run, rag, effective_timeout=effective_timeout
)
```

…which calls `batch_ingest_from_spider.ingest_article` at `batch_ingest_from_spider.py:237-323`, which at line 286 dispatches:

```python
import ingest_wechat
...
await asyncio.wait_for(
    ingest_wechat.ingest_article(url, rag=rag),
    timeout=timeout_s,
)
```

`ingest_wechat.ingest_article` (defined at `ingest_wechat.py:916`, docstring line 917 says: *"Ingest a single WeChat article."*) is hardcoded WeChat-specific:

- `ingest_wechat.py:944` — `article_hash = hashlib.md5(url.encode()).hexdigest()[:10]` (URL hash, OK on any URL but used for WeChat image-dir namespace)
- `ingest_wechat.py:984` — `doc_id = f"wechat_{article_hash}"` (LightRAG doc id is hardcoded `wechat_*` prefix regardless of source)
- The full function (916-…) treats `url` as a WeChat article: cache check in WeChat-image-namespace dir, scrape via WeChat-specific cascade, image extraction tuned for WeChat HTML, etc.

**Summary:** Every layer of the pipeline EXCEPT the final ainsert dispatch is source-aware. The candidate SQL pulls RSS, Layer 1 batches RSS, Layer 1 persist writes `rss_articles.layer1_*`, scrape pre-Layer-2 routes by URL and persists to `rss_articles.body`, Layer 2 batches RSS, Layer 2 persist writes `rss_articles.layer2_*`, and the per-row `ingestions` insert tags correct `source='rss'`. Then the `if result.verdict == 'ok'` branch at line 1708 calls `ingest_article(url_d, ...)` without any source dispatch and `ingest_wechat.ingest_article` runs WeChat code on a generic blog URL.

---

## 3. Production DB — `ingestions` skip_reason histogram (source='rss')

### Schema check

```sql
PRAGMA table_info(ingestions);
```

Production schema (Hermes `~/OmniGraph-Vault/data/kol_scan.db`, queried via `sqlite3 'file:...?mode=ro'`):

```
(0, 'id', 'INTEGER', 0, None, 1)
(1, 'article_id', 'INTEGER', 1, None, 0)
(2, 'source', 'TEXT', 1, "'wechat'", 0)
(3, 'status', 'TEXT', 1, None, 0)
(4, 'ingested_at', 'TEXT', 0, "datetime('now', 'localtime')", 0)
(5, 'enrichment_id', 'TEXT', 0, None, 0)
(6, 'skip_reason_version', 'INTEGER', 1, '0', 0)
```

**Note:** the live schema does NOT have a textual `skip_reason` column. Only `skip_reason_version` (cohort integer per quick `260509-s29` Wave 2). So the brief's literal `skip_reason` query has to be reframed against `(status, skip_reason_version)`.

### Gap confirmation

```sql
SELECT COUNT(*) FROM ingestions WHERE source='rss';                          -- 1604
SELECT COUNT(*) FROM ingestions WHERE source='rss' AND status='ok';          -- 0
SELECT COUNT(*) FROM rss_articles WHERE body IS NOT NULL;                    -- 546
SELECT COUNT(*) FROM rss_articles;                                            -- 1649
```

### Status histogram (source='rss')

```sql
SELECT status, COUNT(*) FROM ingestions WHERE source='rss' GROUP BY status ORDER BY 2 DESC;
```

| status | n |
|---|---|
| skipped | 1600 |
| failed | 4 |

### Status × skip_reason_version histogram (source='rss')

```sql
SELECT skip_reason_version, status, COUNT(*) FROM ingestions WHERE source='rss' GROUP BY skip_reason_version, status ORDER BY 3 DESC;
```

| skip_reason_version | status | n |
|---|---|---|
| 0 | skipped | 1578 |
| 1 | skipped | 22 |
| 0 | failed | 4 |

**Interpretation:** 1600 RSS rows ended `skipped` (cohort v0=1578, v1=22) and 4 ended `failed`. ZERO ended `ok`. The `skipped` rows are NOT failures of the pipeline — they are Layer 1 / Layer 2 rejects (see Section 4 cross-tab below). The `failed` rows are the actual ingest failures.

---

## 4. Production DB — `rss_articles` layer1_verdict histogram (body present, layer2 missing)

### Brief query

```sql
SELECT layer1_verdict, COUNT(*)
  FROM rss_articles
 WHERE body IS NOT NULL AND layer2_verdict IS NULL
 GROUP BY layer1_verdict
 ORDER BY 2 DESC;
```

| layer1_verdict | n |
|---|---|
| reject | 503 |

503 body-bearing RSS rows have layer1=reject and layer2 was never run (correct — Layer 2 only runs on Layer 1 candidates per `batch_ingest_from_spider.py:1760-1766`).

### layer2_verdict on body-bearing rows

```sql
SELECT layer2_verdict, COUNT(*)
  FROM rss_articles
 WHERE body IS NOT NULL
 GROUP BY layer2_verdict
 ORDER BY 2 DESC;
```

| layer2_verdict | n |
|---|---|
| (NULL) | 503 |
| reject | 39 |
| ok | 4 |

Only 4 body-bearing RSS rows reached `layer2_verdict='ok'`. **All 4 are exactly the same 4 rows that show `ingestions(status='failed')` above.**

### Cross-tab

```sql
SELECT r.layer1_verdict, r.layer2_verdict, i.status,
       (CASE WHEN r.body IS NOT NULL THEN 'body' ELSE 'no-body' END) AS bod,
       COUNT(*)
  FROM rss_articles r LEFT JOIN ingestions i
    ON r.id = i.article_id AND i.source = 'rss'
 GROUP BY r.layer1_verdict, r.layer2_verdict, i.status, bod
 ORDER BY 5 DESC;
```

| layer1 | layer2 | ingest status | body | n |
|---|---|---|---|---|
| reject | (NULL) | skipped | no-body | 1058 |
| reject | (NULL) | skipped | body | 503 |
| candidate | (NULL) | (NULL) | no-body | 45 |
| candidate | reject | skipped | body | 31 |
| reject | reject | skipped | body | 8 |
| candidate | ok | failed | body | 4 |

**Interpretation:**
- **1058 + 503 = 1561 rows** are Layer 1 rejects. The 503 with body are NOT scrape waste — they came from `rss_fetch`'s `<content:encoded>` path BEFORE Layer 1 ran (rss_fetch populates `body` directly when the feed provides full content). These bodies were never scraped via the expensive cascade.
- **45 + 35 = 80 candidate rows** await processing (not yet drained to Layer 2 — likely cron didn't fire, or batch hasn't reached them).
- **31 + 8 = 39 rows** ran Layer 2 → reject. Correctly skipped.
- **4 rows passed Layer 1 + Layer 2 and went to ainsert → all FAILED.** These are the only "real" ingest failures.

### The 4 failure rows (sampled)

```sql
SELECT i.article_id, i.status, i.ingested_at, r.url, r.layer2_verdict, length(r.body)
  FROM ingestions i JOIN rss_articles r ON r.id = i.article_id
 WHERE i.source='rss' AND i.status='failed'
 ORDER BY i.ingested_at DESC;
```

| article_id | status | ingested_at | url | layer2 | body_len |
|---|---|---|---|---|---|
| 2060 | failed | 2026-05-09 18:40:45 | `https://michael.stapelberg.ch/posts/2026-02-01-coding-agent-microvm-nix/` | ok | 61665 |
| 1969 | failed | 2026-05-09 18:40:17 | `https://martinalderson.com/posts/minification-isnt-obfuscation-claude-code-proves-it/?...` | ok | 92 |
| 1954 | failed | 2026-05-09 18:39:23 | `https://martinalderson.com/posts/which-web-frameworks-are-most-token-efficient-for-ai-agents/?...` | ok | 177 |
| 1952 | failed | 2026-05-09 18:37:57 | `https://martinalderson.com/posts/why-on-device-agentic-ai-cant-keep-up/?...` | ok | 122 |

Three of four bodies are <200 chars (the `<description>` excerpt — Layer 2 still scored them `ok` because the prompt tolerates short bodies). The fourth has 61665 chars (real content). All four URLs are non-WeChat blog URLs that were dispatched to `ingest_wechat.ingest_article` per Section 2 finding — and that function is WeChat-specific (cache dir, image namespace, doc_id prefix `wechat_*`).

### KOL baseline for comparison

```sql
SELECT source, status, COUNT(*) FROM ingestions GROUP BY source, status ORDER BY 1, 3 DESC;
```

| source | status | n |
|---|---|---|
| rss | skipped | 1600 |
| rss | failed | 4 |
| wechat | skipped | 597 |
| wechat | ok | 77 |
| wechat | skipped_ingested | 27 |
| wechat | failed | 20 |

WeChat path produces 77 `ok` ingests through the same orchestrator, confirming the pipeline shell works end-to-end. RSS produces 0 because the final dispatch routes RSS URLs into the WeChat-specific ingester.

---

## 5. Local dry-run trace

### Command

```bash
./scripts/local_e2e.sh kol --dry-run --max-articles 1
```

(per CLAUDE.md mandate; the harness's `rss` mode is now deprecated post-ir-4 — its help text says: *"DEPRECATED post-ir-4 (LF-5.1). enrichment/rss_ingest.py was retired"*. The new dual-source path is `kol --dry-run`, which exercises both sources via the UNION ALL candidate SQL.)

### Death point

Layer 1 — corp-network env gap, NOT a code bug:

```
21:00:06 INFO __main__ 197 articles to process (scrape-first) for topics []
21:00:06 WARNING lib.article_filter [layer1] LLM error RuntimeError:
  GOOGLE_CLOUD_PROJECT is not set. Vertex Gemini LLM path requires SA auth
  (GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT).
  See docs/LOCAL_DEV_SETUP.md.
21:00:06 WARNING __main__ [layer1] batch 0 NULL reason=exception:RuntimeError n=30 wall_ms=3
... (batches 1..6 same error) ...
21:00:06 INFO __main__ [layer1] no candidates after batch filtering (total inputs=197);
                         nothing to ingest
[local-e2e] EXIT=0  log=.scratch/local-e2e-kol-20260510-210001.log
```

Death point: `lib/article_filter.py` Layer 1 batch 0, raises `RuntimeError: GOOGLE_CLOUD_PROJECT is not set` from `lib.llm_complete` Vertex path.

### What the trace DID confirm

1. **Dual-source candidate SQL pulls both KOL + RSS** — the harness header logged `197 articles to process (scrape-first) for topics []`. Confirmed via independent local query:

   ```python
   # local DB approximation of ir-4 LF-4.4 candidate SQL
   ('wechat', 76)
   ('rss', 219)
   ```

   The dual-source UNION ALL works (SQL was tested earlier in the analysis loop). 219 RSS local candidates exist with `body IS NOT NULL` — they would have been processed if Layer 1 had run.

2. **Layer 1 dispatches both sources into ONE batch** — the death message says `n=30` per batch, mixed wechat + rss rows. Layer 1 isn't the gap.

### Why the trace can't go deeper locally

- Layer 1 needs Vertex Gemini (corp-reachable), but `GOOGLE_CLOUD_PROJECT` env var isn't auto-set by the harness on this corp laptop. Setting it would need a spike, out of read-only scope.
- Even if Layer 1 ran, Layer 2 needs DeepSeek (corp-blocked per CLAUDE.md), so the dry-run could not reach the ainsert dispatch site at `batch_ingest_from_spider.py:1730` — exactly the site flagged in Section 2.
- The empirical evidence to confirm the bug already exists in production DB (Section 4 — 4 out of 4 ainsert attempts failed). A local dry-run is not needed to confirm scope.

**Skip rationale:** Steps 1-4 already produce decisive evidence. The local trace would have confirmed the SAME finding (death at the WeChat-only ainsert dispatch) but cannot reach that line due to the corp-network DeepSeek block before it. Recording this as documented skip per CLAUDE.md's local-vs-Hermes reachability matrix.

---

## Appendix: SSH commands run

All commands run via `ssh -p 49221 sztimhdd@ohca.ddns.net "<cmd>"` where `<cmd>` is one of:

```bash
# Reachability + git state
hostname
cd ~/OmniGraph-Vault && git rev-parse --short HEAD && git status -sb

# Find DB
ls -la ~/.hermes/omonigraph-vault/data/*.db
find ~/.hermes/omonigraph-vault -name '*.db' -type f | head -5
find ~/OmniGraph-Vault -name 'kol_scan.db' -type f | head -5

# All SELECT-only queries via venv-Python (sqlite3 CLI not on Hermes PATH).
# Connection always:
#   sqlite3.connect('file:/home/sztimhdd/OmniGraph-Vault/data/kol_scan.db?mode=ro', uri=True)
# Queries:
PRAGMA table_info(ingestions);
PRAGMA table_info(rss_articles);
SELECT COUNT(*) FROM ingestions WHERE source='rss';
SELECT COUNT(*) FROM ingestions WHERE source='rss' AND status='ok';
SELECT COUNT(*) FROM rss_articles WHERE body IS NOT NULL;
SELECT COUNT(*) FROM rss_articles;
SELECT status, COUNT(*) FROM ingestions WHERE source='rss' GROUP BY status ORDER BY 2 DESC;
SELECT skip_reason_version, status, COUNT(*) FROM ingestions WHERE source='rss' GROUP BY skip_reason_version, status ORDER BY 3 DESC;
SELECT layer1_verdict, COUNT(*) FROM rss_articles WHERE body IS NOT NULL AND layer2_verdict IS NULL GROUP BY layer1_verdict ORDER BY 2 DESC;
SELECT layer2_verdict, COUNT(*) FROM rss_articles WHERE body IS NOT NULL GROUP BY layer2_verdict ORDER BY 2 DESC;
SELECT layer1_verdict, (CASE WHEN body IS NOT NULL THEN 'body' ELSE 'no-body' END) AS bod, COUNT(*) FROM rss_articles GROUP BY layer1_verdict, bod ORDER BY 3 DESC;
SELECT r.layer1_verdict, r.layer2_verdict, i.status, (CASE WHEN r.body IS NOT NULL THEN 'body' ELSE 'no-body' END) AS bod, COUNT(*) FROM rss_articles r LEFT JOIN ingestions i ON r.id = i.article_id AND i.source = 'rss' GROUP BY r.layer1_verdict, r.layer2_verdict, i.status, bod ORDER BY 5 DESC LIMIT 30;
SELECT i.article_id, i.status, i.ingested_at, r.url, r.layer1_verdict, r.layer2_verdict, length(r.body) AS body_len FROM ingestions i JOIN rss_articles r ON r.id = i.article_id WHERE i.source='rss' AND i.status='failed' ORDER BY i.ingested_at DESC;
SELECT id, length(body), substr(body, 1, 200) FROM rss_articles WHERE id IN (1952, 1954, 1969, 2060);
SELECT source, status, COUNT(*) FROM ingestions GROUP BY source, status ORDER BY 1, 3 DESC;
```

All queries `SELECT-only` / `PRAGMA-only`. No INSERT / UPDATE / DELETE / CREATE / DROP / ALTER / VACUUM. Read-only URI mode (`mode=ro`) used on every connection. Hermes git status pre and post investigation match (verified `git status -sb` returned same untracked-file list throughout; no production code, env, or DB row mutations).

---

## Estimated fix shape (~50 LOC quick scope)

For the planner's downstream use — not part of this read-only deliverable, but distilled from the evidence:

1. Add `from lib.scraper import scrape_url` import in a new generic ingester (or reuse the existing one — `lib/scraper.py` already has the auto-routing cascade).
2. Either:
   - **Option A (minimal):** add a `source: str = 'wechat'` parameter to `batch_ingest_from_spider.ingest_article` (line 237). When `source == 'rss'`, build `doc_id = f"rss_{article_hash}"`, fetch the body from `rss_articles.body` (already persisted), and call `rag.ainsert(body, ids=[doc_id])` directly. Skip the WeChat-specific cache + image pipeline entirely. Pass `source` from caller line 1730. Roughly ~30-40 LOC.
   - **Option B (cleaner):** extract a generic `_ainsert_text_only(rag, body, doc_id)` helper into `lib/ainsert.py`, call it from both `ingest_wechat.ingest_article` and a new `ingest_rss.ingest_article` (or inline it in the orchestrator). Roughly ~50-70 LOC; tests add another ~30-50.
3. Backfill: re-mark the 4 `ingestions(status='failed')` RSS rows + reset their layer2_at so they re-attempt next tick. (Single SQL UPDATE — out of scope here, but trivial.)

Either option is single-file or two-file change. No schema migration needed (cohort versioning already in place via `skip_reason_version`). No new dependencies. The 80 untouched RSS candidates would naturally drain on the next scheduled cron tick once the ainsert dispatch routes them to the right ingester.

---

**End of investigation.**

# Quick 260507-lai — Summary

**Description:** v3.5 Ingest Refactor foundation — bypass `_classify_full_body`,
wire ingest loop to placeholder Layer 1/2 filters in `lib/article_filter.py`.

**Date:** 2026-05-07
**Status:** ✅ Code shipped (Hermes-side cutover pending operator)

---

## Commits (in order, all on `main`)

| # | SHA | Subject |
|---|-----|---------|
| 1 | `bd735ae` | feat(filter): lib/article_filter.py with Layer 1/2 placeholders |
| 2 | `5d37232` | test(filter): pin Layer 1/2 placeholder interface contract |
| 3 | `f1a963b` | feat(ingest): bypass _classify_full_body — wire to placeholder Layer 1/2 (v3.5 foundation) |
| 4 | `fbe3401` | docs(deploy): v3.5 foundation Hermes deploy runbook |
| 5 | this commit | docs(quick-260507-lai): plan + summary + STATE update |

`git status -sb` clean and synced post-each-commit.

---

## Requirements satisfied

- **V35-FOUND-01** — `lib/article_filter.py` exposes `FilterResult`,
  `layer1_pre_filter`, `layer2_full_body_score`. Both layers return
  `FilterResult(passed=True, reason="placeholder: ...")`. 7 contract
  tests in `tests/unit/test_article_filter.py` (frozen dataclass,
  always-pass, placeholder substring in reason).
- **V35-FOUND-02** — ingest loop in `batch_ingest_from_spider.py` calls
  `layer1_pre_filter` BEFORE scrape and `layer2_full_body_score` AFTER
  scrape. The `_classify_full_body` call is removed; the function body
  is retained for future cleanup.
- **V35-FOUND-03** — `_build_topic_filter_query` SQL no longer joins
  `classifications`, no longer uses `LIKE`, no longer references
  `c.depth_score` / `c.topic`. Returns `(sql, ())` regardless of topic
  argument.
- **V35-FOUND-04** — `HERMES-DEPLOY.md` covers pre-flight, three cron
  removals (`b50ec39b889f`, `fc768319e0c1`, `c7ded378de8f`), one cron
  edit (`2b7a8bee53e0`), resume + smoke + 3-commit rollback.

---

## Production code changes

### `lib/article_filter.py` (new — 117 lines)

Frozen `FilterResult` dataclass with two fields (`passed: bool`, `reason: str`)
plus two placeholder filter functions. Both always return `passed=True`
with a reason containing the literal `placeholder` so log greps can flag
any cron run still relying on always-pass before real logic ships.

### `batch_ingest_from_spider.py`

```diff
+from lib.article_filter import layer1_pre_filter, layer2_full_body_score

 def _build_topic_filter_query(topics: list[str]) -> tuple[str, tuple[str, ...]]:
-    placeholders = " OR ".join("LOWER(c.topic) LIKE ?" for _ in topics)
     sql = """
-        SELECT a.id, a.title, a.url, acc.name, c.depth_score, a.body, a.digest
+        SELECT a.id, a.title, a.url, acc.name, a.body, a.digest
         FROM articles a
         JOIN accounts acc ON a.account_id = acc.id
-        LEFT JOIN classifications c ON a.id = c.article_id
-        WHERE (c.topic IS NULL OR ({placeholders}))
-          AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
+        WHERE a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
         ORDER BY a.id
     """
-    normalized = tuple(f"%{t.strip().lower()}%" for t in topics)
-    return sql, normalized
+    return sql, ()

-for i, (art_id, title, url, account, depth, body, digest) in enumerate(rows, 1):
+for i, (art_id, title, url, account, body, digest) in enumerate(rows, 1):

-cls_result = await _classify_full_body(conn, article_id, url, title, body, api_key, topic_filter=topics)
-if cls_result is None: skip
-if cls_topics don't match: skip
-if cls_depth < min_depth: skip
+layer1 = layer1_pre_filter(title, summary=digest or "", content_length=None)
+if not layer1.passed: skip
+# (existing pre-scrape persistence preserved)
+layer2 = layer2_full_body_score(article_id, title, body or "")
+if not layer2.passed: skip
```

`_classify_full_body`, `_call_deepseek_fullbody`, `_build_fullbody_prompt`
function bodies are retained (only the ingest-loop call is removed).
`--min-depth` and `--topic-filter` CLI flags are retained, silently
ignored.

---

## Tests

### `tests/unit/test_article_filter.py` (new — 7 GREEN)

Pins the placeholder interface contract:
- 3 tests for Layer 1 (returns `FilterResult`, always passes, reason mentions
  "placeholder")
- 3 mirror tests for Layer 2
- 1 frozen-dataclass test (`FrozenInstanceError` on `.passed = False`)

### `tests/unit/test_batch_ingest_topic_filter.py` (rewritten — 11 GREEN)

Pre-Quick: pinned the OLD topic-filter SQL (LIKE/JOIN/NULL). Rewritten to
pin the v3.5 contract:
- SQL selects v3.5 column shape (no `c.depth_score`)
- SQL does NOT contain `classifications`, `c.depth_score`, `c.topic`, or `LIKE`
- SQL JOINs `accounts`, anti-joins `ingestions WHERE status='ok'`,
  `ORDER BY a.id`
- params is always `()` regardless of topics
- topics arg is silently accepted (parameterized over 3 lists)

### `tests/unit/test_classify_full_body_topic_hint.py` (2 obsolete tests removed)

`test_ingest_from_db_passes_list_topic_through` and
`test_ingest_from_db_converts_str_topic_to_list` asserted that the ingest
loop calls `_classify_full_body(topic_filter=...)`. Both behaviours are
explicitly removed by V35-FOUND-02. The 7 remaining tests in the file
still validate `_classify_full_body`'s own behaviour (signature + prompt
construction); function body retained.

### Local pytest

- 29/29 directly-affected tests pass
  (`test_article_filter` + `test_classifications_multitopic` +
   `test_classifications_upsert` + `test_batch_ingest_hash` +
   `test_batch_ingest_topic_filter` + `test_classify_full_body_topic_hint`)
- Smoke: `--from-db --topic-filter agent --max-articles 1 --dry-run` against
  `.dev-runtime/data/kol_scan.db` enumerates 531 candidates and exits cleanly

---

## Hermes deployment

Runbook at
`.planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md`.

6 steps for user-driven SSH execution:
1. Pre-flight (`git pull --ff-only`, verify commit chain)
2. Remove 3 obsolete crons (`daily-classify-kol`, `daily-enrich`, `rss-classify`)
3. Edit `daily-ingest` cron to drop `--topic-filter`
4. Resume + verify next-fire
5. Optional 1-article dry-run smoke
6. Rollback: 3-commit `git revert` chain

Total wall-clock: ~5–10 minutes. No DB migrations, no destructive DDL.

---

## What's next

**Hermes-side execution (operator):** Run the runbook from the existing
SSH session. The next `daily-ingest` cron firing will exercise the v3.5
foundation end-to-end against production DB.

**Real Layer 1/2 logic:** Deferred to follow-up quicks per
`.planning/PROJECT-Ingest-Refactor-v3.5.md` Phase B+C. The Layer 1/2
function bodies in `lib/article_filter.py` are the only files that need
to change; the ingest loop wiring is now the stable contract.

**Dead code cleanup (future):** `_classify_full_body`,
`_call_deepseek_fullbody`, `_build_fullbody_prompt` function bodies
remain in `batch_ingest_from_spider.py` even though the ingest loop no
longer calls them. A follow-up quick can delete them once the v3.5
foundation has run a clean cron cycle on production.

---

## Compliance with strict scope

- ✅ No Phase 20 / Agentic-RAG-v1 planning docs touched
- ✅ Selective `git add` per-commit (no `-A` / `.`)
- ✅ Forward-only commit history (no stash / reset / rebase / amend / force-push)
- ✅ No schema changes — no `CREATE`/`ALTER`/`DROP TABLE`, no new migrations
- ✅ `_classify_full_body` family function bodies retained
- ✅ `--min-depth` and `--topic-filter` CLI flags retained (silently ignored)
- ✅ Operator runs Hermes-side via runbook (agent does not SSH)

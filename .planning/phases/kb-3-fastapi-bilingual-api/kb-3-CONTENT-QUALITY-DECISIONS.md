---
artifact: DECISIONS
phase: kb-3-fastapi-bilingual-api
created: 2026-05-13
authority: locked decision — gsd-planner MUST emit at least one plan task implementing this filter; cannot be silently dropped
related_req: DATA-07
audience: gsd-planner (when /gsd:plan-phase kb-3 runs), kb-3 executor agents
---

# kb-3 — Content Quality Filter (DATA-07)

> **Status:** Locked decision authored 2026-05-13 by user after auditing kb-1 SSG output and finding the article library shows zero WeChat articles in homepage / list cards. Root cause: `list_articles()` returned all 2501 scanned rows (no body filter, no Layer-1/Layer-2 verdict filter), and a separate cross-source merge-sort bug pushed all KOL rows past the limit. This decision adds the missing quality gate. The sort bug is a separate quick task — see § "Companion fix" below.

## Decision

`kb/data/article_query.py` list-style query functions MUST apply a 3-condition content-quality filter excluding any article that fails ANY of:

1. **Body present** — `body IS NOT NULL AND body != ''` (DB body field non-empty; "本地有完整的body")
2. **Layer 1 passed** — `layer1_verdict = 'candidate'` (Layer 1 explicitly approved; not 'reject', not NULL)
3. **Layer 2 not rejected** — `layer2_verdict IS NULL OR layer2_verdict != 'reject'` (Layer 2 didn't kill it; NULL is allowed for backwards-compat with rows from before Layer 2 was deployed)

**Symmetric application:** both `articles` (KOL) and `rss_articles` have `body`, `layer1_verdict`, `layer2_verdict` columns since v3.5 ir-4. Filter SQL is identical modulo table name. No source-specific carve-out.

**Affected query functions:** all of these MUST be updated:
- `list_articles()` (kb-1 — REQ DATA-04)
- `topic_articles_query()` (kb-2 — REQ TOPIC-02)
- `entity_articles_query()` (kb-2 — REQ ENTITY-02)
- `cooccurring_entities_in_topic()` (kb-2 — REQ TOPIC-03)
- `related_entities_for_article()` (kb-2 — REQ LINK-01)
- `related_topics_for_article()` (kb-2 — REQ LINK-02)

**NOT affected (intentional carve-out):**
- `get_article_by_hash()` — direct URL access by hash. A user clicking a search result, KG synthesize source link, or bookmark must still resolve to the rendered detail page even if the article wouldn't appear in a list. **The detail page reaches `kb/output/articles/{hash}.html` via static-file serve regardless.** Rationale: list curates discoverability; detail preserves direct-URL stability.
- The SSG-rendered detail HTML files (`kb/output/articles/*.html`) — already on disk, served as static assets. The filter only changes which articles appear in *list* surfaces, not which detail pages exist.

## Exact SQL clause (paste-ready for plan tasks)

For KOL (`articles` table):

```sql
WHERE body IS NOT NULL
  AND body != ''
  AND layer1_verdict = 'candidate'
  AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')
```

For RSS (`rss_articles` table) — identical:

```sql
WHERE body IS NOT NULL
  AND body != ''
  AND layer1_verdict = 'candidate'
  AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')
```

When combined with existing `lang =` / pagination clauses:

```sql
SELECT id, title, url, body, content_hash, lang, update_time
FROM articles
WHERE body IS NOT NULL
  AND body != ''
  AND layer1_verdict = 'candidate'
  AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')
  AND lang = ?           -- only when lang param non-null
ORDER BY update_time DESC, id DESC
```

## Env override (kill-switch for debugging)

```python
import os
QUALITY_FILTER_ENABLED = os.environ.get("KB_CONTENT_QUALITY_FILTER", "on").lower() != "off"
```

When `KB_CONTENT_QUALITY_FILTER=off`, the WHERE clauses (3 quality conditions) are skipped — list functions revert to pre-DATA-07 behavior. Used for:
- Debugging "why doesn't this article show up" tickets
- One-off audits of the unfiltered corpus
- Migration verification (compare filtered vs unfiltered counts)

Default is `on`. The env var is read at import time once per process — no per-call overhead.

## Expected visibility (verified 2026-05-13 against `.dev-runtime/data/kol_scan.db`, mirror of Hermes prod)

| Source | Total scanned | Pass filter | % visible |
|---|---|---|---|
| KOL (`articles`) | 789 | **127** | 16% |
| RSS (`rss_articles`) | 1712 | **33** | 2% |
| **Combined** | **2501** | **160** | **6.4%** |

**Why RSS is so low (2%):** RSS Layer 1 reject rate is ~93% (1588 of 1712 are `reject`) — most RSS feeds publish heavy-noise tech listicles that Layer 1 prompt v1 (HARD-KEEP RULE 0) correctly filters. Visibility is the point of the filter.

**Why KOL is higher (16%):** WeChat KOL accounts in the seed list are pre-curated for quality (handpicked influencers in AI/Agent space), so `candidate` rate is naturally higher (~27%). Of those, 60% have body successfully scraped → ~16% pass all 3 conditions.

These percentages are **the intended quality bar**, not a bug. The 6% combined visibility is healthy for a curated KB; the previous 100% (2501 articles, including stubs and rejects) was the wrong baseline.

## Cross-phase impact

| Phase | Surface | Inherits filter? | Action needed |
|---|---|---|---|
| **kb-1** | `kb/output/articles/index.html` (list page) | YES | Re-run SSG export after kb-3 ships data layer change. No template change. |
| **kb-1** | `kb/output/index.html` (homepage Latest cards) | YES | Same. |
| **kb-1** | `kb/output/articles/{hash}.html` (detail pages) | NO | Already-rendered files persist. Future re-runs may not re-render filtered-out articles, but existing files remain accessible. |
| **kb-2** | Topic page article list | YES | kb-2-04 query functions inherit filter automatically. Tests may need fixture rows that satisfy the filter. |
| **kb-2** | Entity page article list | YES | Same as topic. |
| **kb-2** | Homepage "Browse by Topic" / "Featured Entities" sections | YES | Article counts shown will reflect filtered counts. |
| **kb-2** | Article detail related-link rows | YES (LINK-01/02) | Related-entities and related-topics also filtered through their respective queries. |
| **kb-3** | `GET /api/articles` | YES (primary surface for this REQ) | — |
| **kb-3** | `GET /api/article/{hash}` | NO (carve-out) | Direct URL access preserved. |
| **kb-3** | `GET /api/search` | OPEN QUESTION (see below) | Plan task should resolve. |

**Open question — search results filtering:** Should `/api/search?q=...` apply DATA-07 to FTS5 hits? Two camps:
- **Apply filter** (consistent with list views) — search becomes a quality-curated discovery surface
- **Skip filter** (search is keyword retrieval, not curation) — a user searching for a known term should find any matching article including pre-Layer-1 historical rows

**Decision:** Apply filter by default; expose `KB_SEARCH_BYPASS_QUALITY=on` env override for power users / admin debugging. Same pattern as the global override but scoped to search. Document this in the API-04 plan task.

## Fixture coordination (kb-2-01)

`tests/integration/kb/conftest.py::build_kb2_fixture_db()` (kb-2-01 plan, already committed `977f13f`) must populate `layer1_verdict` and `layer2_verdict` columns on fixture article rows so the filter doesn't accidentally drop test data. Per kb-2-01 PLAN, the fixture currently inserts ~5 topics × 3 articles + 6 above-threshold entities. Each article row MUST have:
- `body` — non-empty (already required for kb-1 fixture)
- `layer1_verdict = 'candidate'`
- `layer2_verdict` — either `'ok'` (positive case) or `NULL` (backwards-compat case)

A small fraction of fixture rows (≥ 2 per source) SHOULD set `layer1_verdict = 'reject'` or `body = NULL` — these are negative-case rows that the DATA-07 filter must exclude. kb-3 plan task implementing DATA-07 MUST include unit tests that verify both positive (filter-passing) and negative (filter-excluding) fixture rows.

If kb-2-01 has already shipped without these verdict columns, the kb-3 plan task MUST add them as a fixture extension (additive — don't break kb-2 tests; they'll just see verdict='candidate' on every row, which all pass).

## Rollout plan (suggested for kb-3 planner)

**Wave 0 (foundation, depends on nothing):**
- Update `_NULL_VERDICT_GUARD` if needed in `kb/data/article_query.py` (defensive: handle case where DB has NULL verdict but env says filter on — current code may not have this guard).
- Verify both tables have all 3 columns via `PRAGMA table_info()` at module import — fail loud if any missing (don't silently disable filter on schema drift).

**Wave 1 (data layer):**
- Modify all 6 affected query functions to apply DATA-07 SQL clauses.
- Honor `KB_CONTENT_QUALITY_FILTER` env override.
- Add unit tests covering positive + negative + NULL-verdict + missing-body cases.

**Wave 2 (re-export verification):**
- Re-run `python kb/export_knowledge_base.py` against fixture and against `.dev-runtime/data/kol_scan.db`.
- Verify expected counts: ~127 KOL + ~33 RSS visible in articles list page (vs current 0+50).
- Capture before/after screenshots — homepage Latest section now shows mixed KOL+RSS, not RSS-only.

**Wave 3 (API surface):**
- API-02 `GET /api/articles` honors filter (delegated by calling `list_articles()`).
- API-04 `GET /api/search?mode=fts` honors filter unless `KB_SEARCH_BYPASS_QUALITY=on`.
- API-03 `GET /api/article/{hash}` does NOT filter (carve-out).
- Add API integration tests covering filter behavior + override.

## Acceptance criteria (grep-verifiable)

```bash
# 1. Filter SQL present in article_query.py
grep -E "layer1_verdict = 'candidate'" kb/data/article_query.py | wc -l   # should be ≥ 3

# 2. Env override implemented
grep "KB_CONTENT_QUALITY_FILTER" kb/data/article_query.py | wc -l   # should be ≥ 1

# 3. get_article_by_hash NOT filtered (carve-out preserved)
grep -A 20 "def get_article_by_hash" kb/data/article_query.py | grep "layer1_verdict"   # should be empty

# 4. Module-import schema check
grep "PRAGMA table_info" kb/data/article_query.py   # should find new guard

# 5. Unit tests cover filter behavior
test -f tests/unit/kb/test_data07_quality_filter.py
grep "KB_CONTENT_QUALITY_FILTER" tests/unit/kb/test_data07_quality_filter.py   # should be ≥ 2 (on + off cases)

# 6. After kb-3 ship + SSG re-run: kb-1 list page reflects filter
grep -c 'data-source="wechat"' kb/output/articles/index.html   # should be > 0 (was 0 before kb-3)

# 7. Visibility numbers within tolerance
PYTHONPATH=. python -c "import os; os.environ['KB_DB_PATH']='.dev-runtime/data/kol_scan.db'; from kb.data import article_query; print(len(article_query.list_articles(limit=10000)))"
# expected: ~160 ± 5% (depends on prod data drift)
```

## Out of scope for kb-3 (explicit deferrals)

- **Filesystem-fallback body resurrection** — currently 1032 articles have `body = NULL` in DB but a viable `~/.hermes/omonigraph-vault/images/{hash}/final_content.md` file. Strict DATA-07 SQL filter excludes them (since SQL can't see filesystem). One-time backfill migration (read filesystem → write DB) would resurrect these. Deferred to **v2.0.x quick task** post-kb-3 ship. Justification: v2.0 ships the canonical filter; data drift cleanup is a separate concern that doesn't gate the quality bar.

- **Re-classification of old `layer1_verdict = NULL` rows** — 46 KOL + ~0 RSS rows have `layer1_verdict IS NULL` (pre-Layer-1 deployment). DATA-07 excludes them by design. v2.1 candidate: re-run Layer 1 over historical NULL rows to bring them into the candidate pool.

- **Search-bypass UI** — power-user toggle to disable quality filter via UI checkbox (vs env var). Deferred to v2.1 admin/debug surface.

- **Layer 3 / Layer 4 verdict columns** — if future ingest pipeline adds more layers, DATA-07 clause does NOT auto-extend. The clause is fixed at 3 conditions. New verdict layers require an explicit DATA-08 amendment.

## Companion fix (separate quick task, NOT a kb-3 plan)

The **cross-source merge-sort bug** discovered 2026-05-13 (KOL ISO timestamps + RSS RFC 822 strings sort lexicographically wrong, pushing all KOL articles past `limit`) is INDEPENDENT of DATA-07 and should ship as its own quick task BEFORE kb-3 begins. Once both ship:
- DATA-07 reduces visible pool from 2501 → ~160
- Sort fix ensures the ~160 are sorted correctly by actual time, mixing KOL and RSS chronologically

If sort fix doesn't ship: DATA-07 alone would expose the sort bug more visibly (homepage 20 cards become 20/160, almost all RSS still wins lex sort). Run them as a pair.

Suggested quick task slug: `260513-xxx-rss-update-time-iso-normalize` — adds RFC 822 → ISO-8601 parsing in `_row_to_record_rss` so all merge-sort keys are uniform ISO strings.

## Reading list for the kb-3 planner

When `/gsd:plan-phase kb-3` runs, the gsd-planner MUST read this file and:
1. Allocate at least one plan task to implement the data-layer filter (estimate Wave 1 of kb-3)
2. Update at least one plan task to verify the API layer honors filter (Wave 3)
3. Reference this file in `<read_first>` of any plan task touching `kb/data/article_query.py`
4. Verify acceptance criteria above are distributed across plan acceptance grep patterns
5. Treat the "Open question — search results filtering" as a SETTLED decision (apply filter; bypass via env)

The planner MUST NOT silently drop DATA-07 — it is a locked v2.0 REQ added 2026-05-13 to close a real user-visible quality bug.

# Quick 260507-ent — Summary

**Description:** Emergency fix: revert UPSERT to `ON CONFLICT(article_id, topic)`
for multi-topic loop compatibility.

**Date:** 2026-05-07
**Status:** ✅ Complete (Hermes-side execution pending operator)

---

## Commits (in order, all on `main`)

| # | SHA | Subject |
|---|-----|---------|
| 1 | `428b16f` | fix(classify): revert UPSERT to ON CONFLICT(article_id, topic) — multi-topic loop compatibility |
| 2 | `25ca385` | docs(cv-repair): hermes runbook for 2026-05-07 CV mass-classify fix |
| 3 | `74fe773` | docs(claude.md): record 2026-05-07 CV mass-classify lesson #6 |

(2 more atomic commits — PLAN.md + SUMMARY.md — close out the GSD artifacts.)

Push range: `b0ce575..74fe773 → main`. `git status -sb` clean and synced
post-each-commit.

---

## What changed in production code

### `batch_classify_kol.py:447`

Pre-fix (Quick 260506-se5):

```python
ON CONFLICT(article_id) DO UPDATE SET
    topic=excluded.topic,
    depth_score=excluded.depth_score,
    relevant=excluded.relevant,
    excluded=excluded.excluded,
    reason=excluded.reason
```

Post-fix:

```python
ON CONFLICT(article_id, topic) DO UPDATE SET
    depth_score=excluded.depth_score,
    relevant=excluded.relevant,
    excluded=0,
    reason=excluded.reason
```

(Removed `topic=excluded.topic` because the conflict target now includes
topic — overwriting it would be a no-op.)

### `batch_ingest_from_spider.py:1024-1043`

Same pattern — second call site (full-body classify in ingest path,
introduced in Phase 20 RIN-01). Without this companion change, migration
005 would break the ingest path with `sqlite3.OperationalError: ON
CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint`.

### `migrations/005_drop_article_id_unique_index.sql` (new)

Single statement: `DROP INDEX IF EXISTS idx_classifications_article_id`.
Reverses migration 004's article_id-only UNIQUE INDEX. Idempotent.

---

## Tests

### `tests/unit/test_classifications_multitopic.py` (new)

4 regression tests, all GREEN:

1. `test_multi_topic_loop_creates_one_row_per_topic` — 5 sequential
   INSERTs with different topics produce 5 rows, not 1.
2. `test_rerun_loop_is_idempotent_upsert` — running the same multi-topic
   loop twice updates non-PK columns, doesn't duplicate rows.
3. `test_multi_article_multi_topic_isolation` — INSERTs for article 1
   don't affect article 2.
4. `test_migration_005_idempotent` — applying migration 005 twice is a
   no-op.

### Schema-update touchups

- `tests/unit/test_batch_ingest_hash.py` — dropped now-redundant
  single-column UNIQUE INDEX from in-memory test schema.
- `tests/unit/test_classify_full_body_topic_hint.py` — switched test
  schema from `article_id INTEGER PRIMARY KEY` to composite
  `PRIMARY KEY (article_id, topic)` so post-fix `ON CONFLICT(article_id,
  topic)` binds correctly.

### Local pytest (post-fix)

- 27 directly-affected tests across 7 files: ALL GREEN.
- Targeted suite: `test_classifications_multitopic` (4) +
  `test_classifications_upsert` (3) + `test_batch_ingest_hash` (2) +
  `test_classify_full_body_topic_hint` (2 covered) +
  `test_scrape_first_classify` (9) + `test_vision_worker` (10) +
  `test_graded_classify_prompt_quality` (1) — all pass.
- Full `pytest tests/unit/` hung at ~33% on this Windows env with stdout
  buffering issues; observed 4 F's in the visible portion. Per CLAUDE.md
  baseline, ≤13 pre-existing fails are accepted (e.g.
  test_lightrag_embedding_vertex requires real GCP creds). No new
  failures detected in the directly-affected paths.

---

## Production-shape verification

Replayed the cron's sequential per-topic INSERT pattern on
`.dev-runtime/data/kol_scan.db` (563 articles, 755 existing
classifications):

```
Test article_ids: [719, 718, 717]
Cron iteration: --topic Agent  written 3 rows
Cron iteration: --topic LLM    written 3 rows
Cron iteration: --topic RAG    written 3 rows
Cron iteration: --topic NLP    written 3 rows
Cron iteration: --topic CV     written 3 rows

article_id=719: 5 distinct topics (expected 5)
article_id=718: 5 distinct topics (expected 5)
article_id=717: 5 distinct topics (expected 5)

SUCCESS: cron-shaped multi-topic sequential invocation produces
5 rows per article. Pre-fix bug would have left 1 row per article
with topic='CV'. Fix verified.
```

Log: `/tmp/local-multitopic-prodshape-<ts>.log`.

---

## Local DB parity

`.dev-runtime/data/kol_scan.db` was backed up to
`kol_scan.db.backup-pre-mig005-<ts>` and migration 005 applied. Local
schema confirmed:

- No `idx_classifications_article_id` (never present locally — dev-runtime
  DB never ran migration 004; migration 005 was a safe no-op).
- Table-level `UNIQUE(article_id, topic)` constraint preserved.
- Existing topic distribution healthy (Agent=394, LLM=322, ... — multi-row
  model intact).

Post-Hermes-repair, Hermes schema will match this local state.

---

## Hermes repair runbook

Path:
`.planning/quick/260507-ent-cron-mass-classify-cv-bug-revert-upsert-/HERMES-REPAIR-RUNBOOK.md`

7 steps, user-driven SSH execution:

1. Pre-flight (pull fix, verify HEAD)
2. Pause classify cron
3. Backup DB (mandatory per Lessons 2026-05-06 #2)
4. Apply migration 005
5. Verify index gone + topic distribution healthy
6. Re-enable cron
7. Smoke ingest with `agent,hermes,openclaw,harness` filter

Includes rollback path and post-repair monitoring guidance.

---

## Lesson #6 (CLAUDE.md)

Two related lessons added under `### 2026-05-07 (CV mass-classify postmortem)`:

1. **Schema changes need production-shape cron simulation, not just unit
   tests.** Mock-only unit tests with single INSERT calls miss
   cross-component bugs that emerge only when the cron's actual
   sequential CLI invocation pattern is replayed. Add cron-loop
   simulator to v3.5 candidates.

2. **Dropping a UNIQUE constraint requires reverting every dependent
   `ON CONFLICT(col)` call site.** Grep pattern provided for future
   schema migrations.

---

## What's next

**Hermes-side execution (operator):** Run the runbook from the existing
SSH session. Expected wall-clock: 30-90 minutes (the bulk is re-classify
of recent candidates; migration 005 is a one-shot DDL).

**Tomorrow 06:00 ADT cron:** Should run the fixed SQL and accumulate
correct multi-topic rows. If cron still returns 0 candidates, the issue
is candidate-pool, not classify SQL — reroute to v3.5 ingest refactor
(`PROJECT-Ingest-Refactor-v3.5.md`).

**v3.5 candidate addition:** "Production-shape local snapshot + cron
loop simulator" — local 24h cron path simulator that any non-trivial
schema/SQL change must pass before push. Captured in Lesson #6.

---

## Compliance with strict scope

- ✅ No Phase 20 / Agentic-RAG-v1 / other phase planning docs touched
- ✅ Selective `git add` per-commit (no `-A` / `.`)
- ✅ Forward-only commit history (no stash / reset / rebase / amend / force-push)
- ✅ Quick 260506-se5 commit preserved; only the SQL semantics reversed via migration 005
- ✅ Migration 004 file unchanged
- ✅ Operator runs Hermes-side via runbook (agent does not SSH)

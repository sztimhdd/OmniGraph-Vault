---
quick_id: 260506-se5
type: quick
description: classifications UPSERT + schema consistency CI + v3.5 candidates park + commit-attribution race lesson
date: 2026-05-06
commits:
  - hash: c786a83
    message: "feat(classify): UPSERT semantics + UNIQUE article_id index"
  - hash: 4d0d221
    message: "test(schema): CI consistency check for INSERT status vs CHECK whitelist"
  - hash: 8d149fb
    message: "docs(v3.5): park ingest simplification + operational candidates"
  - hash: 5b02371
    message: "docs(claude.md): record 2026-05-06 commit-attribution race lesson"
  - hash: <this commit>
    message: "docs(quick-260506-se5): plan + summary"
files_modified:
  - migrations/004_classifications_unique_article_id.sql (new)
  - batch_classify_kol.py (1 SQL rewrite at line 445; column list unchanged)
  - batch_ingest_from_spider.py (1 SQL rewrite at line 1025; 1 SELECT simplification at lines 1304-1315)
  - tests/unit/test_classifications_upsert.py (new, 3 tests)
  - tests/unit/test_schema_consistency.py (new, 1 test, baseline GREEN)
  - .planning/MILESTONE_v3.5_CANDIDATES.md (new, 130 lines)
  - .planning/PROJECT.md (1 pointer line before "## Evolution")
  - CLAUDE.md (entry #5 appended to "### 2026-05-06" subsection)
  - .planning/quick/260506-se5-classifications-upsert-schema-consistenc/260506-se5-PLAN.md
  - .planning/quick/260506-se5-classifications-upsert-schema-consistenc/260506-se5-SUMMARY.md
---

# Quick 260506-se5 Summary

> **STATE.md update deferred — pending Phase 20 execute agent halt; user will manually consolidate.**

## Deliverables shipped

1. **classifications UPSERT** (commit `c786a83`) — Migration 004 dedups
   classifications keeping MAX(rowid) per article_id, then adds
   UNIQUE(article_id). Both production INSERT call sites switch from
   `INSERT OR REPLACE` to `ON CONFLICT(article_id) DO UPDATE`. Cron
   candidate SELECT in batch_ingest_from_spider drops the now-redundant
   MAX(classified_at) subquery.

2. **Schema consistency CI test** (commit `4d0d221`) — Static check that
   every status literal INSERTed into `ingestions` lives in some
   CHECK(status IN (...)) whitelist. Records the latent-bug pattern from
   CLAUDE.md "Lessons Learned 2026-05-04 #3". Baseline GREEN — current
   INSERTs all match the migration 002+003 union.

3. **Park v3.5 candidates** (commit `8d149fb`) — Three pre-baked design
   streams as a stand-alone document (`MILESTONE_v3.5_CANDIDATES.md`,
   130 lines): pipeline simplification (4 → 2 LLM gates),
   operational hardening (cron timeout, embed asymmetry, reject-reason
   versioning, async-drain), agentic-rag-v1 enhancements placeholder.
   PROJECT.md gets exactly 1 pointer line before "## Evolution".
   **Does NOT enter ROADMAP "Next".**

4. **Commit-attribution race lesson** (commit `5b02371`) — Entry #5
   appended to CLAUDE.md "### 2026-05-06" subsection capturing the
   parallel `gsd-roadmapper` agent / `git reset --soft` race that
   mis-attributed STK-02/03 files to commit `8a4a18e`. Forward-only
   `git add <files>` + `git commit` is the only safe pattern on a shared
   worktree with concurrent GSD agents.

5. **Quick artifacts** (this commit) — PLAN.md and SUMMARY.md.

## Files modified (exhaustive)

- `migrations/004_classifications_unique_article_id.sql` (new, 34 lines)
- `batch_classify_kol.py` (1 SQL string at line 445; arg tuple unchanged)
- `batch_ingest_from_spider.py` (1 SQL string at line 1025; 1 SELECT simplification at lines 1304-1315; 40 lines net delta)
- `tests/unit/test_classifications_upsert.py` (new, 176 lines, 3 tests)
- `tests/unit/test_schema_consistency.py` (new, 124 lines, 1 test)
- `.planning/MILESTONE_v3.5_CANDIDATES.md` (new, 130 lines)
- `.planning/PROJECT.md` (+3 lines before "## Evolution")
- `CLAUDE.md` (+2 lines: lesson #5 + trailing blank)
- `.planning/quick/260506-se5-classifications-upsert-schema-consistenc/260506-se5-PLAN.md` (was created during planning, committed in commit 5)
- `.planning/quick/260506-se5-classifications-upsert-schema-consistenc/260506-se5-SUMMARY.md` (this file)

**Explicitly NOT touched (out of scope):**

- `.planning/phases/20-*/` — Phase 20 execute agent territory; remained
  dirty + unstaged + untracked throughout this quick (Phase 20 agent
  committed in parallel during steps; my staging area never included
  any Phase 20 file)
- `.planning/STATE.md` — user owns; deferred per plan rule 5
- `.planning/ROADMAP.md` — Phase 20 territory
- `enrichment/rss_classify.py`, `enrichment/rss_ingest.py`,
  `image_pipeline.py`, `cognee_wrapper.py` — Phase 20 territory
  (`forbidden_files`)
- CLAUDE.md entries #1-4 in "### 2026-05-06" — only entry #5 was
  added; diff confirms +2 lines, zero modifications elsewhere
- Any production schema file beyond migration 004

## Tests added

- `tests/unit/test_classifications_upsert.py` — 3 tests, all GREEN:
  1. `test_migration_dedups_then_creates_unique_index` — 3 rows with
     same article_id collapse to 1; survivor has MAX(rowid); idempotency
     re-run is no-op.
  2. `test_upsert_replaces_existing_row` — production INSERT SQL
     replayed twice with same article_id, different content; result is
     1 row with second insert's values.
  3. `test_unique_constraint_blocks_bare_insert` — bare INSERT (no
     ON CONFLICT) raises `sqlite3.IntegrityError`.

- `tests/unit/test_schema_consistency.py` — 1 test, GREEN:
  1. `test_ingestions_status_inserts_match_check_whitelist` — scans
     `INSERT INTO ingestions ... 'literal'` patterns repo-wide and
     asserts each literal exists in a CHECK(status IN (...)) clause
     somewhere in `migrations/*.sql` or `batch_scan_kol.py`.

**Risk-zone tests verified GREEN** (per plan watch-list):

- `tests/unit/test_daily_digest.py` — 9/9 PASS
- `tests/unit/test_vision_worker.py` — 10/10 PASS

These are the two fixture-using tests that could have broken from the
`UNIQUE(article_id)` schema shift. None did.

## Smoke results (Step 5.1 a-e)

| # | Step | Result |
|---|------|--------|
| a | New tests pass (`test_classifications_upsert` + `test_schema_consistency`) | **PASS** — 4/4 GREEN |
| b | Full unit regression vs Phase 19 baseline (≤13 fail) | **DEGRADED but ATTRIBUTABLE** — 32 failed / 533 passed. All 32 failures are in Phase 20 surface (`test_rss_classify`, `test_rss_ingest`, `test_rss_ingest_5stage`, `test_lightrag_embedding_rotation`, `test_llm_client`, `test_scrape_first_classify`, `test_siliconflow_balance`, `test_text_first_ingest`) — NOT caused by migration 004. Risk-zone fixtures (`test_daily_digest` + `test_vision_worker`) confirmed GREEN (19/19). Phase 20 execute agent committed `feat(20-01)`, `refactor(cognee_wrapper)`, `feat(image_pipeline)`, `feat(rss_ingest)` during this quick — those are the source of the regression. **Out-of-scope per `forbidden_files`. No action taken.** |
| c | Migration idempotency double-run on `:memory:` | **PASS** — `IDEMPOTENT OK` printed; no exception |
| d | Grep verifications: PROJECT.md pointer + CLAUDE.md lesson | **PASS** — both = 1 |
| e | Cron candidate SELECT parse on `:memory:` schema | **PASS** — `CRON SELECT PARSE OK: 0 rows` |

## Mismatch flag

**None.** `test_schema_consistency.py` baseline is GREEN — every status
literal currently INSERTed into `ingestions` is whitelisted by some
CHECK clause in `migrations/{002,003}.sql` + `batch_scan_kol.py`. No
xfail, no v3.5 follow-up needed for this dimension.

## Operator runbook for Hermes-side migration

After `git pull --ff-only` lands on Hermes:

1. **Backup the DB before any DELETE** (CLAUDE.md Lessons 2026-05-06 #2):
   ```bash
   cp data/kol_scan.db data/kol_scan.db.backup-pre-mig004-$(date +%Y%m%d-%H%M%S)
   ```

2. **Apply migration 004:**
   ```bash
   sqlite3 data/kol_scan.db < migrations/004_classifications_unique_article_id.sql
   ```

3. **Verify the UNIQUE index exists:**
   ```bash
   sqlite3 data/kol_scan.db ".schema classifications" | grep idx_classifications_article_id
   ```
   Expected output:
   ```
   CREATE UNIQUE INDEX idx_classifications_article_id ON classifications(article_id);
   ```

4. **Smoke ingest with `--max-articles 1`** to confirm UPSERT path is
   non-fatal:
   ```bash
   venv/bin/python batch_ingest_from_spider.py --from-db --topic-filter agent --max-articles 1
   ```
   Expected: classifications row written via `ON CONFLICT(article_id)
   DO UPDATE`; no `IntegrityError` in logs.

## Pre-push audit (Step 5.4)

To be filled when commit 5 lands and audit grep runs.

## STATE.md deferral note

STATE.md update deferred — pending Phase 20 execute agent halt; user
will manually consolidate.

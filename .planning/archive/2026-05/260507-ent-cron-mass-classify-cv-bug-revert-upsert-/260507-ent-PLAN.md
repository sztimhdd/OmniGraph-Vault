# Quick 260507-ent — Plan

**Description:** Emergency fix: revert UPSERT to `ON CONFLICT(article_id, topic)`
for multi-topic loop compatibility.

**Triggered by:** 2026-05-07 08:29 ADT cron mass-classified all 653 articles
as `topic='CV'` after Quick 260506-se5 (commit `c786a83`) introduced
single-column `ON CONFLICT(article_id) DO UPDATE SET topic=excluded.topic`.

**Created:** 2026-05-07
**Status:** Ready for execution (executed inline in same session)

---

## Tasks

### Task 1 — Code fix + tests + migration 005

**Files:**
- `batch_classify_kol.py` (modify INSERT at line 447)
- `batch_ingest_from_spider.py` (modify INSERT at line 1028 — second call site)
- `migrations/005_drop_article_id_unique_index.sql` (new)
- `tests/unit/test_classifications_multitopic.py` (new — 4 regression tests)
- `tests/unit/test_batch_ingest_hash.py` (drop now-redundant unique index in test schema)
- `tests/unit/test_classify_full_body_topic_hint.py` (switch to composite PRIMARY KEY)

**Action:** Revert both production INSERT call sites from
`ON CONFLICT(article_id) DO UPDATE SET topic=excluded.topic, ...` to
`ON CONFLICT(article_id, topic) DO UPDATE SET ...` (no topic overwrite).
Migration 005 drops `idx_classifications_article_id` (added by migration 004);
table-level `UNIQUE(article_id, topic)` from the original schema becomes
the binding uniqueness constraint again. New regression test verifies
multi-topic sequential INSERT produces N rows per article, not 1 row
with the last topic.

**Verify:**
- `pytest tests/unit/test_classifications_multitopic.py -v` → 4/4 GREEN
- `pytest tests/unit/test_classifications_upsert.py tests/unit/test_batch_ingest_hash.py tests/unit/test_classify_full_body_topic_hint.py` → all GREEN
- `git status -sb` clean post-commit, in sync with origin

**Done:** Commit + push fix to origin/main.

---

### Task 2 — Production-shape multi-topic test

**Files:** `.dev-runtime/data/kol_scan.db` (read + write test rows)

**Action:** Replay the cron's sequential per-topic INSERT pattern against
the actual production-shape local DB (563 articles, 755 existing
classifications). 5 sequential INSERTs (one per test topic) for 3 test
articles, using the EXACT post-fix SQL.

**Verify:** 15 distinct (article_id, topic) rows produced (5 topics × 3
articles), zero topic overwrites. Pre-fix bug would have produced 3 rows
all with `topic='CV'`.

**Done:** Test log saved to `/tmp/local-multitopic-prodshape-<ts>.log`.

---

### Task 3 — Hermes repair runbook

**Files:** `.planning/quick/260507-ent-cron-mass-classify-cv-bug-revert-upsert-/HERMES-REPAIR-RUNBOOK.md`

**Action:** Write a 7-step runbook for user-driven SSH execution: pull
fix → pause cron → backup DB → apply migration 005 → re-classify → re-enable
cron → smoke ingest. Include rollback path and post-repair monitoring
guidance.

**Verify:** Runbook covers all transition steps; agent does NOT SSH
itself (operator runs each step manually).

**Done:** Commit + push runbook.

---

### Task 4 — Local DB schema parity

**Files:** `.dev-runtime/data/kol_scan.db` (apply migration 005 — no-op
locally because dev-runtime DB never had migration 004 applied)

**Action:** Backup local DB, apply migration 005, verify table-level
`UNIQUE(article_id, topic)` is the only uniqueness constraint left and
no `idx_classifications_article_id` exists.

**Verify:** Local schema matches expected post-Hermes-repair state
(no article_id-only UNIQUE).

**Done:** Schema confirmed parity.

---

### Task 5 — CLAUDE.md Lesson #6

**Files:** `CLAUDE.md` (append "### 2026-05-07" subsection to Lessons Learned)

**Action:** Two related lessons:
1. Schema/SQL changes need production-shape cron-invocation simulation
   before push (mock-only unit tests miss cross-component bugs).
2. Dropping a UNIQUE constraint must include grep + revert of every
   `ON CONFLICT(col)` call site that depends on it.

**Verify:** Lessons read cleanly, link to v3.5 candidate (cron-loop
simulator).

**Done:** Commit + push.

---

## Strict scope (per user prompt)

- DO NOT modify Phase 20 / Agentic-RAG-v1 / other phase planning docs
- DO NOT use `git stash` / `git reset` / `git rebase` / `git commit --amend` / `git push --force` / `git add -A` / `git add .`
- DO NOT SSH to Hermes (operator runs runbook)
- DO NOT delete Quick 260506-se5 commit (history preserved)
- DO NOT modify migration 004 file (already pushed; migration 005 reverses it)

## must_haves

- Multi-topic loop produces N rows per article (verified by both unit
  test and production-shape simulation).
- Migration 005 drops `idx_classifications_article_id` cleanly and is
  idempotent.
- Both production call sites use `ON CONFLICT(article_id, topic)` so the
  schema parity holds after migration 005 deploys.
- Hermes runbook has rollback path that backs up the DB before any
  destructive DDL.
- Lesson #6 captures both root cause (sequential cron CLI) and
  preventative grep pattern.

## Trust boundary with operator

This quick task ships **everything except the Hermes-side execution**.
The operator runs the runbook from an existing SSH session; agent's
delivery ends at "runbook + fix commit pushed to origin".

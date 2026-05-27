---
phase: quick-260507-lai
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - lib/article_filter.py
  - tests/unit/test_article_filter.py
  - batch_ingest_from_spider.py
  - .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md
autonomous: true
requirements:
  - V35-FOUND-01  # Layer 1/2 placeholder interface (`lib/article_filter.py`)
  - V35-FOUND-02  # Bypass `_classify_full_body` in ingest loop, wire to layers
  - V35-FOUND-03  # Simplify candidate SQL — drop classifications join
  - V35-FOUND-04  # Hermes operator runbook for cron cleanup + cutover
must_haves:
  truths:
    - "lib/article_filter.py exposes layer1_pre_filter() and layer2_full_body_score(), both returning FilterResult(passed=True, ...) placeholders"
    - "tests/unit/test_article_filter.py — 7 tests pass, pinning the placeholder interface contract"
    - "batch_ingest_from_spider.py ingest loop calls layer1 BEFORE scrape and layer2 AFTER scrape; no longer calls _classify_full_body"
    - "_build_topic_filter_query SELECT no longer joins classifications and no longer references c.depth_score / c.topic"
    - "min_depth gate code path is removed from ingest loop (layers don't return depth)"
    - "_classify_full_body, _call_deepseek_fullbody, _build_fullbody_prompt function bodies are NOT deleted (only ingest-loop call is removed)"
    - "--min-depth and --topic-filter CLI flags retained for back-compat (silently ignored)"
    - "Dry-run smoke (--dry-run --max-articles 1) reaches layer1/layer2 placeholder code without crashing"
    - "HERMES-DEPLOY.md exists with cron-remove + cron-edit + resume + smoke runbook"
  artifacts:
    - path: "lib/article_filter.py"
      provides: "Layer 1/2 placeholder filter API (always-pass)"
      exports: ["FilterResult", "layer1_pre_filter", "layer2_full_body_score"]
    - path: "tests/unit/test_article_filter.py"
      provides: "Interface-contract tests pinning placeholder behavior"
      contains: "FilterResult"
    - path: "batch_ingest_from_spider.py"
      provides: "Ingest loop wired to placeholder filters; classify gate bypassed"
    - path: ".planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md"
      provides: "Hermes operator runbook for v3.5 foundation cutover"
  key_links:
    - from: "batch_ingest_from_spider.py (ingest loop)"
      to: "lib.article_filter.layer1_pre_filter"
      via: "import + call before scrape"
      pattern: "from lib.article_filter import"
    - from: "batch_ingest_from_spider.py (ingest loop)"
      to: "lib.article_filter.layer2_full_body_score"
      via: "call after scrape, before LightRAG ainsert"
      pattern: "layer2_full_body_score"
    - from: "tests/unit/test_article_filter.py"
      to: "lib.article_filter"
      via: "import + assert FilterResult fields"
      pattern: "from lib.article_filter import"
---

<objective>
Wire the v3.5 Ingest Refactor **foundation**: introduce always-pass Layer 1/2
placeholder filters and bypass the broken `_classify_full_body` gate in
`batch_ingest_from_spider.py`. This unblocks the KOL ingest path after this
morning's UPSERT-vs-multi-topic-loop disaster (commit `c786a83` reverted in
`428b16f`).

Purpose:
- The `classifications` table mass-corruption (all 653 rows → topic='CV') has
  already been rolled back, but the structural risk remains: any future
  classify-gate change can re-block ingest. Permanently bypassing the gate +
  introducing a Layer 1/2 interface lets future quicks add real filtering
  logic without touching the ingest control flow.
- This is **foundation only** — Layer 1/2 are pure placeholders that always
  pass. Real filter logic is deferred to follow-up quicks.

Output:
- `lib/article_filter.py` — new module with `FilterResult` dataclass + two
  placeholder functions
- `tests/unit/test_article_filter.py` — 7 contract tests
- `batch_ingest_from_spider.py` — ingest loop bypasses `_classify_full_body`,
  candidate SQL drops the classifications JOIN
- `HERMES-DEPLOY.md` — operator runbook for cron cleanup + cutover
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/PROJECT-Ingest-Refactor-v3.5.md
@CLAUDE.md
@batch_ingest_from_spider.py

<interfaces>
<!-- Key facts the executor needs from the codebase. Use these directly. -->

## Existing function — `_build_topic_filter_query` (NOT `_build_candidate_sql`)

The user spec calls it `_build_candidate_sql` but the actual function name in
`batch_ingest_from_spider.py:1293` is **`_build_topic_filter_query`**. Use the
real name. Signature is unchanged:

```python
def _build_topic_filter_query(topics: list[str]) -> tuple[str, tuple[str, ...]]:
```

Current SQL (lines 1312-1320) — to be replaced:

```python
sql = f"""
    SELECT a.id, a.title, a.url, acc.name, c.depth_score, a.body, a.digest
    FROM articles a
    JOIN accounts acc ON a.account_id = acc.id
    LEFT JOIN classifications c ON a.id = c.article_id
    WHERE (c.topic IS NULL OR ({placeholders}))
      AND a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
    ORDER BY a.id
"""
normalized = tuple(f"%{t.strip().lower()}%" for t in topics)
return sql, normalized
```

New SQL (no LIKE placeholders, no classifications join, no `c.depth_score`):

```python
sql = """
    SELECT a.id, a.title, a.url, acc.name, a.body, a.digest
    FROM articles a
    JOIN accounts acc ON a.account_id = acc.id
    WHERE a.id NOT IN (SELECT article_id FROM ingestions WHERE status = 'ok')
    ORDER BY a.id
"""
return sql, ()
```

The column-tuple shape changes: `c.depth_score` is removed. **Find every call
site that unpacks the row tuple** (`grep _build_topic_filter_query` and
follow-up `cursor.fetchall()` consumers in the same file) and remove
`depth_score` from the unpack. If the variable was only used by the deleted
min_depth gate, this is safe.

## Existing call site — `_classify_full_body` invocation

Located in `ingest_from_db` (around lines 1325+). The current pattern:
1. Call `_classify_full_body(...)` which writes a classifications row and
   returns `{"depth": int, "topics": list, "rationale": str}` or `None`.
2. If `None` → skip (fail-closed per D-10.04).
3. Compare `depth < min_depth` → skip if too shallow.
4. (Optional) topic-filter check — already mostly handled by the candidate
   SQL.
5. Proceed to LightRAG `ainsert`.

After this quick:
- Step 1 is replaced by `layer1_pre_filter(title, summary=digest, content_length=None)`
  BEFORE the scrape.
- After scrape returns `body`, step 1.5 is `layer2_full_body_score(article_id, title, body)`.
- Steps 2/3/4 are removed (placeholders always pass; no depth returned).
- Step 5 unchanged.

## Existing skipped-row recording

There is already a "write ingestions row with status='skipped'" code path in
the ingest loop (used by current min_depth/topic skips). Reuse it — do NOT
add a `reason` column to the `ingestions` table. The skip reason is
log-only via `logger.info`.

## Hermes deployment context

Three obsolete cron jobs to remove (per spec):
- `daily-classify-kol` (id: b50ec39b889f)
- `daily-enrich` (id: fc768319e0c1)
- `rss-classify` (id: c7ded378de8f)

One cron to optionally edit:
- `daily-ingest` (id: 2b7a8bee53e0) — drop `--topic-filter` from command since
  it's now silently ignored.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create lib/article_filter.py + tests/unit/test_article_filter.py</name>
  <files>
    lib/article_filter.py
    tests/unit/test_article_filter.py
  </files>
  <behavior>
    `lib/article_filter.py` exports:
    - `FilterResult` — `@dataclass(frozen=True)` with fields: `passed: bool`, `reason: str`
      (and any additional fields the spec's verbatim content provides — match exactly).
    - `layer1_pre_filter(title: str, summary: str, content_length: int | None) -> FilterResult`
      — placeholder; always returns `FilterResult(passed=True, reason="placeholder: layer1 always-pass")`.
    - `layer2_full_body_score(article_id: int, title: str, body: str) -> FilterResult`
      — placeholder; always returns `FilterResult(passed=True, reason="placeholder: layer2 always-pass")`.

    `tests/unit/test_article_filter.py` exports 7 tests pinning the contract:
    - layer1 returns FilterResult
    - layer1 passes for arbitrary input (placeholder)
    - layer1 reason mentions "placeholder"
    - layer2 returns FilterResult
    - layer2 passes for arbitrary input (placeholder)
    - layer2 reason mentions "placeholder"
    - FilterResult is frozen (assigning to .passed raises FrozenInstanceError)

    The verbatim content of both files is reproduced in the user spec (parent prompt
    `<task_specification>`). Use the verbatim content exactly — no edits, no additions.
  </behavior>
  <action>
    Step 1 — Create `lib/article_filter.py`:
    - Reproduce the verbatim content from the parent prompt's `<task_specification>` section
      (the spec section references "Verbatim content provided in spec — see prompt context").
    - File MUST use `from dataclasses import dataclass` and define `@dataclass(frozen=True) class FilterResult`.
    - Both functions return `FilterResult` instances; both placeholders set `passed=True`.
    - Type-annotate ALL parameters and return types per Python coding-style rules.

    Step 2 — Create `tests/unit/test_article_filter.py`:
    - Reproduce the 7-test verbatim content from the parent prompt's spec.
    - Use `pytest` (no fixtures needed for pure placeholders).
    - Imports: `from lib.article_filter import FilterResult, layer1_pre_filter, layer2_full_body_score`
      and `from dataclasses import FrozenInstanceError` (or `import pytest` for `pytest.raises`).

    Step 3 — Verify GREEN locally before committing:
    ```bash
    DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/unit/test_article_filter.py -v
    ```
    Expect: 7 passed.

    Step 4 — Commit in TWO atomic commits (per spec ordering — lib first, then tests):
    ```bash
    git add lib/article_filter.py
    git commit -m "feat(filter): lib/article_filter.py with Layer 1/2 placeholders"

    git add tests/unit/test_article_filter.py
    git commit -m "test(filter): pin Layer 1/2 placeholder interface contract"
    ```
    Use ONLY explicit `git add <file>` — never `git add -A` / `git add .` (CLAUDE.md Lesson #5).
    Never `git stash` / `reset` / `rebase` / `amend` / `force-push` (Lesson #5).

    NOTES (locked decisions, do not redesign):
    - This is V35-FOUND-01. Layer 1/2 are placeholders that always pass; real logic comes later.
    - Per CLAUDE.md HIGHEST PRIORITY PRINCIPLES, do NOT add features beyond the spec
      (no logging, no metrics, no real filter logic, no kwargs beyond the locked signatures).
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/unit/test_article_filter.py -v</automated>
  </verify>
  <done>
    - `lib/article_filter.py` exists, exports `FilterResult`, `layer1_pre_filter`, `layer2_full_body_score`
    - `tests/unit/test_article_filter.py` — 7 tests pass
    - Two commits in `git log --oneline -3`: feat(filter) before test(filter)
    - No `pytest` failures introduced in `tests/unit/` baseline
  </done>
</task>

<task type="auto">
  <name>Task 2: Patch batch_ingest_from_spider.py — bypass classify, simplify SQL</name>
  <files>
    batch_ingest_from_spider.py
  </files>
  <action>
    Implements V35-FOUND-02 (bypass classify) and V35-FOUND-03 (simplify SQL).

    Step 1 — Rewrite `_build_topic_filter_query` (~line 1293-1322):
    - Function name UNCHANGED (`_build_topic_filter_query`).
    - Function signature UNCHANGED: `(topics: list[str]) -> tuple[str, tuple[str, ...]]`.
    - Replace SQL body with the simplified form (see <interfaces> block above):
      no `LEFT JOIN classifications`, no `c.depth_score`, no `c.topic` predicate,
      no `placeholders` interpolation.
    - Return `sql, ()` (empty params tuple).
    - Add docstring note: "v3.5 (260507-lai): topics parameter retained for API
      compat but no longer used in SQL — Layer 1/2 placeholder filters in lib/article_filter.py
      replace the classifications gate."
    - Delete the `placeholders = ...` and `normalized = ...` local-variable lines —
      the function no longer needs them.

    Step 2 — Find the `_build_topic_filter_query` consumer (likely in `ingest_from_db`
    around line 1325+, or a helper that unpacks the row tuple). The row tuple changes from
    `(id, title, url, acc.name, c.depth_score, body, digest)` to
    `(id, title, url, acc.name, body, digest)`. **Update every unpack** to remove
    `depth_score`. Use `grep -n "_build_topic_filter_query" batch_ingest_from_spider.py`
    and trace fetchall consumers from there.

    Step 3 — Patch the ingest loop's `_classify_full_body` call site:
    - Add at top of file (or near other `lib.*` imports): `from lib.article_filter import layer1_pre_filter, layer2_full_body_score`
    - Locate the `_classify_full_body(...)` call in the ingest loop.
    - Replace per the spec pattern (reproduced below — use exactly):

      ```python
      # v3.5 Layer 1: cheap pre-filter (placeholder = always pass)
      layer1 = layer1_pre_filter(
          title=title,
          summary=digest,        # WeChat digest is 200-char summary
          content_length=None,   # WeChat doesn't have length until scrape
      )
      if not layer1.passed:
          logger.info("layer1 reject id=%s reason=%s", article_id, layer1.reason)
          # reuse existing skipped-record path (status='skipped'); reason log-only
          # ... (use the existing pattern in this file — do NOT invent a new one)
          continue

      # scrape body (existing scrape logic — unchanged)
      body = await _scrape_body(url, ...)  # use whatever the current call shape is

      # v3.5 Layer 2: full-body LLM scoring (placeholder = always pass)
      layer2 = layer2_full_body_score(
          article_id=article_id,
          title=title,
          body=body,
      )
      if not layer2.passed:
          logger.info("layer2 reject id=%s reason=%s", article_id, layer2.reason)
          # reuse existing skipped-record path
          continue

      # proceed with LightRAG ainsert (existing — unchanged)
      ```
    - Delete the `min_depth` gate code path (since layers don't return depth).
    - Delete any topic-filter post-classify check (already redundant — placeholder always passes).
    - **DO NOT** delete `_classify_full_body`, `_call_deepseek_fullbody`, or
      `_build_fullbody_prompt` function bodies. Only stop calling them.
    - **DO NOT** add an `ingestions.reason` column. **DO NOT** modify `ingestions` schema.
    - **DO NOT** add new CLI flags. The `--min-depth` and `--topic-filter` flags
      stay (silently ignored).

    Step 4 — Smoke test (dry-run interface integrity):
    ```bash
    DEEPSEEK_API_KEY=dummy OMNIGRAPH_BASE_DIR=.dev-runtime/ \
      PYTHONPATH=. venv/Scripts/python batch_ingest_from_spider.py \
      --from-db --max-articles 1 --dry-run \
      2>&1 | head -30
    ```
    Expect: doesn't crash; candidate SQL parses OK; layer1/layer2 placeholder logging
    visible OR dry-run exits cleanly before scrape — either is acceptable for a
    placeholder always-pass smoke. **Do not** require a successful scrape; the
    interface integrity check is the goal.

    Step 5 — Run full unit-test baseline to confirm no new failures:
    ```bash
    DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/unit/ --tb=short -q
    ```
    Expect: ≤13 pre-existing failures baseline, NO new failures introduced by this patch.
    If new failures appear, diagnose and fix before committing.

    Step 6 — Commit (atomic, single file):
    ```bash
    git status -sb  # self-check: only batch_ingest_from_spider.py modified
    git add batch_ingest_from_spider.py
    git commit -m "$(cat <<'EOF'
    feat(ingest): bypass _classify_full_body — wire to placeholder Layer 1/2 (v3.5 foundation)

    - _build_topic_filter_query: drop classifications join, drop c.depth_score
      (topics param retained for API compat, silently ignored)
    - ingest loop: replace _classify_full_body call with layer1_pre_filter (pre-scrape)
      + layer2_full_body_score (post-scrape); both placeholder always-pass
    - delete min_depth gate (layers don't return depth)
    - retain _classify_full_body / _call_deepseek_fullbody / _build_fullbody_prompt
      function bodies (only call removed; future quick can delete)
    - retain --min-depth and --topic-filter CLI flags (back-compat, silently ignored)

    Unblocks KOL ingest path after 2026-05-07 cron classifications mass-corruption
    (Quick 260506-se5 reverted in 428b16f). Real Layer 1/2 logic deferred to follow-up
    quick — see .planning/PROJECT-Ingest-Refactor-v3.5.md Phase B+C.
    EOF
    )"
    ```
    Use ONLY explicit `git add <file>` — never `git add -A` / `.`. Never `git stash`/
    `reset`/`rebase`/`amend`/`force-push` (CLAUDE.md Lesson #5).

    LOCKED CONSTRAINTS (do not redesign):
    - Do NOT touch other modules (enrichment/*, batch_classify_kol.py, batch_scan_kol.py).
    - Do NOT change schema. Do NOT add columns. Do NOT add migrations.
    - Do NOT modify Cognee logic. Do NOT modify Vision Cascade.
    - Do NOT write real LLM call code in lib/article_filter.py.
    - The `_classify_full_body` SQL INSERT to `classifications` stays untouched
      since the function is retained (per spec Change 1c). It will simply no
      longer execute because nothing calls it.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy OMNIGRAPH_BASE_DIR=.dev-runtime/ PYTHONPATH=. venv/Scripts/python batch_ingest_from_spider.py --from-db --max-articles 1 --dry-run 2>&1 | head -30 && DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/unit/ --tb=short -q</automated>
  </verify>
  <done>
    - `_build_topic_filter_query` SQL no longer contains "classifications" or "c.depth_score"
    - `grep -n "_classify_full_body(" batch_ingest_from_spider.py` shows the function
      definition still present but NO call sites in the ingest loop
    - `grep -n "from lib.article_filter import" batch_ingest_from_spider.py` returns 1 hit
    - `grep -n "layer1_pre_filter\|layer2_full_body_score" batch_ingest_from_spider.py`
      returns ≥2 hits (one call each in the ingest loop)
    - Dry-run smoke doesn't crash; pytest baseline shows no new failures
    - One commit added: `feat(ingest): bypass _classify_full_body ...`
  </done>
</task>

<task type="auto">
  <name>Task 3: Create HERMES-DEPLOY.md operator runbook</name>
  <files>
    .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md
  </files>
  <action>
    Implements V35-FOUND-04. Reproduce the verbatim ~30-line runbook content from
    the parent prompt's `<task_specification>` section. Required content blocks:

    1. **Pre-flight** — pull latest, confirm commit hashes for Tasks 1+2 are present:
       ```bash
       cd ~/OmniGraph-Vault && git pull --ff-only && git log --oneline -5
       ```
    2. **Cron remove (3 obsolete crons)** — exact `cronjob remove <id>` commands for:
       - `daily-classify-kol` (id: `b50ec39b889f`)
       - `daily-enrich` (id: `fc768319e0c1`)
       - `rss-classify` (id: `c7ded378de8f`)
    3. **Optional cron edit** — for `daily-ingest` (id: `2b7a8bee53e0`):
       drop `--topic-filter agent,hermes,openclaw,harness` from command (now silently
       ignored, but cleaner to remove). Provide the explicit `cronjob update` command.
    4. **Resume daily-ingest** — re-enable / verify next-fire timestamp.
    5. **Optional smoke test** — 1-article dry-run on Hermes side to confirm the
       layer1/layer2 placeholders are reachable in production.
    6. **Rollback** — if anything goes wrong, the `git revert <commit>` sequence to
       restore pre-v3.5-foundation state.

    Follow the verbatim content as locked in spec. No new instructions. No new commands.

    Commit:
    ```bash
    git add .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md
    git commit -m "docs(deploy): v3.5 foundation Hermes deploy runbook"
    ```

    The final `docs(quick-260507-lai): plan + summary` commit is handled by the
    quick workflow itself — DO NOT pre-create it here.
  </action>
  <verify>
    <automated>test -f .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md && grep -q "b50ec39b889f" .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md && grep -q "fc768319e0c1" .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md && grep -q "c7ded378de8f" .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md && grep -q "2b7a8bee53e0" .planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/HERMES-DEPLOY.md</automated>
  </verify>
  <done>
    - HERMES-DEPLOY.md exists at the spec'd path
    - Contains all four cron IDs (3 to remove, 1 to edit)
    - Contains pre-flight, remove, edit, resume, smoke, rollback sections
    - One commit added: `docs(deploy): v3.5 foundation Hermes deploy runbook`
  </done>
</task>

</tasks>

<verification>
After all 3 tasks complete:

```bash
# Commit chain (4 atomic commits — quick workflow adds the 5th plan/summary commit later)
git log --oneline -5
# Expect (most recent first):
#  docs(deploy): v3.5 foundation Hermes deploy runbook
#  feat(ingest): bypass _classify_full_body — wire to placeholder Layer 1/2 (v3.5 foundation)
#  test(filter): pin Layer 1/2 placeholder interface contract
#  feat(filter): lib/article_filter.py with Layer 1/2 placeholders
#  ... (older)

# Unit tests GREEN — Layer 1/2 contract
DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/unit/test_article_filter.py -v
# Expect: 7 passed

# No regression in unit baseline
DEEPSEEK_API_KEY=dummy venv/Scripts/python -m pytest tests/unit/ --tb=short -q
# Expect: ≤13 pre-existing failures baseline; NO new failures

# Interface integrity smoke
DEEPSEEK_API_KEY=dummy OMNIGRAPH_BASE_DIR=.dev-runtime/ \
  PYTHONPATH=. venv/Scripts/python batch_ingest_from_spider.py \
  --from-db --max-articles 1 --dry-run 2>&1 | head -30
# Expect: doesn't crash; SQL parses; layer1/layer2 placeholder reached or dry-run exit

# Code-shape sanity checks
grep -c "_classify_full_body(" batch_ingest_from_spider.py
# Expect: 1 (the function definition only — no call sites)

grep -c "from lib.article_filter import" batch_ingest_from_spider.py
# Expect: 1

grep -c "layer1_pre_filter\|layer2_full_body_score" batch_ingest_from_spider.py
# Expect: ≥2

# Schema untouched (sanity)
git diff HEAD~4 -- batch_ingest_from_spider.py | grep -E "^\+.*CREATE TABLE|ALTER TABLE|DROP TABLE"
# Expect: empty (no schema changes)
```
</verification>

<success_criteria>
- [ ] `lib/article_filter.py` exists with `FilterResult`, `layer1_pre_filter`, `layer2_full_body_score`
- [ ] `tests/unit/test_article_filter.py` — 7 tests pass
- [ ] `_build_topic_filter_query` SQL no longer joins `classifications`
- [ ] Ingest loop in `batch_ingest_from_spider.py` calls `layer1_pre_filter` (pre-scrape)
      and `layer2_full_body_score` (post-scrape) — no `_classify_full_body` call
- [ ] `_classify_full_body` / `_call_deepseek_fullbody` / `_build_fullbody_prompt` function
      bodies still present (only call removed)
- [ ] `--min-depth` and `--topic-filter` CLI flags retained (silently ignored)
- [ ] No schema changes (no CREATE/ALTER/DROP TABLE, no new migrations)
- [ ] HERMES-DEPLOY.md exists with cron remove/edit/resume/smoke/rollback runbook
- [ ] 4 atomic commits in `git log --oneline -5` (5th = plan/summary, added by workflow)
- [ ] Dry-run smoke + pytest baseline both green
</success_criteria>

<output>
After completion, the quick workflow itself creates the SUMMARY artifact. This
plan does NOT pre-create the summary file — that's the workflow's job at the
final commit step.
</output>

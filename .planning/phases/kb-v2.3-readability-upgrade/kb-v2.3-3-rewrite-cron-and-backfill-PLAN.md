---
phase: kb-v2.3-readability-upgrade
plan: 3
type: execute
wave: 3
depends_on: [kb-v2.3-1, kb-v2.3-2]
files_modified:
  - scripts/rewrite_body_cron.py
  - scripts/translate_body_cron.py
  - tests/unit/test_rewrite_body_cron.py
autonomous: false
requirements: [CRON-REWRITE, FORK-X-WIRING, RETRANSLATE-RESET, BACKFILL-572]
must_haves:
  truths:
    - "rewrite_body_cron.py is idempotent (WHERE body_rewritten IS NULL), serial, mirrors translate_body_cron structure; --dry-run lists candidates without LLM call or UPDATE"
    - "translate_body_cron reads COALESCE(body_rewritten, body) so the clean rewritten text is what gets translated (Fork X)"
    - "After backfill, all ~572 displayed articles have non-NULL body_rewritten (SQL count == displayed count)"
    - "body_translated/title_translated are reset to NULL ONLY for rows that now have body_rewritten, so the translation cron re-translates from clean source"
    - "A spot-checked row's body_translated derives from the clean body_rewritten after re-translation"
  artifacts:
    - path: "scripts/rewrite_body_cron.py"
      provides: "Async serial DeepSeek rewrite cron mirroring translate_body_cron; --dry-run + --limit; commit-per-row UPDATE of body_rewritten + rewritten_at"
      exports: ["main"]
      min_lines: 120
    - path: "scripts/translate_body_cron.py"
      provides: "Fork-X: COALESCE(body_rewritten, body) AS body in both UNION ALL subqueries"
      contains: "COALESCE(body_rewritten, body) AS body"
    - path: "tests/unit/test_rewrite_body_cron.py"
      provides: "Behavior-anchor tests RW-1..RW-5 on seeded in-memory DB + mocked LLM"
      min_lines: 100
  key_links:
    - from: "scripts/rewrite_body_cron.py:_rewrite_one_row"
      to: "lib/rewrite.py:rewrite_body_with_deepseek"
      via: "lazy import inside per-row function (dry-run never imports DeepSeek chain)"
      pattern: "from lib.rewrite import rewrite_body_with_deepseek"
    - from: "scripts/translate_body_cron.py:_select_candidate_rows"
      to: "body_rewritten column"
      via: "COALESCE(body_rewritten, body) AS body in both articles + rss_articles subqueries"
      pattern: "COALESCE\\(body_rewritten, body\\) AS body"
    - from: "re-translation reset step"
      to: "translation cron re-run"
      via: "UPDATE ... SET body_translated=NULL, title_translated=NULL WHERE body_rewritten IS NOT NULL"
      pattern: "body_translated = NULL"
---

<objective>
Ship the rewrite cron, wire Fork X, run the full 572-article backfill on Aliyun, and re-translate the ~464 already-translated rows from clean source. This is the THREE-step ordered Stage 1c sequence: (a) rewrite backfill -> body_rewritten; (b) reset body_translated for rewritten rows; (c) translation cron re-translates from clean body_rewritten (via COALESCE SELECT).

Purpose: This is where the clean data actually gets produced and reaches both the source-language display (via plan 02's read path) and the English side (via the kept translation cron reading the rewritten column). It depends on plan 01's validated rewrite function and plan 02's schema+read-path.

Output: All ~572 displayed articles have clean body_rewritten; the translation cron sources from the clean column; the 464 dirty-sourced translations are regenerated clean. Deployed and run on Aliyun.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-CONTEXT.md
@.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md
@scripts/translate_body_cron.py
@lib/rewrite.py

<interfaces>
<!-- Exact code to mirror / modify. Line numbers verified 2026-07-02. -->

scripts/translate_body_cron.py — pieces to COPY VERBATIM:
```python
# lines 48-49 — DEEPSEEK_API_KEY guard BEFORE any lib.* import
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
# lines 52-54 — sys.path bootstrap
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# lines 62-78 — _resolve_db_path() (BASE_DIR/data/kol_scan.db, fallback BASE_DIR/kol_scan.db)
# lines 81-103 — _setup_logging() (dual sink, UTF-8, force=True); change filename to rewrite-body-cron-YYYYMMDD.log
# lines 251-280 — _run() serial loop shape (for row in rows: await _one_row(...))
# lines 299-306 — main() = asyncio.run(_run(args, logger))
```

scripts/translate_body_cron.py current SELECT to MODIFY (lines 119-141, verified):
```python
    sql = """
        SELECT id, table_name, title, body, body_translated, title_translated
          FROM (
            SELECT id, 'articles' AS table_name, title, body,
                   body_translated, title_translated, layer2_at
              FROM articles
             WHERE layer1_verdict = 'candidate' AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND (body_translated IS NULL OR title_translated IS NULL)
            UNION ALL
            SELECT id, 'rss_articles' AS table_name, title, body,
                   body_translated, title_translated, layer2_at
              FROM rss_articles
             WHERE layer1_verdict = 'candidate' AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               AND (body_translated IS NULL OR title_translated IS NULL)
          )
         ORDER BY layer2_at ASC, id ASC
         LIMIT ?
    """
```

lib/rewrite.py (from plan 01):
```python
async def rewrite_body_with_deepseek(title: str, body: str) -> str | None: ...
# Returns cleaned body, OR None when: LLM empty, OR URL-set diff valve rejects.
```

DATA-07 displayed-corpus filter (== 572): layer1_verdict='candidate' AND layer2_verdict='ok' AND body IS NOT NULL AND body != ''
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write scripts/rewrite_body_cron.py + behavior-anchor test (RW-1..RW-5)</name>
  <files>scripts/rewrite_body_cron.py, tests/unit/test_rewrite_body_cron.py</files>
  <read_first>
    - scripts/translate_body_cron.py (FULL file — the skeleton to mirror: guard 48-49, path 52-54, _resolve_db_path 62-78, _setup_logging 81-103, SELECT 106-141, per-row 144-248, _run 251-280, main 299-306)
    - lib/rewrite.py (the function to lazy-import in the per-row body)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md (Finding 1 complete skeleton, Finding 8 behavior-anchor RW-1..RW-5 table, Architecture Patterns rewrite_body_cron.py skeleton, Pitfalls 2 & 7)
    - CLAUDE.md (Behavior-Anchor Harness section — 3-signal test; RESEARCH Finding 8 concludes rewrite cron QUALIFIES on signals b+c, so this test file is MANDATORY)
    - tests/unit/test_ingest_from_db_orchestration.py (the canonical behavior-anchor pattern: seeded in-memory DB, assert post-conditions + mocked-callable args)
  </read_first>
  <behavior>
    - RW-1 (dry-run): --dry-run runs the SELECT but makes NO LLM call and NO UPDATE. Seed 3 rows body_rewritten IS NULL; mock rewrite_body_with_deepseek asserted not-called; all 3 rows still body_rewritten IS NULL post-run.
    - RW-2 (idempotency): rows with body_rewritten NOT NULL are skipped by the WHERE guard. Seed 2 rows (1 populated, 1 NULL); assert exactly 1 LLM call; populated row unchanged.
    - RW-3 (per-row failure isolated): mock LLM raises on row 1, returns a string on row 2; assert row 1 body_rewritten NULL, row 2 populated (broad except logs + continues).
    - RW-4 (--limit N): seed 5 eligible rows, run --limit 2; assert exactly 2 LLM calls.
    - RW-5 (UPDATE persists both cols): run on 1 row returning a valid string; assert body_rewritten AND rewritten_at both non-NULL post-run.
    In-memory DB fixture must include body_rewritten TEXT + rewritten_at DATETIME (mirrors conftest update in plan 02).
  </behavior>
  <action>
Create `scripts/rewrite_body_cron.py` mirroring translate_body_cron.py. Concrete requirements:

1. Copy VERBATIM from translate_body_cron.py: the `os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")` guard (Pitfall 2), the sys.path bootstrap (52-54), `_resolve_db_path()` (62-78), `_setup_logging()` (81-103) — change ONLY the log filename to `.scratch/rewrite-body-cron-YYYYMMDD.log`.

2. `DEFAULT_LIMIT = 10`. Optional oversized-body guard `MAX_REWRITE_CHARS = 30000` (RESEARCH Open Question 3): if `len(body) > MAX_REWRITE_CHARS`, skip with logger.warning and leave body_rewritten NULL (avoid truncation risk on the 154K-char max article) — count as "skipped_oversize".

3. `_select_candidate_rows(conn, limit)` — SELECT `id, table_name, title, body` with the idempotency guard `AND body_rewritten IS NULL` (RESEARCH Finding 1). Both articles + rss_articles via UNION ALL, ORDER BY layer2_at ASC, id ASC, LIMIT ?. Tuple shape `(id, table_name, title, body)`.

4. `async def _rewrite_one_row(row, conn, dry_run, logger) -> str`:
   - unpack `art_id, table, title, body`.
   - if dry_run: log "[dry-run] WOULD rewrite id=..." and return "dry_run" (NO import of lib.rewrite).
   - oversized guard -> return "skipped_oversize".
   - lazy import: `from lib.rewrite import rewrite_body_with_deepseek` (Pitfall 2 — inside the function).
   - try/except around `result = await rewrite_body_with_deepseek(title or "", body)`; on exception log WARNING "leaving NULL" and set result=None (Pitfall 7 — serial, no gather).
   - if result: `conn.execute(f"UPDATE {table} SET body_rewritten = ?, rewritten_at = ? WHERE id = ?", (result, datetime.now(timezone.utc).isoformat(), art_id))` then `conn.commit()`; log "rewrite ok id=.. in=.. out=.."; return "ok". Else return "fail" (result None includes valve-reject -> body_rewritten stays NULL -> body fallback, no regression).
   - `# noqa: S608` on the f-string UPDATE (table is a SELECT literal, not user input — same as translate cron).

5. `_run(args, logger)` — open sqlite3.connect (read-write, NOT ?mode=ro), SELECT candidates, serial `for row in rows: outcome = await _rewrite_one_row(...)` with a tally dict; log summary; close in finally. `_parse_args` with `--dry-run` and `--limit` (DEFAULT_LIMIT). `main()` = `asyncio.run(_run(...))`.

Create `tests/unit/test_rewrite_body_cron.py` implementing RW-1..RW-5 against a seeded in-memory sqlite DB (include body_rewritten + rewritten_at columns). Mock rewrite_body_with_deepseek via monkeypatch on `lib.rewrite`. Anchor on observable post-conditions (DB row state + mock call count), NOT internal call shape.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_rewrite_body_cron.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")' scripts/rewrite_body_cron.py` == 1 and it appears BEFORE any `from lib` / `import lib` line (grep -n, confirm line order).
    - `grep "body_rewritten IS NULL" scripts/rewrite_body_cron.py` matches (idempotency guard).
    - `grep "from lib.rewrite import rewrite_body_with_deepseek" scripts/rewrite_body_cron.py` matches AND is inside `_rewrite_one_row` (lazy — grep -n, confirm indentation/position after the dry_run early-return).
    - `grep "SET body_rewritten = ?, rewritten_at = ?" scripts/rewrite_body_cron.py` matches.
    - `grep -c "asyncio.gather" scripts/rewrite_body_cron.py` == 0 (serial only — Pitfall 7).
    - `venv/Scripts/python.exe scripts/rewrite_body_cron.py --dry-run --limit 3` runs without importing DeepSeek chain and without any UPDATE (dry-run).
    - `venv/Scripts/python.exe -m pytest tests/unit/test_rewrite_body_cron.py -v` — RW-1..RW-5 all pass.
  </acceptance_criteria>
  <done>rewrite_body_cron.py mirrors translate_body_cron (guard, path, DB resolve, logging, serial loop, commit-per-row); idempotent WHERE body_rewritten IS NULL; lazy rewrite import; oversized guard; behavior-anchor RW-1..RW-5 green.</done>
</task>

<task type="auto">
  <name>Task 2: Fork-X wiring — COALESCE(body_rewritten, body) in translate_body_cron.py SELECT</name>
  <files>scripts/translate_body_cron.py</files>
  <read_first>
    - scripts/translate_body_cron.py (lines 119-141 — the SELECT with the two UNION ALL subqueries; the tuple unpacking at ~157; the per-row call at ~184)
    - .planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-RESEARCH.md (Finding 7 CRITICAL Fork-X wiring — the exact 3-line change; Pitfall 4)
  </read_first>
  <action>
Surgical change to `scripts/translate_body_cron.py:_select_candidate_rows` ONLY. In BOTH UNION ALL subqueries (articles ~line 122-123 and rss_articles ~line 130-131), replace the bare `body,` in the inner SELECT column list with `COALESCE(body_rewritten, body) AS body,`:

Articles subquery:
```sql
    SELECT id, 'articles' AS table_name, title,
           COALESCE(body_rewritten, body) AS body,
           body_translated, title_translated, layer2_at
      FROM articles
     WHERE ...  -- unchanged
```
RSS subquery (identical pattern):
```sql
    SELECT id, 'rss_articles' AS table_name, title,
           COALESCE(body_rewritten, body) AS body,
           body_translated, title_translated, layer2_at
      FROM rss_articles
     WHERE ...  -- unchanged
```
The outer SELECT (`SELECT id, table_name, title, body, ...`) stays UNCHANGED — the `AS body` alias means the tuple unpacking at line ~157 and `translate_body_with_deepseek_tavily(title, body, ...)` at ~184 get the coalesced value with ZERO downstream change (RESEARCH Finding 7). Do NOT touch the WHERE clauses, the per-row function, or lib/translate.py.

This must deploy so that any NEW article gets its English derived from clean body_rewritten (falls back to dirty body transparently when body_rewritten is still NULL).
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/ -k translate -v; venv/Scripts/python.exe -c "import ast,sys; ast.parse(open('scripts/translate_body_cron.py').read()); print('parse ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "COALESCE(body_rewritten, body) AS body" scripts/translate_body_cron.py` == 2 (both subqueries).
    - The outer `SELECT id, table_name, title, body, body_translated, title_translated` line is UNCHANGED (grep matches it verbatim).
    - No change to the WHERE clauses (still `(body_translated IS NULL OR title_translated IS NULL)`).
    - No change to lib/translate.py (git diff shows scripts/translate_body_cron.py only for this task).
    - `python -c "ast.parse(...)"` confirms the file parses.
  </acceptance_criteria>
  <done>Both translate_body_cron SELECT subqueries read COALESCE(body_rewritten, body) AS body; outer SELECT and per-row path unchanged; file parses; Fork X wired.</done>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 3: Run the 572-article backfill on Aliyun (deploy cron + guarded re-translation reset + verify counts)</name>
  <files>scripts/rewrite_body_cron.py, scripts/translate_body_cron.py (Aliyun deploy targets)</files>
  <action>
This is a human-action checkpoint gating a large one-time paid-API run on prod data with an ordered 3-step sequence. The executor performs the schema apply + 3 ordered backfill steps documented in <how-to-verify> via Bash SSH to Aliyun (per aliyun_vitaclaw_ssh.md), but PAUSES for operator cost/timing confirmation before firing the 572-row batch. No batch is launched until the operator responds to the resume-signal.
  </action>
  <read_first>
    - scripts/rewrite_body_cron.py (the cron to deploy + run)
    - scripts/translate_body_cron.py (Fork-X wired — the translate cron that re-translates)
    - kb-v2.3-CONTEXT.md (<success_criteria> Stage 1 Backfill gate; <specifics> corpus counts 572 = KOL 463 + RSS 109, 464 already-translated)
    - MEMORY.md: aliyun_vitaclaw_ssh.md (Aliyun SSH alias aliyun-vitaclaw — the deploy target), aliyun_ssh_manual_trigger_env.md (MUST `set -a; source /root/.hermes/.env; set +a;` before manual trigger, else DEEPSEEK_API_KEY=dummy -> silent 401)
    - CANONICAL Aliyun DB path (verified 2026-07-02): `/root/OmniGraph-Vault/data/kol_scan.db`. This is the exact path kb-api uses (`KB_DB_PATH` in the systemd unit) and what `_resolve_db_path()` resolves to on Aliyun. Use it verbatim in every raw `sqlite3` command below — do NOT guess a path. (Note: `/root/.hermes/omonigraph-vault/kol_scan.db` is a symlink to this same file and returns identical data today, but a raw sqlite3 command should target the canonical file directly rather than depend on the symlink persisting.)
    - CLAUDE.md Principle #7 (Claude owns deployments — sync/run via CLI yourself, do not outsource) BUT this is marked checkpoint because it is a large one-time paid-API run on prod data with an ordered 3-step sequence — pause for the operator to confirm cost + timing before firing the 572-row batch.
  </read_first>
  <what-built>
    rewrite_body_cron.py (idempotent DeepSeek rewrite cron) and the Fork-X COALESCE wiring in translate_body_cron.py, both proven by unit tests. This step deploys them to Aliyun and executes the ordered 3-step backfill against the live 572-article corpus.
  </what-built>
  <how-to-verify>
    Executor performs (via Bash SSH to Aliyun per aliyun_vitaclaw_ssh.md; run migration 009 first, then the 3 ordered steps):

    STEP 0 (schema): apply migration 009 on Aliyun: `venv/bin/python kb/data/migrations/run_migrations.py` — confirm body_rewritten + rewritten_at exist on both tables (PRAGMA table_info).

    STEP A (rewrite backfill): sync repo to Aliyun; run in batches with env sourced:
    `set -a; source /root/.hermes/.env; set +a; venv/bin/python scripts/rewrite_body_cron.py --limit 100` — repeat until 0 candidates. Monitor `.scratch/rewrite-body-cron-*.log` for ok/fail/skipped_oversize tally + valve-reject warnings.
    VERIFY A: `sqlite3 /root/OmniGraph-Vault/data/kol_scan.db "SELECT (SELECT COUNT(*) FROM articles WHERE body_rewritten IS NOT NULL) + (SELECT COUNT(*) FROM rss_articles WHERE body_rewritten IS NOT NULL);"` approaches 572 (minus any legitimate valve-rejects/oversize skips — log the exact accepted count + reject count). Use the canonical DB path (see <read_first>).

    STEP B (guarded re-translation reset — LOCKED, only rows we cleaned):
    `UPDATE articles SET body_translated = NULL, title_translated = NULL WHERE body_rewritten IS NOT NULL;`
    `UPDATE rss_articles SET body_translated = NULL, title_translated = NULL WHERE body_rewritten IS NOT NULL;`
    The `WHERE body_rewritten IS NOT NULL` guard ensures we NEVER blow away a translation for a row we did not clean (CONTEXT.md re-translation section). Log affected row counts.

    STEP B.5 (FORK-X DEPLOY GATE — MANDATORY, blocks STEP C): before triggering ANY re-translation, confirm the Task-2 COALESCE change actually reached the Aliyun copy of translate_body_cron.py. If the repo sync missed Task 2, STEP C would re-translate 464 articles from the DIRTY `body` undetected. Run on Aliyun:
    `ssh aliyun-vitaclaw "grep -c 'COALESCE(body_rewritten, body) AS body' ~/OmniGraph-Vault/scripts/translate_body_cron.py"`
    This MUST print `2` (both UNION ALL subqueries). If it prints 0 or 1: STOP — re-sync the repo to Aliyun (git pull / databricks-style sync) and re-run the gate. Do NOT proceed to STEP C until the gate returns exactly 2. (Also confirm the running/scheduled translate cron uses this file, not an archived copy.)

    STEP C (re-translate from clean source — ONLY after STEP B.5 gate returns 2): run the Fork-X-wired translate cron until 0 candidates:
    `set -a; source /root/.hermes/.env; set +a; venv/bin/python scripts/translate_body_cron.py --limit 100` — the COALESCE SELECT now sources from clean body_rewritten.
    VERIFY C: spot-check 2-3 rows — their body_translated must derive from the clean body_rewritten (compare a distinctive cleaned phrase; confirm no residual boilerplate markers 关注公众号 in body_translated).
  </how-to-verify>
  <resume-signal>Type "approved" after the operator confirms cost/timing, then executor runs the 3 ordered steps and reports final counts (body_rewritten count, valve-reject count, re-translated count) + the spot-check evidence. Confirm "backfill complete, counts verified" to unblock Stage 2.</resume-signal>
  <verify>
    <automated>ssh aliyun-vitaclaw "sqlite3 /root/OmniGraph-Vault/data/kol_scan.db \"SELECT (SELECT COUNT(*) FROM articles WHERE body_rewritten IS NOT NULL) + (SELECT COUNT(*) FROM rss_articles WHERE body_rewritten IS NOT NULL) AS rewritten_total;\"" && ssh aliyun-vitaclaw "grep -c 'COALESCE(body_rewritten, body) AS body' ~/OmniGraph-Vault/scripts/translate_body_cron.py"</automated>
  </verify>
  <done>Migration 009 applied on Aliyun; body_rewritten non-NULL count == (572 - logged valve-rejects - oversize-skips); guarded re-translation reset touched only cleaned rows; translate cron re-ran to 0 candidates; spot-checked body_translated is clean-sourced; all counts + evidence cited in SUMMARY.</done>
  <acceptance_criteria>
    - Migration 009 applied on Aliyun (PRAGMA table_info shows body_rewritten + rewritten_at both tables).
    - Post-backfill: body_rewritten non-NULL count == (572 - valve_rejects - oversize_skips), with valve_rejects + oversize_skips explicitly logged and reasonable (< 30% total per plan 01 gate).
    - Re-translation reset touched ONLY rows with body_rewritten IS NOT NULL (affected-row count logged == body_rewritten count).
    - FORK-X DEPLOY GATE (STEP B.5) PASSED before STEP C: on Aliyun, `grep -c 'COALESCE(body_rewritten, body) AS body' ~/OmniGraph-Vault/scripts/translate_body_cron.py` == 2. STEP C is gated on this returning exactly 2 — re-translation MUST NOT run against a stale (pre-Fork-X) translate_body_cron.py. Evidence (the grep output == 2) cited in SUMMARY.
    - After STEP C: 0 candidates remain in the translate cron; spot-checked body_translated derives from clean source (no 关注公众号 boilerplate residue).
    - All evidence (counts, log excerpts, spot-check) cited in the plan SUMMARY.
  </acceptance_criteria>
</task>

</tasks>

<verification>
- rewrite_body_cron.py idempotent + serial + commit-per-row; RW-1..RW-5 green; --dry-run makes no LLM call/UPDATE.
- translate_body_cron COALESCE(body_rewritten, body) in both subqueries; downstream unchanged.
- Aliyun: migration 009 applied; ~572 articles have non-NULL body_rewritten (minus logged valve/oversize); guarded reset touched only cleaned rows; translate cron re-ran; spot-checked translation is clean-sourced.
</verification>

<success_criteria>
CONTEXT.md Stage 1 gates satisfied:
- "Cron: rewrite_body_cron.py is idempotent (WHERE body_rewritten IS NULL), has a batch limit, mirrors translate_body_cron structure; a dry-run lists candidates without error."
- "Backfill: all ~572 displayed articles have non-NULL body_rewritten after backfill (SQL count == displayed count, minus logged valve-rejects); translation cron subsequently reads body_rewritten (spot-checked row's body_translated derives from the clean version)."
- Re-translation reset ran as an explicit guarded ordered step (only rows with body_rewritten).
</success_criteria>

<output>
After completion, create `.planning/phases/kb-v2.3-readability-upgrade/kb-v2.3-3-rewrite-cron-and-backfill-SUMMARY.md`.

STEADY-STATE GAP — MANDATORY ISSUES.md entry at close-out (Warning 5 / CLAUDE.md Principle #10): the backfill + re-translation only cleans the articles that exist at run time. New articles ingested AFTER the backfill but BEFORE the next rewrite-cron run have `body_rewritten` NULL, so the Fork-X COALESCE falls back to the DIRTY `body` and the translation cron produces a dirty-sourced `body_translated` for them (which the `WHERE body_translated IS NULL` guard then never regenerates). CONTEXT.md defers steady-state automation, but this gap MUST NOT be lost. The executor surfaces it in the SUMMARY close-out report; the ORCHESTRATOR (not the executor) transcribes a P3 (🟢 future-scope) row into `.planning/ISSUES.md`: "kb-v2.3 steady-state — new articles between rewrite-cron runs get dirty-sourced translation until the rewrite cron runs; wire a rewrite-cron systemd timer (or fold into daily-ingest) + a periodic re-translation sweep for freshly-rewritten rows." Update ISSUES.md `Last updated:` header.
</output>

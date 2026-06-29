---
phase: quick-260629-gvl
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - batch_scan_kol.py
  - tests/unit/test_scan_last_scanned.py
autonomous: true
requirements: [ISSUES-73]
gap_closure: false

must_haves:
  truths:
    - "accounts.last_scanned_at column added idempotently (PRAGMA-guarded ALTER, safe on re-run)"
    - "Every SUCCESSFUL scan attempt (ok=True) stamps last_scanned_at — INCLUDING 0-article accounts"
    - "A FAILED attempt (ok=False / cookie-dead) does NOT stamp last_scanned_at"
    - "Staleness ordering (max_accounts path) sorts by last_scanned_at: NULL-first, then oldest-attempted, then name"
    - "A just-scanned empty account rotates to the BACK of the staleness queue (not pinned to head)"
    - "Default path (max_accounts is None) stays byte-behavior-identical: SELECT ORDER BY name + random.shuffle"
    - "The 4 existing tests in test_scan_max_accounts.py still pass (no regression)"
  artifacts:
    - path: "batch_scan_kol.py"
      provides: "last_scanned_at column + stamp-on-success + staleness re-ordering"
      contains: "last_scanned_at"
    - path: "tests/unit/test_scan_last_scanned.py"
      provides: "Behavior-anchor tests for stamp + ordering + no-stamp-on-failure"
      contains: "def test_"
  key_links:
    - from: "run() scan loop"
      to: "accounts.last_scanned_at"
      via: "UPDATE ... SET last_scanned_at = datetime('now','localtime') WHERE name = ? when ok is True"
      pattern: "last_scanned_at\\s*=\\s*datetime"
    - from: "staleness SELECT (max_accounts path)"
      to: "accounts.last_scanned_at"
      via: "ORDER BY (last_scanned_at IS NULL) DESC, last_scanned_at ASC, name ASC"
      pattern: "last_scanned_at IS NULL"
---

<objective>
Fix ISSUES #73 — KOL scan staleness coverage. The 260626-jgp `--max-accounts` staleness
path orders accounts by their newest ARTICLE `scanned_at`. Genuinely-empty accounts have NO
article rows → `MAX(a.scanned_at) IS NULL` forever → permanently pinned to the staleness head.
They get re-attempted every batch, never make progress, and starve other accounts.

Fix: track a per-account `last_scanned_at` stamped on every successful scan ATTEMPT (even when
0 articles return), and order the staleness queue by that column instead of article recency.
After an empty account is attempted once, its `last_scanned_at` becomes recent → it rotates to
the back, letting the queue advance.

Purpose: 8 non-CV dormant accounts (科学空间 / 腾讯AI Lab / 夕小瑶智能体 / NewBeeNLP / ShowMeAI /
陈宇明 / 漫士沉思录 / 大猿搬砖简记) stop pinning the staleness head; the queue rotates fairly.
Output: modified `batch_scan_kol.py` + a new behavior-anchor test file.

NOTE: This plan covers Phase 1 (code) ONLY as an executor task. Phase 2 (Aliyun data delete of
the 5 CV-cluster accounts + 226 orphan CV articles) is an OPERATOR runbook executed by the
orchestrator via SSH — documented in <operator_phase_2> below. The executor does NOT SSH Aliyun
and does NOT touch any production DB.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@batch_scan_kol.py
@tests/unit/test_scan_max_accounts.py

<interfaces>
<!-- Exact current shape — use directly, no codebase exploration needed. -->

batch_scan_kol.init_db(db_path: Path) -> sqlite3.Connection
  - Has an idempotent migration block (lines ~132-142) with a local helper:
        def _ensure_column(c, table, column, type_def) -> None:
            cols = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}")
  - Currently calls:
        _ensure_column(conn, "articles", "content_hash", "TEXT")
        _ensure_column(conn, "articles", "enriched", "INTEGER DEFAULT 0")
        _ensure_column(conn, "ingestions", "enrichment_id", "TEXT")
        conn.commit()
  - accounts schema: id, name (UNIQUE), wechat_id, fakeid (UNIQUE), tags, source,
    category, notes, created_at. NO last_scanned_at yet.

batch_scan_kol.scan_account(conn, name, fakeid, days_back, max_articles)
    -> tuple[bool, int, int, bool]   # (ok, new, skipped, session_invalid)
  - ok=True  → WeChat API call succeeded (even if 0 new articles).
  - ok=False + session_invalid=True → ret=200003 (cookie dead).

batch_scan_kol.run(days_back, max_articles, account_filter, resume,
                   daily=False, summary_json=False, max_accounts=None) -> None
  - Default path (max_accounts is None, lines ~245-256):
        rows = conn.execute("SELECT name, fakeid FROM accounts ORDER BY name").fetchall()
        ... random.shuffle(rows)        # KEEP BYTE-IDENTICAL
  - Staleness path (max_accounts is not None, lines ~262-272) — CURRENT (to be replaced):
        rows = conn.execute("""
            SELECT acc.name, acc.fakeid
            FROM accounts acc
            LEFT JOIN articles a ON a.account_id = acc.id
            GROUP BY acc.id
            ORDER BY (MAX(a.scanned_at) IS NULL) DESC, MAX(a.scanned_at) ASC, acc.name ASC
        """).fetchall()
        ...
        rows = rows[:max_accounts]
  - Scan loop (line ~296):
        for i, (name, fakeid) in enumerate(rows, 1):
            ...
            ok, new, skipped, session_invalid = scan_account(conn, name, fakeid, days_back, max_articles)
            ...
            if ok:
                scanned_count += 1
                ...
            else:
                failed_count += 1
                ...
</interfaces>

<sibling_test_conventions>
tests/unit/test_scan_max_accounts.py establishes the harness pattern this new test MUST mirror:
  - os.environ.setdefault("DEEPSEEK_API_KEY", "dummy") + ("GEMINI_API_KEY", "dummy") BEFORE
    `import batch_scan_kol` (defuses import-time key coupling).
  - _seed_db(tmp_db, accounts_with_articles): conn = batch_scan_kol.init_db(tmp_db) (real schema),
    INSERT OR IGNORE accounts + articles, commit, close.
  - monkeypatch.setattr(batch_scan_kol, "DB_PATH", tmp_db)
  - monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)
  - monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)   # prevents resurrection
  - monkeypatch.setattr(batch_scan_kol, "scan_account", mock.MagicMock(return_value=(True,0,0,False)))
  - monkeypatch.setattr(batch_scan_kol.time, "sleep", lambda *_a, **_k: None)
  - Selection order pinned via scan_account call_args: scanned_names = [c.args[1] for c in m.call_args_list]
    (scan_account signature: (conn, name, fakeid, days_back, max_articles) → name is args[1]).
</sibling_test_conventions>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add last_scanned_at column, stamp on success, re-order staleness queue (+ behavior tests)</name>
  <files>batch_scan_kol.py, tests/unit/test_scan_last_scanned.py</files>
  <behavior>
    Write tests/unit/test_scan_last_scanned.py FIRST (RED), mirroring test_scan_max_accounts.py
    harness conventions. Four observable contracts:

    - test_stamp_on_success_even_zero_articles:
        Seed 3 accounts (no articles). monkeypatch scan_account → (True, 0, 0, False).
        run(max_accounts=3). Then open a fresh sqlite3 connection to tmp_db and assert
        ALL 3 accounts have a non-NULL last_scanned_at. (Core fix: a 0-article success
        still stamps.)

    - test_no_stamp_on_failure:
        Seed 3 accounts. monkeypatch scan_account → (False, 0, 0, True) (cookie dead).
        run(max_accounts=3) — NOTE: 3/3 failures = 100% session-invalid, which trips the
        SESSION_INVALID_THRESHOLD sys.exit(2) path. Wrap run() in pytest.raises(SystemExit)
        OR seed enough success accounts to stay under 30% — simplest: assert via
        pytest.raises(SystemExit) then still query the DB afterward (the UPDATEs, if any,
        committed before exit). Assert last_scanned_at stays NULL for all 3 (a failed
        attempt must not mark fresh). Keeping it simple: catch SystemExit, then assert NULL.

    - test_staleness_orders_by_last_scanned_at:
        Seed 4 accounts: 1 with last_scanned_at = NULL (never attempted), 3 with distinct
        last_scanned_at values (set directly via UPDATE in the seed). scan_account →
        (True,0,0,False). run(max_accounts=2). Assert the 2 names handed to scan_account
        (via c.args[1]) are [NULL-account, then oldest-stamped] in that order.

    - test_just_scanned_rotates_to_back:
        Fold into the above OR a 4th test: seed 3 accounts ALL with last_scanned_at set,
        one of them VERY recent (e.g. '2026-06-29 12:00:00') and two older. run(max_accounts=2).
        Assert the very-recent account is NOT among the 2 scanned (it sorted to the back).

    Run the new file — it MUST fail (no last_scanned_at column / no stamp / old ordering).
    THEN implement Task actions to make all pass. Keep test_scan_max_accounts.py green.
  </behavior>
  <action>
    Implement three surgical changes in batch_scan_kol.py, then add the test file.

    (1) ADD COLUMN — in init_db(), inside the idempotent migration block, add ONE line
        AFTER the existing three _ensure_column calls and BEFORE the existing conn.commit()
        (line ~141-142):
            _ensure_column(conn, "accounts", "last_scanned_at", "TEXT")
        TEXT, nullable, no default. NULL = never attempted. Idempotent (PRAGMA-guarded).

    (2) STAMP ON SUCCESS — in run()'s scan loop (line ~306-319), inside the `if ok:` branch
        (the success branch, alongside scanned_count += 1), add:
            conn.execute(
                "UPDATE accounts SET last_scanned_at = datetime('now','localtime') WHERE name = ?",
                (name,),
            )
            conn.commit()
        Stamp ONLY when ok is True (API call succeeded, regardless of new/skipped count —
        INCLUDING 0-article accounts). Do NOT stamp in the `else:` (failure) branch — a
        cookie-dead run must not reset everyone's staleness and mask the problem. Match the
        existing commit cadence (the loop already commits inside _import_articles; an explicit
        commit here keeps the stamp durable per-account).

    (3) RE-ORDER STALENESS SELECT — replace the current LEFT JOIN/GROUP BY query (lines
        ~262-268, the `else:` / max_accounts-is-not-None branch) with a direct column read:
            rows = conn.execute("""
                SELECT name, fakeid FROM accounts
                ORDER BY (last_scanned_at IS NULL) DESC, last_scanned_at ASC, name ASC
            """).fetchall()
        Keep the surrounding code IDENTICAL: the `if not rows: logger.error(...); sys.exit(1)`
        guard stays, and `rows = rows[:max_accounts]` truncation stays. Returns the same
        (name, fakeid) 2-tuple the loop consumes. Version-safe: boolean (IS NULL) ordering,
        NO `NULLS FIRST` keyword. Update the inline comment to reflect ordering by
        last_scanned_at (attempt time) instead of MAX(article scanned_at).

    DO NOT touch the default path (max_accounts is None): SELECT ... ORDER BY name +
    random.shuffle MUST stay byte-identical.

    Then write tests/unit/test_scan_last_scanned.py per <behavior>, mirroring the
    test_scan_max_accounts.py harness (env seed before import; init_db real schema;
    monkeypatch DB_PATH / load_env / init_accounts / scan_account / time.sleep; assert via
    call_args[1] for selection order and via a fresh DB query for stamp post-conditions).

    Discipline: forward-only commit, explicit `git add batch_scan_kol.py
    tests/unit/test_scan_last_scanned.py` (NEVER -A), NO --amend/reset/force-push.
    markdownlint MD0xx cosmetic — ignore.
  </action>
  <verify>
    <automated>cd /c/Users/huxxha/Desktop/OmniGraph-Vault && DEEPSEEK_API_KEY=dummy GEMINI_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/test_scan_last_scanned.py tests/unit/test_scan_max_accounts.py -v</automated>
  </verify>
  <done>
    - accounts.last_scanned_at column added via _ensure_column (idempotent, PRAGMA-guarded).
    - run() stamps last_scanned_at on every ok=True scan (incl. 0-article); never on ok=False.
    - Staleness SELECT orders by (last_scanned_at IS NULL) DESC, last_scanned_at ASC, name ASC.
    - Default path (max_accounts is None) unchanged (ORDER BY name + shuffle).
    - All 4 new tests pass AND all 4 existing test_scan_max_accounts.py tests still pass.
  </done>
</task>

</tasks>

<operator_phase_2>
## Phase 2 — Aliyun data delete (ORCHESTRATOR runs via SSH; NOT an executor task)

The executor does NOT perform any step below. After Task 1 lands and is committed, the
orchestrator executes this runbook against Aliyun `kol_scan.db`. Scope: ONLY the SQLite
scan DB — does NOT touch the LightRAG KG / Qdrant (the 226 CV articles may already be in
the KG; cleaning the KG is OUT of scope per the user's "clean the scan DB" instruction).

**Pre-delete gate (HARD — resurrection guard):**
1. Verify the 5 CV account names are NOT in `kol_config.FAKEIDS` AND NOT in the kol_registry
   `list_accounts()`. If ANY are present, `init_accounts()` will resurrect them on the next
   `run()`. The 5 CV accounts have `source=None` (NOT the registry-sourced pattern), strongly
   suggesting they are absent from both — but VERIFY before deleting:
       grep -nE "CVer|CV技术指南|OpenCV学堂|我爱计算机视觉|AIWalker" kol_config.py
       (and inspect kol_registry list_accounts() output)
   BRANCH: if any CV name IS present → remove it from kol_config.py (separate code edit,
   commit forward-only) BEFORE the DB delete, else the delete is undone next batch.

**Backup (mandatory first):**
2. `cp kol_scan.db kol_scan.db.bak-pre-cvdelete-260629` on Aliyun.

**Delete in a transaction (verify counts before/after):**
3. Capture pre-counts:
       SELECT COUNT(*) FROM articles WHERE account_id IN (5766,5767,5768,5769,5799,16,17,18,19,49);
       SELECT COUNT(*) FROM accounts WHERE id IN (5766,5767,5768,5769,5799);
   Then, inside BEGIN/COMMIT, clean child rows referencing the doomed article ids FIRST
   (FK order), then the articles, then the accounts:
       -- child rows keyed by article_id (classifications, ingestions, extracted_entities)
       DELETE FROM classifications     WHERE article_id IN (SELECT id FROM articles WHERE account_id IN (5766,5767,5768,5769,5799,16,17,18,19,49));
       DELETE FROM ingestions          WHERE article_id IN (SELECT id FROM articles WHERE account_id IN (5766,5767,5768,5769,5799,16,17,18,19,49));
       DELETE FROM extracted_entities  WHERE article_id IN (SELECT id FROM articles WHERE account_id IN (5766,5767,5768,5769,5799,16,17,18,19,49));
       -- articles for the 5 live CV accounts + 5 orphan account_ids (226 CV arts)
       DELETE FROM articles WHERE account_id IN (5766,5767,5768,5769,5799,16,17,18,19,49);
       -- the 5 live CV account rows (orphan ids 16/17/18/19/49 are NOT in accounts)
       DELETE FROM accounts WHERE id IN (5766,5767,5768,5769,5799);
   NOTE: ingestions has no FK to articles (v3.5 dual-source schema comment) but still keys
   by article_id — delete its rows too. Verify post-counts are 0 for the target ids.
   Expected removed: ~145 articles under the 5 live CV accounts + 226 orphan CV articles = ~371.

**Ship the new code + bootstrap:**
4. SCP the new `batch_scan_kol.py` to Aliyun (git fetch is 443-blocked per 260626-jgp →
   single-file SCP, then verify the file's last_scanned_at line landed). Wrap any manual
   trigger with `set -a; source /root/.hermes/.env; set +a;` (per MEMORY: systemd
   EnvironmentFile is NOT inherited by ad-hoc SSH commands → DEEPSEEK_API_KEY=dummy silent 401).
5. Bootstrap: fire `batch_scan_kol.py --daily --max-accounts 1` once. Confirm:
   - the scanned account gets last_scanned_at stamped (SELECT name,last_scanned_at FROM accounts
     WHERE last_scanned_at IS NOT NULL ORDER BY last_scanned_at DESC LIMIT 5);
   - 0 CV accounts remain (SELECT COUNT(*) FROM accounts WHERE id IN (5766,5767,5768,5769,5799) → 0);
   - over subsequent batches the 8 non-CV dormant accounts each acquire a stamp and rotate to
     the back of the staleness queue.

**Close-out:** update ISSUES.md #73 row → Resolved (recent) with date + commit + this quick slug;
update `Last updated:` at top.
</operator_phase_2>

<verification>
- pytest: tests/unit/test_scan_last_scanned.py (4 new) + tests/unit/test_scan_max_accounts.py
  (4 existing) all pass.
- Code review: last_scanned_at column added idempotently; stamp only on ok=True; staleness
  SELECT reads last_scanned_at directly (no LEFT JOIN); default path unchanged.
- Operator Phase 2 (orchestrator, post-merge): backup taken, pre-delete gate passed, ~371 CV
  articles + 5 CV accounts removed, new code SCP'd, bootstrap confirms stamping + 0 CV remain.
</verification>

<success_criteria>
- ISSUES #73 staleness root cause fixed: empty-but-healthy accounts rotate to the back of the
  staleness queue after one successful attempt instead of pinning the head forever.
- accounts.last_scanned_at exists and is stamped on every successful scan attempt.
- Failed (cookie-dead) attempts do not falsely mark accounts fresh.
- Default (full-scan) path behavior is byte-identical.
- 5 CV-cluster accounts + 226 orphan CV articles removed from Aliyun kol_scan.db (operator phase).
- 8 non-CV dormant accounts retained and now properly rotated by last_scanned_at.
</success_criteria>

<output>
After completion, create `.planning/quick/260629-gvl-260629-kol-dead-account-prune-and-guard/260629-gvl-SUMMARY.md`
</output>

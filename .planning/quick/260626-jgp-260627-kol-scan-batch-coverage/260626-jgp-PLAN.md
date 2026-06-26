---
phase: quick-260626-jgp
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - batch_scan_kol.py
  - tests/unit/test_scan_max_accounts.py
  - deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service
  - deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer
  - deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer
  - deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer
  - deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer
  - deploy/aliyun/systemd/omnigraph-kol-classify.timer
  - deploy/aliyun/systemd/omnigraph-kol-scan.timer
autonomous: true
requirements: [JGP-01, JGP-02]

must_haves:
  truths:
    - "Default path (max_accounts is None) is byte-behavior-identical to current: same `SELECT name, fakeid FROM accounts ORDER BY name` + unconditional `random.shuffle(rows)` preserved, no truncation."
    - "Staleness path (max_accounts is not None) selects the staleest N accounts NULL-first (never-scanned), then oldest-scanned, then name tiebreak; does NOT shuffle (deterministic partition); truncates rows to first max_accounts."
    - "Staleness SQL is version-safe: uses `(MAX(a.scanned_at) IS NULL) DESC` boolean ordering, NEVER the `NULLS FIRST` keyword (Aliyun SQLite version unknown)."
    - "argparse is backward-compatible: --max-accounts is type=int default=None; existing --daily alone, --resume, --account, --days-back, --max-articles, --summary-json all keep working unchanged; --daily+--resume mutual-exclusion intact."
    - "Template service omnigraph-kol-scan-batch@.service ExecStart runs `batch_scan_kol.py --daily --max-accounts 15`, has RuntimeMaxSec=1800, keeps OnFailure=omnigraph-kol-scan-alert.service, Type=simple/User=root/WorkingDirectory=/root/OmniGraph-Vault/EnvironmentFile=/root/.hermes/.env/After+Wants network-online.target, venv-aim1 python path."
    - "Four lean batch timers @1..@4 each have [Timer] with ONLY OnCalendar + Persistent=true + Unit=omnigraph-kol-scan-batch@N.service; NO Requires= anywhere; OnCalendar UTC = @1 01:30, @2 05:30, @3 11:00, @4 15:30; WantedBy=timers.target."
    - "omnigraph-kol-classify.timer retimed OnCalendar 11:15→16:00 UTC and the `Requires=omnigraph-kol-classify.service` line dropped from [Unit]; Persistent=true kept."
    - "omnigraph-kol-scan.timer gets a SUPERSEDED header comment, file NOT deleted (alert+template chain depends on the .service definition staying)."
    - "Scope: zero edits to spiders/wechat_spider.py, ingest cron units, classify LOGIC (only its timer time), cookie self-heal chain (-alert.service / -refresh.*), MCP tunnel."
  artifacts:
    - path: "batch_scan_kol.py"
      provides: "--max-accounts flag + staleness-ordered SELECT + shuffle guard + run() param threading"
    - path: "tests/unit/test_scan_max_accounts.py"
      provides: "Behavior-anchor tests: staleness selection, default-path-no-truncation, argparse parse"
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service"
      provides: "Template service: --max-accounts 15 + RuntimeMaxSec=1800 + OnFailure alert chain"
      contains: "--max-accounts 15"
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer"
      provides: "Batch 1 timer, OnCalendar 01:30 UTC, Unit=...@1.service, no Requires="
      contains: "01:30:00"
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer"
      provides: "Batch 2 timer, OnCalendar 05:30 UTC, Unit=...@2.service, no Requires="
      contains: "05:30:00"
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer"
      provides: "Batch 3 timer, OnCalendar 11:00 UTC, Unit=...@3.service, no Requires="
      contains: "11:00:00"
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer"
      provides: "Batch 4 timer, OnCalendar 15:30 UTC, Unit=...@4.service, no Requires="
      contains: "15:30:00"
    - path: "deploy/aliyun/systemd/omnigraph-kol-classify.timer"
      provides: "Retimed classify timer 16:00 UTC, Requires= dropped"
      contains: "16:00:00"
    - path: "deploy/aliyun/systemd/omnigraph-kol-scan.timer"
      provides: "Superseded header comment, definition retained for reference"
      contains: "SUPERSEDED 2026-06-27"
  key_links:
    - from: "batch_scan_kol.py:main()"
      to: "batch_scan_kol.py:run()"
      via: "max_accounts keyword threaded through argparse -> run() call"
      pattern: "max_accounts"
    - from: "deploy/aliyun/systemd/omnigraph-kol-scan-batch@N.timer"
      to: "deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service"
      via: "Unit=omnigraph-kol-scan-batch@N.service in [Timer]"
      pattern: "Unit=omnigraph-kol-scan-batch@"
---

<objective>
Change KOL WeChat scan from 1 round/day (covers only ~18/58 accounts due to SESSION_LIMIT=54 truncation against shuffled order) to staleness-partitioned 4-batch multi-cron coverage that guarantees 58/58 accounts scanned daily.

Approved root cause + solution are LOCKED (user approved 2026-06-25). This is a `quick-full` execute plan — do NOT re-investigate or re-design.

Purpose: Each cron invocation today scans a random ~18 accounts; the same accounts never get refreshed for days. Adding `--max-accounts N` + a deterministic staleness ordering lets 4 staggered timers each take the 15 staleest accounts, so 4×15=60 ≥ 58 unique accounts get covered every day on a rotating-by-staleness basis.

Output:
- `batch_scan_kol.py` gains a backward-compatible `--max-accounts` flag (default None = current behavior unchanged).
- A new behavior-anchor test file pinning observable selection semantics.
- Repo copies (source of truth) of the new template service + 4 batch timers + retimed classify timer + a superseded header on the old scan timer under `deploy/aliyun/systemd/`.

NOTE: The actual Aliyun rollout (install units, daemon-reload, enable/disable timers, disable old scan timer) is OPERATOR work that the orchestrator performs in Phase 2 — the EXECUTOR only authors the repo artifacts and runs local pytest. Do NOT SSH to Aliyun.
</objective>

<context>
@.planning/STATE.md
@CLAUDE.md

<interfaces>
<!-- Ground-truth extracted by orchestrator from batch_scan_kol.py — use directly, no codebase exploration needed. -->

batch_scan_kol.py — relevant current shape:
- Line 15: `import random`
- Line 37: `DB_PATH = Path(os.environ.get("KOL_SCAN_DB_PATH", str(PROJECT_ROOT / "data" / "kol_scan.db")))`
- Line 38: `SESSION_LIMIT = 54`
- `accounts` schema: `id, name, wechat_id, fakeid, tags, source, category, notes, created_at` (NO last_scanned column)
- `articles` schema: `id, account_id (FK accounts.id), title, url, digest, update_time, scanned_at, content_hash, enriched`
- run() signature (line 236):
  `def run(days_back: int, max_articles: int, account_filter: str | None, resume: bool, daily: bool = False, summary_json: bool = False) -> None:`
- Line 245: `rows = conn.execute("SELECT name, fakeid FROM accounts ORDER BY name").fetchall()`
- Line 252: `random.shuffle(rows)`  <-- runs UNCONDITIONALLY today, right after SELECT, before resume/account_filter narrowing
- Loop at 276 consumes `(name, fakeid)` 2-tuples; breaks at `req_count >= SESSION_LIMIT`
- main() argparse (lines 329-339); run(...) called with kwargs at lines 344-351; mutual-exclusion `--daily`+`--resume` at line 341

Sibling test pattern to mirror (tests/unit/test_classify_multitopic_argparse.py):
- Seed dummy env BEFORE import: `os.environ.setdefault("DEEPSEEK_API_KEY","dummy")` + `os.environ.setdefault("GEMINI_API_KEY","dummy")`
- `_run_main_with(monkeypatch, argv)` helper: mock run() via `monkeypatch.setattr(mod, "run", MagicMock())`; force DB existence by replacing `DB_PATH` with a `MagicMock()` whose `.exists.return_value=True` (WindowsPath.exists is a read-only slot, cannot patch directly); `monkeypatch.setattr(sys, "argv", [...])`; call `mod.main()`; return the mock for assertions.
</interfaces>

<systemd_models>
<!-- EXACT current unit contents (orchestrator-read). Model new files on these. -->

omnigraph-kol-scan.service (template source — DO NOT modify this file; the @.service is a NEW file):
```
[Unit]
Description=OmniGraph daily KOL scan (WeChat MP API)
After=network-online.target
Wants=network-online.target
OnFailure=omnigraph-kol-scan-alert.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/OmniGraph-Vault
EnvironmentFile=/root/.hermes/.env
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_scan_kol.py --daily
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

omnigraph-kol-scan.timer (current — gets SUPERSEDED header only, NOT deleted):
```
[Unit]
Description=OmniGraph daily KOL scan (WeChat MP API) timer
Requires=omnigraph-kol-scan.service

[Timer]
OnCalendar=*-*-* 11:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

omnigraph-kol-classify.timer (current — retime 11:15→16:00 UTC + drop Requires line):
```
[Unit]
Description=OmniGraph daily KOL Layer-1 classify (5 topics) timer
Requires=omnigraph-kol-classify.service

[Timer]
OnCalendar=*-*-* 11:15:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```
</systemd_models>

<discipline>
- Forward-only commits. Explicit `git add <files>` — NEVER `-A`. NO `--amend` / `git reset` / `push --force` (memory feedback_no_amend_in_concurrent_quicks).
- markdownlint MD0xx cosmetic warnings — ignore.
- "omonigraph" runtime-dir typo is irrelevant here (no runtime-dir paths touched).
- Aliyun batch math (rationale, not code): 15 accounts × ~2.7 page-req ≈ 40 < 50 WeChat real rate-limit → never trips 50/50; 4×15=60 ≥ 58 accounts; scan times (01:30/05:30/11:00/15:30 UTC) sit between even-hour ingest fires; classify 16:00 UTC coincides with the 16:00 ingest hour but classify is DB-light (~16s, no graphml write) so collision is benign.
</discipline>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add --max-accounts staleness path to batch_scan_kol.py + behavior-anchor tests</name>
  <files>batch_scan_kol.py, tests/unit/test_scan_max_accounts.py</files>
  <behavior>
    Write tests/unit/test_scan_max_accounts.py FIRST (RED), mirroring tests/unit/test_classify_multitopic_argparse.py conventions:

    - At top, BEFORE `import batch_scan_kol`:
        `os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")`
        `os.environ.setdefault("GEMINI_API_KEY", "dummy")`
      (defuse import-time coupling — batch_scan_kol imports config + spiders.wechat_spider which eager-import.)

    - Test (a) staleness selection — pin "selects the staleest N, NULL-first":
        * Build a real sqlite at tmp_path. Easiest: call `batch_scan_kol.init_db(tmp_db)` to get the exact prod schema, then INSERT accounts + articles directly. Insert ~5-6 accounts; 2 with NO articles rows (never-scanned → MAX(scanned_at) IS NULL), the rest with articles whose scanned_at differ (e.g. '2026-06-01 ...' older vs '2026-06-25 ...' newer). Give accounts distinct names so name-tiebreak is observable.
        * `monkeypatch.setattr(batch_scan_kol, "DB_PATH", tmp_db)` (a real Path here is fine — run() opens it).
        * `monkeypatch.setattr(batch_scan_kol, "load_env", lambda: None)` (no network/env load).
        * `monkeypatch.setattr(batch_scan_kol, "init_accounts", lambda conn: 0)` (no-op — accounts already seeded; avoid kol_registry/kol_config network/import work).
        * Capture scanned accounts in order: `m = MagicMock(return_value=(True, 0, 0, False)); monkeypatch.setattr(batch_scan_kol, "scan_account", m)`. (scan_account returns `(ok, new, skipped, session_invalid)`.)
        * Call `batch_scan_kol.run(days_back=120, max_articles=20, account_filter=None, resume=False, max_accounts=3)`.
        * Assert exactly 3 accounts were handed to scan_account, and they are the 2 never-scanned (first, name-ordered between themselves) + the single oldest-scanned account, in staleness order. Extract handed names from `m.call_args_list` — scan_account signature is `scan_account(conn, name, fakeid, days_back, max_articles)` so name is positional arg index 1 (`c.args[1]`).

    - Test (b) default path still offers ALL accounts (no truncation, shuffle preserved as a path):
        * Same seeding harness. `monkeypatch.setattr(batch_scan_kol, "random", ...)` is fragile; instead `monkeypatch.setattr(batch_scan_kol.random, "shuffle", lambda x: None)` to make order deterministic without disabling the call path.
        * Call `run(days_back=120, max_articles=20, account_filter=None, resume=False, max_accounts=None)`.
        * Assert `scan_account` call_count == total seeded accounts (no truncation). Do NOT assert a specific staleness order on the default path (it is the shuffle path).

    - Test (c) argparse — `--max-accounts` parses to int / absent → None:
        * Reuse the sibling `_run_main_with(monkeypatch, argv)` harness: mock `run` via MagicMock; replace `DB_PATH` with a `MagicMock()` whose `.exists.return_value=True`; set `sys.argv`; call `main()`.
        * NOTE: batch_scan_kol.main() does NOT guard on `DB_PATH.exists()` (unlike batch_classify_kol). So the MagicMock DB_PATH is harmless but unnecessary; including it is fine for harness symmetry. Verify against the actual main() — if no exists() guard, you may omit the DB_PATH patch.
        * `--max-accounts 15` present → assert `run` received `max_accounts=15` (int). main() calls run() with KEYWORD args, so assert via `mock_run.call_args.kwargs["max_accounts"] == 15`.
        * absent → assert `mock_run.call_args.kwargs["max_accounts"] is None`.
        * Also assert one existing flag still threads (e.g. `mock_run.call_args.kwargs["daily"]` for `--daily`) to prove backward compatibility.

    Run pytest — these MUST fail RED first (run() has no max_accounts param yet, argparse has no flag).
  </behavior>
  <action>
    Implement the minimal change in batch_scan_kol.py to turn the tests GREEN. Keep it ~15-20 LoC, single file, backward-compatible.

    1. run() signature — add a new keyword param with default None (placement AFTER summary_json to preserve existing keyword-arg call sites):
       `def run(days_back: int, max_articles: int, account_filter: str | None, resume: bool, daily: bool = False, summary_json: bool = False, max_accounts: int | None = None) -> None:`

    2. Branch the account SELECT on max_accounts (replaces lines 245 + 252 region). Keep the `if not rows: ... sys.exit(1)` guard after the branch.

       When `max_accounts is None` (DEFAULT — byte-behavior-identical to today):
         - `rows = conn.execute("SELECT name, fakeid FROM accounts ORDER BY name").fetchall()`
         - (the empty-rows guard)
         - `random.shuffle(rows)`  ← preserved exactly, with its existing comment.

       When `max_accounts is not None` (STALENESS PATH — deterministic, NO shuffle):
         - Use the VERSION-SAFE staleness query (do NOT use `NULLS FIRST`):
           ```sql
           SELECT acc.name, acc.fakeid
           FROM accounts acc
           LEFT JOIN articles a ON a.account_id = acc.id
           GROUP BY acc.id
           ORDER BY (MAX(a.scanned_at) IS NULL) DESC, MAX(a.scanned_at) ASC, acc.name ASC
           ```
           (returns the SAME `(name, fakeid)` 2-tuple shape the loop consumes; never-scanned NULL rows sort FIRST, then oldest-scanned, then name tiebreak.)
         - (the empty-rows guard)
         - DO NOT shuffle.
         - `rows = rows[:max_accounts]` (truncate to the staleest N).

       Cleanest structure: one `if max_accounts is None: ... else: ...` block that produces `rows`, with the shuffle living inside the `is None` branch only. Keep the existing comment on the shuffle. Leave the `resume` and `account_filter` narrowing blocks (lines 255-266) UNCHANGED and AFTER this branch — they still apply to both paths.

    3. main() — add the flag and thread it:
       - argparse: `parser.add_argument("--max-accounts", type=int, default=None, help="Cap scan to the N staleest accounts (NULL-first, oldest-scanned). Default None = scan all (shuffled).")`
       - run() call: add `max_accounts=args.max_accounts,` to the keyword args.

    Do NOT touch SESSION_LIMIT, scan_account, _import_articles, init_db, init_accounts, the mutual-exclusion check, or any other logic. Do NOT touch spiders/wechat_spider.py.

    Run pytest GREEN. Then atomic forward-only commit:
      `git add batch_scan_kol.py tests/unit/test_scan_max_accounts.py`
      `git commit -m "feat(scan): add --max-accounts staleness-partition path to batch_scan_kol (260626-jgp)"`
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -m pytest tests/unit/test_scan_max_accounts.py -v</automated>
  </verify>
  <done>
    pytest tests/unit/test_scan_max_accounts.py is GREEN (3+ tests pass) on Windows venv. batch_scan_kol.py: run() has max_accounts param, staleness SELECT uses `(MAX(a.scanned_at) IS NULL) DESC` (no NULLS FIRST keyword), shuffle only on max_accounts-is-None path, default path SELECT+shuffle byte-identical to before, --max-accounts flag threaded through main(). Atomic commit landed on main, NOT pushed.
  </done>
</task>

<task type="auto">
  <name>Task 2: Author systemd repo unit copies under deploy/aliyun/systemd/</name>
  <files>deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service, deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer, deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer, deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer, deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer, deploy/aliyun/systemd/omnigraph-kol-classify.timer, deploy/aliyun/systemd/omnigraph-kol-scan.timer</files>
  <action>
    Create / modify the repo source-of-truth copies of the new units. These are repo artifacts only — the orchestrator installs them on Aliyun in Phase 2. Model exactly on the current units in <systemd_models>.

    1. CREATE deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service (template):
       ```
       [Unit]
       Description=OmniGraph KOL scan batch %i (WeChat MP API, staleness-partitioned)
       After=network-online.target
       Wants=network-online.target
       OnFailure=omnigraph-kol-scan-alert.service

       [Service]
       Type=simple
       User=root
       WorkingDirectory=/root/OmniGraph-Vault
       EnvironmentFile=/root/.hermes/.env
       ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python /root/OmniGraph-Vault/batch_scan_kol.py --daily --max-accounts 15
       RuntimeMaxSec=1800
       StandardOutput=journal
       StandardError=journal

       [Install]
       WantedBy=multi-user.target
       ```

    2. CREATE the 4 LEAN timers. Each [Timer] has ONLY OnCalendar + Persistent=true + Unit= (NO Requires= — memory aliyun_drift_recovery_260528 v4: Requires= in a timer wrongly fires the service on TIMER start). The Unit= line is REQUIRED for a template timer so the timer triggers the correctly-instanced service.

       deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer:
       ```
       [Unit]
       Description=OmniGraph KOL scan batch 1 timer (01:30 UTC, staleness-partitioned)

       [Timer]
       OnCalendar=*-*-* 01:30:00 UTC
       Persistent=true
       Unit=omnigraph-kol-scan-batch@1.service

       [Install]
       WantedBy=timers.target
       ```

       deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer — same but Description "batch 2 timer (05:30 UTC...)", `OnCalendar=*-*-* 05:30:00 UTC`, `Unit=omnigraph-kol-scan-batch@2.service`.

       deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer — Description "batch 3 timer (11:00 UTC...)", `OnCalendar=*-*-* 11:00:00 UTC`, `Unit=omnigraph-kol-scan-batch@3.service`.

       deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer — Description "batch 4 timer (15:30 UTC...)", `OnCalendar=*-*-* 15:30:00 UTC`, `Unit=omnigraph-kol-scan-batch@4.service`.

    3. MODIFY deploy/aliyun/systemd/omnigraph-kol-classify.timer — retime 11:15→16:00 UTC AND drop the `Requires=omnigraph-kol-classify.service` line from [Unit]. Keep Persistent=true. Result:
       ```
       [Unit]
       Description=OmniGraph daily KOL Layer-1 classify (5 topics) timer

       [Timer]
       OnCalendar=*-*-* 16:00:00 UTC
       Persistent=true

       [Install]
       WantedBy=timers.target
       ```

    4. MODIFY deploy/aliyun/systemd/omnigraph-kol-scan.timer — PREPEND a header comment (do NOT delete the file; do NOT change the body). The .service it referenced stays valid as the alert-chain anchor. Result:
       ```
       # SUPERSEDED 2026-06-27 by omnigraph-kol-scan-batch@{1..4}.timer (4-batch staleness coverage). Disabled on Aliyun; definition retained for reference.
       [Unit]
       Description=OmniGraph daily KOL scan (WeChat MP API) timer
       Requires=omnigraph-kol-scan.service

       [Timer]
       OnCalendar=*-*-* 11:00:00 UTC
       Persistent=true

       [Install]
       WantedBy=timers.target
       ```

    Do NOT touch: omnigraph-kol-scan.service (template stays, alert anchor), omnigraph-kol-scan-alert.service, omnigraph-kol-refresh.{service,timer}, omnigraph-mcp-tunnel.service, omnigraph-kol-classify.service (logic), any ingest timers/services.

    Atomic forward-only commit:
      `git add deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer deploy/aliyun/systemd/omnigraph-kol-classify.timer deploy/aliyun/systemd/omnigraph-kol-scan.timer`
      `git commit -m "chore(systemd): 4-batch KOL scan timers + retime classify 16:00 UTC (260626-jgp)"`
  </action>
  <verify>
    <automated>ls deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer deploy/aliyun/systemd/omnigraph-kol-scan-batch@2.timer deploy/aliyun/systemd/omnigraph-kol-scan-batch@3.timer deploy/aliyun/systemd/omnigraph-kol-scan-batch@4.timer && grep -c "max-accounts 15" deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service && grep -c "RuntimeMaxSec=1800" deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service && grep -c "OnFailure=omnigraph-kol-scan-alert.service" deploy/aliyun/systemd/omnigraph-kol-scan-batch@.service && grep -L "Requires=" deploy/aliyun/systemd/omnigraph-kol-scan-batch@1.timer && grep -c "16:00:00" deploy/aliyun/systemd/omnigraph-kol-classify.timer && grep -c "SUPERSEDED 2026-06-27" deploy/aliyun/systemd/omnigraph-kol-scan.timer</automated>
  </verify>
  <done>
    All 5 new batch unit files exist. Template @.service has `--max-accounts 15`, `RuntimeMaxSec=1800`, and `OnFailure=omnigraph-kol-scan-alert.service`. Each @N.timer has OnCalendar (01:30/05:30/11:00/15:30 UTC respectively), Persistent=true, Unit=omnigraph-kol-scan-batch@N.service, and NO Requires= line. classify.timer OnCalendar=16:00 UTC with Requires line dropped. Old scan.timer has the SUPERSEDED header and is NOT deleted. Atomic commit landed on main, NOT pushed.
  </done>
</task>

</tasks>

<verification>
- Task 1: `venv/Scripts/python.exe -m pytest tests/unit/test_scan_max_accounts.py -v` GREEN; confirm staleness SQL has no `NULLS FIRST` token (`grep -i "nulls first" batch_scan_kol.py` returns nothing) and shuffle is inside the max_accounts-is-None branch only.
- Task 2: all 7 unit-file grep checks in the Task 2 <verify> pass; `grep -rL "Requires=" deploy/aliyun/systemd/omnigraph-kol-scan-batch@{1,2,3,4}.timer` confirms none of the 4 new timers carry Requires=.
- Scope guard: `git diff --name-only <pre>..HEAD` lists ONLY batch_scan_kol.py, tests/unit/test_scan_max_accounts.py, and the 7 deploy/aliyun/systemd/ files (plus planning docs). No spiders/wechat_spider.py, no ingest units, no classify .service, no -alert/-refresh/-tunnel files.
- Two atomic forward-only commits on main, NOT pushed. Explicit `git add <files>`, no `-A`, no `--amend`.
</verification>

<success_criteria>
- batch_scan_kol.py: backward-compatible `--max-accounts` (int, default None); default path unchanged (SELECT ORDER BY name + unconditional shuffle, no truncation); staleness path uses version-safe `(MAX(a.scanned_at) IS NULL) DESC` ordering, no shuffle, truncates to N.
- tests/unit/test_scan_max_accounts.py GREEN: staleness selection (NULL-first), default-no-truncation, argparse parse — all behavior-anchored, not SQL-string-matched.
- deploy/aliyun/systemd/: template @.service (--max-accounts 15 + RuntimeMaxSec=1800 + OnFailure alert) + 4 lean @N.timer (no Requires=, correct OnCalendar, Unit= naming instance) + classify.timer retimed 16:00 UTC w/ Requires dropped + old scan.timer superseded-header (not deleted).
- Scope honored: zero edits outside the named files.
- 2 atomic forward-only commits, not pushed; orchestrator handles Aliyun rollout in Phase 2.
</success_criteria>

<output>
After completion, create `.planning/quick/260626-jgp-260627-kol-scan-batch-coverage/260626-jgp-SUMMARY.md`
</output>

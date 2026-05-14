---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 07
type: execute
wave: 3
depends_on: ["kb-4-06"]  # run after dev-runtime smoke is green; prod-shape is the harder gate
files_modified:
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-HERMES-PRODSHAPE.md
  - .playwright-mcp/kb-4-prodshape-*.png
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-07-SUMMARY.md
autonomous: false
requirements: [DEPLOY-05]  # prod-shape e2e verification depth; also closes kb-3-12 deferred Hermes prod-shape item
must_haves:
  truths:
    - "Hermes prod-shape DB obtained via user-coordinated transfer (NOT speculative SSH)"
    - "DATA-07 visibility on prod-shape DB matches predicted ~6.4% scaling pattern"
    - "All 6 endpoint families return expected shapes against prod-shape DB"
    - "All 3 smoke scenarios pass against prod-shape DB"
    - "Visual regression check vs kb-1/kb-2/kb-3 baseline screenshots: zero pixel-level breakage"
  artifacts:
    - path: ".planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-HERMES-PRODSHAPE.md"
      provides: "prod-shape e2e smoke artifact (closes kb-3-12 deferral)"
      min_lines: 50
  key_links:
    - from: "kb-4-HERMES-PRODSHAPE.md"
      to: "kb-3-VERIFICATION.md DATA-07 prediction"
      via: "verifies 6.4% scales correctly to larger Hermes prod row count"
---

<objective>
Run the kb-4-05 (Local UAT) + kb-4-06 (3 smoke scenarios) protocols a SECOND time, against a prod-shape `kol_scan.db` snapshot from Hermes — closing the deferred item from `.planning/phases/kb-3-fastapi-bilingual-api/deferred-items.md` ("Hermes prod data verification deferred — pending production-shape DB sync").

Per memory `feedback_dont_speculative_ssh_ask_hermes.md`: this plan does NOT speculatively SSH into Hermes. It coordinates with the user (who owns the Hermes channel) to either (a) scp a recent prod DB snapshot down, or (b) accept current `.dev-runtime` snapshot as the prod-shape proxy if it's recent + rich enough.

Purpose: depth verification of DEPLOY-05 + closing kb-3 deferral.
Output: `kb-4-HERMES-PRODSHAPE.md` + visual regression diff vs kb-1/kb-2/kb-3 baselines.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md  (kb-4-05 — dev runtime baseline)
@.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md  (kb-4-06 — dev runtime smoke)
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-VERIFICATION.md  (DATA-07 6.4% prediction)
@.planning/phases/kb-3-fastapi-bilingual-api/deferred-items.md

<interfaces>
- DATA-07 visibility prediction (kb-3-VERIFICATION): 160/2501 articles = 6.4% on .dev-runtime snapshot
- On Hermes prod (~3000-4000 rows total per recent CLAUDE.md context), 6.4% should scale linearly → ~190-256 visible articles
- Memory `feedback_dont_speculative_ssh_ask_hermes.md`: ask user to relay to Hermes for prod data, do not SSH speculatively
- kb-3-12 deferral noted: "Hermes prod data verification deferred — pending production-shape DB sync from ohca.ddns.net:49221"
</interfaces>
</context>

<tasks>

<task type="checkpoint:decision" gate="blocking">
  <name>Task 1 (CHECKPOINT): Decide prod-shape DB source</name>
  <decision>How to obtain a prod-shape DB for kb-4 e2e verification</decision>
  <context>
    Per memory `feedback_dont_speculative_ssh_ask_hermes.md`, the agent does NOT speculatively SSH into Hermes. Three options to bring prod-shape DB down for local re-runs of UAT + smoke:
  </context>
  <options>
    <option id="option-a">
      <name>User scp's latest Hermes prod DB to local</name>
      <pros>
        - True prod-shape verification — DATA-07 6.4% prediction validated against actual prod row counts
        - Highest confidence for kb-4 close
      </pros>
      <cons>
        - Coordination with user — they need to run scp from Hermes to local
        - DB may be in active use (need to copy WAL + DB safely or stop ingest cron briefly)
      </cons>
      <action_if_chosen>
        Plan emits a copy-paste-ready command for user to run. User runs scp + reports completion. Plan resumes.

        Suggested user command:
        ```
        # On user's local Windows (PowerShell):
        scp -P 49221 user@ohca.ddns.net:~/OmniGraph-Vault/data/kol_scan.db ./.dev-runtime/data/kol_scan.prodshape.db
        scp -P 49221 user@ohca.ddns.net:~/OmniGraph-Vault/data/kol_scan.db-wal ./.dev-runtime/data/kol_scan.prodshape.db-wal 2>/dev/null
        ```

        Then plan re-runs kb-4-05 + kb-4-06 logic against KB_DB_PATH=.dev-runtime/data/kol_scan.prodshape.db.
      </action_if_chosen>
    </option>
    <option id="option-b">
      <name>Treat current .dev-runtime/data/kol_scan.db as the prod-shape proxy</name>
      <pros>
        - Zero coordination cost
        - Quick path to phase close
        - .dev-runtime DB was already used by kb-3 + kb-4-05 + kb-4-06 — known good
      </pros>
      <cons>
        - May not be recent enough (Hermes ingest cron has shipped daily since the local snapshot was taken)
        - DATA-07 6.4% scaling prediction can't be validated at higher row count
        - kb-3-12 deferred item stays partially open — only "best-effort proxy verification" recorded
      </cons>
      <action_if_chosen>
        Document choice in HERMES-PRODSHAPE.md as "proxy verification — .dev-runtime DB used as prod-shape stand-in; full prod-shape verification deferred to operator post-deploy". Re-run is essentially a no-op (kb-4-05 + kb-4-06 already covered this DB); note this and skip Tasks 2-3 below, jumping to "verdict: proxy verified".
      </action_if_chosen>
    </option>
    <option id="option-c">
      <name>User runs the smoke directly on Hermes (skip local re-run; use Hermes as the test target)</name>
      <pros>
        - Most realistic — actual prod environment, actual prod data, actual Caddy + systemd
        - True same-host verification per DEPLOY-05
      </pros>
      <cons>
        - Requires user to run kb/deploy/install.sh on Hermes first (operator deploy workflow)
        - Out of scope for kb-4-PLANNING phase — this is the operator deploy step kb-4 produces artifacts FOR
        - But: user could spin up a parallel instance on Hermes for testing without disrupting Hermes's existing workloads
      </cons>
      <action_if_chosen>
        Plan emits a Hermes operator prompt for user to forward (per CLAUDE.md PRINCIPLE #5 channel separation: write a Hermes prompt, don't outsource SSH commands). User forwards to Hermes; Hermes runs install.sh + smoke; user pastes back report. Plan documents Hermes verdict.
      </action_if_chosen>
    </option>
  </options>
  <resume-signal>option-a / option-b / option-c</resume-signal>
</task>

<task type="auto">
  <name>Task 2: If option-a — re-run UAT + 3 smoke scenarios against prod-shape DB</name>
  <files>
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-HERMES-PRODSHAPE.md
    .playwright-mcp/kb-4-prodshape-*.png
  </files>
  <read_first>
    - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
    - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-SMOKE-VERIFICATION.md
  </read_first>
  <action>
    SKIP this task if Task 1 chose option-b or option-c.

    For option-a:

    Step 1 — Verify scp'd file is valid:
    ```bash
    sqlite3 .dev-runtime/data/kol_scan.prodshape.db 'SELECT COUNT(*) FROM articles; SELECT COUNT(*) FROM rss_articles;' 2>&1
    sqlite3 .dev-runtime/data/kol_scan.prodshape.db 'PRAGMA integrity_check;'
    ```
    Document row counts + integrity result.

    Step 2 — Re-run rebuild pipeline against prod-shape DB:
    ```bash
    export KB_DB_PATH="$(pwd)/.dev-runtime/data/kol_scan.prodshape.db"
    venv/Scripts/python.exe kb/scripts/detect_article_lang.py
    venv/Scripts/python.exe kb/export_knowledge_base.py
    venv/Scripts/python.exe kb/scripts/rebuild_fts.py
    ```
    Capture row counts after detect (lang coverage), HTML page counts after export, FTS row count after rebuild.

    Step 3 — DATA-07 visibility validation:
    ```sql
    -- Run in sqlite3 prodshape db:
    SELECT COUNT(*) AS total_scanned FROM articles UNION ALL SELECT COUNT(*) FROM rss_articles;
    SELECT COUNT(*) AS visible FROM articles
      WHERE body IS NOT NULL AND body != ''
        AND layer1_verdict = 'candidate'
        AND (layer2_verdict IS NULL OR layer2_verdict != 'reject');
    ```
    Compute visibility ratio. Compare against kb-3-VERIFICATION's 6.4% on .dev-runtime. State whether pattern scales linearly.

    Step 4 — Restart local_serve.py with prod-shape KB_DB_PATH. Re-run a SUBSET of kb-4-05 (the API smoke table) + ALL 3 smoke scenarios from kb-4-06 against prod-shape DB.

    Capture screenshots with prefix `kb-4-prodshape-` to distinguish from `kb-4-uat-` and `kb-4-smoke-`.

    Document in `kb-4-HERMES-PRODSHAPE.md`:
    - Section: "Prod DB inventory" (row counts, lang coverage, DATA-07 visibility ratio)
    - Section: "API Smoke (prod-shape)" (6 endpoints x status code + key fields)
    - Section: "3 Smoke Scenarios (prod-shape)" (12 sub-steps)
    - Section: "Visual regression vs dev-runtime baseline" (compare 5 page-type screenshots side-by-side, document any visible differences — long-title overflow at higher row count, RTL/CJK edge cases at scale, etc.)

    Step 5 — If visual regression observed (e.g., long Chinese title overflow at scale), invoke conditional Skills:
    ```
    Skill(skill="ui-ux-pro-max", args="<observed regression description + screenshot paths>")
    Skill(skill="frontend-design", args="<implement the fix>")
    ```
    (Same conditional pattern as kb-4-05 — fix properly, not band-aid.)
  </action>
  <verify>
    <automated>
      # Skip-aware: only require if Task 1 = option-a
      python -c "
from pathlib import Path
summary = Path('.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-07-SUMMARY.md').read_text(encoding='utf-8')
if 'option-a' in summary:
    prodshape = Path('.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-HERMES-PRODSHAPE.md').read_text(encoding='utf-8')
    assert 'Prod DB inventory' in prodshape
    assert 'API Smoke (prod-shape)' in prodshape
    assert '3 Smoke Scenarios (prod-shape)' in prodshape
    assert 'Visual regression' in prodshape
    print('option-a sections all present')
elif 'option-b' in summary:
    print('option-b — skipped per Task 1 choice')
elif 'option-c' in summary:
    print('option-c — Hermes operator prompt path; see kb-4-HERMES-PRODSHAPE.md')
"
    </automated>
  </verify>
  <done>
    - If option-a: HERMES-PRODSHAPE.md fully populated with prod-shape verdicts
    - If option-b: HERMES-PRODSHAPE.md notes proxy verification + scope decision
    - If option-c: HERMES-PRODSHAPE.md contains the Hermes operator prompt + Hermes-side report when received
  </done>
</task>

<task type="auto">
  <name>Task 3: If option-c — emit Hermes operator prompt for user to forward</name>
  <files>
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-HERMES-PRODSHAPE.md
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/HERMES-DEPLOY-260514.md
  </files>
  <action>
    SKIP this task if Task 1 chose option-a or option-b.

    For option-c:

    Write a Hermes operator prompt to `HERMES-DEPLOY-260514.md` per CLAUDE.md PRINCIPLE #5 — user owns the Hermes channel, agent provides the prompt template:

    ```markdown
    # Hermes deploy prompt — kb-4 prod-shape verification
    Date: 2026-05-14
    Plan: kb-4-07

    Hi Hermes — please run the following kb-4 verification on prod and report back:

    ## Step 1 — Pull latest main
    ```bash
    cd ~/OmniGraph-Vault
    git fetch origin main
    git status -sb
    git pull --ff-only
    ```

    ## Step 2 — Run install.sh (or skip if already deployed; verify systemctl status)
    ```bash
    sudo bash kb/deploy/install.sh
    # OR if already running:
    systemctl status kb-api --no-pager | head -10
    ```
    Report:
    - Active/inactive
    - journalctl -u kb-api --since '5 minutes ago' tail (any ERROR lines?)

    ## Step 3 — Sanity probe API
    ```bash
    curl -fsS http://127.0.0.1:8766/health
    curl -fsS 'http://127.0.0.1:8766/api/articles?limit=5' | python3 -c "import sys, json; d=json.load(sys.stdin); print('count:', len(d['items']), 'total:', d.get('total'))"
    ```
    Report values.

    ## Step 4 — Smoke 3 scenarios via curl + Caddy public URL
    Run the 3 PROJECT-KB-v2.md smoke scenarios manually + report PASS/FAIL per sub-step.

    ## Step 5 — daily_rebuild.sh dry-run
    ```bash
    sudo -u kb bash kb/scripts/daily_rebuild.sh
    ```
    Report wallclock + any error lines.

    Paste back the full report (commands run + output) so OmniGraph kb-4-07 can record the result.
    ```

    Document in HERMES-PRODSHAPE.md:
    - Section "Operator prompt path chosen"
    - Section "Awaiting Hermes report"
    - Once user pastes Hermes's report → record verbatim under "Hermes-side verification"
  </action>
  <verify>
    <automated>
      python -c "
from pathlib import Path
summary = Path('.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-07-SUMMARY.md').read_text(encoding='utf-8')
if 'option-c' in summary:
    assert Path('.planning/phases/kb-4-ubuntu-deploy-cron-smoke/HERMES-DEPLOY-260514.md').exists()
    print('Hermes operator prompt emitted')
else:
    print('option-c not chosen, skip')
"
    </automated>
  </verify>
  <done>
    - If option-c: Hermes prompt file exists, ready for user to forward
    - HERMES-PRODSHAPE.md has placeholder for Hermes report
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4 (CHECKPOINT): User reviews prod-shape evidence + signs off</name>
  <what-built>
    - kb-4-HERMES-PRODSHAPE.md with Task 1 choice + corresponding evidence
    - If option-a: 12+ prod-shape screenshots + visibility validation
    - If option-c: Hermes operator prompt + (eventually) Hermes-side report
  </what-built>
  <how-to-verify>
    1. Read kb-4-HERMES-PRODSHAPE.md "Prod DB inventory" — does the visibility ratio match the predicted 6.4% scaling?
    2. Spot-check screenshots (option-a) or the Hermes report (option-c)
    3. Confirm no critical regression vs dev-runtime baseline
    4. Type 'approved' to close kb-3-12 deferral; or 'fix: <issue>'
  </how-to-verify>
  <resume-signal>'approved' or 'fix: <description>'</resume-signal>
</task>

</tasks>

<verification>
- kb-3-12 deferral closed (verbatim recorded in HERMES-PRODSHAPE.md)
- DATA-07 visibility prediction validated (or proxy/Hermes-side documented)
- Visual regression check completed
</verification>

<success_criteria>
- Production-shape verification complete via one of three paths (option-a/b/c)
- kb-4-HERMES-PRODSHAPE.md is the artifact the milestone-close uses to assert "kb-3 deferred item closed"
</success_criteria>

<output>
After completion: `.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-07-SUMMARY.md` + `kb-4-HERMES-PRODSHAPE.md` (+ optional `HERMES-DEPLOY-260514.md`)
</output>

---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 04
type: execute
wave: 2
depends_on: ["kb-4-01", "kb-4-02"]
files_modified:
  - kb/scripts/daily_rebuild.sh
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-04-SUMMARY.md
autonomous: true
requirements: [DEPLOY-04]
must_haves:
  truths:
    - "daily_rebuild.sh runs the chained pipeline: detect_article_lang → export_knowledge_base → rebuild_fts → sitemap regen → VACUUM"
    - "VACUUM is race-safe against running uvicorn (which holds DB read-only via URI mode)"
    - "FTS5 rebuild is atomic (rebuild_fts.py uses CREATE TABLE-RENAME pattern, not DROP-CREATE)"
    - "Script logs to /var/log/kb-rebuild.log with timestamped rotation"
    - "Script exits non-zero on any pipeline stage failure (set -euo pipefail)"
    - "database-reviewer Skill invoked + findings applied"
  artifacts:
    - path: "kb/scripts/daily_rebuild.sh"
      provides: "cron-invoked daily rebuild script"
      min_lines: 60
  key_links:
    - from: "kb/scripts/daily_rebuild.sh"
      to: "kb/scripts/rebuild_fts.py"
      via: "python kb/scripts/rebuild_fts.py call"
      pattern: "rebuild_fts.py"
    - from: "kb/scripts/daily_rebuild.sh"
      to: "kb/export_knowledge_base.py"
      via: "python kb/export_knowledge_base.py call"
      pattern: "export_knowledge_base.py"
    - from: "kb/scripts/daily_rebuild.sh"
      to: "kol_scan.db VACUUM"
      via: "sqlite3 KB_DB_PATH 'VACUUM'"
      pattern: "VACUUM"
---

<objective>
Ship `kb/scripts/daily_rebuild.sh` — the cron-invoked daily script that re-runs the full SSG + FTS5 pipeline and VACUUMs the SQLite DB. Cron entry fires at 12:00 server-local daily.

Pipeline stages (in order):
1. `detect_article_lang.py` — backfill any new `lang IS NULL` rows (DATA-03 idempotency)
2. `export_knowledge_base.py` — re-render kb/output/ from latest DB state
3. `rebuild_fts.py` — full FTS5 trigram index rebuild
4. Sitemap + robots.txt regen (lifted from kb-1 export script if not already)
5. `VACUUM` on kol_scan.db — reclaim deleted rows + defragment

The script is reviewed by `database-reviewer` Skill — VACUUM exclusive write vs running uvicorn read-only access is the primary concern.

Purpose: DEPLOY-04. Daily cron freshness for SSG + FTS5 + DB compaction.
Output: 1 shell script + SUMMARY.md with database-reviewer findings.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/ROADMAP-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@kb/docs/02-DECISIONS.md
@kb/docs/07-KB4-DEPLOY.md
@kb/docs/10-DESIGN-DISCIPLINE.md

@kb/scripts/rebuild_fts.py
@kb/scripts/detect_article_lang.py
@kb/export_knowledge_base.py

<interfaces>
- DEPLOY-04 (REQUIREMENTS-KB-v2.md): cron-invoked script chaining detect → export → rebuild_fts. Logs /var/log/kb-rebuild.log. Cron at 12:00 daily.
- DATA-03: detect_article_lang.py is idempotent (only updates rows where lang IS NULL). Daily re-invocation safe.
- SEARCH-02: rebuild_fts.py performs full FTS5 rebuild < 5s on prod.
- C3 contract: schema-additive only — VACUUM is allowed (no schema changes).
- uvicorn (kb-api.service) holds the DB via URI mode `mode=ro` per kb/api.py — concurrent read with cron-side VACUUM is the race scenario.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Invoke database-reviewer Skill on rebuild pipeline race scenarios</name>
  <files>.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-04-SUMMARY.md (records invocation evidence)</files>
  <read_first>
    - kb/scripts/rebuild_fts.py (existing — kb-3-07)
    - kb/api.py (verify if it opens DB with mode=ro URI or read-write)
    - kb/data/article_query.py (verify connection URI mode)
    - kb/docs/10-DESIGN-DISCIPLINE.md (kb-4 database-reviewer requirements)
  </read_first>
  <action>
    Step 1 — Inspect kb/api.py + kb/data/article_query.py to determine current DB connection mode:
    ```bash
    grep -n 'sqlite3.connect\|file:.*mode=' kb/api.py kb/data/*.py
    ```
    Record findings: is uvicorn opening DB read-only (mode=ro) or read-write?

    Step 2 — Draft the daily_rebuild.sh script (see Task 2 for full contents). Then BEFORE writing it to disk, invoke database-reviewer:

    ```
    Skill(
      skill="database-reviewer",
      args="Review proposed daily cron rebuild pipeline for SQLite race conditions on a single Ubuntu host where:
      - kb-api.service (uvicorn) runs continuously, opens kol_scan.db for read-only queries (verify URI mode in step 1)
      - daily_rebuild.sh runs at 12:00 chaining: detect_article_lang → export_knowledge_base → rebuild_fts → VACUUM
      - Hermes-side ingest cron (separate, not v2.0 KB scope) writes to articles + rss_articles + classifications + extracted_entities tables
      - LightRAG storage at ~/.hermes/omonigraph-vault/lightrag_storage/ — read-only consumption only this milestone

      Specific concerns to evaluate:

      (a) VACUUM acquires EXCLUSIVE write lock. If uvicorn holds a read transaction at the same instant, VACUUM blocks. Worst case: VACUUM hangs forever or fails after busy_timeout. Should we:
          (i) Stop uvicorn before VACUUM (systemctl stop) — but then API is offline ~1-2 min during rebuild
          (ii) Use 'PRAGMA wal_checkpoint(TRUNCATE)' instead of VACUUM (cheaper, no exclusive lock if WAL mode)
          (iii) Skip VACUUM if a recent VACUUM ran (check sqlite_stat1 last update?)
          (iv) Set busy_timeout high (e.g. 30s) and let VACUUM retry naturally

      (b) detect_article_lang.py writes to articles.lang (UPDATE WHERE lang IS NULL). Concurrent with Hermes ingest cron (same host) — does ingest cron also write to articles? If yes, what's the lock interaction (likely fine since SQLite handles row-level via WAL, but state explicitly).

      (c) rebuild_fts.py — does it use BEGIN / COMMIT atomicity? CREATE TABLE temp + INSERT + RENAME pattern? Or DROP TABLE + CREATE? Latter creates a window where /api/search?mode=fts returns empty.

      (d) export_knowledge_base.py — read-only per EXPORT-02. Should be safe but verify no accidental writes (test fixture cleanup, unintended PRAGMA, etc.).

      (e) Lock contention with FTS5 rebuild + concurrent /api/search reads — does rebuild_fts hold a write lock long enough to block reads? If rebuild < 5s on 160 rows (kb-3-07 verified), tolerable, but document the window.

      (f) /var/log/kb-rebuild.log — disk-fill DOS? Add logrotate or use built-in size cap?

      (g) Crash recovery: if cron is killed mid-VACUUM, is the DB recoverable? (yes, SQLite VACUUM is atomic — but document the recovery procedure)

      (h) Should the cron exit code be checked? (yes — failed rebuild should not silently degrade FTS5 quality)

      (i) Order matters: VACUUM should be LAST (after rebuild_fts) — if VACUUM is before, it could invalidate FTS5 statistics that rebuild_fts is about to redo.

      Output: ordered list of (severity, finding, fix). Critical findings MUST be applied before script ships."
    )
    ```

    Step 3 — Apply Skill findings. Most likely outcomes:
    - VACUUM order = LAST (after rebuild_fts)
    - busy_timeout = 30000ms (30s) at start of script via sqlite3 PRAGMA
    - Use `wal_checkpoint(TRUNCATE)` BEFORE VACUUM (reclaim WAL frames first)
    - rebuild_fts.py uses CREATE temp + INSERT + DROP old + RENAME (atomic swap, not DROP-CREATE)
    - logrotate: use the script-side approach `[ -s /var/log/kb-rebuild.log ] && [ $(stat -c%s /var/log/kb-rebuild.log) -gt 10485760 ] && mv ... .1`

    Document Skill output verbatim in SUMMARY.
  </action>
  <verify>
    <automated>
      grep -c 'Skill(skill="database-reviewer"' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-04-SUMMARY.md  # ≥1
    </automated>
  </verify>
  <done>
    - SUMMARY contains literal Skill(skill="database-reviewer" invocation
    - Skill findings table (severity / finding / fix)
    - Script design decisions (VACUUM order, busy_timeout, log rotation) traced to specific Skill findings
  </done>
</task>

<task type="auto">
  <name>Task 2: Write daily_rebuild.sh applying database-reviewer findings</name>
  <files>kb/scripts/daily_rebuild.sh</files>
  <read_first>
    - kb/scripts/rebuild_fts.py (verify it's invocable as `python kb/scripts/rebuild_fts.py`)
    - kb/scripts/detect_article_lang.py (verify --idempotent default)
    - kb/export_knowledge_base.py (verify env-driven KB_OUTPUT_DIR)
    - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-04-SUMMARY.md (Skill findings from Task 1)
  </read_first>
  <action>
    Write `kb/scripts/daily_rebuild.sh` (POSIX bash, set -euo pipefail). Structure:

    ```bash
    #!/usr/bin/env bash
    # Daily KB rebuild: lang detect → SSG re-render → FTS5 rebuild → VACUUM.
    # Cron entry (recommended):
    #   0 12 * * * /opt/OmniGraph-Vault/kb/scripts/daily_rebuild.sh >> /var/log/kb-rebuild.log 2>&1
    set -euo pipefail

    # ---- Configuration ----
    : "${KB_INSTALL_PREFIX:=/opt/OmniGraph-Vault}"
    : "${KB_DB_PATH:=/home/kb/.hermes/data/kol_scan.db}"
    : "${KB_LOG:=/var/log/kb-rebuild.log}"
    : "${KB_PYTHON:=${KB_INSTALL_PREFIX}/venv/bin/python}"
    : "${KB_LOG_MAX_BYTES:=10485760}"  # 10 MiB before rotation

    # busy_timeout in ms — VACUUM + writes wait this long before erroring
    : "${KB_SQLITE_BUSY_TIMEOUT_MS:=30000}"

    cd "${KB_INSTALL_PREFIX}"

    log() { printf '[%s][daily-rebuild] %s\n' "$(date -Iseconds)" "$*"; }

    # ---- Phase 0: log rotation (manual, simple — keeps last 1) ----
    if [[ -f "${KB_LOG}" ]]; then
      LOG_SIZE=$(stat -c%s "${KB_LOG}" 2>/dev/null || echo 0)
      if (( LOG_SIZE > KB_LOG_MAX_BYTES )); then
        mv "${KB_LOG}" "${KB_LOG}.1"
        log "rotated log (was ${LOG_SIZE} bytes)"
      fi
    fi

    log "===== daily rebuild start ====="
    log "KB_DB_PATH=${KB_DB_PATH}"
    log "KB_INSTALL_PREFIX=${KB_INSTALL_PREFIX}"

    # ---- Phase 1: lang detect (idempotent — only fills NULL) ----
    log "[1/4] detect_article_lang"
    "${KB_PYTHON}" kb/scripts/detect_article_lang.py
    log "[1/4] OK"

    # ---- Phase 2: SSG re-render ----
    log "[2/4] export_knowledge_base"
    "${KB_PYTHON}" kb/export_knowledge_base.py
    log "[2/4] OK"

    # ---- Phase 3: FTS5 rebuild (atomic — CREATE temp + RENAME pattern) ----
    log "[3/4] rebuild_fts"
    "${KB_PYTHON}" kb/scripts/rebuild_fts.py
    log "[3/4] OK"

    # ---- Phase 4: WAL checkpoint + VACUUM (LAST, per database-reviewer Skill) ----
    log "[4/4] wal_checkpoint(TRUNCATE) + VACUUM"
    sqlite3 "${KB_DB_PATH}" <<SQL
.timeout ${KB_SQLITE_BUSY_TIMEOUT_MS}
PRAGMA wal_checkpoint(TRUNCATE);
VACUUM;
SQL
    log "[4/4] OK"

    log "===== daily rebuild complete ====="
    ```

    Run shellcheck on the file:
    ```
    shellcheck kb/scripts/daily_rebuild.sh
    ```
    (Or document deferred to Ubuntu host if Windows-side shellcheck unavailable.)

    SUMMARY must include:
    - shellcheck output (or deferred rationale)
    - Pipeline order rationale (why detect → export → rebuild_fts → VACUUM, traced to database-reviewer Skill output from Task 1)
    - Cron entry recommendation (recorded in script header comment + SUMMARY)
    - Manual smoke result: `bash kb/scripts/daily_rebuild.sh` against `.dev-runtime/data/kol_scan.db` (export KB_DB_PATH + KB_INSTALL_PREFIX appropriately)
  </action>
  <verify>
    <automated>
      test -f kb/scripts/daily_rebuild.sh
      bash -n kb/scripts/daily_rebuild.sh  # syntax
      grep -E 'set -euo pipefail' kb/scripts/daily_rebuild.sh
      grep -E 'detect_article_lang' kb/scripts/daily_rebuild.sh
      grep -E 'export_knowledge_base' kb/scripts/daily_rebuild.sh
      grep -E 'rebuild_fts' kb/scripts/daily_rebuild.sh
      grep -E 'VACUUM' kb/scripts/daily_rebuild.sh
      grep -E 'wal_checkpoint' kb/scripts/daily_rebuild.sh
      # VACUUM appears AFTER rebuild_fts (line order check)
      python -c "
lines = open('kb/scripts/daily_rebuild.sh').read().splitlines()
fts_line = next((i for i,l in enumerate(lines) if 'rebuild_fts' in l and not l.strip().startswith('#')), -1)
vac_line = next((i for i,l in enumerate(lines) if 'VACUUM' in l), -1)
assert fts_line < vac_line, f'rebuild_fts ({fts_line}) must precede VACUUM ({vac_line})'
print('order OK')
"
    </automated>
  </verify>
  <done>
    - kb/scripts/daily_rebuild.sh exists, bash-parseable, all 4 stages present
    - VACUUM after rebuild_fts (database-reviewer key finding)
    - Log rotation present (avoid disk-fill DOS)
    - busy_timeout set on sqlite3 invocation
    - Local smoke run against .dev-runtime DB succeeds (or documented deferral if blocked)
    - SUMMARY includes Skill invocation + findings + applied fixes table
  </done>
</task>

</tasks>

<verification>
- daily_rebuild.sh exists, executes 4 stages in correct order
- database-reviewer discipline floor met (≥1 SUMMARY contains Skill(skill="database-reviewer"))
- DEPLOY-04 satisfied
</verification>

<success_criteria>
- DEPLOY-04: Daily cron script chains detect → export → rebuild_fts → VACUUM idempotently
- database-reviewer findings (race conditions, atomicity, log rotation) addressed in script
</success_criteria>

<output>
After completion: `.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-04-SUMMARY.md`
</output>

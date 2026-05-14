---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 05
type: execute
wave: 3
depends_on: ["kb-4-01", "kb-4-02", "kb-4-03", "kb-4-04"]
files_modified:
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
  - .playwright-mcp/kb-4-uat-*.png  (Playwright screenshots — generated)
  - .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-05-SUMMARY.md
autonomous: false
requirements: [DEPLOY-05]  # Rule 3 mandatory Local UAT — runtime evidence for same-host deploy verification
must_haves:
  truths:
    - "Local single-port deploy via .scratch/local_serve.py runs successfully against .dev-runtime DB"
    - "All 5 SSG page types load: /, /articles/, /articles/{hash}.html, /topics/{slug}.html, /entities/{slug}.html, /ask/"
    - "All 6 API endpoints return expected shapes: /health, /api/articles, /api/article/{hash}, /api/search?mode=fts, /api/search?mode=kg + poll, /api/synthesize + poll"
    - "Playwright screenshots captured at 3 viewports (375 / 768 / 1280 px) for 5 page types = 15 total"
    - "Zero horizontal scroll on any captured viewport (visual verification per kb-1-UI-SPEC §UI-03 + kb-2-UI-SPEC + kb-3-UI-SPEC)"
    - "Browser console: no 404 for /static/* assets, no JS errors during interactive flows"
    - "If visual gap surfaces: ui-ux-pro-max + frontend-design Skills invoked + documented"
  artifacts:
    - path: ".planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md"
      provides: "Local UAT artifact per kb/docs/10-DESIGN-DISCIPLINE.md Rule 3"
      min_lines: 60
    - path: ".playwright-mcp/kb-4-uat-*.png"
      provides: "Playwright screenshot evidence × 15"
  key_links:
    - from: "kb-4-LOCAL-UAT.md"
      to: ".planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-VERIFICATION.md (kb-4-08)"
      via: "cited as 'Local UAT' section in VERIFICATION"
      pattern: "kb-4-LOCAL-UAT.md"
---

<objective>
Run the mandatory local UAT per `kb/docs/10-DESIGN-DISCIPLINE.md` **Rule 3** before kb-4 can be marked complete. This is **NOT** the same as the smoke scenarios (kb-4-06) — this is the broader endpoint-by-endpoint runtime exercise that surfaces the runtime-only issues that no test suite catches (stale assets, embedding-dim mismatch, schema drift, etc., as kb-3 case study showed).

For ANY visual gap surfaced during UAT, this plan invokes `ui-ux-pro-max` + `frontend-design` Skills to design + implement a proper fix — NOT a band-aid CSS override.

Purpose: Rule 3 mandatory artifact. No KB phase may close without Local UAT evidence.
Output: `kb-4-LOCAL-UAT.md` with curl + Playwright evidence + 15 screenshots + any gap-fix Skill invocations.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@kb/docs/10-DESIGN-DISCIPLINE.md
@.scratch/local_serve.py

@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md
@.planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-VERIFICATION.md

@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-HUMAN-UAT.md

<interfaces>
- Rule 3 (kb/docs/10-DESIGN-DISCIPLINE.md): mandatory local UAT before phase complete
- Local launcher: .scratch/local_serve.py (single-port, mounts SSG + /api/* + /static/img on :8766)
- Endpoint inventory (from kb-3-VERIFICATION):
  GET /health
  GET /api/articles?page=1&limit=20&source=&lang=&q=
  GET /api/article/{hash}
  GET /api/search?q=&mode=fts&lang=&limit=20
  GET /api/search?q=&mode=kg&lang= (returns 202 + job_id)
  GET /api/search/{job_id}
  POST /api/synthesize {question, lang}
  GET /api/synthesize/{job_id}
- Page inventory: /, /articles/, /articles/{hash}.html, /topics/, /topics/{slug}.html, /entities/, /entities/{slug}.html, /ask/
- Viewports: mobile=375, tablet=768, desktop=1280 (per kb-1 UI-03 + kb-3-UI-SPEC)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Pre-UAT setup — render SSG + populate FTS5 + start local server</name>
  <files>
    kb/output/  (regenerated)
    .scratch/kb-4-uat-prep.log
  </files>
  <read_first>
    - .scratch/local_serve.py
    - kb/scripts/daily_rebuild.sh (kb-4-04 — for prep equivalence)
  </read_first>
  <action>
    Step 1 — Verify .dev-runtime/data/kol_scan.db exists and is the latest snapshot (check `articles` row count, `lang` column non-NULL coverage). Document.

    Step 2 — Run the rebuild pipeline against .dev-runtime DB:
    ```bash
    export KB_DB_PATH="$(pwd)/.dev-runtime/data/kol_scan.db"
    export KB_IMAGES_DIR="$(pwd)/.dev-runtime/images"
    export KB_OUTPUT_DIR="$(pwd)/kb/output"

    venv/Scripts/python.exe kb/scripts/detect_article_lang.py
    venv/Scripts/python.exe kb/export_knowledge_base.py
    venv/Scripts/python.exe kb/scripts/rebuild_fts.py
    ```
    Capture stdout/stderr to `.scratch/kb-4-uat-prep.log`.

    Step 3 — Inventory the rendered output:
    ```bash
    ls kb/output/topics/*.html | wc -l        # expect 5
    ls kb/output/entities/*.html | wc -l      # expect ≥6 on dev fixture
    ls kb/output/articles/*.html | head -5    # sanity
    ```

    Step 4 — Start local_serve.py in background:
    ```bash
    venv/Scripts/python.exe .scratch/local_serve.py > .scratch/local_serve.log 2>&1 &
    LOCAL_PID=$!
    echo "$LOCAL_PID" > .scratch/local_serve.pid
    sleep 3  # uvicorn boot
    curl -fsS http://localhost:8766/health || { kill $LOCAL_PID; exit 1; }
    ```

    Document setup state in `.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md` "Setup" section.
  </action>
  <verify>
    <automated>
      test -f .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
      curl -fsS http://localhost:8766/health
      ls kb/output/topics/*.html | wc -l  # ≥5 (Agent/CV/LLM/NLP/RAG)
    </automated>
  </verify>
  <done>
    - SSG rendered against .dev-runtime DB
    - local_serve.py running (PID recorded)
    - /health returns 200
    - kb-4-LOCAL-UAT.md "Setup" section populated with row counts, page counts, env values
  </done>
</task>

<task type="auto">
  <name>Task 2: Curl smoke — all 6 API endpoint families + capture response shapes</name>
  <files>
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md  (extend with "API Smoke" section)
    .scratch/kb-4-curl-smoke.log
  </files>
  <action>
    For each endpoint, run curl + capture status + key response fields. Append to `kb-4-LOCAL-UAT.md` "API Smoke" section.

    ```bash
    BASE=http://localhost:8766
    LOG=.scratch/kb-4-curl-smoke.log
    : > "$LOG"

    # 1. /health
    echo "=== /health ===" >> "$LOG"
    curl -fsS "$BASE/health" | jq . >> "$LOG"

    # 2. GET /api/articles
    echo "=== /api/articles?limit=5 ===" >> "$LOG"
    RESP=$(curl -fsS "$BASE/api/articles?limit=5")
    echo "$RESP" | jq '{count: .items | length, total: .total, page: .page}' >> "$LOG"
    KNOWN_HASH=$(echo "$RESP" | jq -r '.items[0].hash')
    echo "KNOWN_HASH=$KNOWN_HASH" >> "$LOG"

    # 3. GET /api/article/{hash}
    echo "=== /api/article/$KNOWN_HASH ===" >> "$LOG"
    curl -fsS "$BASE/api/article/$KNOWN_HASH" | jq '{hash, title, lang, source, body_source}' >> "$LOG"

    # 4. GET /api/search?mode=fts (zh)
    echo "=== /api/search?q=langchain&mode=fts ===" >> "$LOG"
    curl -fsS "$BASE/api/search?q=langchain&mode=fts&limit=3" | jq '{count: .items | length, sample: .items[0]}' >> "$LOG"

    # 5. GET /api/search?mode=kg (async)
    echo "=== /api/search?q=...&mode=kg ===" >> "$LOG"
    JOB=$(curl -fsS "$BASE/api/search?q=AI%20Agent&mode=kg" | jq -r '.job_id')
    echo "kg job_id=$JOB" >> "$LOG"
    sleep 2
    curl -fsS "$BASE/api/search/$JOB" | jq '{status, has_result: (.result != null)}' >> "$LOG"

    # 6. POST /api/synthesize + poll
    echo "=== POST /api/synthesize ===" >> "$LOG"
    SJOB=$(curl -fsS -X POST "$BASE/api/synthesize" \
      -H 'Content-Type: application/json' \
      -d '{"question":"What is LangGraph?","lang":"en"}' | jq -r '.job_id')
    echo "synthesize job_id=$SJOB" >> "$LOG"
    # Poll up to 90s (likely fts5_fallback if no LightRAG storage on dev)
    for i in $(seq 1 30); do
      STATE=$(curl -fsS "$BASE/api/synthesize/$SJOB" | jq -r '.status')
      [[ "$STATE" == "done" || "$STATE" == "failed" ]] && break
      sleep 3
    done
    curl -fsS "$BASE/api/synthesize/$SJOB" | jq '{status, fallback_used, confidence, result_len: (.result.markdown | length // 0)}' >> "$LOG"
    ```

    For each endpoint, extract status code + key response fields into `kb-4-LOCAL-UAT.md` "API Smoke" markdown table:

    | Endpoint | Status | Key Fields | Notes |
    |---|---|---|---|
    | GET /health | 200 | {ok: true} | — |
    | GET /api/articles?limit=5 | 200 | items.length=5, total=160 | DATA-07 visibility ~6.4% |
    | ... | ... | ... | ... |

    Any non-2xx or unexpected shape — flag in "Issues" section + decide:
    - Hot-fix in scope (small contract drift)
    - Defer to follow-up (architectural)
    - Halt UAT and reopen the phase
  </action>
  <verify>
    <automated>
      grep '## API Smoke' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
      grep '| GET /health |' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
      grep '| GET /api/articles' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
      grep '| POST /api/synthesize' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
    </automated>
  </verify>
  <done>
    - kb-4-LOCAL-UAT.md "API Smoke" table populated for all 6 endpoint families
    - .scratch/kb-4-curl-smoke.log contains raw curl output
    - Any 4xx/5xx flagged in "Issues" section with disposition
  </done>
</task>

<task type="auto">
  <name>Task 3: Playwright UAT — 5 page types × 3 viewports = 15 screenshots + interactive flows</name>
  <files>
    .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md  (extend with "Playwright UAT" section)
    .playwright-mcp/kb-4-uat-*.png
  </files>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-HUMAN-UAT.md (kb-1 visual baseline pattern)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md  (token + component spec)
    - .planning/phases/kb-2-topic-pillar-entity-pages/kb-2-UI-SPEC.md
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md
  </read_first>
  <action>
    Use Playwright MCP tools (`mcp__playwright__browser_*`). For each (page × viewport) combination, capture:
    - Screenshot at fullPage=true
    - Browser console messages (any errors / 404s)
    - Network requests for /static/* (any 404)

    Page list:
    1. `/` (homepage)
    2. `/articles/` (article list)
    3. `/articles/{KNOWN_HASH}.html` (one article detail — use hash from Task 2)
    4. `/topics/agent.html` (topic pillar)
    5. `/entities/` (entity index) AND one `/entities/{slug}.html` (entity detail)
    6. `/ask/` (Q&A page)

    Viewport list: 375×667 (mobile), 768×1024 (tablet), 1280×800 (desktop).

    For each combination:
    ```python
    # Pseudocode using MCP tools:
    browser_navigate(url=f"http://localhost:8766/{page_path}")
    browser_resize(width=W, height=H)  # or set initial viewport
    browser_take_screenshot(fullPage=True, filename=f".playwright-mcp/kb-4-uat-{page}-{W}.png")
    msgs = browser_console_messages()  # check for errors
    reqs = browser_network_requests()  # filter /static/* 404s
    ```

    Interactive flows to exercise:
    - **Lang toggle**: on /, click 中/EN toggle → verify lang chip flip + cookie update + page chrome strings change
    - **Search inline reveal**: on /articles/, type "langchain" in search box → verify result reveal (no /search page nav per kb-3-UI-SPEC)
    - **Q&A submit**: on /ask/, type a question + lang=en → click submit → verify state matrix transitions (idle → submitting → polling → done OR fts5_fallback)
    - **Topic chip**: on /, click a topic chip → verify navigation to /topics/{slug}.html
    - **Entity chip on article detail**: on article page, click related-entity chip → verify nav to /entities/{slug}.html

    Capture interactive flow screenshots:
    - `.playwright-mcp/kb-4-uat-lang-toggle-zh.png` and `kb-4-uat-lang-toggle-en.png`
    - `.playwright-mcp/kb-4-uat-qa-submitting.png`, `kb-4-uat-qa-done.png` (or `kb-4-uat-qa-fts5_fallback.png`)

    Compare each captured screenshot against kb-1/kb-2/kb-3 baseline UAT screenshots (if available in .playwright-mcp/ from prior phases). Document any visible regression.

    Append to `kb-4-LOCAL-UAT.md` "Playwright UAT" section:

    | Page | Viewport | Screenshot | Console errors | /static 404s | Visual notes |
    |---|---|---|---|---|---|
    | / | 375 | kb-4-uat-home-375.png | 0 | 0 | OK |
    | / | 768 | kb-4-uat-home-768.png | 0 | 0 | OK |
    | ... | ... | ... | ... | ... | ... |

    **CONDITIONAL Skill invocation**: If any visual issue is observed (overflow, truncation, broken layout, missing logo even after kb-4-03 sourced it, lang chip not rendering, qa state not transitioning, etc.), invoke:

    ```
    Skill(
      skill="ui-ux-pro-max",
      args="Audit production-data-rendered Playwright screenshots from kb-4 UAT for the following observed issues: <list of specific issues with screenshot paths>. Reference baseline UI-SPECs: kb-1 §3 (chip + glow + icon), kb-2 §3 (topic + entity layouts), kb-3 §3 (Q&A 8-state matrix). For each issue, output: (severity, root cause, designed fix that preserves the locked token system, files-to-touch). Do NOT propose new :root vars unless absolutely unavoidable — kb-3-VERIFICATION confirmed 31 vars baseline preserved across all phases."
    )

    Skill(
      skill="frontend-design",
      args="Implement the ui-ux-pro-max fix recommendations into kb/templates/* and kb/static/style.css using the locked token set. Constraints: zero new :root vars (per UI-SPEC §2.1 hard rules), CSS LOC budget 2100 (kb-3 used 2099/2100 — any growth requires explicit justification). Output: file paths + diff range + verification grep."
    )
    ```

    If Skill is invoked: append "Visual Gap Fixes" subsection to kb-4-LOCAL-UAT.md with literal Skill block + applied fix table + screenshot proof of post-fix.
  </action>
  <verify>
    <automated>
      ls .playwright-mcp/kb-4-uat-*.png | wc -l  # ≥15 (5 pages × 3 viewports), more if interactive
      grep '## Playwright UAT' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
      grep '| / | 375 |' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
      grep '| /ask/' .planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-LOCAL-UAT.md
    </automated>
  </verify>
  <done>
    - ≥15 page screenshots captured + ≥4 interactive flow screenshots
    - kb-4-LOCAL-UAT.md "Playwright UAT" table populated
    - Console error / network 404 columns populated for each row
    - If visual issues observed: ui-ux-pro-max + frontend-design Skill blocks present in SUMMARY/UAT doc + post-fix screenshots
    - If no visual issues: explicit "no gaps observed; conditional Skill invocations not triggered" note
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4 (CHECKPOINT): User reviews Playwright screenshots + signs off Local UAT</name>
  <what-built>
    - 15+ Playwright screenshots in .playwright-mcp/kb-4-uat-*.png
    - kb-4-LOCAL-UAT.md with Setup + API Smoke + Playwright UAT sections
    - Any visual gaps fixed (with Skill invocation evidence)
  </what-built>
  <how-to-verify>
    1. Open .playwright-mcp/ folder + view all kb-4-uat-*.png files
    2. Skim kb-4-LOCAL-UAT.md "Issues" sections — confirm any flagged items resolved
    3. Verify subjectively that the rendered site matches kb-1/kb-2/kb-3 UI-SPEC intent (Swiss minimal dark, lang chips correctly colored, no horizontal scroll, no broken layouts)
    4. Type 'approved' to proceed; or describe issues for hot-fix loop
  </how-to-verify>
  <resume-signal>'approved' or list specific issues to fix</resume-signal>
</task>

</tasks>

<verification>
- kb-4-LOCAL-UAT.md exists with Setup, API Smoke, Playwright UAT, (optional) Visual Gap Fixes sections
- ≥15 Playwright screenshots in .playwright-mcp/
- User approval recorded in SUMMARY
- Rule 3 (10-DESIGN-DISCIPLINE) satisfied: phase has Local UAT evidence
</verification>

<success_criteria>
- Rule 3 mandatory artifact present + cited
- All endpoints + pages exercised in real runtime, not just TestClient
- Any visual gaps closed via proper ui-ux-pro-max + frontend-design Skill invocation (NOT band-aid CSS)
</success_criteria>

<output>
After completion: `.planning/phases/kb-4-ubuntu-deploy-cron-smoke/kb-4-05-SUMMARY.md` + `kb-4-LOCAL-UAT.md`
</output>

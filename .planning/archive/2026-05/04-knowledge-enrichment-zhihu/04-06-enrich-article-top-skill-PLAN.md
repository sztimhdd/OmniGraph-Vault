---
phase: 04-knowledge-enrichment-zhihu
plan: 06
type: execute
wave: 4
depends_on: [04-02, 04-03, 04-04, 04-05]
files_modified:
  - skills/enrich_article/SKILL.md
  - skills/enrich_article/README.md
autonomous: false
requirements: [D-01, D-02, D-03, D-07]
must_haves:
  truths:
    - "SKILL.md has valid Hermes frontmatter with name=enrich_article"
    - "SKILL.md body contains a for-loop instruction referencing /zhihu-haowen-enrich per question"
    - "SKILL.md body shells to python enrichment/extract_questions.py, then fetch_zhihu.py, then merge_and_ingest.py"
    - "No Python helper script is created (D-01/D-02: orchestration lives in Markdown)"
    - "Skill instructs the agent to parse stdout JSON from each helper to drive control flow (D-03)"
  artifacts:
    - path: "skills/enrich_article/SKILL.md"
      provides: "Top-level enrichment orchestrator — for-loop + 3 Python helpers"
      contains: "name: enrich_article"
      min_lines: 120
    - path: "skills/enrich_article/README.md"
      provides: "Human-facing doc"
      min_lines: 15
  key_links:
    - from: "skills/enrich_article/SKILL.md"
      to: "/zhihu-haowen-enrich child skill"
      via: "per-question invocation in skill body"
      pattern: "/zhihu-haowen-enrich"
    - from: "skills/enrich_article/SKILL.md"
      to: "python -m enrichment.extract_questions"
      via: "shell command in skill body"
      pattern: "python -m enrichment\\.extract_questions"
    - from: "skills/enrich_article/SKILL.md"
      to: "python -m enrichment.merge_and_ingest"
      via: "shell command in skill body"
      pattern: "python -m enrichment\\.merge_and_ingest"
---

<objective>
Create the top-level Hermes orchestration skill `enrich_article`. Per D-01,
this skill IS the orchestration — no Python orchestrator file. Its body
contains the per-question for-loop (D-02), invokes the child
`/zhihu-haowen-enrich` skill once per question, and shells to the three
Python helpers (extract_questions, fetch_zhihu, merge_and_ingest) in order.

Purpose: This is the skill the user (or the WeChat ingest flow in plan 07)
calls. It's the seam where Hermes takes over from Python.

Output: Complete skill directory at `skills/enrich_article/` with SKILL.md
and README.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-02-SUMMARY.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-03-SUMMARY.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-04-SUMMARY.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-05-SUMMARY.md
@skills/zhihu-haowen-enrich/SKILL.md
@skills/omnigraph_ingest/SKILL.md
@CLAUDE.md

<interfaces>
The three Python helpers this skill calls (all emit single-line JSON on stdout
per D-03):

1. `python -m enrichment.extract_questions <article_md_path> --hash <hash>`
   - OK:      `{"hash":"...","status":"ok","question_count":N,"artifact":"/path/to/questions.json"}`
   - Skipped: `{"hash":"...","status":"skipped","reason":"too_short","char_count":N}`
   - Error:   `{"hash":"...","status":"error","error":"..."}`

2. `python -m enrichment.fetch_zhihu <zhihu_url> --hash <hash> --q-idx <N>`
   - OK:    `{"hash":"...","q_idx":N,"status":"ok","md_path":"...","image_count":N}`
   - Error: `{"hash":"...","q_idx":N,"status":"error","error":"..."}`

3. `python -m enrichment.merge_and_ingest <hash> --article-path <path> --article-url <url>`
   - OK:    `{"hash":"...","status":"ok","enriched":2|-2,"question_count":N,"success_count":N,...}`
   - Error: `{"hash":"...","status":"error","error":"..."}`

Child skill (plan 05): `/zhihu-haowen-enrich`
- Inputs via env: ARTICLE_HASH, Q_IDX, QUESTION
- Output: writes haowen.json to $ENRICHMENT_DIR/<ARTICLE_HASH>/<Q_IDX>/haowen.json
- Skill does NOT return JSON — outer skill reads haowen.json from disk

Questions file shape (from extract_questions):
```json
{
  "hash": "abc123",
  "article_path": "/path/to/article.md",
  "questions": [
    {"question": "Q text", "context": "why gap"},
    ...
  ]
}
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 6.1: Create skills/enrich_article/SKILL.md</name>
  <files>skills/enrich_article/SKILL.md</files>
  <read_first>
    - skills/zhihu-haowen-enrich/SKILL.md (child skill — invocation name + input env vars)
    - skills/omnigraph_ingest/SKILL.md (frontmatter + decision-tree reference)
    - skills/hermes_claude_code_bridge/SKILL.md (multi-step orchestration in Markdown style reference)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-01, D-02, D-03, D-07
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §1 (skill-chaining via /skill-name + skill_view)
  </read_first>
  <action>
    Create `skills/enrich_article/SKILL.md` with this exact content:

    ```markdown
    ---
    name: enrich_article
    description: |
      Use this skill to enrich a WeChat article with 知乎 好问 AI-search insights
      BEFORE ingesting it into the OmniGraph-Vault knowledge graph. Trigger phrases
      include: "enrich this article", "do the full knowledge enrichment pass",
      "add this article with Zhihu enrichment".

      This skill orchestrates the complete per-article enrichment pipeline:

        1. Extract 1–3 under-documented questions from the article (Python helper
           `enrichment/extract_questions.py`, Gemini + Google Search grounding).
        2. For EACH question, invoke the `/zhihu-haowen-enrich` child skill to
           drive zhida.zhihu.com and get the AI summary + best-cited Zhihu URL.
        3. For EACH successful 好问 result, shell to `enrichment/fetch_zhihu.py`
           to fetch the full Zhihu answer (markdown + images).
        4. Shell to `enrichment/merge_and_ingest.py` to merge artifacts, ingest
           into LightRAG with D-08 metadata, and update SQLite status.

      Total runtime: up to ~10 minutes per article (3 questions × 180s + overhead).

      Do NOT use this skill when:
      - The user just wants un-enriched ingest (no Zhihu step) — call
        `omnigraph_ingest` directly instead. Note: per D-07 (Phase 4 policy),
        enrichment is the DEFAULT path for production ingest. Direct
        `omnigraph_ingest` without this skill is a debug-only escape hatch.
      - The article is < 2000 chars (the extract-questions helper will return
        `skipped` and no 好问 calls will happen; this skill still completes
        cleanly and calls merge_and_ingest with empty haowen_list → enriched=-1 or
        regular ingest path handled by the outer caller)
      - The article has already been enriched (articles.enriched = 2) — idempotency
        is handled by the caller, not this skill
    compatibility: |
      Requires: GEMINI_API_KEY, Python venv at $OMNIGRAPH_ROOT/venv, CDP-reachable
      Edge at $CDP_URL (for child skill), Hermes `send_message` tool (for login-wall
      recovery), Python helpers under enrichment/ package.
    metadata:
      openclaw:
        os: ["linux", "darwin"]
        requires:
          bins: ["python", "bash"]
          config: ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "CDP_URL"]
    ---

    # enrich_article

    **Purpose**: End-to-end Zhihu-enriched ingest of ONE WeChat article.

    ## Inputs

    | Variable | Required | Source |
    |----------|----------|--------|
    | `ARTICLE_PATH` | yes | Local path to the scraped WeChat MD file (typically `~/.hermes/omonigraph-vault/images/<hash>/final_content.md`) |
    | `ARTICLE_URL` | yes | Original WeChat URL (used for SQLite updates) |
    | `ARTICLE_HASH` | optional | md5[:10] of article bytes; derived automatically if omitted |
    | `ENRICHMENT_DIR` | optional | Defaults to `~/.hermes/omonigraph-vault/enrichment` |

    ## Decision Tree

    ### Step 1 — Extract questions

    Shell:

    ```bash
    cd $OMNIGRAPH_ROOT
    source venv/bin/activate 2>/dev/null || source venv/Scripts/activate
    python -m enrichment.extract_questions "$ARTICLE_PATH" --hash "$ARTICLE_HASH"
    ```

    The helper prints a single-line JSON to stdout. Parse the JSON.

    #### Branch — `status == "skipped"` (article too short)

    The article is under the `ENRICHMENT_MIN_LENGTH` threshold. Skip directly to
    **Step 4: Merge & ingest** (with `success_count=0`; merge_and_ingest will
    handle the empty-haowen path). No questions to ask → no child-skill calls.

    Do NOT mark as failure. The outer caller (e.g., ingest_wechat.py) decides
    whether this article gets `enriched=-1` or passes through a regular ingest.

    #### Branch — `status == "error"`

    Report the error to the user and HALT. Do NOT proceed to Step 4 (no
    questions.json to merge from). This protects the SQLite state — article stays
    `enriched=0` (pending) and is eligible for retry.

    #### Branch — `status == "ok"`

    The output `artifact` path points to
    `$ENRICHMENT_DIR/$ARTICLE_HASH/questions.json`.

    Read the file. Extract the `questions` array (list of `{question, context}`
    dicts). Note the length N (will be 1–3).

    ### Step 2 — Per-question 好问 + Zhihu fetch (FOR LOOP)

    For each question Q at index Q_IDX in `0..N-1`:

    #### 2a — Invoke `/zhihu-haowen-enrich` child skill

    Invoke the child skill, passing the question text and context via environment:

    - Set `ARTICLE_HASH = $ARTICLE_HASH`
    - Set `Q_IDX = <current index>`
    - Set `QUESTION = <question text>`

    Then execute `/zhihu-haowen-enrich`.

    After the child skill returns, read the file
    `$ENRICHMENT_DIR/$ARTICLE_HASH/$Q_IDX/haowen.json`:

    - If file contains `{question, summary, best_source_url, timestamp}` →
      success for this question. Continue to 2b.
    - If file contains `{question, error, timestamp}` → this question failed.
      SKIP 2b for this index; move on to the next question.
    - If file is missing entirely → treat as failure, log "haowen.json not
      produced for q_idx=<N>" to stderr, continue to next question.

    #### 2b — Fetch the Zhihu source article (only if 2a succeeded)

    Shell:

    ```bash
    python -m enrichment.fetch_zhihu "$BEST_SOURCE_URL" \
      --hash "$ARTICLE_HASH" --q-idx "$Q_IDX"
    ```

    where `$BEST_SOURCE_URL` is the value from the haowen.json `best_source_url`
    field.

    Parse the single-line JSON stdout:

    - `status == "ok"` → great, Zhihu MD is on disk at `md_path`. Continue loop.
    - `status == "error"` → log the error to stderr, continue loop. The question
      still counts as partial-success for merge (summary was captured, just the
      deep-fetch failed).

    **Loop iteration budget**: the outer agent has `max_turns=90`. Each iteration
    consumes ~15–20 turns. Budget: 3 × 20 = 60 turns for the loop, leaving margin
    for steps 1, 3, and 4.

    ### Step 3 — (no-op — all per-question work done in step 2)

    ### Step 4 — Merge & ingest

    Shell:

    ```bash
    python -m enrichment.merge_and_ingest "$ARTICLE_HASH" \
      --article-path "$ARTICLE_PATH" \
      --article-url "$ARTICLE_URL"
    ```

    Parse the single-line JSON stdout:

    - `status == "ok"` with `enriched == 2` → full or partial success. Report to
      user: "Article enriched with <success_count>/<question_count> questions.
      Ingested to LightRAG as 1 enriched WeChat doc + <zhihu_docs_ingested> Zhihu
      child docs."
    - `status == "ok"` with `enriched == -2` → all questions failed but the
      un-enriched WeChat MD was ingested. Report: "Article ingested without
      enrichment (all 3 Zhihu searches failed). SQLite status: enriched=-2;
      re-enrichable later."
    - `status == "error"` → CRITICAL: ingestion failed. Report the error to the
      user, recommend inspecting `$ENRICHMENT_DIR/$ARTICLE_HASH/` for artifacts
      and `~/.hermes/omonigraph-vault/lightrag_storage/` for state.

    ## Error Handling Summary

    | At step | Error | User-facing response |
    |---------|-------|----------------------|
    | 1 | `extract_questions` error | "⚠️ Question extraction failed: <error>. Article unchanged. Retry after fix." |
    | 1 | `extract_questions` skipped | "ℹ️ Article too short (<2000 chars); proceeding to un-enriched ingest." → Step 4 |
    | 2a | child skill error (haowen.json has error field) | silent — question abandoned, loop continues |
    | 2a | child skill didn't produce file | "⚠️ /zhihu-haowen-enrich produced no output for q_idx=<N>." — loop continues |
    | 2b | `fetch_zhihu` error | silent — question still partial-success, loop continues |
    | 4 | `merge_and_ingest` error | "⚠️ Ingest failed: <error>. Inspect enrichment dir. SQLite: article remains enriched=0 (pending). Eligible for retry." |

    ## Output Format (Success)

    ```
    Starting enrichment — up to 10 minutes for 3 questions...
    Extracted N questions from article.
    Question 1: <text> ... ✓ haowen found, ✓ Zhihu fetched
    Question 2: <text> ... ✗ 好问 timeout, skipped
    Question 3: <text> ... ✓ haowen found, ✓ Zhihu fetched
    Merging and ingesting...
    ✅ Article enriched (2/3 questions). LightRAG: 1 WeChat + 2 Zhihu docs. enriched=2.
    ```

    ## Privacy Note

    All artifacts stored locally under `$ENRICHMENT_DIR`. External API calls:
    Gemini (question extraction + image vision), Zhihu (content fetch only, no
    auth data leaves the machine), Telegram bot (QR image only, if login-wall
    fires).

    ## Related Skills

    - Child: `/zhihu-haowen-enrich` (invoked N times inside Step 2a)
    - Alternative: `omnigraph_ingest` — un-enriched ingest (debug-only per D-07)
    - Follow-on: `omnigraph_query` — query the enriched graph
    ```

    Make sure no `scripts/` directory is created — per D-01 this skill is pure
    orchestration in Markdown.
  </action>
  <verify>
    <automated>test -f skills/enrich_article/SKILL.md && ! test -d skills/enrich_article/scripts</automated>
  </verify>
  <acceptance_criteria>
    - File `skills/enrich_article/SKILL.md` exists
    - `grep -q "^name: enrich_article$" skills/enrich_article/SKILL.md` succeeds
    - `grep -q "/zhihu-haowen-enrich" skills/enrich_article/SKILL.md` succeeds
    - `grep -q "python -m enrichment.extract_questions" skills/enrich_article/SKILL.md` succeeds
    - `grep -q "python -m enrichment.fetch_zhihu" skills/enrich_article/SKILL.md` succeeds
    - `grep -q "python -m enrichment.merge_and_ingest" skills/enrich_article/SKILL.md` succeeds
    - `grep -q "haowen.json" skills/enrich_article/SKILL.md` succeeds
    - `grep -Eq "enriched *== *2|enriched == -2" skills/enrich_article/SKILL.md` succeeds (D-07 state handling documented)
    - `grep -q "status.*skipped" skills/enrich_article/SKILL.md` succeeds (D-07 short-article branch)
    - `test ! -d skills/enrich_article/scripts` (D-01: no shell helper)
    - `wc -l skills/enrich_article/SKILL.md` >= 120
  </acceptance_criteria>
  <done>Top-level orchestrator skill exists with 4-step decision tree and D-07 state handling</done>
</task>

<task type="auto">
  <name>Task 6.2: Create skills/enrich_article/README.md</name>
  <files>skills/enrich_article/README.md</files>
  <read_first>
    - skills/enrich_article/SKILL.md (just-created; README points to its decision tree)
    - skills/zhihu-haowen-enrich/README.md (pattern reference)
  </read_first>
  <action>
    Create `skills/enrich_article/README.md`:

    ```markdown
    # enrich_article (Hermes skill)

    End-to-end Zhihu-enriched ingest of a WeChat article. Orchestrates:
    1. Question extraction (Gemini + Google Search grounding)
    2. Per-question `/zhihu-haowen-enrich` child skill invocation
    3. Per-question `fetch_zhihu.py` deep-fetch
    4. `merge_and_ingest.py` → LightRAG + SQLite

    Phase 4 of the OmniGraph-Vault knowledge pipeline.

    ## Install

    1. `./deploy.sh` from the repo root (syncs this skill to remote)
    2. Hermes discovers the skill via `skills.external_dirs`
    3. Restart: `hermes gateway restart` or `/new` in chat

    ## Usage

    Trigger: "enrich this article" + `ARTICLE_URL` / `ARTICLE_PATH`

    Runtime: ~10 minutes per article (3 questions × ~3 min each).

    ## Design Notes

    Per D-01, ALL orchestration lives in this Markdown SKILL.md — there is no
    Python `orchestrator.py` or `run_enrichment.py`. The Python helpers
    (`enrichment/extract_questions.py`, `enrichment/fetch_zhihu.py`,
    `enrichment/merge_and_ingest.py`) are pure deterministic subprocesses with
    no Hermes awareness.

    The per-question for-loop is a natural-language instruction that the
    Hermes agent interprets across 3 iterations. Total turn budget ~60 (fits
    under max_turns=90).

    ## Testing

    REMOTE-ONLY. There is no unit-test path for the orchestration itself — it
    is a Hermes-agent-driven flow. Integration test:

    ```bash
    ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST
    cd ~/OmniGraph-Vault
    # From Hermes chat:
    /enrich_article ARTICLE_URL=https://mp.weixin.qq.com/s/... ARTICLE_PATH=/path/to/final_content.md
    ```

    Then verify in `~/.hermes/omonigraph-vault/enrichment/<hash>/` that questions.json
    and <q_idx>/haowen.json were written, and SQLite articles.enriched = 2 or -2.

    ## Related

    - Child skill: `/zhihu-haowen-enrich` (invoked per question)
    - Python helpers: `enrichment/extract_questions.py`, `enrichment/fetch_zhihu.py`, `enrichment/merge_and_ingest.py`
    - Alternative: `omnigraph_ingest` (un-enriched; debug-only)
    ```
  </action>
  <verify>
    <automated>test -f skills/enrich_article/README.md && grep -q "REMOTE-ONLY" skills/enrich_article/README.md</automated>
  </verify>
  <acceptance_criteria>
    - File `skills/enrich_article/README.md` exists
    - `grep -q "/zhihu-haowen-enrich" skills/enrich_article/README.md` succeeds
    - `grep -q "extract_questions\|fetch_zhihu\|merge_and_ingest" skills/enrich_article/README.md` succeeds
    - `grep -q "REMOTE-ONLY" skills/enrich_article/README.md` succeeds
  </acceptance_criteria>
  <done>README explains skill purpose, install, and remote-only test flow</done>
</task>

</tasks>

<verification>
  - Both SKILL.md and README.md present in skills/enrich_article/
  - No scripts/ subdirectory (D-01 compliance)
  - SKILL.md has 4 decision-tree steps + all three shell commands + child-skill invocation
</verification>

<success_criteria>
- Top-level orchestrator exists as pure Markdown (D-01)
- Per-question for-loop lives in skill body (D-02)
- D-03 stdout contracts documented for each shell command
- D-07 state handling covered (ok → 2, all-fail → -2, too-short → skipped path)
- Child skill invocation via `/zhihu-haowen-enrich`
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-06-SUMMARY.md`.
</output>

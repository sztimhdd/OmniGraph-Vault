---
phase: 04-knowledge-enrichment-zhihu
plan: 05
type: execute
wave: 4
depends_on: [04-00]
files_modified:
  - skills/zhihu-haowen-enrich/SKILL.md
  - skills/zhihu-haowen-enrich/README.md
  - skills/zhihu-haowen-enrich/references/flow.md
autonomous: false
requirements: [D-02, D-03, D-13]
must_haves:
  truths:
    - "SKILL.md has valid Hermes frontmatter with name, description, compatibility, metadata"
    - "SKILL.md body documents the 10-step Zhihu 好问 CDP flow in prose"
    - "SKILL.md body includes the D-13 login-wall Telegram recovery branch using send_message + MEDIA:"
    - "SKILL.md body instructs the agent to write haowen.json at $ENRICHMENT_DIR/<hash>/<q_idx>/"
    - "No Python helper script is created (D-02: pure skill, CDP + skill_view only)"
    - "Manual integration test on remote Hermes confirms agent can invoke the skill and it produces haowen.json"
  artifacts:
    - path: "skills/zhihu-haowen-enrich/SKILL.md"
      provides: "Hermes skill body — 10-step CDP flow + login recovery"
      contains: "name: zhihu-haowen-enrich"
      min_lines: 100
    - path: "skills/zhihu-haowen-enrich/README.md"
      provides: "Human-facing doc: install, test, edge cases"
      min_lines: 20
    - path: "skills/zhihu-haowen-enrich/references/flow.md"
      provides: "Reference: per-step selector strategy + fallback decision tree"
      min_lines: 50
  key_links:
    - from: "skills/zhihu-haowen-enrich/SKILL.md"
      to: "Hermes send_message tool with MEDIA: attachment"
      via: "login-wall branch in skill body"
      pattern: "MEDIA:"
    - from: "skills/zhihu-haowen-enrich/SKILL.md"
      to: "$ENRICHMENT_DIR/<hash>/<q_idx>/haowen.json"
      via: "write-to-disk instruction at skill output"
      pattern: "haowen.json"
---

<objective>
Create the Zhihu 好问 Hermes skill. This is a pure-Markdown skill — no Python
helper — that instructs the Hermes agent to drive zhida.zhihu.com through the
10-step CDP flow (RESEARCH.md §2), extract the AI summary and best-source URL,
handle the login-wall via Telegram (D-13), and write the result to disk.

Purpose: The top-level `enrich_article` skill (plan 06) invokes this skill
once per question via `/zhihu-haowen-enrich`. D-02 mandates the per-question
loop lives in Hermes, not Python.

Output: Complete skill directory at `skills/zhihu-haowen-enrich/` with
SKILL.md, README.md, and a `references/flow.md` for step-by-step selector
strategy.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-00-SUMMARY.md
@skills/omnigraph_ingest/SKILL.md
@skills/hermes_claude_code_bridge/SKILL.md
@CLAUDE.md

<interfaces>
RESEARCH.md §2 10-step flow (repeated here for direct reference):

| Step | Action | Wait | Failure recovery |
|------|--------|------|------------------|
| 1 | browser_navigate https://zhida.zhihu.com/ | `load` | Telegram notify, abort question |
| 2 | Detect login wall | 2s | **D-13**: screenshot QR, send_message MEDIA:, wait /resume |
| 3 | Find search entry (contenteditable / role=searchbox) | visible+enabled | Probe DOM; abort |
|| 4 | Enter question text | text visible | **DO NOT use document.execCommand or innerText manipulation — Draft.js rejects synthetic input (verified failure, 2026-04-27). Working methods:** (A) Click the "新对话" button → bottom input area becomes available for browser_type; (B) Click on a prior search entry in left sidebar history → re-triggers that search. Fallback: if neither works, manually position and use browser_press to type character-by-character. |
| 5 | Submit (Enter key or 搜索 button) | URL/panel change | Retry once |
| 6 | Wait for AI summary (sentinel "完成回答") | ≤120s | Timeout → mark failed |
| 7 | Extract summary (innerText of main article) | — | Empty → failed |
| 8 | Expand 全部来源 panel | cards render | No panel → failed |
| 9 | Pick best source card (title match + engagement) | parsed | No card → failed |
|| 10 | Click card → read location.href | valid Zhihu answer URL | Ad URL → failed |
||      | **IMPORTANT:** Source panel cards are React components, NOT `<a>` tags. |  |  |
||      | The URL is NOT in the DOM. You MUST click the card, wait for |  |  |
||      | navigation, then capture `window.location.href`. |  |  |

D-13 Telegram recovery (RESEARCH.md §6):
- Screenshot QR element → save to `$ENRICHMENT_DIR/$HASH/$Q_IDX/zhihu_login_qr.png`
- Call native Hermes tool `send_message` with body starting `MEDIA:<qr_path>\n\n<msg>`
- Wait for user `/resume` (standard Hermes pause pattern, no custom code)
- On resume, reload + retry from step 3

D-03 output contract:
- On success: write `$ENRICHMENT_DIR/$HASH/$Q_IDX/haowen.json`
  ```json
  {"question": "<input>", "summary": "<ai summary>", "best_source_url": "<url>", "timestamp": "<ISO>"}
  ```
- On failure: write the same file with `{"question": "<input>", "error": "<reason>", "timestamp": "<ISO>"}`
- Per D-02/D-03, the skill does NOT print JSON to stdout — the outer skill reads haowen.json from disk after the child skill returns.

Frontmatter pattern (from skills/omnigraph_ingest/SKILL.md):
```yaml
---
name: zhihu-haowen-enrich
description: |
  [long-form, includes trigger phrases and "do not use when" clauses]
compatibility: |
  Requires: CDP-reachable Edge browser...
metadata:
  openclaw:
    os: ["linux"]   # remote-only
    requires:
      bins: ["python"]
      config: ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN"]
---
```

Note: `name` uses dashes `zhihu-haowen-enrich` (matches the `/skill-name`
invocation convention from RESEARCH.md §1).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 5.1: Create skills/zhihu-haowen-enrich/SKILL.md (Hermes skill body)</name>
  <files>skills/zhihu-haowen-enrich/SKILL.md</files>
  <read_first>
    - skills/omnigraph_ingest/SKILL.md (frontmatter + decision-tree style reference)
    - skills/hermes_claude_code_bridge/SKILL.md (decision-tree style reference — similar orchestration flavor)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §2 (10-step flow), §6 (Telegram MEDIA: convention)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md D-02, D-03, D-13
  </read_first>
  <action>
    Create `skills/zhihu-haowen-enrich/SKILL.md`. The skill body is pure Markdown
    agent instructions — no shell scripts invoked. The agent drives browser_cdp
    directly per the 10-step flow. Exact content:

    ```markdown
    ---
    name: zhihu-haowen-enrich
    description: |
      Use this skill when the orchestrator (typically the `enrich_article` skill)
      asks for a Zhihu 好问 AI-synthesized answer for a single technical question.
      Trigger: the outer skill body invokes `/zhihu-haowen-enrich` with one argument —
      the question text (Chinese ok).

      This skill drives zhida.zhihu.com through a 10-step CDP flow using the
      `browser_navigate`, `browser_evaluate`, and `browser_click` tools, extracts the
      AI summary + best-cited Zhihu source URL, and writes the result to
      `$ENRICHMENT_DIR/<article_hash>/<q_idx>/haowen.json`.

      The skill is ALSO responsible for login-wall recovery: if Zhihu shows a QR
      login screen, the skill screenshots the QR, sends it to the user via the
      `send_message` Telegram tool using the `MEDIA:<path>` convention, and pauses
      for a user `/resume` reply. On resume, it retries from step 3.

      Do NOT use this skill for:
      - WeChat article ingestion (use `omnigraph_ingest`)
      - General web scraping (no CDP orchestration outside the 好问 flow)
      - Asking the user a question (this skill runs unattended; user interaction
        only via the login-wall Telegram branch)
    compatibility: |
      Requires: CDP-reachable Edge browser at CDP_URL (default http://localhost:9223),
      Zhihu session cookies (or user scans QR via Telegram), Hermes `send_message` tool,
      environment variables ARTICLE_HASH and Q_IDX passed by the outer skill.
    metadata:
      openclaw:
        os: ["linux", "darwin"]
        requires:
          bins: ["python"]
          config: ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "CDP_URL"]
    ---

    # zhihu-haowen-enrich

    **Purpose**: For ONE question, drive zhida.zhihu.com, extract the AI summary and
    best-cited Zhihu source URL, write `haowen.json` to disk. Called by the
    `enrich_article` skill, once per question.

    ## Inputs (read from outer-skill environment)

    | Variable | Required | Purpose |
    |----------|----------|---------|
    | `ARTICLE_HASH` | yes | WeChat article hash (determines output subdirectory) |
    | `Q_IDX` | yes | Question index (0, 1, or 2) |
    | `QUESTION` | yes | The question text to search on 好问 |
    | `ENRICHMENT_DIR` | optional | Override base dir; defaults to `~/.hermes/omonigraph-vault/enrichment` |

    If any required variable is missing, write an error haowen.json and return.

    ## Output

    Always writes a single file: `$ENRICHMENT_DIR/$ARTICLE_HASH/$Q_IDX/haowen.json`.

    On success:
    ```json
    {
      "question": "<input QUESTION>",
      "summary": "<AI-synthesized answer text>",
      "best_source_url": "<https://www.zhihu.com/question/.../answer/... OR https://zhuanlan.zhihu.com/p/...>",
      "timestamp": "<ISO 8601 UTC>"
    }
    ```

    On failure (any step):
    ```json
    {
      "question": "<input QUESTION>",
      "error": "<short reason: login_wall_timeout | search_failed | ai_timeout | no_sources | bad_url | ...>",
      "timestamp": "<ISO 8601 UTC>"
    }
    ```

    ## Decision Tree

    ### Step 1 — Navigate

    Use `browser_navigate` to `https://zhida.zhihu.com/`. Wait for the `load` event.

    On network error or CN-block: write failure haowen.json with
    `error: "navigation_failed: <message>"` and return.

    ### Step 2 — Login-wall detection (D-13)

    Wait 2 seconds for page to stabilize, then check:

    - Is the current URL `zhihu.com/signin` or `zhihu.com/login`?
    - Is there a visible element with text "登录" inside a modal?
    - Is there a visible QR-code image element (aspect ratio ~1:1)?

    If ANY of the above is true → login wall detected:

    1. Use `browser_evaluate` with a screenshot-of-element script to save the QR to
       `$ENRICHMENT_DIR/$ARTICLE_HASH/$Q_IDX/zhihu_login_qr.png`. Ensure the directory
       exists first.
    2. Call the `send_message` tool with this exact message body:
       ```
       MEDIA:<absolute path to zhihu_login_qr.png>

       Zhihu login expired on the remote browser. Scan the QR on your phone with
       the Zhihu mobile app to re-authenticate, then reply `/resume` to continue
       enrichment for question: "<QUESTION>".
       ```
       Use the default `send_message` target (Hermes resolves via
       `_get_cron_auto_delivery_target`; FR-20 default).
    3. Pause and wait for user `/resume`. This is the standard Hermes pause pattern
       — do not implement custom polling.
    4. On resume, reload the page (`browser_navigate` same URL) and continue from
       step 3 below.

    If the login wall persists after resume (QR scan didn't work, or user canceled),
    write failure haowen.json with `error: "login_wall_timeout"` and return.

    ### Step 3 — Find search entry

    Use role-based querying (NOT CSS selectors — Zhihu uses auto-generated class hashes):
    - Query for an element with role=searchbox OR a contenteditable div (Draft.js editor).
    - Wait until the element is visible AND enabled.

    If not found after 10 seconds: write failure haowen.json with
    `error: "search_entry_not_found"` and return.

    ### Step 4 — Enter question text

    Focus the editor. Draft.js does not accept direct `value=` assignment. Use one
    of these approaches in order:

    1. Call `document.execCommand('insertText', false, <QUESTION>)`
    2. Simulate keystrokes via `browser_evaluate` + InputEvent dispatching
    3. As a last resort, click a historical-search entry if `<QUESTION>` matches.

    Verify the text appears in the editor before proceeding.

    ### Step 5 — Submit

    Press Enter, OR click the element with text "搜索" / role=button. Wait for a
    URL or panel change.

    If submit does nothing after 2 attempts: failure, `error: "submit_ignored"`.

    ### Step 6 — Wait for AI summary

    Poll the page for the sentinel text `完成回答` (AI-generation complete) OR a
    streaming-complete DOM state. Timeout: 120 seconds
    (env `ENRICHMENT_HAOWEN_TIMEOUT`, default 120).

    If timeout reached: failure, `error: "ai_summary_timeout"`.

    ### Step 7 — Extract summary

    Use `browser_evaluate`:
    ```js
    document.querySelector('[role=main] article').innerText
    ```
    Or a broader selector if that's empty. Verify the summary is non-empty
    and doesn't contain error/placeholder text.

    ### Step 8 — Expand source panel

    Find and click an element with text matching `/全部来源\s*\d+/` (or
    `查看全部来源`, `展开来源`). Wait for source cards to render.

    If no source panel: failure, `error: "no_sources"`.

    ### Step 9 — Pick best source card

    Parse the visible source cards. Heuristic (in order):
    1. Title contains ≥1 keyword from `<QUESTION>` (tokenize on whitespace + jieba
       if available)
    2. Highest combined 点赞 + 关注 count
    3. Falls back to the first card

    ### Step 10 — Click card → extract final URL

    Click the chosen card. Wait for navigation or for a new tab. Read
    `window.location.href` (or the newly opened tab's URL).

    Validate: the URL must match `zhihu.com/question/.../answer/...` or
    `zhuanlan.zhihu.com/p/...`. If it's an ad URL or a non-Zhihu domain:
    failure, `error: "bad_source_url: <url>"`.

    ### Finalize

    Write `haowen.json` to `$ENRICHMENT_DIR/$ARTICLE_HASH/$Q_IDX/haowen.json` with
    fields per the Output section above. Include the ISO 8601 UTC timestamp.

    The outer `enrich_article` skill reads this file after this skill returns.

    ## Error Handling Summary

    | Error code | When |
    |------------|------|
    | `navigation_failed` | Step 1 network/CN block |
    | `login_wall_timeout` | Step 2 — Telegram retry failed |
    | `search_entry_not_found` | Step 3 — DOM pattern drifted |
    | `question_input_failed` | Step 4 — editor rejected text |
    | `submit_ignored` | Step 5 |
    | `ai_summary_timeout` | Step 6 — >120s |
    | `empty_summary` | Step 7 |
    | `no_sources` | Step 8 |
    | `no_source_cards` | Step 9 |
    | `bad_source_url: <url>` | Step 10 |

    All errors are WRITTEN to haowen.json; the skill itself exits cleanly so the
    outer skill's for-loop keeps iterating.

    ## References

    See `references/flow.md` for per-step selector strategy + empirical refinements
    captured during real-world runs.

    ## Related Skills

    - Orchestrator: `enrich_article` (calls this skill once per question)
    - Related Python helpers: `enrichment/fetch_zhihu.py` (runs AFTER this skill, on
      the resulting best_source_url)
    ```

    (Exact content above — copy verbatim.)
  </action>
  <verify>
    <automated>test -f skills/zhihu-haowen-enrich/SKILL.md && grep -q "^name: zhihu-haowen-enrich$" skills/zhihu-haowen-enrich/SKILL.md</automated>
  </verify>
  <acceptance_criteria>
    - File `skills/zhihu-haowen-enrich/SKILL.md` exists
    - `grep -q "^name: zhihu-haowen-enrich$" skills/zhihu-haowen-enrich/SKILL.md` succeeds
    - `grep -q "MEDIA:" skills/zhihu-haowen-enrich/SKILL.md` succeeds (D-13 recovery)
    - `grep -q "haowen.json" skills/zhihu-haowen-enrich/SKILL.md` succeeds
    - `grep -q "ARTICLE_HASH" skills/zhihu-haowen-enrich/SKILL.md` succeeds
    - `grep -q "Q_IDX" skills/zhihu-haowen-enrich/SKILL.md` succeeds
    - `grep -q "完成回答" skills/zhihu-haowen-enrich/SKILL.md` succeeds (step 6 sentinel)
    - `grep -c "Step [0-9]" skills/zhihu-haowen-enrich/SKILL.md` returns >= 10 (all 10 steps present)
    - `wc -l skills/zhihu-haowen-enrich/SKILL.md` >= 100
    - No `scripts/` directory inside the skill (D-02: pure Markdown, no shell helper): `test ! -d skills/zhihu-haowen-enrich/scripts`
  </acceptance_criteria>
  <done>SKILL.md exists with correct frontmatter, 10-step flow, D-13 recovery, disk-output contract</done>
</task>

<task type="auto">
  <name>Task 5.2: References + README</name>
  <files>skills/zhihu-haowen-enrich/references/flow.md, skills/zhihu-haowen-enrich/README.md</files>
  <read_first>
    - skills/zhihu-haowen-enrich/SKILL.md (just-created; references point back to its step numbers)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §2 probes list (questions to answer during first remote run)
  </read_first>
  <action>
    Create `skills/zhihu-haowen-enrich/references/flow.md` (loaded at agent Level 2 via `skill_view(name, file_path)`):

    ```markdown
    # Zhihu 好问 CDP Flow — Empirical Reference

    This document captures per-step selector strategy and empirical findings from
    real-world runs. Update after every skill invocation that reveals new DOM
    behavior.

    ## First-run probes (PRD §7 / RESEARCH.md §2)

    On the FIRST invocation of this skill on remote, capture these observations to
    refine the selectors:

    1. Does the search entry appear immediately, or behind a "search" button click?
    2. Is the Draft.js contenteditable div reachable via role=`textbox` or `searchbox`?
    3. What exact DOM pattern marks "AI summary generation complete"? (e.g. is
       there a `.is-complete` class, a CSS property transition, or only the
       `完成回答` text sentinel?)
    4. What text pattern identifies the sources-panel trigger? `全部来源 N`,
       `查看全部来源`, `展开来源`?
    5. What is the realistic AI-generation latency distribution? If p95 exceeds
       120s, raise `ENRICHMENT_HAOWEN_TIMEOUT`.

    Record answers inline in this file after each run (append, don't overwrite).

    ## Login-wall heuristic (Step 2)

    Login wall detected IF any of:
    - URL contains `/signin` or `/login`
    - Visible element with text `登录` inside a modal layer (not a regular link)
    - Visible image with aspect ratio ~1:1 and `alt` or data attribute containing
      `qr` / `扫码`

    False positives (do NOT treat as login wall):
    - Top-bar `登录` button (always present for logged-out UI but doesn't block usage)
    - Hidden login modal that never rendered

    ## Draft.js input (Step 4)

    Known-working insertion methods (in priority order):

    1. `document.execCommand('insertText', false, <QUESTION>)` — works in most
       Chromium versions
    2. `contenteditable_div.focus()` + InputEvent dispatch with
       `{inputType: 'insertText', data: <QUESTION>, bubbles: true}`
    3. Simulate keystrokes via CDP `Input.insertText` if Playwright exposes it

    Setting `.textContent` or `.innerHTML` directly does NOT trigger Draft.js state
    updates — the value is visually there but Zhihu doesn't see it on submit.

    ## Source card picker (Step 9)

    The best-source heuristic is a triple:
    1. Keyword overlap with the question (tokenize both)
    2. Upvote count (`点赞数`)
    3. Follower count of the answer author

    If all three are tied or unavailable, take the first card. Ad slots are
    marked with class `advertisement` or an `iframe` embed — skip those.

    ## Bad-URL filter (Step 10)

    Accept:
    - `https://www.zhihu.com/question/<qid>/answer/<aid>`
    - `https://zhuanlan.zhihu.com/p/<pid>`

    Reject:
    - `zhihu.com/market/...` (paid content)
    - `zhihu.com/people/...` (author profile, not an answer)
    - Any external domain (Zhihu sometimes links out)

    ## Rate limits and retries

    - Per-question budget: 120s (step 6) + 10s (other steps) = ~130s ceiling
    - Whole-article budget (3 questions): ~10 minutes
    - If Zhihu rate-limits the IP, subsequent navigations will show a CAPTCHA —
      treat as a login wall (Step 2 recovery path) and let the user resolve it.
    ```

    Create `skills/zhihu-haowen-enrich/README.md`:

    ```markdown
    # zhihu-haowen-enrich (Hermes skill)

    Drives zhida.zhihu.com's AI-search UI per question and writes the result
    (AI summary + best-source Zhihu URL) to disk.

    Used by the `enrich_article` orchestration skill (Phase 4 knowledge
    enrichment).

    ## Install

    1. Copy this directory to a Hermes-discoverable location (remote WSL):
       ```
       /home/<user>/OmniGraph-Vault/skills/zhihu-haowen-enrich/
       ```
    2. Ensure Hermes `skills.external_dirs` includes
       `/home/<user>/OmniGraph-Vault/skills` (already configured on the
       production remote).
    3. Restart Hermes gateway: `hermes gateway restart` (or `/new` in chat).

    ## Prerequisites

    - CDP-reachable Edge at `CDP_URL` (default `http://localhost:9223`)
    - Zhihu session cookies in that Edge user-data-dir (or reply `/resume` to the
      QR prompt)
    - Hermes `send_message` tool configured with a Telegram target (FR-20 default)
    - Env vars: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN` in `~/.hermes/.env`

    ## Testing

    The skill is REMOTE-ONLY and MANUAL (per Phase 4 VALIDATION.md §Manual-Only
    Verifications). To smoke-test:

    ```bash
    ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST
    cd ~/OmniGraph-Vault
    # From Hermes CLI or chat:
    #   /zhihu-haowen-enrich  ARTICLE_HASH=test Q_IDX=0 QUESTION="LightRAG 的多跳实体消歧怎么做?"
    # Then inspect:
    ls ~/.hermes/omonigraph-vault/enrichment/test/0/haowen.json
    cat ~/.hermes/omonigraph-vault/enrichment/test/0/haowen.json
    ```

    Expect either `{question, summary, best_source_url, timestamp}` (success)
    or `{question, error, timestamp}` (graceful failure).

    ## Related

    - Orchestrator: `enrich_article` (calls this skill once per question)
    - Follow-on: `python enrichment/fetch_zhihu.py` (runs on the URL this skill returns)
    ```
  </action>
  <verify>
    <automated>test -f skills/zhihu-haowen-enrich/references/flow.md && test -f skills/zhihu-haowen-enrich/README.md</automated>
  </verify>
  <acceptance_criteria>
    - File `skills/zhihu-haowen-enrich/references/flow.md` exists
    - File `skills/zhihu-haowen-enrich/README.md` exists
    - `grep -q "Draft.js" skills/zhihu-haowen-enrich/references/flow.md` succeeds
    - `grep -q "execCommand" skills/zhihu-haowen-enrich/references/flow.md` succeeds
    - `grep -q "login-wall" skills/zhihu-haowen-enrich/references/flow.md` succeeds (quoted text check)
    - `grep -q "REMOTE-ONLY" skills/zhihu-haowen-enrich/README.md` succeeds
    - `wc -l skills/zhihu-haowen-enrich/references/flow.md` >= 50
  </acceptance_criteria>
  <done>References and README exist with practical content</done>
</task>

<task type="checkpoint:human-verify">
  <name>Task 5.3: Remote smoke-test the skill (manual integration)</name>
  <files>skills/zhihu-haowen-enrich/ (no file changes — test run only)</files>
  <read_first>
    - skills/zhihu-haowen-enrich/SKILL.md
    - skills/zhihu-haowen-enrich/README.md (test instructions)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-VALIDATION.md (Manual-Only Verifications table)
  </read_first>
  <action>
    The skill is pure-Markdown and cannot be unit-tested. It must be smoke-tested against
    a live remote Hermes instance.

    Manual verification (user runs these steps):

    1. Push the skill to remote: `./deploy.sh`
    2. SSH to remote:
       ```
       ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST
       ```
    3. Restart Hermes gateway if needed: `hermes gateway restart` (or `/new` in chat)
    4. Verify the skill is discovered: `hermes skills list | grep zhihu-haowen-enrich`
    5. From Hermes chat/CLI, invoke the skill with a test question:
       ```
       /zhihu-haowen-enrich
       ARTICLE_HASH=smoketest
       Q_IDX=0
       QUESTION=LightRAG 的多跳实体消歧怎么做?
       ```
    6. Wait up to 3 minutes (120s AI-generation + overhead)
    7. Inspect output file:
       ```
       cat ~/.hermes/omonigraph-vault/enrichment/smoketest/0/haowen.json
       ```
    8. Confirm one of:
       - Success: file contains `question`, `summary`, `best_source_url`, `timestamp`
       - Graceful failure: file contains `question`, `error`, `timestamp` — record the error code for follow-up selector tuning
       - **Catastrophic failure (skill crashed without writing file)**: investigate skill body + Hermes session log at `~/.hermes/sessions/`

    9. If the login-wall branch fired, confirm:
       - Telegram received the QR image
       - Replying `/resume` caused the skill to retry and succeed
       - This validates D-13 end-to-end

    Resume-signal: type "skill smoke-test passed" with a one-line summary of what
    happened (success / which error code / did login-wall fire).
  </action>
  <verify>
    <automated>ls ~/.hermes/omonigraph-vault/enrichment/smoketest/0/haowen.json 2>/dev/null && python -c "import json; d=json.load(open('$HOME/.hermes/omonigraph-vault/enrichment/smoketest/0/haowen.json')); print('ok' if 'question' in d else 'missing_question')"</automated>
  </verify>
  <acceptance_criteria>
    - On remote: `~/.hermes/omonigraph-vault/enrichment/smoketest/0/haowen.json` EXISTS after the test run
    - File contains a `question` field matching the test input
    - File is valid JSON (parses with `python -c "import json; json.load(open(...))"`)
    - Either `summary`+`best_source_url` OR `error` is present (never both, never neither)
    - If `error` is present: user confirms the error code is in the expected set from SKILL.md "Error Handling Summary" table — any new/unexpected error indicates a selector needs updating in references/flow.md
  </acceptance_criteria>
  <done>At least ONE remote smoke-test invocation produces haowen.json (success or graceful failure); any new error codes logged to references/flow.md for future tuning</done>
</task>

</tasks>

<verification>
  - SKILL.md, references/flow.md, README.md all present and well-formed
  - No scripts/ subdirectory in the skill (D-02 compliance)
  - Remote smoke test produced a haowen.json (success or graceful failure)
</verification>

<success_criteria>
- Skill directory has correct 3-file structure matching existing skills pattern
- SKILL.md frontmatter valid; body covers all 10 steps + D-13 recovery
- D-03 disk-output contract documented (haowen.json shape)
- D-13 Telegram MEDIA: convention used (no custom delivery code)
- Manual smoke test confirms Hermes can discover + invoke the skill
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-05-SUMMARY.md`.
</output>

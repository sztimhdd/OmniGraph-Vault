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

1. Click the "新对话" button if visible — this opens a fresh input area that
   accepts `browser_type` directly.
2. Call `document.execCommand('insertText', false, <QUESTION>)` via `browser_evaluate`.
3. Dispatch an InputEvent with `{inputType: 'insertText', data: <QUESTION>, bubbles: true}`
   on the contenteditable element.

**DO NOT use `.innerText =` or `.innerHTML =` assignment** — Draft.js state will
not update and the value is silently ignored on submit. This is a confirmed failure
mode (verified 2026-04-27).

Verify the text appears in the editor before proceeding. If no approach inserts
the text successfully: write failure haowen.json with
`error: "question_input_failed"` and return.

### Step 5 — Submit

Press Enter on the focused editor, OR click the element with text "搜索" /
role=button. Wait for a URL change or a results panel to appear.

If submit does nothing after 2 attempts: write failure haowen.json with
`error: "submit_ignored"` and return.

### Step 6 — Wait for AI summary

Poll the page for the sentinel text `完成回答` (AI-generation complete) OR a
streaming-complete DOM state. Timeout: 120 seconds
(env `ENRICHMENT_HAOWEN_TIMEOUT`, default 120).

If timeout reached: write failure haowen.json with
`error: "ai_summary_timeout"` and return.

### Step 7 — Extract summary

Use `browser_evaluate`:
```js
document.querySelector('[role=main] article').innerText
```
Or a broader selector if that's empty. Verify the summary is non-empty
and does not contain error or placeholder text.

If the summary is empty after selector expansion: write failure haowen.json with
`error: "empty_summary"` and return.

### Step 8 — Expand source panel

Find and click an element with text matching `/全部来源\s*\d+/` (or
`查看全部来源`, `展开来源`). Wait for source cards to render.

If no source panel is found: write failure haowen.json with
`error: "no_sources"` and return.

### Step 9 — Pick best source card

Parse the visible source cards. Heuristic (in order):
1. Title contains ≥1 keyword from `<QUESTION>` (tokenize on whitespace)
2. Highest combined 点赞 + 关注 count
3. Falls back to the first non-ad card

Skip any card that is an advertisement (class `advertisement` or iframe embed).

If no card survives the filter: write failure haowen.json with
`error: "no_source_cards"` and return.

### Step 10 — Click card and extract final URL

Click the chosen card. Source panel cards are React components, NOT `<a>` tags —
the URL is NOT in the DOM. You MUST click the card, wait for navigation or a new
tab to open, then read `window.location.href` (or the new tab's URL).

Validate: the URL must match `zhihu.com/question/.../answer/...` or
`zhuanlan.zhihu.com/p/...`. If the URL is an ad link or a non-Zhihu domain:
write failure haowen.json with `error: "bad_source_url: <url>"` and return.

### Finalize

Write `haowen.json` to `$ENRICHMENT_DIR/$ARTICLE_HASH/$Q_IDX/haowen.json` with
fields per the Output section above. Include the ISO 8601 UTC timestamp.

The outer `enrich_article` skill reads this file after this skill returns.
Do NOT print the JSON to stdout — write to disk only (D-03 contract).

## Error Handling Summary

| Error code | When |
|------------|------|
| `navigation_failed` | Step 1 network/CN block |
| `login_wall_timeout` | Step 2 — Telegram retry failed or user canceled |
| `search_entry_not_found` | Step 3 — DOM pattern drifted |
| `question_input_failed` | Step 4 — editor rejected all insertion methods |
| `submit_ignored` | Step 5 — submit had no effect after 2 attempts |
| `ai_summary_timeout` | Step 6 — AI generation exceeded 120s |
| `empty_summary` | Step 7 — extracted text was blank |
| `no_sources` | Step 8 — source panel not found |
| `no_source_cards` | Step 9 — all cards were ads or filtered |
| `bad_source_url: <url>` | Step 10 — URL was not a valid Zhihu answer/column |

All errors are WRITTEN to haowen.json; the skill itself exits cleanly so the
outer skill's for-loop keeps iterating.

## References

See `references/flow.md` for per-step selector strategy and empirical refinements
captured during real-world runs.

## Related Skills

- Orchestrator: `enrich_article` (calls this skill once per question)
- Related Python helper: `enrichment/fetch_zhihu.py` (runs AFTER this skill, on
  the resulting best_source_url)

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

1. Click "新对话" button → new input area accepts `browser_type` directly. This
   is the most reliable path; try it first.
2. `document.execCommand('insertText', false, <QUESTION>)` — works in most
   Chromium versions when the contenteditable element has focus.
3. `contenteditable_div.focus()` + InputEvent dispatch with
   `{inputType: 'insertText', data: <QUESTION>, bubbles: true}`

**Setting `.textContent` or `.innerHTML` directly does NOT trigger Draft.js state
updates** — the value is visually present but Zhihu ignores it on submit. This
is a confirmed failure mode verified empirically on 2026-04-27.

## Source card picker (Step 9)

The best-source heuristic is a triple:
1. Keyword overlap with the question (tokenize both on whitespace)
2. Upvote count (`点赞数`)
3. Follower count of the answer author (if visible in card)

If all three are tied or unavailable, take the first non-ad card.

Ad slots are marked with class `advertisement` or contain an `iframe` embed —
skip those unconditionally.

## Bad-URL filter (Step 10)

Accept:
- `https://www.zhihu.com/question/<qid>/answer/<aid>`
- `https://zhuanlan.zhihu.com/p/<pid>`

Reject:
- `zhihu.com/market/...` (paid content)
- `zhihu.com/people/...` (author profile, not an answer)
- Any external domain (Zhihu sometimes links out to partner sites)

**IMPORTANT:** Source panel cards are React components, NOT `<a>` tags. The URL
is NOT in the DOM before click. You MUST click the card, wait for navigation or
a new tab, and then read `window.location.href`. Do not attempt to extract the
URL from the card's HTML before clicking.

## Rate limits and retries

- Per-question budget: 120s (step 6) + ~10s (all other steps) ≈ 130s ceiling
- Whole-article budget (3 questions): ~10 minutes
- If Zhihu rate-limits the IP, subsequent navigations will show a CAPTCHA —
  treat as a login wall (Step 2 recovery path) and let the user resolve it via
  Telegram.

## Run log

Append entries here after each real-world invocation:

```
Date:
Question:
Step reached:
Outcome (success / error code):
New selector observations:
```

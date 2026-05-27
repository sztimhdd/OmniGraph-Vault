# Phase 4: knowledge-enrichment-zhihu - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> See `04-CONTEXT.md` for locked decisions.

**Date:** 2026-04-27

---

## Gray areas presented

1. Python↔Hermes skill bridge ✅ selected
2. Where orchestrate.py runs ✅ selected
3. LightRAG upsert + doc structure ✅ selected
4. Image pipeline regression gate ✅ selected

All 4 selected for discussion. User explicitly asked for more after the first
round; 3 additional areas surfaced (retry policy, extract LLM, Zhihu login).

---

## Area 1: Python↔Hermes skill bridge

**Q:** Which bridge mechanism for Python ↔ zhihu-haowen-enrich skill?
Options: A. Invert — Hermes drives / B. SSH/CLI bridge / C. HTTP API / D. Inline re-implementation
**Answer:** A. Invert — Hermes drives

**Q:** Where does the per-question loop live under "Hermes drives"?
Options: A1 Hermes loops in Markdown / A2 Python loops / A3 Hybrid
**Answer:** A1. Hermes loops in Markdown

**Q:** Contract between Hermes and Python scripts?
Options: stdout JSON + args / Files on disk / Mixed
**Answer:** User redirected — "web search for Hermes best practices"
**Action taken:** Searched Hermes docs (brave-search + tavily-extract on
  creating-skills and automate-with-cron pages). Found: Hermes's documented
  pattern is "script stdout becomes agent context" with a 50KB cap
  (`tool_output.max_bytes`). Presented follow-up with that context.
**Follow-up Q:** Contract re-presented with Hermes best-practice grounding.
**Follow-up answer:** Mixed — JSON on stdout + artifacts on disk.

---

## Area 2: Where orchestrate.py runs

Implicitly resolved by Area 1 A1 decision. Confirmed with two explicit
follow-ups:

**Q:** Dev loop — how do edits reach remote?
Options: git push/pull / rsync / sshfs / develop-on-remote
**Answer:** Git push → git pull on remote

**Q:** Can any part be exercised locally on Windows?
Options: Python helpers yes (mock Hermes) / No (everything remote) / CDP tunnel
**Answer:** No — everything is remote-only

---

## Area 3: LightRAG upsert + doc structure

**Q:** Enriched WeChat MD ingestion semantics?
Options: Re-ainsert after delete / Just re-ainsert / Append-only
**Answer:** "if the enrichment is a must-have logic for each wechat article, then this is a moot point"
**Action taken:** Surfaced the underlying question — is enrichment mandatory?
  (Originally dropped from top-4 due to AskUserQuestion 4-option limit.)

**Q (follow-up):** Is enrichment mandatory, or opt-in?
Options: Mandatory / Opt-in per PRD / Hybrid with skip-short-articles
**Answer:** Mandatory — enrich before first ingest

**Q:** 3 Zhihu answers — how to represent in LightRAG?
Options: Independent docs + reference edge / Embedded as chunks / Both
**Answer:** Independent docs + reference edge

**Q:** Phase-0 LightRAG spike?
Options: Delete-by-id + re-ainsert / Observe ainsert() behavior / Skip
**Answer:** Delete-by-id + re-ainsert on one real article

---

## Area 4: Image pipeline regression gate

**Q:** Regression gate that proves refactor didn't break WeChat ingest?
Options: Golden-file / Unit tests / Live re-ingest / Both golden + unit
**Answer:** Both golden-file AND unit tests

**Q:** Where does describe_image() live?
Options: batch describe_images(paths) / single describe_image(path)
**Answer:** batch describe_images(paths)

---

## Additional round (user requested "explore more")

**Q:** Partial-failure retry policy?
Options: Abandon / Per-question retry table / Abandon + manual re-run
**Answer:** Abandon failures, ingest what we have

**Q:** LLM for extract_questions?
Options: DeepSeek v4 Pro / DeepSeek v4 Flash / Gemini 2.5 Flash Lite
**Answer:** "does Gemini-2.5-Flash-Lite support google web grounding?"
**Action taken:** Confirmed yes (all Gemini 2.5 models support `google_search`
  tool). Noted that extract_questions is reading-comprehension over a fixed
  article, so grounding's value is different from a generative lookup task.
**Follow-up Q:** Gemini + grounding / Gemini no grounding / DeepSeek Pro no grounding
**Follow-up answer:** Gemini 2.5 Flash Lite + Google Search grounding

**Q:** Zhihu login persistence?
Options: User re-logs manually / Skill triggers login flow / Persistent cookies
**Answer:** "use Hermes to nudge user via Telegram, or even screenshot the
  login qr code and send to user via Telegram to scan and login"
**Follow-up Q:** Telegram nudge + QR screenshot / Telegram nudge only
**Follow-up answer:** Telegram nudge + QR screenshot

---

## Final check

**Q:** Ready to write CONTEXT.md?
**Answer:** Write CONTEXT.md now

---

## Summary of non-obvious moves

1. User's "moot point" observation on upsert led to surfacing the mandatory-vs-opt-in question that the gray-area top-4 had missed. Result: PRD section 12 Phase 5 `--enrich` flag is superseded.
2. User redirected the contract question to web research instead of picking an option. Research surfaced Hermes's documented "stdout = agent context, 50KB cap" pattern, which made "Mixed" the clearly-correct choice.
3. User's Gemini-grounding question led to confirming the capability exists, which tipped the LLM selection from DeepSeek to Gemini+grounding — overriding the PRD default.
4. User proposed the Telegram QR rescue pattern (not in my options) — folded in as D-13.

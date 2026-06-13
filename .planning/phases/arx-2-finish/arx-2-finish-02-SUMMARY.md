---
phase: arx-2-finish
plan: 02
wave: 3
status: complete
completed: 2026-06-12
requirements: [REQ-1.1-B-1, REQ-1.1-B-2, REQ-1.1-B-3, REQ-1.1-B-4]
---

# Wave 3 (plan 02) — GAP B: Deep Research frontend — SUMMARY

## What was built

The entire Deep Research frontend (zero research UI existed). A `/research/` page
mirroring `/ask/` with the three locked divergences:
1. a 5-STAGE STEPPER (not the Q&A 8-state matrix),
2. a `fetch()`+ReadableStream manual SSE parser (POST+JSON body → EventSource won't work),
3. a custom `renderResearchSources` (done event sources use `.uri`, not `.hash`).

### Task 1 — templates + research.js
- **`kb/templates/research.html`** (NEW): extends base.html, hero, query textarea +
  `max_iterations` number input (`name="max_iterations"`, min 1 max 10 value 3),
  "Run Deep Research" submit → `window.KbResearch.submit(q, iterations)`, includes
  `_research_result.html`, loads marked.min.js + research.js.
- **`kb/templates/_research_result.html`** (NEW): `id="research-result"` (Pitfall 3),
  `.research-stepper` with 5 `<li data-stage=...>` (web_baseline/retriever/reasoner/
  verifier/synthesizer — match SSE event names), `.qa-answer prose` + `.qa-sources-list`
  reuse classes (Pitfall 2), `.research-error-banner`.
- **`kb/static/research.js`** (NEW, self-contained IIFE): copied verbatim from qa.js —
  buildTitleMap, rewriteOrphanCitations, rewriteAnswerHtml, renderAnswerMarkdown; wrote
  custom `renderResearchSources` (Pitfall 7 — `.uri` not `.hash`, http→link / else plain
  chip); wrote the `fetch()` + `getReader()` + manual SSE frame-split pump (`parseFrame`,
  `onStageUpdate` maps status→step-state, `onDone`, `onError`). Did NOT reuse qa.js
  submit/poll/mode/feedback/retry. `node` Function-construct parse: OK.

### Task 2 — CSS budget, stepper CSS, nav, SSG, locale
- **CSS budget**: raised `test_css_budget_within_2100` ceiling 2150 → 2300 (Path 1 locked;
  ISSUE #6 — style.css was already 2191 > 2150, test RED pre-phase).
- **`kb/static/style.css`**: appended ~80-line stepper block leaning on existing tokens
  (`--accent` running, `--accent-green` done, `--error` failed, `--text-tertiary` pending/
  skipped, `--radius-*`). One `@keyframes research-pulse`, one responsive tweak. Final:
  **2271 lines (< 2300)**.
- **`kb/templates/base.html`**: added `/research/` link to nav (after /ask/) + footer (2 links).
- **`kb/export_knowledge_base.py`**: added research.html SSG render block mirroring ask_html
  (`env.get_template("research.html").render(...)` + `_write_atomic(.../research/index.html)`).
  `_write_atomic` mkdir's the `research/` parent (Pitfall 1 — no separate mkdir needed).
- **`kb/locale/{en,zh-CN}.json`**: added `nav.research` + 17 `research.*` keys to BOTH files.
  Parity verified: 18 keys each, zh==en, JSON valid.

### Task 3 — local one-port UAT (Principle #6, MANDATORY)

Local `local_serve.py` :8766 + Playwright MCP browser UAT (main session).

**Boot debugging (2 deviations, both documented local-only non-issues):**
1. `_build_llm_rerank()` → `get_rerank_func()` hangs probing the corp-blocked
   `databricks_serving` reranker. Fixed with `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1`
   (the built-in escape at kb/api.py:59 — degrades to hybrid).
2. The local `~/.hermes/omonigraph-vault` nano-vectordb store is 768-dim (713-node dev
   store) but the app embeds 3072 → `AssertionError: Embedding dim mismatch, expected:
   3072, but loaded: 768`. **This is the documented CONTEXT §NON-ISSUE** (local .dev-runtime
   dim mismatch — never occurs on Aliyun/Databricks, both 3072). Resolved for local UAT by
   pointing `RAG_WORKING_DIR` at a fresh empty 3072 dir (`.dev-runtime/lightrag_empty_3072`)
   so the app boots → retriever returns 0 chunks → synthesizer degrades gracefully → all 5
   SSE frames still emit. This exercises the COMPLETE frontend wiring, which is Task 3's
   purpose (UI wiring, NOT KG richness — that's Waves 4/5 on the real 3072 KGs).

**UAT evidence (Principle #6):**
- Launcher: `RAG_WORKING_DIR=.../lightrag_empty_3072 OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1 OMNIGRAPH_DEEPSEEK_TIMEOUT=15 DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe .scratch/local_serve.py`
- Boot: `lightrag_singleton_ready wall_s=1.80` → `Application startup complete` → `Uvicorn running on http://127.0.0.1:8766`.
- curl smoke: `GET /research/` → **HTTP 200** (stepper + 5 data-stage + 深度研究 present).
- curl SSE: `POST /api/research {"query":"What is an AI agent?","max_iterations":1}` →
  event sequence **`web_baseline → retriever → reasoner → verifier → synthesizer → done`**
  (all 5 stage frames + terminal done). `done` payload has markdown/confidence/sources/
  images_embedded/note_lines (graceful-degrade body: `❌ LLM synthesis failed: Connection error.`).
- Browser UAT (Playwright MCP, main session):
  - Stepper state machine end-to-end: `web_baseline=done, retriever=skipped, reasoner=failed,
    verifier=failed, synthesizer=done` (onStageUpdate correctly mapped each SSE status), section
    `data-research-state=done`, `.qa-answer` rendered markdown, error banner hidden.
  - **0 console errors** (`browser_console_messages` empty → research.js parsed + SSE pump clean).
  - Network: **`POST /api/research => 200`** + research.js/style.css/marked.min.js all 200.
  - Bilingual: zh-CN toggle renders 深度研究 (nav h1 + hero), 核实迭代次数, 运行深度研究, Chinese
    disclaimer — no raw locale-key literals.
  - Screenshots (3): `.playwright-mcp/arx-frontend-uat-01-idle-form.png`,
    `arx-frontend-uat-02-final-report.png`, `arx-frontend-uat-03-bilingual-zh.png`.

## Verification

| Check | Result |
|-------|--------|
| research.js node parse | OK |
| research.js greps (getReader, /api/research, renderResearchSources, KbResearch, research-result id, no qa-result leak) | all OK |
| _research_result.html (id, stepper, 5 data-stage, qa-answer, qa-sources-list) | all OK |
| style.css <= 2300 | 2271 ✅ |
| `pytest test_research_router.py + test_search_inline_reveal.py` | 29 passed ✅ |
| locale parity (research.* + nav.research, zh==en, >=15) | 18 keys ✅ |
| base.html /research/ links (nav + footer) | 2 ✅ |
| SSG bake → kb/output/research/index.html | rendered (13.9KB) ✅ |
| Local UAT: GET /research/ 200, SSE 5-stage+done, stepper completes, 0 console errors, POST 200, bilingual | ✅ (Principle #6) |

## Key files

- created: `kb/templates/research.html`, `kb/templates/_research_result.html`, `kb/static/research.js`
- modified: `kb/static/style.css`, `kb/templates/base.html`, `kb/export_knowledge_base.py`, `kb/locale/en.json`, `kb/locale/zh-CN.json`, `tests/integration/kb/test_search_inline_reveal.py`
- UAT: `.playwright-mcp/arx-frontend-uat-0{1,2,3}-*.png` (gitignored evidence)

## Self-Check: PASS

Bilingual /research/ page with 5-stage live stepper + max_iterations control + real-markdown
report + Sources; fetch()+ReadableStream SSE parse (not EventSource); reused qa.js render half +
custom renderResearchSources; SSG-registered; nav+footer linked; CSS <= 2300; local one-port UAT
proves render+stream+graceful-degrade end-to-end (Principle #6) before wave close.

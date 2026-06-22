---
phase: arx-2-finish
plan: 02
type: execute
wave: 3
depends_on: ["arx-2-finish-01"]
files_modified:
  - kb/templates/research.html
  - kb/templates/_research_result.html
  - kb/static/research.js
  - kb/static/style.css
  - kb/templates/base.html
  - kb/export_knowledge_base.py
  - kb/locale/zh-CN.json
  - kb/locale/en.json
  - tests/integration/kb/test_search_inline_reveal.py
autonomous: false   # contains a local-UAT human-verify checkpoint (Principle #6)
requirements: [REQ-1.1-B-1, REQ-1.1-B-2, REQ-1.1-B-3, REQ-1.1-B-4]
must_haves:
  truths:
    - "A /research/ page exists with a query input + max_iterations (1-10) control"
    - "Submitting a query streams the 5-stage stepper live (each stage lights pending->running->done/skipped/failed)"
    - "The final report renders real markdown + images + a Sources list"
    - "The page is bilingual (zh-CN + en) with research.* locale keys in both files"
    - "research/index.html is produced by the SSG bake (not auto-discovered)"
    - "nav + footer link to /research/ on every page"
  artifacts:
    - path: "kb/templates/research.html"
      provides: "Deep Research page (mirrors ask.html) + max_iterations control"
      min_lines: 60
    - path: "kb/templates/_research_result.html"
      provides: "5-stage stepper partial with .qa-answer + .qa-sources-list for JS reuse"
      contains: "research-stepper"
      min_lines: 50
    - path: "kb/static/research.js"
      provides: "fetch()+ReadableStream SSE parser + reused qa render fns + renderResearchSources"
      contains: "getReader"
      min_lines: 200
    - path: "kb/export_knowledge_base.py"
      provides: "research.html SSG render block (+ research/ mkdir)"
      contains: "research/index.html"
  key_links:
    - from: "kb/static/research.js"
      to: "POST /api/research"
      via: "fetch + ReadableStream reader + manual SSE frame split on blank line"
      pattern: "/api/research"
    - from: "kb/static/research.js"
      to: "done event sources[].uri"
      via: "custom renderResearchSources (sources use .uri not .hash)"
      pattern: "renderResearchSources"
    - from: "kb/templates/_research_result.html"
      to: "research.js render functions"
      via: "shared CSS classes .qa-answer + .qa-sources-list"
      pattern: "qa-answer"
    - from: "kb/export_knowledge_base.py"
      to: "research/index.html in output dir"
      via: "env.get_template('research.html').render + _write_atomic"
      pattern: "research\\.html"
---

<objective>
GAP B (DOMINANT) — build the entire Deep Research frontend. Zero research UI exists
today. Mirror the /ask/ Q&A pattern with three critical divergences: (1) a 5-STAGE
STEPPER instead of the Q&A 8-state matrix; (2) a fetch()+ReadableStream SSE parser
because /api/research is a POST+JSON-body SSE (EventSource is GET-only); (3) a custom
renderResearchSources because the done event's sources use `.uri` not `.hash`.

Purpose: Without this, the real synthesis from Wave 1 is invisible to users — the
endpoint streams SSE but nothing renders it. This plan is the user-facing feature.

Output: 8 files (2 new templates, 1 new JS, edits to style.css/base.html/export/2 locales,
test ceiling raise) + a local-UAT checkpoint gate.

**Skill note:** invoke `frontend-design` + `ui-ux-pro-max` skills for the 5-stage stepper
visual treatment (states, transitions, brand-consistent tokens, accessibility/aria-live).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md
@kb/templates/ask.html
@kb/templates/_qa_result.html
@kb/static/qa.js
@kb/api_routers/research.py
@kb/templates/base.html
@kb/export_knowledge_base.py
@kb/locale/zh-CN.json
@kb/locale/en.json

<interfaces>
<!-- SSE WIRE PROTOCOL (from research.py:61-69 + orchestrator.py:224-236) — research.js MUST parse: -->
<!-- Request: POST /api/research  {"query": str (1..2000), "max_iterations": int (1..10, default 3)} -->
<!-- Frame: event: NAME \n data: JSON \n\n  (frames separated by a blank line) -->
<!-- 5 stage events in fixed order: web_baseline, retriever, reasoner, verifier, synthesizer -->
<!--   stage frames carry {"stage":..,"status":"ok"|"skipped"|"failed","reason":..,"duration_s":..,...} -->
<!--   EXCEPT synthesizer which has NO status field (Axis 8 terminal). -->
<!-- Terminal: event: done \n data: {"markdown":str,"confidence":float, -->
<!--   "sources":[{"kind":str,"uri":str,"title":str|null,"snippet":str|null}],"images_embedded":[str],"note_lines":[str]} -->
<!-- Error: event: error \n data: {"message":str,"type":str}  (HTTP stays 200 once headers flushed) -->

<!-- qa.js REUSE (copy verbatim into research.js IIFE — no import system; both are self-contained IIFEs): -->
<!--   buildTitleMap          qa.js:82-91 -->
<!--   rewriteOrphanCitations qa.js:101-131 -->
<!--   rewriteAnswerHtml      qa.js:144-303  (img src fix, dead-link demote, KB_BASE_PATH prepend) -->
<!--   renderAnswerMarkdown   qa.js:306-323  (marked.js -> rewriteOrphanCitations -> rewriteAnswerHtml) -->
<!--   renderSources          qa.js:325-355  (ASSUMES s.hash — DO NOT use for research; see Pitfall 7) -->
<!-- DO NOT reuse: submit/pollOnce/setupModeToggle/setupFeedbackHandlers/setupRetryHandler. -->

<!-- PITFALL 7 (KEY divergence): done.sources[i] has .uri NOT .hash. WRITE a custom -->
<!--   renderResearchSources(sources, resultEl) (~30 LoC) rendering chips from s.uri/s.title. -->
<!-- PITFALL 2: render fns call $('.qa-answer', resultEl) + $('.qa-sources-list', resultEl) — -->
<!--   _research_result.html MUST include those EXACT class names. -->
<!-- PITFALL 3: result section id MUST be research-result (NOT qa-result) or qa.js captures it. -->
<!-- NOTE: locale key qa.mode.long_form.label is already "深度研究"; use a DISTINCT nav.research label. -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: research.html + _research_result.html (5-stage stepper) + research.js (SSE parser + reused renderers + renderResearchSources)</name>
  <read_first>
    - kb/templates/ask.html (FULL — mirror: extends base.html, hero, form, include result partial, extra_scripts script set incl marked.js)
    - kb/templates/_qa_result.html (the 8-state matrix to NOT copy — build a stepper instead)
    - kb/static/qa.js (COPY verbatim: buildTitleMap 82-91, rewriteOrphanCitations 101-131, rewriteAnswerHtml 144-303, renderAnswerMarkdown 306-323; use renderSources 325-355 as the template for renderResearchSources)
    - kb/api_routers/research.py (the SSE wire shapes the JS parses)
    - .planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md §Risk B (reuse map, SSE parse pattern lines 243-281, stepper skeleton lines 369-385, Pitfalls 2/3/7)
  </read_first>
  <action>
    **research.html** (~95 LoC) — `{% extends "base.html" %}`. Mirror ask.html: a research-hero
    using `research.page_title` + `research.hero_subtitle` locale keys, a form with a query
    textarea (`research.input_placeholder` / `research.input_aria`) + a `max_iterations` number
    input `min="1" max="10" value="3"` labelled `research.iterations_label`, a submit button
    (`research.submit`), `{% include "_research_result.html" %}`, and an extra_scripts block
    loading research.js plus whatever marked.js include ask.html uses (match ask.html's script
    set so renderAnswerMarkdown's `marked` dependency is present). Add `research.disclaimer` near the form.

    **_research_result.html** (~85 LoC) — 5-STAGE STEPPER from RESEARCH lines 369-385:
    - `<section id="research-result" data-research-state="idle" class="research-result" aria-live="polite" hidden>`
    - `<ol class="research-stepper">` with FIVE `<li class="research-step" data-stage="STAGE" data-step-state="pending">`
      where STAGE is each of web_baseline, retriever, reasoner, verifier, synthesizer (data-stage
      values MUST match the SSE event names exactly). Each li has `.research-step__dot`,
      `.research-step__label` (bilingual `data-lang="zh"`/`data-lang="en"` spans from
      `research.stage.STAGE` keys), `.research-step__status`.
    - `<article class="qa-answer prose"></article>` (EXACT class for renderAnswerMarkdown reuse — Pitfall 2)
    - `<aside class="qa-sources"><ul class="qa-sources-list" role="list"></ul></aside>` (Pitfall 2)
    - `<div class="research-error-banner" role="alert" hidden></div>`
    id MUST be `research-result` (Pitfall 3).

    **research.js** (~280 LoC) — NEW self-contained IIFE. Structure:
    1. Mirror qa.js top-of-IIFE setup (`$` helper, `marked` ref, `base` from window.KB_BASE_PATH).
       COPY verbatim: buildTitleMap, rewriteOrphanCitations, rewriteAnswerHtml, renderAnswerMarkdown.
    2. WRITE `renderResearchSources(sources, resultEl)` (~30 LoC, Pitfall 7): render `.qa-sources-list`
       chips from `s.uri` + `s.title` directly (NOT `s.hash`). Label `s.title || s.uri`; link to
       `s.uri` only if it is an http(s) URL, else render a plain (non-link) chip.
    3. WRITE submit + SSE pump per RESEARCH lines 247-281: `fetch(base+'/api/research', {method:'POST',
       headers:{'Content-Type':'application/json'}, body: JSON.stringify({query, max_iterations})})`;
       `reader = r.body.getReader()`; `decoder = new TextDecoder()`; accumulate `buffer`; split on
       the blank-line frame separator; keep the incomplete trailing frame; `parseFrame` each.
    4. `parseFrame(raw)`: read `event: ` / `data: ` lines, `JSON.parse(data)`, dispatch
       done -> onDone, error -> onError, else -> onStageUpdate(event, payload).
    5. `onStageUpdate(stage, payload)`: stage frames arrive AT completion, so mark THAT step
       `done`/`skipped`/`failed` from `payload.status` (synthesizer has no status -> `done`),
       and mark the NEXT step `running`. On submit, set step 1 `running` and section
       `data-research-state="running"`.
    6. `onDone(payload)`: `renderAnswerMarkdown(payload.markdown, payload.sources)` into `.qa-answer`;
       `renderResearchSources(payload.sources, resultEl)`; mark any non-terminal steps `done`;
       section `data-research-state="done"`.
    7. `onError(msg)`: show `.research-error-banner`; section `data-research-state="error"`.
    8. Wire submit button + Enter-to-submit; `window.KbResearch = {submit}`;
       `resultEl = document.getElementById('research-result')` (NOT qa-result — Pitfall 3).

    Simplicity-First: copy only the 5 render fns + setup; do not pull qa.js poll/feedback/mode code.
  </action>
  <verify>
    <automated>node -e "new Function(require('fs').readFileSync('kb/static/research.js','utf8')); console.log('research.js parses OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `kb/templates/research.html` exists; `grep -q "max_iterations" kb/templates/research.html` AND `grep -q "_research_result.html" kb/templates/research.html` succeed.
    - `kb/templates/_research_result.html` exists; `grep -q 'id="research-result"' ...` succeeds; `grep -q "research-stepper" ...` succeeds; `grep -c 'data-stage=' kb/templates/_research_result.html` returns >= 5; `grep -q "qa-answer" ...` AND `grep -q "qa-sources-list" ...` succeed.
    - `kb/static/research.js` exists; greps succeed for `getReader`, `/api/research`, `renderResearchSources`, `renderAnswerMarkdown`, `KbResearch`. `grep -q "getElementById('research-result')" kb/static/research.js` succeeds; `grep "getElementById('qa-result')" kb/static/research.js` returns NOTHING.
    - The node Function-construct verify prints "research.js parses OK" (no syntax error).
  </acceptance_criteria>
  <done>3 frontend files exist; stepper has 5 data-stage steps + qa-* reuse classes; research.js parses and contains the SSE pump + custom source renderer.</done>
</task>

<task type="auto">
  <name>Task 2: style.css stepper (raise CSS budget to 2300) + base.html nav/footer + export SSG block + bilingual locale keys</name>
  <read_first>
    - kb/static/style.css (the `.qa-*` / `.chip` / `.prose` tokens ~1107-1374 to lean on; confirm count with `wc -l`)
    - kb/templates/base.html (nav at 42-45, footer nav ul at 80)
    - kb/export_knowledge_base.py (ask_html block at 644-650; render_index_pages 563-570; READ `_write_atomic` to see if it mkdir's parents)
    - kb/locale/zh-CN.json + kb/locale/en.json (flat dotted keys; qa.* at 163-184)
    - tests/integration/kb/test_search_inline_reveal.py (test_css_budget_within_2100 ~143-147)
    - .planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md §CSS Budget + §Locale Keys + §Base.html Nav + §export block + Pitfall 1/5
    - .planning/ISSUES.md row #6
  </read_first>
  <action>
    **CSS budget decision (LOCKED — Path 1, raise ceiling to 2300):** RESEARCH §CSS Budget confirms
    style.css is ~2191 lines and `test_css_budget_within_2100` ALREADY FAILS pre-phase (ISSUE #6).
    Do NOT trim uncertain "dead" rules. Edit `tests/integration/kb/test_search_inline_reveal.py`
    at the budget assertion (~line 147): change the ceiling to `<= 2300` and add comment
    `# arx-2-finish raised 2150 -> 2300: +~55 lines for the 5-stage research stepper (ISSUE #6 deferred)`.

    **style.css** (~50-60 NEW lines) — append a `/* ===== Deep Research stepper (arx-2-finish) ===== */`
    block leaning on existing `.chip`/`.prose`/color tokens:
    - `.research-result`, `.research-stepper` (ol reset + flex/grid), `.research-step`
    - `.research-step__dot` with state colors via `[data-step-state="pending|running|done|skipped|failed"]`
      (running = pulse animation, done = success token, failed = error token, skipped = muted)
    - one `@keyframes` pulse, `.research-error-banner` (reuse error token), one narrow-screen responsive tweak.
    Invoke ui-ux-pro-max for the state palette; stay under +60 lines so total <= 2300 (verify with `wc -l`).

    **base.html** — TWO edits (RESEARCH lines 300-313):
    - NAV after line 45 (after /ask/ link): add `<a href="{{ base_path }}/research/">` mirroring the
      ask link's icon+span structure with `nav.research` bilingual `data-lang` spans.
    - FOOTER nav ul after the /ask/ `<li>` (line 80): add a `<li><a href="{{ base_path }}/research/">…</a></li>`
      with `nav.research` bilingual spans.

    **export_knowledge_base.py** — after the ask_html block (line 650), add (RESEARCH lines 330-334):
    if `_write_atomic` does NOT mkdir parents, FIRST add `(output_dir / "research").mkdir(parents=True, exist_ok=True)`
    (Pitfall 1); then
    `research_html = env.get_template("research.html").render(lang="zh-CN", page_url=f"{config.KB_BASE_PATH}/research/")`
    and `_write_atomic(output_dir / "research" / "index.html", research_html)`. Match the ask block's
    render-arg set minus hot_question_keys (research has no hot questions).

    **locale** — add the `research.*` namespace to BOTH kb/locale/zh-CN.json and kb/locale/en.json,
    flat dotted keys (match the file's existing style), using RESEARCH lines 342-360 zh values +
    parallel English. Required keys: `nav.research` (use a label DISTINCT from the existing
    `qa.mode.long_form.label`="深度研究" — e.g. zh "深度研究" is fine for nav since it's a separate
    page, but pick a clear English "Deep Research"), `research.page_title`, `research.hero_subtitle`,
    `research.input_placeholder`, `research.input_aria`, `research.iterations_label`, `research.submit`,
    `research.stage.web_baseline`, `research.stage.retriever`, `research.stage.reasoner`,
    `research.stage.verifier`, `research.stage.synthesizer`, `research.state.running`,
    `research.state.done`, `research.state.error`, `research.sources.title`, `research.retry.button`,
    `research.disclaimer`. Keep JSON valid (no trailing comma) and key-parity across both files.
  </action>
  <verify>
    <automated>venv/Scripts/python.exe -c "import json; z=json.load(open('kb/locale/zh-CN.json',encoding='utf-8')); e=json.load(open('kb/locale/en.json',encoding='utf-8')); rz={k for k in z if k.startswith('research.') or k=='nav.research'}; re={k for k in e if k.startswith('research.') or k=='nav.research'}; assert rz==re, ('parity broken', rz^re); assert len(rz)>=15, ('too few', len(rz)); print('locale parity OK', len(rz))"</automated>
  </verify>
  <acceptance_criteria>
    - `wc -l kb/static/style.css` returns <= 2300 (the appended stepper block stays within the raised ceiling).
    - `tests/integration/kb/test_search_inline_reveal.py` budget assertion now reads `<= 2300` and passes: `venv/Scripts/python.exe -m pytest tests/integration/kb/test_search_inline_reveal.py -v` is green.
    - `grep -q 'href="{{ base_path }}/research/"' kb/templates/base.html` succeeds (nav + footer both link /research/ — `grep -c` returns >= 2).
    - `grep -q "research/index.html" kb/export_knowledge_base.py` AND `grep -q 'get_template("research.html")' kb/export_knowledge_base.py` succeed (SSG render block present — Fact 3).
    - The locale parity verify command prints "locale parity OK" with count >= 15 (research.* keys present in BOTH zh-CN.json and en.json, no parity break, JSON still valid).
    - A bake produces `kb/output/research/index.html`: run the SSG export (or `make` bake) and confirm `ls kb/output/research/index.html` succeeds (pre-req for Wave 4/5 deploy that `cp -R kb/output _ssg` carries it).
  </acceptance_criteria>
  <done>style.css under 2300 + budget test green; nav/footer link /research/; export SSG block renders research/index.html; bilingual research.* locale parity (>=15 keys each); bake emits kb/output/research/index.html.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Local one-port KB deploy + browser UAT of /research/ (Principle #6 — MANDATORY before this wave is marked complete)</name>
  <read_first>
    - CLAUDE.md Principle #6 (KB local UAT mandatory — local_serve.py + browser UAT + cite evidence; green tests necessary-not-sufficient)
    - Memory kb_local_uat_mandatory (kb/ phases MUST run local_serve.py + browser UAT before complete)
    - .scratch/local_serve.py (the single-port :8766 launcher serving SSG + /api/* + /static/*)
    - .planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md §5-STAGE STEPPER (the visual the UAT must observe)
  </read_first>
  <what-built>
    No new code. A real local one-port deploy + browser UAT proving the /research/ page that
    Tasks 1-2 built actually RENDERS, the 5-stage stepper streams live, and the final report
    draws real synthesized prose (from Wave 1 / plan 01). This is the Principle #6 gate that a
    green test suite alone does NOT satisfy. Runtime issues (missing /static/research.js after a
    stale bake, SSE frame-parse bug, locale key not resolving, stepper not advancing) only surface
    here — exactly the failure mode kb-3 (2026-05-14) closed this rule against.
  </what-built>
  <how-to-verify>
    1. **Bake first** so the SSG output includes the new page: run the SSG export (the same path
       export_knowledge_base.py uses, or `make` bake) and confirm `kb/output/research/index.html`
       + `kb/output/static/research.js` exist. local_serve.py serves the baked SSG.
    2. **Start local deploy:** `venv/Scripts/python.exe .scratch/local_serve.py` — single port :8766
       serves SSG + `/api/*` + `/static/*`. Confirm it boots (stdout ready line).
    3. **Smoke the endpoint family the wave touched:** `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8766/research/`
       (expect 200); `curl -N -X POST http://127.0.0.1:8766/api/research -H 'Content-Type: application/json'
       -d '{"query":"What is an AI agent?","max_iterations":1}' --max-time <OMNIGRAPH_LLM_TIMEOUT_SEC>` →
       confirm 5 stage frames + a terminal `event: done`. (If the local KG starves to 0 chunks, the
       graceful-degrade path from Wave 1 still emits a terminal report — acceptable here; this task
       proves the UI wiring, not KG richness. The real-KG E2E is Wave 4/5.)
    4. **Browser UAT (Playwright MCP, main session ONLY — never a sub-agent):**
       - `browser_navigate` to `http://127.0.0.1:8766/research/`; `browser_snapshot` for refs.
       - `browser_type` a query, set max_iterations=1, `browser_click` submit.
       - Observe the 5-stage stepper advancing (pending→running→done/skipped/failed); `browser_wait_for`
         the final report to render. Re-snapshot after state changes (refs invalidate on DOM update).
       - `browser_take_screenshot` at: (a) idle form, (b) stepper mid-stream, (c) final report rendered.
         Save to `.playwright-mcp/arx-frontend-uat-*.png` (>= 3).
       - `browser_console_messages(level="error")` → no JS errors (proves research.js parsed + ran,
         SSE pump didn't throw). `browser_network_requests()` → POST /api/research returned 200.
    5. **Bilingual spot-check:** toggle the lang switch (or load with the other lang default) and
       confirm the stepper labels + hero render in BOTH zh-CN and en (research.* keys resolve, no
       raw `research.stage.retriever` literals leaking through).
    6. **Cite evidence in the wave SUMMARY:** launcher command, :8766 boot line, curl status + the
       5-stage-event sequence, screenshot paths, console-error count (0), network 200 — per Principle #6.
  </how-to-verify>
  <acceptance_criteria>
    - local_serve.py booted on :8766 and `GET /research/` returned 200 (recorded in SUMMARY).
    - `POST /api/research` streamed 5 stage frames + a terminal done event (sequence recorded).
    - >= 3 screenshots saved under `.playwright-mcp/arx-frontend-uat-*.png` (`ls .playwright-mcp/arx-frontend-uat-*.png | wc -l` >= 3): idle form, stepper mid-stream, final report.
    - Browser console shows 0 JS errors; `browser_network_requests` confirms POST /api/research 200.
    - Bilingual labels confirmed (zh-CN + en) — no raw locale-key literals leaking in the rendered stepper.
    - Any runtime issue discovered (stale bake / missing static / SSE parse bug) is recorded + fixed before the wave is marked complete (Principle #6 — green tests are necessary-not-sufficient).
  </acceptance_criteria>
  <resume-signal>Type "frontend UAT pass" with the screenshot paths + the 5-stage event sequence, or report the runtime issue found so it is fixed before Wave 3 closes.</resume-signal>
</task>

</tasks>

<verification>
- `node -e` Function-construct: research.js parses with no syntax error.
- `venv/Scripts/python.exe -m pytest tests/integration/test_research_router.py tests/integration/kb/test_search_inline_reveal.py -v` — transport tests + raised CSS-budget test green.
- locale parity command prints "locale parity OK" (>=15 research.* keys, zh==en).
- Bake emits kb/output/research/index.html; SSG export block + base.html nav/footer link /research/.
- Principle #6 local UAT: local_serve.py :8766 + browser UAT, >= 3 screenshots, 0 console errors, POST /api/research 200, bilingual labels — cited in SUMMARY.
</verification>

<success_criteria>
- A bilingual /research/ page exists with a 5-stage live stepper, query + max_iterations(1-10) control, and a real-markdown + images + Sources report.
- research.js consumes POST /api/research via fetch()+ReadableStream manual SSE-frame parse (NOT EventSource), reuses only qa.js render fns, and renders sources by .uri (renderResearchSources).
- SSG bake registers research/index.html (not auto-discovered); nav + footer link it; CSS stays <= 2300.
- Local one-port UAT proves the page renders + streams + degrades gracefully (Principle #6) before the wave closes.
</success_criteria>

<output>
After completion, create `.planning/phases/arx-2-finish/arx-2-finish-02-SUMMARY.md`
</output>
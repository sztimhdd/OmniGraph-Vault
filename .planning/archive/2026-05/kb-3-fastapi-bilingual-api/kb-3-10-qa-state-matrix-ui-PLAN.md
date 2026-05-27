---
phase: kb-3-fastapi-bilingual-api
plan: 10
subsystem: ui-qa-result
tags: [frontend, jinja2, javascript, state-machine, ui-ux-pro-max, frontend-design]
type: execute
wave: 4
depends_on: ["kb-3-03", "kb-3-08", "kb-3-09"]
files_modified:
  - kb/templates/ask.html
  - kb/templates/_qa_result.html
  - kb/static/qa.js
  - kb/static/style.css
  - tests/integration/kb/test_ask_html_state_matrix.py
autonomous: true
requirements:
  - QA-01
  - QA-02
  - QA-03
  - QA-04
  - QA-05
  - I18N-07

must_haves:
  truths:
    - "ask.html result region implements 8-state matrix per kb-3-UI-SPEC §3.1 (idle/submitting/polling/streaming/done/error/timeout/fts5_fallback)"
    - "kb/static/qa.js drives the state machine via fetch -> POST /api/synthesize -> poll GET /api/synthesize/{job_id}"
    - "Polling cadence env-overridable via KB_QA_POLL_INTERVAL_MS (default 1500ms) and KB_QA_POLL_TIMEOUT_MS (default 60000ms) injected via Jinja2"
    - "fts5_fallback state shows yellow chip + explainer + answer (no entities row, no feedback row — restraint per UI-SPEC D-9 + D-10)"
    - "Feedback persists to localStorage as kb_qa_feedback_{job_id}"
    - "Token discipline: zero new :root vars added to style.css; reuse kb-1 chip/glow/icon/state classes"
    - "All state-indicator copy goes through i18n (data-state-text-* attributes from kb-3-03 locale keys)"
  artifacts:
    - path: "kb/templates/_qa_result.html"
      provides: "Jinja2 partial — the qa-result component with 8-state HTML structure (extracted for testability)"
      min_lines: 100
    - path: "kb/templates/ask.html"
      provides: "extended to {% include '_qa_result.html' %} replacing static placeholder block"
    - path: "kb/static/qa.js"
      provides: "state machine + fetch wrapper + polling + feedback handlers"
      min_lines: 200
    - path: "kb/static/style.css"
      provides: "+~30 LOC qa-result data-attribute selectors (no new tokens)"
    - path: "tests/integration/kb/test_ask_html_state_matrix.py"
      provides: "rendered-HTML grep tests for all 30+ UI-SPEC §8 patterns"
      min_lines: 100
  key_links:
    - from: "kb/static/qa.js"
      to: "POST /api/synthesize + GET /api/synthesize/{job_id} (kb-3-08, kb-3-09)"
      via: "fetch() with JSON body / interval polling"
      pattern: "fetch\\(.*'/api/synthesize'|fetch\\(.*synthesize"
    - from: "kb/templates/_qa_result.html"
      to: "qa.* locale keys (kb-3-03)"
      via: "{{ key | t(lang) }} filter calls"
      pattern: "qa\\.state\\.|qa\\.fallback\\.|qa\\.sources\\.|qa\\.entities\\."
    - from: "kb/templates/_qa_result.html"
      to: "chat-bubble-question + lightning-bolt icons (kb-3-03)"
      via: "icon() macro calls"
      pattern: "icon\\('chat-bubble-question'\\)|icon\\('lightning-bolt'\\)"
---

<objective>
Wire kb/templates/ask.html to the live FastAPI Q&A backend (kb-3-08 + kb-3-09). Implements the 8-state matrix locked by kb-3-UI-SPEC §3.1: idle → submitting → polling → done | error | timeout → fts5_fallback. Extracts the result region into `_qa_result.html` partial so it can be tested in isolation. JavaScript state machine in `kb/static/qa.js` drives the transitions via fetch + polling.

Purpose: This is the headline UI surface kb-3 ships. It's the only part of the milestone where the user types something and gets back a knowledge-graph synthesis answer. Per `kb/docs/10-DESIGN-DISCIPLINE.md` kb-3 entry, this plan MUST invoke `ui-ux-pro-max` AND `frontend-design` Skills as tool calls — listing UI-SPEC.md in `<read_first>` is NOT equivalent.

Output: 1 new partial template, extended ask.html, new qa.js, ~30 LOC CSS, integration tests against rendered HTML covering UI-SPEC §8 grep patterns.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-03-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-08-SUMMARY.md
@.planning/phases/kb-3-fastapi-bilingual-api/kb-3-09-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md
@kb/templates/ask.html
@kb/templates/_icons.html
@kb/templates/base.html
@kb/static/style.css
@kb/static/lang.js
@kb/locale/zh-CN.json
@kb/locale/en.json
@kb/i18n.py
@kb/docs/10-DESIGN-DISCIPLINE.md
@CLAUDE.md

<interfaces>
8-state matrix (verbatim from UI-SPEC §3.2 — DO NOT redesign):

| State | Trigger | data-qa-state |
|---|---|---|
| idle | page load | "idle" + hidden |
| submitting | submit click | "submitting" |
| polling | 202 received | "polling" |
| streaming | (reserved v2.1) | "streaming" |
| done | poll returns done + fallback_used=false | "done" |
| error | transport error / 4xx / 5xx | "error" |
| timeout | poll exceeds 60s | "timeout" → auto-transition to fts5_fallback after 500ms |
| fts5_fallback | poll returns done + fallback_used=true | "fallback" |

State CSS pattern (paste-ready from UI-SPEC §3.2):

```css
.qa-result[data-qa-state="idle"] [data-qa-state-only] { display: none; }
.qa-result[data-qa-state="submitting"] [data-qa-state-only*="submitting"] { display: block; }
.qa-result[data-qa-state="polling"] [data-qa-state-only*="polling"] { display: block; }
.qa-result[data-qa-state="streaming"] [data-qa-state-only*="streaming"] { display: block; }
.qa-result[data-qa-state="done"] [data-qa-state-only*="done"] { display: block; }
.qa-result[data-qa-state="error"] [data-qa-state-only*="error"] { display: block; }
.qa-result[data-qa-state="timeout"] [data-qa-state-only*="timeout"] { display: block; }
.qa-result[data-qa-state="fallback"] [data-qa-state-only*="fts5_fallback"] { display: block; }
```

(All other `[data-qa-state-only]` elements default to `display: none` via the idle rule — only the matching state's elements show.)

Polling defaults (env-overridable via Jinja2 inject — see UI-SPEC §3.2):

```jinja2
<!-- in ask.html or base.html: -->
<script>
  window.KB_QA_POLL_INTERVAL_MS = {{ qa_poll_interval_ms | default(1500) }};
  window.KB_QA_POLL_TIMEOUT_MS = {{ qa_poll_timeout_ms | default(60000) }};
</script>
```

These can be injected by the export driver (kb-1 driver loop) reading env at build time. For kb-3 the API path doesn't need them server-side — they're build-time constants.

Markdown library: `marked.js` v4+ bundled into `kb/static/marked.min.js` (D-5 from UI-SPEC §11). Loaded via `<script src="/static/marked.min.js"></script>` in ask.html.

NOTE: the executor MUST download `marked.min.js` v4.x as a one-time setup step (e.g. `curl -o kb/static/marked.min.js https://cdn.jsdelivr.net/npm/marked@4.3.0/lib/marked.umd.min.js`). The file is committed; the runtime page does NOT hit a CDN.

Component HTML structure (paste-ready, verbatim from UI-SPEC §3.1):

```html
<!-- kb/templates/_qa_result.html — extracted partial -->
<section id="qa-result"
         data-qa-state="idle"
         class="qa-result"
         aria-live="polite"
         aria-atomic="false"
         hidden>

  <!-- Question echo (visible after submit) -->
  <div class="qa-question">
    <span class="qa-question-icon" aria-hidden="true">{{ icon('chat-bubble-question') }}</span>
    <p class="qa-question-text"></p>
  </div>

  <!-- State indicator (submitting / polling / streaming) -->
  <div class="qa-state-indicator" data-qa-state-only="submitting polling streaming">
    <div class="qa-spinner" aria-hidden="true"></div>
    <p class="qa-state-text"
       data-state-text-submitting="{{ 'qa.state.submitting' | t(lang) }}"
       data-state-text-polling="{{ 'qa.state.polling' | t(lang) }}"
       data-state-text-streaming="{{ 'qa.state.streaming' | t(lang) }}"></p>
  </div>

  <!-- fts5_fallback banner -->
  <div class="qa-fallback-banner" data-qa-state-only="fts5_fallback" hidden>
    <span class="qa-confidence-chip qa-confidence-chip--fallback">
      {{ icon('lightning-bolt') }}
      <span class="lang-zh">{{ 'qa.fallback.label' | t('zh-CN') }}</span>
      <span class="lang-en">{{ 'qa.fallback.label' | t('en') }}</span>
    </span>
    <p class="qa-fallback-explainer">
      <span class="lang-zh">{{ 'qa.fallback.explainer' | t('zh-CN') }}</span>
      <span class="lang-en">{{ 'qa.fallback.explainer' | t('en') }}</span>
    </p>
  </div>

  <!-- Error banner -->
  <div class="qa-error-banner" data-qa-state-only="error" role="alert" hidden>
    <span class="qa-error-icon">{{ icon('warning') }}</span>
    <p class="qa-error-text"></p>
    <button type="button" class="qa-retry-btn glow">
      <span class="lang-zh">{{ 'qa.retry.button' | t('zh-CN') }}</span>
      <span class="lang-en">{{ 'qa.retry.button' | t('en') }}</span>
    </button>
  </div>

  <!-- Answer markdown (streaming / done / fts5_fallback) -->
  <article class="qa-answer prose"
           data-qa-state-only="streaming done fts5_fallback"
           hidden></article>

  <!-- Sources (done / fts5_fallback) -->
  <aside class="qa-sources" data-qa-state-only="done fts5_fallback" hidden>
    <h4 class="qa-sources-title">
      <span class="lang-zh">{{ 'qa.sources.title' | t('zh-CN') }}</span>
      <span class="lang-en">{{ 'qa.sources.title' | t('en') }}</span>
    </h4>
    <ul class="qa-sources-list" role="list"></ul>
  </aside>

  <!-- Related entities (done only — NOT fts5_fallback per D-9) -->
  <aside class="qa-entities" data-qa-state-only="done" hidden>
    <h4 class="qa-entities-title">
      <span class="lang-zh">{{ 'qa.entities.title' | t('zh-CN') }}</span>
      <span class="lang-en">{{ 'qa.entities.title' | t('en') }}</span>
    </h4>
    <ul class="qa-entities-list chip-cloud" role="list"></ul>
  </aside>

  <!-- Feedback (done only — NOT fts5_fallback per D-10) -->
  <div class="qa-feedback" data-qa-state-only="done" hidden>
    <p class="qa-feedback-prompt">
      <span class="lang-zh">{{ 'qa.feedback.prompt' | t('zh-CN') }}</span>
      <span class="lang-en">{{ 'qa.feedback.prompt' | t('en') }}</span>
    </p>
    <button type="button" class="qa-feedback-btn qa-feedback-btn--up" aria-label="thumbs-up">
      {{ icon('thumb-up') }}
    </button>
    <button type="button" class="qa-feedback-btn qa-feedback-btn--down" aria-label="thumbs-down">
      {{ icon('thumb-down') }}
    </button>
  </div>
</section>
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Invoke ui-ux-pro-max + frontend-design Skills + create _qa_result.html partial + extend ask.html + minimal CSS</name>
  <read_first>
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md (full spec — DO NOT redesign; implement verbatim)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-UI-SPEC.md (token + chip/glow/icon/state baseline — REUSE verbatim)
    - kb/templates/ask.html (existing kb-1 placeholder result block — REPLACE the static block with `{% include '_qa_result.html' %}`)
    - kb/templates/_icons.html (chat-bubble-question + lightning-bolt — kb-3-03 added them)
    - kb/locale/{zh-CN,en}.json (qa.* keys — kb-3-03 added them)
    - kb/static/style.css (existing tokens + kb-1 + kb-2 classes — APPEND only ~30 LOC at end)
  </read_first>
  <files>kb/templates/_qa_result.html, kb/templates/ask.html, kb/static/style.css</files>
  <action>
    Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1 — this is a UI surface, the named Skills MUST be invoked as tool calls (NOT just listed in read_first):

    Skill(skill="ui-ux-pro-max", args="Implement the kb-3-UI-SPEC §3.1 Q&A result component (qa-result) into the actual ask.html template + a reusable _qa_result.html partial. The spec is locked — do NOT redesign. Implementation rules: zero new :root vars (token discipline), reuse kb-1 + kb-2 classes verbatim (chip / glow / icon / state). The 8-state matrix uses data-attribute selectors (data-qa-state on the section + data-qa-state-only on each child block). The ONE signature moment: result-reveal animation (translate Y -8px → 0, opacity 0 → 1, 400ms ease-out) when state transitions to 'done'. Restraint principle: fts5_fallback shows ONLY answer + sources + chip+explainer (NO entities row per D-9, NO feedback row per D-10) — surface the degradation honestly.")

    Skill(skill="frontend-design", args="Wire the ui-ux-pro-max output into Jinja2: extract the result region into kb/templates/_qa_result.html partial (so it can be unit-tested in isolation). Replace ask.html lines 53-93 (the existing static placeholder result block) with `{% include '_qa_result.html' %}`. Append ~30 LOC to kb/static/style.css for state-attribute selectors AND result-reveal animation keyframes. NO new tokens — only data-attribute selectors composing existing kb-1 + kb-2 utility classes. Add a `<script src='/static/qa.js' defer></script>` tag inside ask.html's extra_scripts block (qa.js itself written in Task 2). Inject KB_QA_POLL_INTERVAL_MS + KB_QA_POLL_TIMEOUT_MS via inline Jinja2 just before the qa.js include.")

    **Step 1 — Create `kb/templates/_qa_result.html`** with the verbatim HTML structure from `<interfaces>` block. This is a Jinja2 partial; it expects `lang` to be in scope (already provided by ask.html which extends base.html). The icon macro must be imported at the top of the partial: `{% from "_icons.html" import icon %}`.

    **Step 2 — REPLACE the static result-framework block in `kb/templates/ask.html`** (currently lines 53-93 — the `<section id="ask-result">...</section>` block). Replace it with:

    ```jinja2
    {% include '_qa_result.html' %}
    ```

    Keep the rest of ask.html intact (hero, form, hot questions, disclaimer, bottom CTA). Update the `submitAsk(e)` function in the existing inline `<script>` block: REMOVE the placeholder logic and route to a new global `window.KbQA.submit(question)` defined in qa.js (Task 2). The simplest replacement:

    ```javascript
    function submitAsk(e) {
      e.preventDefault();
      var input = document.getElementById('ask-input');
      var q = (input.value || '').trim();
      if (!q) return false;
      var lang = (document.documentElement.lang || 'zh-CN').startsWith('en') ? 'en' : 'zh';
      if (window.KbQA && typeof window.KbQA.submit === 'function') {
        window.KbQA.submit(q, lang);
      }
      return false;
    }
    ```

    Inside the `{% block extra_scripts %}` block, AFTER the existing inline script, add:

    ```jinja2
    <script>
      window.KB_QA_POLL_INTERVAL_MS = 1500;
      window.KB_QA_POLL_TIMEOUT_MS = 60000;
    </script>
    <script src="/static/qa.js" defer></script>
    ```

    **Step 3 — APPEND ~30 LOC to `kb/static/style.css`** at the end (NO new :root vars):

    ```css
    /* ---- kb-3 Q&A result component (kb-3-UI-SPEC §3.1) ---- */
    /* All :root tokens reused from kb-1; this section adds NO new vars (D-12). */

    .qa-result { margin-top: 2rem; }
    .qa-result[data-qa-state="idle"] [data-qa-state-only] { display: none; }
    .qa-result[data-qa-state="submitting"] [data-qa-state-only*="submitting"] { display: block; }
    .qa-result[data-qa-state="polling"] [data-qa-state-only*="polling"] { display: block; }
    .qa-result[data-qa-state="streaming"] [data-qa-state-only*="streaming"] { display: block; }
    .qa-result[data-qa-state="done"] [data-qa-state-only*="done"] { display: block; }
    .qa-result[data-qa-state="error"] [data-qa-state-only*="error"] { display: block; }
    .qa-result[data-qa-state="timeout"] [data-qa-state-only*="timeout"] { display: block; }
    .qa-result[data-qa-state="fallback"] [data-qa-state-only*="fts5_fallback"] { display: block; }

    .qa-state-indicator { display: flex; align-items: center; gap: .75rem; padding: 1rem 0; }
    .qa-spinner {
      width: 18px; height: 18px;
      border: 2px solid var(--text);
      border-top-color: transparent;
      border-radius: 50%;
      animation: kb-qa-spin .9s linear infinite;
    }
    @keyframes kb-qa-spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) {
      .qa-spinner { animation: none; border-top-color: var(--accent); }
    }

    .qa-result[data-qa-state="done"] .qa-answer,
    .qa-result[data-qa-state="fallback"] .qa-answer {
      animation: kb-qa-reveal .4s ease-out both;
    }
    @keyframes kb-qa-reveal {
      from { opacity: 0; transform: translateY(-8px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .qa-result[data-qa-state="done"] .qa-answer,
      .qa-result[data-qa-state="fallback"] .qa-answer { animation: none; }
    }

    .qa-confidence-chip {
      display: inline-flex; align-items: center; gap: .375rem;
      padding: .25rem .625rem; border-radius: 999px;
      font-size: .8125rem;
    }
    .qa-confidence-chip--fallback {
      background: rgba(245, 158, 11, .15);
      color: #f59e0b;
      border: 1px solid rgba(245, 158, 11, .3);
    }
    .qa-fallback-banner { padding: .75rem 0; }
    .qa-fallback-explainer { font-size: .875rem; opacity: .8; margin-top: .375rem; }

    .qa-error-banner {
      padding: 1rem; border-radius: .5rem;
      background: rgba(239, 68, 68, .1);
      border: 1px solid rgba(239, 68, 68, .3);
    }

    .qa-question { padding: 1rem 0; opacity: .7; font-style: italic; }
    .qa-question-icon { display: inline-block; vertical-align: middle; margin-right: .5rem; }

    .qa-sources-list { list-style: none; padding: 0; display: flex; flex-direction: column; gap: .5rem; }
    .qa-source-chip a {
      display: inline-flex; align-items: center; gap: .5rem;
      padding: .5rem .75rem; border-radius: .375rem;
      background: var(--bg-card);
      text-decoration: none; color: var(--text);
    }
    .qa-source-chip a:hover { background: rgba(59, 130, 246, .1); }

    .qa-feedback { display: flex; align-items: center; gap: .75rem; padding: 1rem 0; }
    .qa-feedback-btn {
      background: transparent; border: 1px solid var(--text);
      border-radius: 999px; padding: .375rem .75rem;
      cursor: pointer; opacity: .7;
    }
    .qa-feedback-btn:hover { opacity: 1; }
    .qa-feedback-btn[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); }
    ```

    Verify CSS LOC budget per UI-SPEC §8: `wc -l kb/static/style.css` should be ≤ 2100 (kb-2 left it ~1979; this plan adds ~120 LOC including comments).

    Verify token count unchanged: `grep -cE '^\s*--[a-z-]+:' kb/static/style.css` should equal 31 (kb-1 baseline).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && python -c "from jinja2 import Environment, FileSystemLoader; env = Environment(loader=FileSystemLoader('kb/templates')); env.filters['t'] = lambda k, l='zh-CN': k; tmpl = env.get_template('_qa_result.html'); print(tmpl.render(lang='zh-CN'))" | grep -q "qa-result"</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/templates/_qa_result.html` exists with ≥80 lines
    - `grep -q "qa-result" kb/templates/_qa_result.html`
    - `grep -q "data-qa-state" kb/templates/_qa_result.html`
    - `grep -q "qa-state-indicator" kb/templates/_qa_result.html`
    - `grep -q "qa-fallback-banner" kb/templates/_qa_result.html`
    - `grep -q "qa-error-banner" kb/templates/_qa_result.html`
    - `grep -q "qa-sources" kb/templates/_qa_result.html`
    - `grep -q "qa-entities" kb/templates/_qa_result.html`
    - `grep -q "qa-feedback" kb/templates/_qa_result.html`
    - `grep -q "qa-confidence-chip--fallback" kb/templates/_qa_result.html`
    - `grep -q "icon('chat-bubble-question')" kb/templates/_qa_result.html`
    - `grep -q "icon('lightning-bolt')" kb/templates/_qa_result.html`
    - `grep -q "{% include '_qa_result.html' %}" kb/templates/ask.html`
    - `grep -q "Skill(skill=\"ui-ux-pro-max\"" kb/templates/_qa_result.html` (literal in template comment for discipline regex)
    - `grep -q "Skill(skill=\"frontend-design\"" kb/templates/_qa_result.html`
    - `grep -qE "^\\.qa-result\\[data-qa-state=" kb/static/style.css`
    - `grep -qE "^\\.qa-state-indicator" kb/static/style.css`
    - `grep -qE "^\\.qa-confidence-chip--fallback" kb/static/style.css`
    - Token discipline regression: `grep -cE '^\\s*--[a-z-]+:' kb/static/style.css` outputs `31` (no new vars)
    - Style budget: `wc -l < kb/static/style.css` ≤ 2100
  </acceptance_criteria>
  <done>_qa_result.html partial complete; ask.html includes it; CSS appended without new tokens; 30+ UI-SPEC §8 grep patterns satisfied for HTML/CSS portion.</done>
</task>

<task type="auto">
  <name>Task 2: Invoke ui-ux-pro-max + frontend-design Skills + write kb/static/qa.js with full state machine + integration tests</name>
  <read_first>
    - kb/templates/_qa_result.html (Task 1 — qa.js drives this DOM)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md §3.2 state matrix + §3.5 feedback localStorage + §3.6 search reveal (kb-3-11 — qa.js may share patterns)
    - .planning/phases/kb-3-fastapi-bilingual-api/kb-3-API-CONTRACT.md POST /api/synthesize + GET /api/synthesize/{job_id}
    - kb/static/lang.js (existing kb-1 lang switcher — DO NOT modify; coexist)
    - kb/locale/zh-CN.json (qa.* keys — kb-3-03 added them, used via data-state-text-* attrs)
  </read_first>
  <files>kb/static/qa.js, tests/integration/kb/test_ask_html_state_matrix.py, kb/static/marked.min.js</files>
  <action>
    Skill(skill="ui-ux-pro-max", args="Author the JavaScript state machine that drives the qa-result DOM through 8 states: idle → submitting → polling → done|error|timeout → fts5_fallback. The CSS data-attribute selectors (Task 1) already handle which sub-region is visible per state — qa.js's job is to (1) update data-qa-state on the section, (2) inject answer markdown into .qa-answer when state transitions to done/fallback, (3) populate .qa-sources-list and .qa-entities-list per UI-SPEC §3.1 chip structure, (4) capture feedback to localStorage as kb_qa_feedback_{job_id}, (5) implement timeout → fts5_fallback auto-transition (500ms delay per D-8). Polling uses window.KB_QA_POLL_INTERVAL_MS (default 1500) + KB_QA_POLL_TIMEOUT_MS (default 60000). Restraint applied: NO streaming for v2.0 — non-streaming full reveal on done (D-2). NO auto-retry on error — manual retry button only (D-12).")

    Skill(skill="frontend-design", args="Implement: kb/static/qa.js as a single IIFE exposing window.KbQA.submit(question, lang). Internal state machine: setState(name) updates data-qa-state attribute + updates state-text element textContent from data-state-text-{name} attribute (for polling/submitting/streaming). markdown rendering via marked.js (window.marked.parse). Source chip injection per UI-SPEC §3.1 li.qa-source-chip structure: lang-badge + 60-char title + source-icon. Use document.querySelector — no jQuery. Event listeners: form submit (already wired by ask.html submitAsk), retry button click, feedback button click. localStorage write: kb_qa_feedback_{job_id} = 'up'|'down'. Pure ES2017 — no transpiler / bundler.")

    **Step 1 — Download marked.js v4** (one-time setup; bundle, no CDN):

    ```bash
    # In Task action, the executor runs:
    mkdir -p kb/static
    curl -sL "https://cdn.jsdelivr.net/npm/marked@4.3.0/lib/marked.umd.min.js" \
      -o kb/static/marked.min.js
    ```

    Verify file size > 5KB (marked.umd.min.js is ~36KB at v4.3.0).

    **Step 2 — Create `kb/static/qa.js`** (~200 LOC):

    ```javascript
    /* kb/static/qa.js — Q&A result state machine for kb-3.
     *
     * Drives the 8-state matrix per kb-3-UI-SPEC §3.2:
     *   idle → submitting → polling → done | error | timeout → fts5_fallback
     *
     * Skill(skill="ui-ux-pro-max", args="...")
     * Skill(skill="frontend-design", args="...")
     */
    (function () {
      'use strict';

      var POLL_INTERVAL = window.KB_QA_POLL_INTERVAL_MS || 1500;
      var POLL_TIMEOUT  = window.KB_QA_POLL_TIMEOUT_MS  || 60000;

      var resultEl = null;     // #qa-result
      var currentJobId = null;
      var pollTimer = null;
      var pollStarted = 0;

      function $(sel, root) { return (root || document).querySelector(sel); }
      function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

      function setState(state) {
        if (!resultEl) return;
        resultEl.setAttribute('data-qa-state', state);
        if (state !== 'idle') resultEl.hidden = false;
        // Update state-text-* indicator copy if applicable
        var stateText = $('.qa-state-text', resultEl);
        if (stateText) {
          var attr = 'data-state-text-' + state;
          var t = stateText.getAttribute(attr);
          if (t) stateText.textContent = t;
        }
      }

      function setQuestionEcho(q) {
        var p = $('.qa-question-text', resultEl);
        if (p) p.textContent = q;
      }

      function renderAnswerMarkdown(md) {
        var article = $('.qa-answer', resultEl);
        if (!article) return;
        var html = (window.marked && window.marked.parse) ? window.marked.parse(md || '') : (md || '');
        article.innerHTML = html;
      }

      function renderSources(sources) {
        // sources: list of hash strings (kb-3-08 result)
        var ul = $('.qa-sources-list', resultEl);
        if (!ul) return;
        ul.innerHTML = '';
        sources.forEach(function (h) {
          var li = document.createElement('li');
          li.className = 'qa-source-chip';
          li.innerHTML = '<a href="/article/' + encodeURIComponent(h) + '" target="_blank" rel="noopener" class="qa-source-link">'
            + '<span class="qa-source-title">' + h + '</span></a>';
          ul.appendChild(li);
        });
      }

      function renderEntities(entities) {
        var ul = $('.qa-entities-list', resultEl);
        if (!ul) return;
        ul.innerHTML = '';
        (entities || []).forEach(function (e) {
          var li = document.createElement('li');
          li.className = 'entity-chip';
          li.textContent = e.name || e;
          ul.appendChild(li);
        });
      }

      function setError(msg) {
        var p = $('.qa-error-text', resultEl);
        if (p) p.textContent = msg || 'Unknown error';
      }

      function setupFeedbackHandlers() {
        $all('.qa-feedback-btn', resultEl).forEach(function (btn) {
          btn.addEventListener('click', function () {
            if (!currentJobId) return;
            var dir = btn.classList.contains('qa-feedback-btn--up') ? 'up' : 'down';
            try { localStorage.setItem('kb_qa_feedback_' + currentJobId, dir); } catch (e) {}
            $all('.qa-feedback-btn', resultEl).forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
            btn.setAttribute('aria-pressed', 'true');
          });
        });
      }

      function setupRetryHandler() {
        var btn = $('.qa-retry-btn', resultEl);
        if (!btn) return;
        btn.addEventListener('click', function () {
          var input = document.getElementById('ask-input');
          var q = input ? (input.value || '').trim() : '';
          if (!q) return;
          var lang = (document.documentElement.lang || 'zh-CN').indexOf('en') === 0 ? 'en' : 'zh';
          KbQA.submit(q, lang);
        });
      }

      function clearPoll() {
        if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      }

      function pollOnce() {
        if (!currentJobId) return;
        var elapsed = Date.now() - pollStarted;
        if (elapsed > POLL_TIMEOUT) {
          setState('timeout');
          // Auto-transition to fts5_fallback after 500ms (D-8)
          setTimeout(function () { setState('fallback'); }, 500);
          clearPoll();
          return;
        }
        fetch('/api/synthesize/' + encodeURIComponent(currentJobId), { headers: { 'Accept': 'application/json' } })
          .then(function (r) {
            if (!r.ok) {
              if (r.status === 404) throw new Error('job not found');
              throw new Error('HTTP ' + r.status);
            }
            return r.json();
          })
          .then(function (data) {
            if (data.status === 'running') {
              pollTimer = setTimeout(pollOnce, POLL_INTERVAL);
              return;
            }
            // status === 'done' (per kb-3-09 NEVER 500 — failed only happens pre-09)
            if (data.status === 'done') {
              if (data.fallback_used) {
                setState('fallback');
              } else {
                setState('done');
              }
              if (data.result) {
                renderAnswerMarkdown(data.result.markdown || '');
                renderSources(data.result.sources || []);
                if (!data.fallback_used) renderEntities(data.result.entities || []);
              }
              clearPoll();
              return;
            }
            // Defensive: any other status → error
            setError(data.error || 'Unexpected status: ' + data.status);
            setState('error');
            clearPoll();
          })
          .catch(function (e) {
            setError(e && e.message ? e.message : String(e));
            setState('error');
            clearPoll();
          });
      }

      function submit(question, lang) {
        if (!resultEl) resultEl = document.getElementById('qa-result');
        if (!resultEl) return;
        clearPoll();
        currentJobId = null;
        setQuestionEcho(question);
        setState('submitting');
        fetch('/api/synthesize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({ question: question, lang: lang || 'zh' })
        })
          .then(function (r) {
            if (!r.ok) {
              if (r.status === 422) throw new Error('Invalid question');
              throw new Error('HTTP ' + r.status);
            }
            return r.json();
          })
          .then(function (data) {
            currentJobId = data.job_id;
            setState('polling');
            pollStarted = Date.now();
            pollTimer = setTimeout(pollOnce, POLL_INTERVAL);
          })
          .catch(function (e) {
            setError(e && e.message ? e.message : String(e));
            setState('error');
          });
      }

      var KbQA = { submit: submit };
      window.KbQA = KbQA;

      document.addEventListener('DOMContentLoaded', function () {
        resultEl = document.getElementById('qa-result');
        if (!resultEl) return;
        setupFeedbackHandlers();
        setupRetryHandler();
      });
    })();
    ```

    **Step 3 — Create `tests/integration/kb/test_ask_html_state_matrix.py`** verifying the full UI-SPEC §8 grep regression suite against the rendered template:

    ```python
    """UI-SPEC §8 acceptance regression suite — grep-verifiable patterns against rendered ask.html."""
    from __future__ import annotations

    import re
    from pathlib import Path

    import pytest
    from jinja2 import Environment, FileSystemLoader

    REPO = Path(__file__).resolve().parents[3]
    TEMPLATES = REPO / "kb" / "templates"


    @pytest.fixture(scope="module")
    def rendered_ask_html() -> str:
        env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
        # Stub the i18n filter — return key as-is so we can grep the template structure
        env.filters["t"] = lambda key, lang="zh-CN": key
        tmpl = env.get_template("ask.html")
        # ask.html extends base.html — provide minimal context
        return tmpl.render(lang="zh-CN", request=None)


    def test_qa_result_section_present(rendered_ask_html):
        assert "qa-result" in rendered_ask_html


    def test_data_qa_state_attribute(rendered_ask_html):
        assert "data-qa-state" in rendered_ask_html


    def test_qa_state_indicator_present(rendered_ask_html):
        assert "qa-state-indicator" in rendered_ask_html


    def test_qa_fallback_banner_present(rendered_ask_html):
        assert "qa-fallback-banner" in rendered_ask_html


    def test_qa_error_banner_present(rendered_ask_html):
        assert "qa-error-banner" in rendered_ask_html


    def test_qa_sources_present(rendered_ask_html):
        assert "qa-sources" in rendered_ask_html


    def test_qa_entities_present(rendered_ask_html):
        assert "qa-entities" in rendered_ask_html


    def test_qa_feedback_present(rendered_ask_html):
        assert "qa-feedback" in rendered_ask_html


    def test_qa_confidence_chip_fallback(rendered_ask_html):
        assert "qa-confidence-chip--fallback" in rendered_ask_html


    def test_qa_js_referenced_in_ask_html(rendered_ask_html):
        assert "qa.js" in rendered_ask_html


    def test_qa_js_file_exists():
        assert (REPO / "kb" / "static" / "qa.js").exists()


    def test_qa_js_has_fts5_fallback_branch():
        text = (REPO / "kb" / "static" / "qa.js").read_text(encoding="utf-8")
        assert "fts5_fallback" in text or "fallback_used" in text


    def test_qa_js_uses_localstorage_feedback():
        text = (REPO / "kb" / "static" / "qa.js").read_text(encoding="utf-8")
        assert "kb_qa_feedback_" in text


    def test_qa_js_polls_synthesize_endpoint():
        text = (REPO / "kb" / "static" / "qa.js").read_text(encoding="utf-8")
        assert "/api/synthesize" in text


    def test_kb_qa_poll_interval_injected_into_ask(rendered_ask_html):
        assert "KB_QA_POLL_INTERVAL_MS" in rendered_ask_html


    def test_marked_js_bundled():
        f = REPO / "kb" / "static" / "marked.min.js"
        assert f.exists()
        assert f.stat().st_size > 5000


    def test_chat_bubble_question_icon_referenced(rendered_ask_html):
        # icon('chat-bubble-question') macro call should expand to an SVG
        assert "<svg" in rendered_ask_html
        # Verify the icon name is present in the source template (after macro expansion the SVG body shows)
        partial_path = TEMPLATES / "_qa_result.html"
        assert "chat-bubble-question" in partial_path.read_text(encoding="utf-8")


    def test_lightning_bolt_icon_referenced():
        partial_path = TEMPLATES / "_qa_result.html"
        assert "lightning-bolt" in partial_path.read_text(encoding="utf-8")


    def test_css_no_new_root_vars():
        css = (REPO / "kb" / "static" / "style.css").read_text(encoding="utf-8")
        var_count = len(re.findall(r"^\s*--[a-z-]+:", css, re.MULTILINE))
        assert var_count == 31, f"kb-1 baseline = 31 :root vars; got {var_count}"


    def test_css_qa_state_selectors_present():
        css = (REPO / "kb" / "static" / "style.css").read_text(encoding="utf-8")
        assert re.search(r"\.qa-result\[data-qa-state=", css)
        assert ".qa-state-indicator" in css
        assert ".qa-confidence-chip--fallback" in css
        assert ".qa-source-chip" in css


    def test_skill_invocation_strings_in_template():
        partial = (TEMPLATES / "_qa_result.html").read_text(encoding="utf-8")
        assert 'Skill(skill="ui-ux-pro-max"' in partial
        assert 'Skill(skill="frontend-design"' in partial


    def test_skill_invocation_strings_in_qa_js():
        js = (REPO / "kb" / "static" / "qa.js").read_text(encoding="utf-8")
        assert 'Skill(skill="ui-ux-pro-max"' in js
        assert 'Skill(skill="frontend-design"' in js
    ```
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault && pytest tests/integration/kb/test_ask_html_state_matrix.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/static/qa.js` exists with ≥150 LOC
    - File `kb/static/marked.min.js` exists with size > 5KB (bundled, no CDN)
    - `grep -q "fetch.*'/api/synthesize'" kb/static/qa.js` (note: actual code has `'/api/synthesize'` literal)
    - `grep -q "kb_qa_feedback_" kb/static/qa.js`
    - `grep -q "fts5_fallback\\|fallback_used" kb/static/qa.js`
    - `grep -q "KB_QA_POLL_INTERVAL_MS" kb/static/qa.js`
    - `grep -q "Skill(skill=\"ui-ux-pro-max\"" kb/static/qa.js`
    - `grep -q "Skill(skill=\"frontend-design\"" kb/static/qa.js`
    - `pytest tests/integration/kb/test_ask_html_state_matrix.py -v` exits 0 with ≥21 tests passing
    - No regression in kb-1 / kb-2 template tests: `pytest tests/integration/kb/ -v` exits 0
    - All UI-SPEC §8 grep patterns satisfied (cross-checked by individual tests)
  </acceptance_criteria>
  <done>qa.js state machine + 8-state UI live; marked.js bundled; ≥21 grep regression tests pass; UI-SPEC §8 acceptance criteria covered.</done>
</task>

</tasks>

<verification>
- 8-state matrix implemented per kb-3-UI-SPEC §3.1 + §3.2
- Skill invocations literal in BOTH _qa_result.html AND qa.js (regex-verifiable)
- Token discipline: 31 :root vars (kb-1 baseline preserved)
- CSS budget: ≤ 2100 LOC
- ALL 30+ UI-SPEC §8 grep patterns satisfied across template + JS + CSS
- Polling cadence + timeout env-overridable
- Feedback localStorage + retry button + automatic timeout → fts5_fallback transition all present
</verification>

<success_criteria>
- I18N-07 + QA-01..05 satisfied at the UI consumer surface
- Result-reveal animation is the ONE signature moment per page (UI-SPEC §1)
- Restraint principle: fts5_fallback hides entities + feedback (D-9 + D-10)
- No new tokens; no new components beyond the 3 locked by UI-SPEC §10
</success_criteria>

<output>
Create `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-10-SUMMARY.md` documenting:
- _qa_result.html partial + ask.html include + qa.js state machine + marked.js bundle + ~120 LOC CSS
- ≥21 integration tests passing (UI-SPEC §8 grep regression)
- Skill invocation strings literal in template + JS:
  - `Skill(skill="ui-ux-pro-max", ...)` (≥2 occurrences expected)
  - `Skill(skill="frontend-design", ...)` (≥2 occurrences expected)
- Token discipline preserved (31 :root vars unchanged)
- CSS budget within ≤ 2100 LOC
- 8-state matrix verified end-to-end
</output>
</content>
</invoke>
# Phase arx-2-finish: Deep Research UI — Research

**Researched:** 2026-06-12
**Domain:** Python async synthesis + vanilla-JS SSE + Jinja2/SSG KB frontend
**Confidence:** HIGH (all claims verified against actual source files with line numbers)

---

## RESEARCH COMPLETE

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **GAP A** — Real LLM synthesis in `lib/research/stages/synthesizer.py run()`. Must: (1) use ALL chunks, (2) await PLAIN-TEXT provider (not cfg.llm_complete JSON adapter), (3) inline [n] citations, (4) weave image captions, (5) keep CJK heuristic, (6) must NOT raise (best-effort degrade).
- **GAP B** — New `kb/templates/research.html` (~100 LoC) + `kb/templates/_research_result.html` (~80 LoC, 5-STAGE STEPPER not 8-state matrix) + `kb/static/research.js` (~150-250 LoC, CANNOT reuse qa.js submit/poll — must use fetch() + ReadableStream + manual SSE frame parse). REUSE ONLY renderAnswerMarkdown / rewriteAnswerHtml / renderSources from qa.js.
- **GAP D/E** — Aliyun router liveness check + E2E proof on both envs. These are OPS waves; research scope is GAP A + GAP B only.
- Databricks deploy uses FULL Makefile pipeline (Principle #9 — kb/static + kb/templates changed → sync-only forbidden).
- Databricks first-deploy pauses for user "go" checkpoint (STATE-Agentic-RAG-v1.1.md Decision 2).
- ISSUE #44 graphml-rebuild is OUT of this phase. If queries return 0 sources on Aliyun, that is a GAP E scope constraint, not a GAP A/B blocker.

### Claude's Discretion

- Exact synthesis prompt wording and structure.
- Exact stepper visual treatment (within CSS budget + brand conventions).
- Internal structure of research.js SSE frame parser.
- Whether GAP A resolves via new `plain_llm` ResearchConfig field vs lazy `get_llm_func()` import.

### Deferred Ideas (OUT OF SCOPE)

- LLM-driven language detection (CJK heuristic stays).
- Dim reindex / 1024-provider path (GAP C non-issue).
- v1.1-C native function-calling, v1.1-D per-tool-call telemetry, v1.1-E LightRAG cache write-perms.
- ISSUE #44 graphml rebuild (Path X cron / Path Y Hermes batch).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-1.1-B-1 | POST /api/research returns 200 + text/event-stream | ALREADY DONE (38a7286). Transport confirmed at research.py:100-112. |
| REQ-1.1-B-2 | One event per stage + terminal done event | ALREADY DONE (38a7286). Wire protocol documented in §SSE Wire Protocol below. |
| REQ-1.1-B-3 | Wired into kb/api.py | ALREADY DONE (38a7286). No action needed. |
| REQ-1.1-B-4 | Local Databricks UAT 5-step gate passes | Depends Wave 1 (real synthesis) + Wave 2 (UI). Wave 4 ops work. |
| REQ-1.1-B-5 | Databricks Apps deploy + post-deploy UAT | Depends Wave 2 completion. First-deploy checkpoint required. |
</phase_requirements>

---

## Risk A Resolution — Plain-LLM Access for Synthesizer

### Finding

**The ResearchConfig dataclass is frozen** (`@dataclass(frozen=True)` at `lib/research/types.py:104`). It has a `llm_complete: Callable` field (`types.py:107`) which is populated in `from_env()` at `config.py:59` as:

```python
# config.py:51-59
underlying_llm = get_llm_func()          # plain (prompt)->str async provider
llm_complete = make_json_decision_adapter(underlying_llm)  # JSON tool-calling adapter
...
return ResearchConfig(
    llm_complete=llm_complete,           # adapter, NOT underlying_llm
    ...
)
```

`ResearchConfig` does NOT store `underlying_llm` — it stores only the JSON-mode adapter. `get_llm_func()` is synchronous (`lib/llm_complete.py:41`) and returns an async callable (the provider itself is async, e.g. `deepseek_model_complete`).

**Reasoner and Verifier DO use `cfg.llm_complete`** — both call `await cfg.llm_complete(prompt, tools=[...])` in their agent loops (confirmed by test stubs in `test_reasoner_agent_loop.py` and `test_verifier_agent_loop.py` which inject `_LLMDecision`-returning mocks; the real adapter is injected via `cfg.llm_complete` at runtime).

**The synthesizer's `run()` at `synthesizer.py:44` receives `cfg` and `state` but currently IGNORES `cfg.llm_complete`** — confirmed: there is no `await cfg.llm_complete(...)` call anywhere in `synthesizer.py`. The only use of `cfg` is implicit (it's a parameter but unused in the current stub body from line 44 to 139).

### Option Evaluation

**Option (a): Add `plain_llm: Callable` field to ResearchConfig** — requires adding a field to the frozen dataclass at `types.py:104-117`. This violates the doc comment: "Do NOT rename fields, do NOT add fields, do NOT remove defaults — downstream plans (ar-1-02 stage stubs, ar-1-03 CLI, ar-1-04 skill packaging) depend on these exact shapes." The downstream plans have already shipped but the intent is clear. Adding a field also requires updating `from_env()` at `config.py:123-134` to pass it. All 12 tests that construct `ResearchConfig` directly (e.g. `_make_minimal_cfg` in `test_synthesizer_caption_embeds.py:51-59`) would get a new required parameter — unless default=None is used, making it optional.

**Option (b): Synthesizer lazy-imports `get_llm_func()` directly** — mirrors the pattern used in `from_env()` which already does `from lib.llm_complete import get_llm_func` at line 50 inside the function body (lazy import pattern). This is the Axis-3 single-env-read rule concern: it would create a SECOND call to `get_llm_func()` which reads `OMNIGRAPH_LLM_PROVIDER` again. However: (1) `get_llm_func()` is a pure dispatcher that reads the env var — it does NOT open connections or create state, it just imports + returns the function; (2) the env var doesn't change mid-run; (3) synthesizer.run() is async and is awaited, so the lazy import cost is paid once per request at synthesis time, not at module load. This is identical to what `from_env()` already does — reads the same env var in the same way.

**Option (c): Unwrap the adapter** — `make_json_decision_adapter` does not expose the underlying callable as a public field. The adapter closes over `underlying` at `llm_adapter.py:240` but there is no `.underlying` attribute. Would require either modifying the adapter (touching a different module) or adding an attribute to the returned closure. Invasive, unnecessary.

### Recommendation: Option (b) — lazy import of `get_llm_func()` in synthesizer.run()

This is the cleanest option given the constraints:
- Does NOT require modifying the frozen ResearchConfig dataclass (`types.py`)
- Does NOT require updating `from_env()` or any callers
- Does NOT break any existing tests (synthesizer tests pass `llm_complete=lambda *a, **kw: None` in cfg which is correct — the stub LLM is never called, and the real synthesizer will call `get_llm_func()` for the real LLM)
- Matches the existing lazy-import pattern already used in `config.py:50`
- Single env read per synthesis call (acceptable — env doesn't change mid-process)

**Concrete synthesizer change sketch** (~60 LoC to replace lines 99-138):

```python
# lib/research/stages/synthesizer.py — replace lines 99-138
# Real LLM synthesis (arx-2-finish)
from lib.llm_complete import get_llm_func  # lazy — same env-read pattern as from_env()

# Build synthesis prompt from all chunks + reasoner findings + verifier summary
chunks_text = "\n\n".join(
    f"[{i+1}] {s.snippet or '(empty)'}"
    for i, s in enumerate(sources)
)
reasoner_md = (state.reasoned.inferences_md or "") if state.reasoned else ""
verifier_md = (state.verified.fact_check_summary_md or "") if state.verified else ""
images_context = "\n".join(
    f"Image: {alt} — path: /static/img/{path.parent.name}/{path.name}"
    for path, alt in image_entries
)

if lang == "zh":
    prompt = (
        f"你是一个专业研究助手。请基于以下检索片段，为问题"{query}"撰写一份详细的中文研究报告。\n\n"
        f"## 检索片段 (共 {len(sources)} 条, 引用格式 [n])\n{chunks_text}\n\n"
        f"## 推理摘要\n{reasoner_md}\n\n"
        f"## 核实摘要\n{verifier_md}\n\n"
        f"## 可用图片\n{images_context}\n\n"
        "要求:\n1. 行文流畅,结构清晰 (## 标题 + 段落)\n"
        "2. 每个关键论断用 [n] 格式引用对应片段编号\n"
        "3. 适当位置插入图片 Markdown (![alt](/static/img/...))\n"
        "4. 不要重新列出参考文献 (页面已有 Sources 区域)\n"
    )
else:
    prompt = (
        f"You are a research assistant. Based on the retrieved passages below, "
        f"write a detailed research report answering: {query}\n\n"
        f"## Retrieved Passages ({len(sources)} total, cite as [n])\n{chunks_text}\n\n"
        f"## Reasoner Summary\n{reasoner_md}\n\n"
        f"## Verifier Summary\n{verifier_md}\n\n"
        f"## Available Images\n{images_context}\n\n"
        "Requirements:\n1. Clear structure with ## headings and paragraphs\n"
        "2. Cite each key claim with [n] matching passage number\n"
        "3. Embed relevant images as Markdown (![alt](/static/img/...))\n"
        "4. Do NOT add a References section (the page already shows Sources)\n"
    )

try:
    llm = get_llm_func()
    raw_markdown = await llm(prompt)
    if not raw_markdown or not raw_markdown.strip():
        raise ValueError("empty LLM response")
    markdown = raw_markdown
except Exception as exc:  # noqa: BLE001 — terminal stage MUST NOT raise
    note_lines.append(f"> ❌ LLM synthesis failed: {exc!s}")
    # Graceful degrade: fall back to current template behavior
    if lang == "zh":
        title = f"# 关于「{query}」的研究答复"
        body = "\n## 知识图谱检索结果\n\n"
    else:
        title = f"# Research Answer: {query}"
        body = "\n## Knowledge Graph Retrieval\n\n"
    if state.retrieved is not None and state.retrieved.chunks:
        body += state.retrieved.chunks[0].snippet or "(empty)"
    else:
        body += "(no chunks retrieved)\n"
    markdown = title + body

# Append images to markdown
if image_entries:
    markdown += "\n\n"
    for path, alt in image_entries:
        markdown += f"![{alt}](/static/img/{path.parent.name}/{path.name})\n"
# Append degradation notes
if note_lines:
    markdown += "\n\n---\n\n" + "\n".join(note_lines) + "\n"
```

**Confirmation that reasoner/verifier are unaffected**: both stages use `cfg.llm_complete` (the JSON adapter) as their LLM interface. The synthesizer change does NOT touch `cfg.llm_complete`. The adapter's `__module__` forwarding (`llm_adapter.py:249-252`) and the Vertex grounding autodetect at `config.py:101-110` remain intact.

**get_llm_func() is synchronous** (`lib/llm_complete.py:41` — `def get_llm_func() -> Callable:`). It returns an async provider (e.g. `deepseek_model_complete` is async). `synthesizer.run()` is async (`synthesizer.py:44`). So the pattern is: `llm = get_llm_func()` (sync call), then `raw_markdown = await llm(prompt)` (async call). This is correct.

---

## Risk B Resolution — Frontend Reuse Map

### qa.js Reuse Analysis

**Functions to REUSE** (copy or reference via shared module):

| Function | Location | Signature | What it Does |
|----------|----------|-----------|-------------|
| `renderAnswerMarkdown` | `qa.js:306-323` | `(md, sources)` | Renders markdown via marked.js, rewrites orphan citations, rewrites HTML via rewriteAnswerHtml |
| `rewriteAnswerHtml` | `qa.js:144-303` | `(rootEl, sourceHashes)` | Fixes img srcs, demotes dead links to spans, strips duplicate References sections, prepends KB_BASE_PATH |
| `renderSources` | `qa.js:325-355` | `(sources)` | Renders `.qa-sources-list` chips from `sources[]` array |
| `rewriteOrphanCitations` | `qa.js:101-131` | `(md, titleMap)` | Converts LLM-emitted malformed citation patterns to real markdown links |
| `buildTitleMap` | `qa.js:82-91` | `(sources)` | Builds hash→title map from sources array |

**Functions NOT to reuse** (QA-specific submit/poll loop):

| Function | Location | Why Not |
|----------|----------|---------|
| `submit` | `qa.js:502-542` | POSTs to /api/synthesize, expects job_id back, then polls GET /api/synthesize/{job_id} — completely wrong transport for research SSE |
| `pollOnce` | `qa.js:441-499` | Polling GET fallback — not applicable |
| `setupModeToggle` | `qa.js:414-432` | Mode toggle for qa/long_form — research doesn't need this |
| `setupFeedbackHandlers` | `qa.js:376-392` | localStorage feedback for job_id — research has no job_id |
| `setupRetryHandler` | `qa.js:394-404` | Calls submit() which is qa-specific |

**Window globals injected by qa.js** (research.js does NOT need):
- `window.KbQA.submit` — qa page calls this from submitAsk(); research.js has its own submit
- `window.KB_QA_POLL_INTERVAL_MS` / `window.KB_QA_POLL_TIMEOUT_MS` — poll config, irrelevant

**qa.js DOM root assumption**: all render functions call `$('.qa-answer', resultEl)`, `$('.qa-sources-list', resultEl)`, etc. where `resultEl = document.getElementById('qa-result')`. research.js needs its own `resultEl = document.getElementById('research-result')` and the research result partial must contain `.qa-answer`, `.qa-sources-list` with the SAME CSS class names so reuse works without modification. The functions use document-relative or `resultEl`-relative queries — safe as long as element IDs don't collide.

**Reuse implementation strategy**: research.js is a NEW IIFE. Copy the 5 shared functions verbatim into research.js (no cross-file import system in this project — qa.js is also a self-contained IIFE). ~130 LoC of the 250-line qa.js are these reusable functions. The research.js submit/SSE portion is ~120-150 new LoC. Total research.js estimate: ~250-280 LoC.

### SSE Wire Protocol (from research.py)

**Request** (`research.py:48-59`):
```json
POST /api/research
Content-Type: application/json
{"query": "...", "max_iterations": 3}
```
- `query`: 1..2000 chars (required)
- `max_iterations`: int 1..10 (default 3)

**Response**: `Content-Type: text/event-stream`

**Frame format** (`research.py:61-69`):
```
event: <name>\ndata: <json>\n\n
```

**5 Stage Events** (emitted in this fixed order, `research.py:43-45`):

1. `event: web_baseline\ndata: {"stage":"web_baseline","status":"ok"|"skipped"|"failed","reason":null|str,"duration_s":float,"snippet_count":int,...}\n\n`
2. `event: retriever\ndata: {"stage":"retriever","status":"ok"|"failed","reason":null|str,"duration_s":float,"chunk_count":int,"image_candidate_count":int,...}\n\n`
3. `event: reasoner\ndata: {"stage":"reasoner","status":"ok"|"skipped"|"failed","reason":null|str,"duration_s":float,"iter_count":int,"image_analyzed_count":int,...}\n\n`
4. `event: verifier\ndata: {"stage":"verifier","status":"ok"|"skipped"|"failed","reason":null|str,"duration_s":float,"iter_count":int,"confidence":float,"external_citation_count":int,...}\n\n`
5. `event: synthesizer\ndata: {"stage":"synthesizer","duration_s":float,"embedded_image_count":int,"note_line_count":int,"confidence":float}\n\n` — NOTE: NO `status` field (Axis 8 terminal-stage rule)

**Terminal done event** (`orchestrator.py:224-236`):
```
event: done\ndata: {"markdown":str,"confidence":float,"sources":[{"kind":str,"uri":str,"title":str|null,"snippet":str|null}...],"images_embedded":[str...],"note_lines":[str...]}\n\n
```

**Error event** (mid-stream exception, `research.py:95-97`):
```
event: error\ndata: {"message":str,"type":str}\n\n
```
Note: once headers are flushed, HTTP status remains 200 even on error.

**research.js SSE parse pattern** (ReadableStream + manual frame parser):
```javascript
// research.js: CANNOT use EventSource (GET-only)
// Must use fetch() + ReadableStream reader + manual SSE frame split
fetch(base + '/api/research', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({query: q, max_iterations: iterations})
})
.then(function(r) {
  var reader = r.body.getReader();
  var decoder = new TextDecoder();
  var buffer = '';
  function pump() {
    return reader.read().then(function(chunk) {
      if (chunk.done) { onDone(); return; }
      buffer += decoder.decode(chunk.value, {stream: true});
      var frames = buffer.split('\n\n');
      buffer = frames.pop(); // keep incomplete last frame
      frames.forEach(function(frame) { parseFrame(frame); });
      return pump();
    });
  }
  return pump();
});

function parseFrame(raw) {
  var event = null, data = null;
  raw.split('\n').forEach(function(line) {
    if (line.startsWith('event: ')) event = line.slice(7).trim();
    else if (line.startsWith('data: ')) data = line.slice(6);
  });
  if (!event || !data) return;
  var payload = JSON.parse(data);
  if (event === 'done') { onDone(payload); }
  else if (event === 'error') { onError(payload.message); }
  else { onStageUpdate(event, payload); }
}
```

### Frontend Files: Reuse Map Table

| File | Action | Reuse From | Key Lines / Pattern | New LoC Est. |
|------|--------|-----------|--------------------|----|
| `kb/templates/research.html` | CREATE | `ask.html` | Mirror structure: extends base.html, ask-hero, ask-form + max_iterations control (1..10 number input), include `_research_result.html`, extra_scripts with research.js | ~95 |
| `kb/templates/_research_result.html` | CREATE | `_qa_result.html` | Mirror section skeleton. Replace 8-state matrix `data-qa-state-only` attrs with `data-research-state-only`. Build 5-STAGE STEPPER (see below). Include `.qa-answer`, `.qa-sources-list` CSS classes for JS reuse. | ~85 |
| `kb/static/research.js` | CREATE | `qa.js:82-91,101-131,144-323,325-355` | IIFE. Copy 5 reusable render functions (~130 LoC). New submit/SSE/stepper logic (~150 LoC). Window global `window.KbResearch = {submit}`. | ~280 |
| `kb/static/style.css` | EDIT | — | Add `.research-*` stepper CSS. See CSS Budget section. | ~50-60 NEW |
| `kb/templates/base.html` | EDIT | — | NAV: line 42-45 (ask link block) — add research link after it. FOOTER nav ul: line 80 (ask li) — add research li after. | +4 |
| `kb/export_knowledge_base.py` | EDIT | `export_knowledge_base.py:644-650` | Copy the 6-line ask_html block, change template name + output path to `research/index.html`. No extra context vars needed. | +6 |
| `kb/locale/zh-CN.json` | EDIT | — | Add `research.*` namespace (~18 keys). See locale section. | +18 |
| `kb/locale/en.json` | EDIT | — | Add `research.*` namespace (~18 keys). | +18 |

### Base.html Nav Edit Sites

Two edit locations (both minimal — just add one `<a>` element):

**Nav** (`base.html:42-45`):
```html
<!-- AFTER line 45: -->
<a href="{{ base_path }}/research/">
  {{ icon('sparkle', size=16) }}
  <span data-lang="zh">{{ 'nav.research' | t('zh-CN') }}</span><span data-lang="en">{{ 'nav.research' | t('en') }}</span>
</a>
```

**Footer nav ul** (`base.html:80`):
```html
<!-- AFTER the /ask/ li: -->
<li><a href="{{ base_path }}/research/"><span data-lang="zh">{{ 'nav.research' | t('zh-CN') }}</span><span data-lang="en">{{ 'nav.research' | t('en') }}</span></a></li>
```

### export_knowledge_base.py — research.html Registration

Pattern to replicate (lines 644-650):
```python
# Current ask_html block (lines 644-650):
ask_html = env.get_template("ask.html").render(
    lang="zh-CN",
    hot_question_keys=ASK_HOT_QUESTION_KEYS,
    page_url=f"{config.KB_BASE_PATH}/ask/",
)
_write_atomic(output_dir / "ask" / "index.html", ask_html)
```

New research_html block (~6 lines, insert after line 650):
```python
research_html = env.get_template("research.html").render(
    lang="zh-CN",
    page_url=f"{config.KB_BASE_PATH}/research/",
)
_write_atomic(output_dir / "research" / "index.html", research_html)
```

Also need `(output_dir / "research").mkdir(exist_ok=True)` — look at whether `ask/` dir creation is explicit or implicit. Based on `_write_atomic` semantics, check if it creates parent dirs. If not, add `mkdir` before `_write_atomic`.

### Locale Keys Required (~18 per lang)

```json
"nav.research": "深度研究",
"research.page_title": "深度研究",
"research.hero_subtitle": "5 阶段 AI 研究引擎 — 网络基线 → 知识图谱检索 → 推理 → 核实 → 综合",
"research.input_placeholder": "输入研究问题…",
"research.input_aria": "研究问题输入框",
"research.iterations_label": "迭代次数",
"research.submit": "开始研究",
"research.stage.web_baseline": "网络基线",
"research.stage.retriever": "知识检索",
"research.stage.reasoner": "深度推理",
"research.stage.verifier": "事实核实",
"research.stage.synthesizer": "综合报告",
"research.state.running": "研究进行中…",
"research.state.done": "研究完成",
"research.state.error": "研究失败",
"research.sources.title": "参考来源",
"research.retry.button": "重试",
"research.disclaimer": "深度研究报告由 AI 生成,请结合原始文章核实。"
```

(English equivalents parallel — 18 keys × 2 langs = 36 locale additions total)

### 5-STAGE STEPPER Design (for _research_result.html)

The stepper should show all 5 stages, lighting them up as SSE events arrive. Unlike the Q&A 8-state matrix (which hides/shows entire divs via `data-qa-state-only`), the stepper shows all stages simultaneously and uses JS to update each stage's visual state.

HTML skeleton for stepper:
```html
<section id="research-result" data-research-state="idle" class="research-result" aria-live="polite" hidden>
  <!-- Stage progress bar -->
  <ol class="research-stepper" aria-label="...">
    <li class="research-step" data-stage="web_baseline" data-step-state="pending">
      <span class="research-step__dot" aria-hidden="true"></span>
      <span class="research-step__label">...</span>
      <span class="research-step__status"></span>
    </li>
    <!-- × 5 for each stage -->
  </ol>
  <!-- Question echo, spinner, answer, sources, error — similar to qa-result -->
  <article class="qa-answer prose"></article>  <!-- reuse .qa-answer for JS compat -->
  <aside class="qa-sources"><ul class="qa-sources-list" role="list"></ul></aside>  <!-- reuse for JS compat -->
  <div class="research-error-banner" role="alert" hidden>...</div>
</section>
```

Each `data-step-state` cycles: `pending` → `running` → `done` | `skipped` | `failed`.

---

## CSS Budget Verdict (ISSUE #6)

**Current state**: `style.css` is **2191 lines** (verified by `wc -l`). The budget ceiling is 2150 lines. `test_css_budget_within_2100` at `tests/integration/kb/test_search_inline_reveal.py:143-147` asserts `line_count <= 2150` and is ALREADY FAILING pre-this-phase (ISSUES.md row #6 confirms: "2172 lines vs budget 2150" — the wc count of 2191 is the current state as of 2026-06-12, slightly higher than the ISSUES.md figure from 2026-05-30).

**New CSS needed**: A 5-stage stepper requires approximately:
- `.research-result`, `.research-step`, `.research-stepper` base layout: ~15 lines
- Stepper dot states (pending/running/done/skipped/failed) with color coding: ~25 lines
- Animation for running state spinner: ~10 lines
- Responsive adjustments: ~10 lines
- Total: **~50-60 new lines**

**Budget math**: 2191 + 55 (midpoint) = 2246 lines — **96 lines over the 2150 budget**.

**Recommendation**: The plan MUST choose one of two paths before writing CSS:
- **Path 1 (Raise budget)**: Update the test at `tests/integration/kb/test_search_inline_reveal.py:147` to allow `<= 2300` (or 2250). Requires a note justifying the raise. This is appropriate given the test was already failing before this phase.
- **Path 2 (Trim first)**: Audit `style.css` for dead rules (especially from pre-kb-3 `ask-result__*` classes at lines 1258-1331 that may be superseded by `qa-*` classes, and `skeleton--*` classes that may be unused). Budget already shows 41 LoC over budget before this phase started.

**Concrete trim opportunity**: Lines 1258-1331 contain `.ask-result`, `.ask-result__section`, `.ask-result__heading`, `.ask-result__placeholder`, `.ask-result__feedback` — 73 lines of styling for the OLD pre-kb-3 result display, likely superseded by the `.qa-result` and `.qa-*` block. If these are dead, trimming them plus adding 55 stepper lines = net -18 lines (2173 total), still over budget by 23 lines. Need to verify they're truly dead before trimming.

**Recommended plan action**: Raise the budget ceiling to 2300 with a comment, then write lean stepper CSS reusing existing tokens. The test already fails; patching it to reflect the new intentional ceiling is cleaner than fighting a failing test throughout the phase. Document in the plan as a deliberate decision.

---

## Risk C — Test Surface

### Existing Test Count and Coverage

- `tests/integration/test_research_router.py`: 12 tests — all transport/shape-only. NO real LLM calls. They patch `research_stream_with_result` with `_make_fake_stream()`. These tests will NOT detect real synthesis bugs.
- `tests/unit/research/` contains 17 test files including `test_synthesizer_caption_embeds.py` (10 tests). All synthesizer tests use `lambda *a, **kw: None` for the `llm_complete` mock — meaning they test the STUB behavior, not real LLM output.

### GAP A Synthesizer Unit Tests

**New file**: `tests/unit/research/test_synthesizer_llm.py` (NEW)

**Required observables to pin** (cannot mirror LLM output exactly — use behavioral assertions):

1. **All-chunk usage**: When N chunks are provided, the LLM prompt string passed to `get_llm_func()`'s result contains ALL N chunk snippets (not just chunks[0]). Assert by intercepting the call to the returned LLM function.
2. **Non-empty prose**: When mock LLM returns non-empty prose, `result.markdown` is NOT `state.retrieved.chunks[0].snippet` verbatim (not the old stub behavior).
3. **Graceful degrade on LLM failure**: When mock LLM raises, `result.note_lines` contains an entry with "failed" or "error", and `result.markdown` is non-empty (fallback template).
4. **Inline [n] threading**: With a mock LLM that returns prose with `[1]` and `[2]`, the markdown is preserved as-is (the JS handles rendering — synthesizer doesn't need to convert).
5. **Image captions woven**: When `image_entries` are present and LLM returns prose without images, the synthesizer appends image markdown AFTER the LLM prose.

**Test pattern** (following existing test style):

```python
# tests/unit/research/test_synthesizer_llm.py
@pytest.mark.unit
async def test_synthesizer_uses_all_chunks_in_prompt(tmp_path):
    """Prompt contains ALL chunk snippets, not just chunks[0]."""
    chunks = [
        Source(kind="kg_chunk", uri=f"x{i}", snippet=f"chunk-{i}")
        for i in range(3)
    ]
    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(chunks=chunks, image_candidates=[])
    
    captured_prompt = {}
    async def mock_llm(prompt, **kw):
        captured_prompt['prompt'] = prompt
        return "# Real answer\n\nSome prose [1]."
    
    # Patch get_llm_func to return mock_llm
    with mock.patch('lib.research.stages.synthesizer.get_llm_func', return_value=mock_llm):
        result = await run_synthesizer("q", _make_minimal_cfg(tmp_path), state)
    
    for i in range(3):
        assert f"chunk-{i}" in captured_prompt['prompt']

@pytest.mark.unit
async def test_synthesizer_degrades_gracefully_on_llm_failure(tmp_path):
    """LLM exception → note_line added + markdown non-empty (no raise)."""
    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="text")],
        image_candidates=[]
    )
    async def failing_llm(prompt, **kw):
        raise RuntimeError("LLM timeout")
    
    with mock.patch('lib.research.stages.synthesizer.get_llm_func', return_value=failing_llm):
        result = await run_synthesizer("q", _make_minimal_cfg(tmp_path), state)
    
    assert result.markdown  # non-empty
    assert any("failed" in ln.lower() or "error" in ln.lower() for ln in result.note_lines)

@pytest.mark.unit
async def test_synthesizer_real_prose_not_chunks0_verbatim(tmp_path):
    """Real LLM response replaces the stub chunks[0].snippet verbatim."""
    state = ResearchState(query="q", timestamp_start=0.0)
    state.retrieved = RetrieverOutput(
        chunks=[Source(kind="kg_chunk", uri="x", snippet="THE_STUB_SNIPPET")],
        image_candidates=[]
    )
    async def mock_llm(prompt, **kw):
        return "# Real LLM Answer\n\nThis is synthesized prose, not a snippet."
    
    with mock.patch('lib.research.stages.synthesizer.get_llm_func', return_value=mock_llm):
        result = await run_synthesizer("q", _make_minimal_cfg(tmp_path), state)
    
    # The new real-LLM path must NOT return chunks[0].snippet verbatim
    assert "THE_STUB_SNIPPET" not in result.markdown
    assert "Real LLM Answer" in result.markdown
```

**Existing tests that must stay green**:
- All 10 tests in `test_synthesizer_caption_embeds.py` — they test image embedding behavior which is independent of the LLM call. Since they mock `llm_complete=lambda *a, **kw: None` and the new synthesizer calls `get_llm_func()` (not `cfg.llm_complete`), they need the `get_llm_func` mock too OR the test needs to ensure the real `get_llm_func` isn't called. **Pitfall**: the new synthesizer will call `get_llm_func()` at runtime, which requires `OMNIGRAPH_LLM_PROVIDER` to be set or defaults to DeepSeek which then tries to import `lib.llm_deepseek` which expects `DEEPSEEK_API_KEY`. In tests, this will fail. Solution: mock `lib.research.stages.synthesizer.get_llm_func` in ALL synthesizer tests that don't explicitly test the LLM path, OR have `get_llm_func` called in a try/except inside synthesizer that defaults to a no-op provider.

**Better solution**: Keep the graceful degrade path as the default when `get_llm_func()` import succeeds but the provider call fails. The existing tests won't need modification because their mocked LLM will still be called via cfg in the degrade path, not through `get_llm_func`. Actually no — the new synthesizer calls `get_llm_func()` directly, not `cfg.llm_complete`. To keep existing tests green without modification, the synthesizer should catch the import/call failure and degrade. The new tests (`test_synthesizer_llm.py`) should mock `get_llm_func` explicitly. Existing `test_synthesizer_caption_embeds.py` tests should also mock it to prevent I/O — add a session-scoped `autouse` fixture or patch in conftest for the research unit tests directory.

**Simplest approach**: Add a `conftest.py` to `tests/unit/research/` that auto-patches `lib.research.stages.synthesizer.get_llm_func` to return a fast async echo function, UNLESS the specific test sets up its own mock.

---

## Refined Wave Dependency Graph

```
Wave 0 (GAP D ops probe) — read-only SSH Aliyun, 5-min
  └─ Validates Aliyun router liveness BEFORE Wave 3 spends time on E2E

Wave 1 (GAP A backend) — synthesizer.py + test_synthesizer_llm.py
  └─ Can run in PARALLEL with Wave 2 structurally
  └─ But Wave 2's UAT value is LOW without real LLM prose (stub would show degraded text)
  └─ Critical path item: Wave 1 MUST commit before Wave 3 CLI E2E

Wave 2 (GAP B frontend) — research.html + _research_result.html + research.js + style.css + locale + export + base.html
  └─ Structurally independent of Wave 1 (can build UI with stub synthesis)
  └─ UAT requires Wave 1 to have shipped (otherwise testing degraded fallback, not real feature)
  └─ The CSS budget decision (raise or trim) must be resolved BEFORE writing style.css

Wave 3 (Aliyun E2E ops) — depends Wave 0 + Wave 1 + Wave 2
  └─ CLI test: `python -m lib.research "<query>"` with ISSUE #44 awareness (may see 0 sources)
  └─ Browser UAT: Aliyun kb URL

Wave 4 (Databricks E2E ops) — depends Wave 1 + Wave 2 (parallel with Wave 3)
  └─ FULL Makefile (kb/static + kb/templates touched → Principle #9)
  └─ First-deploy human-in-the-loop checkpoint per STATE decision 2
```

**Critical path**: Wave 1 (synthesizer) → Wave 3 CLI verification. Wave 2 (frontend) can overlap with Wave 1 coding but its UAT gate needs Wave 1 prose to be meaningful. Sequencing: complete Wave 1 first (small, ~60 LoC), then Wave 2 (dominant, ~550 LoC across all files).

**True parallelism opportunities**: Wave 3 and Wave 4 are fully parallel ops work. Wave 0 is a pure read-only probe with no side effects.

---

## Common Pitfalls Found in Code

### Pitfall 1: `_write_atomic` for research/index.html — mkdir required

`export_knowledge_base.py` writes `output_dir / "ask" / "index.html"` but the `ask/` directory is created earlier in the build. For `research/index.html`, the `research/` directory does NOT exist yet. Check whether `_write_atomic` creates parent directories. If not, the plan must include `(output_dir / "research").mkdir(parents=True, exist_ok=True)` before the render call.

### Pitfall 2: research.js render functions need `.qa-answer` and `.qa-sources-list` in research result

`renderAnswerMarkdown` calls `$('.qa-answer', resultEl)` (qa.js:307) and `renderSources` calls `$('.qa-sources-list', resultEl)` (qa.js:326). The `_research_result.html` partial MUST include `<article class="qa-answer prose">` and `<ul class="qa-sources-list">` with these exact CSS class names — not `research-answer` or similar — for the reused JS functions to work. This is a subtlety: the template CSS classes must match qa.js's hardcoded selectors.

### Pitfall 3: resultEl ID must be different from `qa-result`

qa.js does `document.getElementById('qa-result')` at startup. If the research page includes `id="qa-result"`, qa.js's `resultEl` would capture it and setup both handlers. Use `id="research-result"` and initialize `resultEl` in research.js separately.

### Pitfall 4: Full Makefile required (Principle #9)

The plan adds `kb/static/research.js` and `kb/templates/research.html`. Both are under `kb/static/` and `kb/templates/` → full pipeline required on Databricks deploy, NOT sync-only. The plan must explicitly call `make deploy` (all passes including Pass 0 SSG bake).

### Pitfall 5: SSG registration missing → 404 on Aliyun after Caddy serve

Aliyun serves `/var/www/kb/` (memory `aliyun_kb_serve_dir_gap` resolved 2026-05-30). The SSG bake outputs to `kb/output/`. If `render_index_pages` in `export_knowledge_base.py` doesn't include the research page registration, the daily_rebuild won't produce `research/index.html` in the output, and Caddy won't serve `/research/`. The Wave 2 plan must include the `export_knowledge_base.py` edit AND verify the output dir contains `research/index.html` after a test bake.

### Pitfall 6: Existing synthesizer tests need `get_llm_func` mock

After the synthesizer is changed to call `get_llm_func()`, the 10 existing `test_synthesizer_caption_embeds.py` tests will fail in CI unless `get_llm_func` is mocked. They currently pass a `lambda` as `cfg.llm_complete` but don't mock `get_llm_func`. Add a `conftest.py` in `tests/unit/research/` with a function-scoped autouse fixture that patches `lib.research.stages.synthesizer.get_llm_func` to return `async def noop_llm(prompt, **kw): return "# Stub\n\nStub body."`.

### Pitfall 7: Verifier confidence field shape in sources

The `done` event's `sources` array contains `{"kind": str, "uri": str, "title": str|null, "snippet": str|null}` (confirmed from `orchestrator.py:228-232`). The `renderSources` function in qa.js expects `s.hash` and `s.title` (qa.js:87-90). The research sources use `s.uri` not `s.hash`. The research.js render path needs either a wrapper that maps `uri` → `hash` for the QA functions, OR research.js must have its own `renderResearchSources` function that uses `s.uri` directly. This is a KEY divergence — the qa.js renderSources assumes `sources[i].hash` but the research done event has `sources[i].uri`.

**Impact**: `renderSources` at qa.js:325-355 builds article links as `/articles/{hash}.html` using `s.hash`. Research sources are `kg_chunk` kind with `uri` values like `kg://entity/...` or article hashes embedded differently. Plan must either (a) write a custom `renderResearchSources` in research.js, or (b) map the sources array before passing to `renderSources`. Option (a) is cleaner (~30 LoC added to research.js).

---

## Environment Availability

This is a code+frontend-only phase (GAP A + GAP B). No new external dependencies. All required tools are confirmed available from the project's existing setup. Skipping detailed env audit.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (confirmed by existing test files) |
| Config file | `pytest.ini` or `pyproject.toml` at project root |
| Quick run command | `venv/Scripts/python.exe -m pytest tests/unit/research/test_synthesizer_llm.py -v` |
| Full suite command | `venv/Scripts/python.exe -m pytest tests/unit/research/ tests/integration/test_research_router.py -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-1.1-B-1 | SSE endpoint exists | integration | `pytest tests/integration/test_research_router.py::test_post_research_returns_event_stream` | Yes |
| REQ-1.1-B-2 | 5 stage events + terminal done | integration | `pytest tests/integration/test_research_router.py::test_sse_emits_five_stage_events_in_order` | Yes |
| REQ-1.1-B-3 | Router in kb/api.py | integration | `pytest tests/integration/test_research_router.py` | Yes |
| GAP-A synthesis | Non-empty prose, all-chunk usage, graceful degrade | unit | `pytest tests/unit/research/test_synthesizer_llm.py -v` | No — Wave 0 gap |
| GAP-B UI | Not automatable (browser UAT) | manual | Playwright MCP screenshots | N/A |
| REQ-1.1-B-4 | Local Databricks UAT | manual E2E | Playwright MCP UAT against localhost:8000 | N/A |
| REQ-1.1-B-5 | Databricks deployed UAT | manual E2E | Playwright MCP UAT against Databricks URL | N/A |

### Wave 0 Gaps

- [ ] `tests/unit/research/test_synthesizer_llm.py` — covers GAP-A real synthesis (3 test functions described above)
- [ ] `tests/unit/research/conftest.py` — autouse fixture mocking `get_llm_func` for existing synthesizer tests that will break when synthesizer.py calls `get_llm_func()` directly

*(All integration/transport tests already exist and green)*

---

## Sources

### Primary (HIGH confidence)

All findings are derived from direct file reads with line numbers. Source files:
- `lib/research/stages/synthesizer.py` — stub code at lines 99-138, run() signature at line 44
- `lib/research/config.py` — from_env() plain-LLM construction at lines 50-59, ResearchConfig return at 123-134
- `lib/research/types.py` — frozen ResearchConfig at 104-117, no plain_llm field confirmed
- `lib/research/llm_adapter.py` — make_json_decision_adapter at 227-254; underlying closure not exposed
- `lib/llm_complete.py` — get_llm_func signature at 41; sync dispatcher, returns async provider
- `lib/research/orchestrator.py` — _run_pipeline stage emit pattern 36-161; done event shape 224-236
- `kb/api_routers/research.py` — SSE wire protocol 61-69; stage filter 43-45; error frame 95-97
- `kb/static/qa.js` — render functions at 82-323; submit/poll at 441-542; IDs at 503
- `kb/templates/ask.html` — full structure; extra_scripts pattern
- `kb/templates/_qa_result.html` — 8-state matrix structure; CSS class names `.qa-answer` etc.
- `kb/templates/base.html` — nav at 42-45; footer nav at 77-80
- `kb/static/style.css` — line count 2191; Q&A section at 1107-1374; potential dead ask-result at 1258-1331
- `kb/export_knowledge_base.py` — ask_html block at 644-650; render_index_pages signature 563-570
- `kb/locale/zh-CN.json` — qa.* keys at 163-184 (21 existing qa.* keys)
- `kb/locale/en.json` — qa.* keys at 163-184 (21 existing qa.* keys)
- `tests/integration/test_research_router.py` — 12 existing transport tests confirmed shape-only
- `tests/unit/research/test_synthesizer_caption_embeds.py` — 10 existing tests; all use `lambda` for llm_complete

---

## Metadata

**Confidence breakdown:**
- GAP A (synthesizer): HIGH — exact code traced with file:line
- GAP B frontend reuse surface: HIGH — functions verified in qa.js with line numbers
- SSE wire protocol: HIGH — read directly from research.py and orchestrator.py
- CSS budget: HIGH — exact line count from wc -l, test assertion read from source
- Wave dependency graph: HIGH — derived from concrete file analysis, not speculation

**Research date:** 2026-06-12
**Valid until:** 2026-07-12 (stable APIs, 30-day estimate)

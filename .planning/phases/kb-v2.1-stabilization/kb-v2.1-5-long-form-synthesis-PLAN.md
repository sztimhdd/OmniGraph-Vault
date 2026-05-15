---
phase: kb-v2.1-5-long-form-synthesis
requirements: [REQ-3 minimum-viable]
priority: P1
skills_required: [python-patterns, frontend-design, writing-tests]
wave: 3
depends_on: [kb-v2.1-4 (shares SynthesizeResult schema), kb-v2.1-2 (image paths render in long-form markdown)]
estimated_loc: 100-180
estimated_time: 0.5d
---

# Phase kb-v2.1-5 — Long-form Synthesis Minimum-Viable

## Goal

Add `mode=long_form` to `/api/synthesize` so users can request a deep research
article instead of a short Q&A answer. Reuse the existing `/kb/ask/` page +
8-state matrix + `SynthesizeResult` schema (from Phase 4) + image rendering
(from Phase 2). NO new endpoint, NO new page, NO preview/save/export flow.

## Why minimum-viable

The full long-form spec (vitaclaw-site agent's REQ 3) had:
- new endpoint or page
- preview behavior
- save/export behavior

We're shipping the **core feature only**: deep research markdown generation
+ structured sources/entities + inline images. Preview/save/export deferred to
v2.2+ if user needs them. This is a 0.5d add-on, not a 1-2d expansion.

## Why almost-free

The engine (`kg_synthesize.synthesize_response()`) already produces long
markdown — it just gets called with different prompt templates. Phase 4's
`SynthesizeResult` schema + Phase 2's image path rewriting + Phase 1's KG
hardening + the existing 8-state UI matrix already give us 90% of what
long-form needs. This phase just adds:

1. A prompt template that asks for long-form output
2. A mode parameter on `/api/synthesize`
3. A UI toggle on `/kb/ask/`

## Files affected

| File | Action |
|---|---|
| `kb/services/synthesize.py` | MODIFY — add `_LONG_FORM_PROMPT_TEMPLATE` (zh + en); dispatch on `mode` param |
| `kb/api.py` | MODIFY — `/api/synthesize` POST body accepts `mode: Literal["qa", "long_form"]` (default `"qa"`); pass through to wrapper |
| `kb/templates/ask.html` | MODIFY — add mode toggle button group above question textarea |
| `kb/static/qa.js` | MODIFY — read mode toggle state; include in POST body; persist via localStorage `kb_qa_mode` |
| `kb/locale/zh-CN.json` + `kb/locale/en.json` | MODIFY — toggle labels + tooltip strings |
| `kb/static/style.css` | MODIFY — toggle button group styling (reuse kb-1 `.glow` + chip pattern; ZERO new `:root` vars) |
| `tests/integration/kb/test_long_form_synthesis.py` | NEW — mode parameter dispatch, prompt template injection, schema parity |
| `tests/integration/kb/test_qa_link_contract.py` (from 260515) | EXTEND — verify mode toggle doesn't break source chip rendering |

## Read first

1. `.planning/phases/kb-v2.1-stabilization/kb-v2.1-4-structured-synthesize-PLAN.md` — `SynthesizeResult` schema (this phase reuses)
2. `.planning/phases/kb-3-fastapi-bilingual-api/kb-3-UI-SPEC.md` § 3.1-3.2 — Q&A 8-state matrix (this phase preserves)
3. `kb/services/synthesize.py` post-Phase-4 state — `kb_synthesize` happy path
4. `kg_synthesize.py` line ~105 — C1 contract `synthesize_response(query_text, mode='hybrid')` (NOT to be modified — KB wrapper uses different prompt to invoke)
5. `kb/templates/ask.html` post-Phase-4 — current page structure
6. `kb/static/qa.js` post-Phase-4 — submit + result rendering flow
7. `.planning/phases/kb-v2.1-stabilization/DEFERRED.md` — what's still deferred (preview/save/export)

## Action

### Task 1 — Define long-form prompt templates

Invoke `Skill(skill="python-patterns", args="Define _LONG_FORM_PROMPT_TEMPLATE_ZH and _EN at module level in kb/services/synthesize.py. Idiomatic Python multi-line string constants. Templates parameterized by user question. Output target: 1500-3000 字 / 800-1500 words. Structured: H2 headings × 3-5 sections. Citations: explicit /article/{hash} refs (lets Phase 4 structured resolution find sources). Images: instruct to include markdown image references when source articles have relevant images. Conservative: 'do not fabricate' clause.")`.

```python
_LONG_FORM_PROMPT_TEMPLATE_ZH = """请基于知识图谱中的真实内容,写一篇深度研究文章。

主题:{question}

要求:
1. 结构化:使用 markdown ## 标题分 3-5 个章节
2. 字数:1500-3000 字
3. 引用:每个论点引用具体来源,链接格式 [/article/{{hash}}.html]
   (hash 是文章在知识库中的 10 字符哈希)
4. 实体:关键技术 / 产品 / 人物用 **粗体** 标注
5. 图片:如果源文章中有相关图片,用 ![alt](URL) 引用
6. 不要编造任何信息 — 严格基于检索到的文章内容

请用中文回答。
"""

_LONG_FORM_PROMPT_TEMPLATE_EN = """Based on real content from the knowledge graph, write a deep research article.

Topic: {question}

Requirements:
1. Structure: use markdown ## headings with 3-5 sections
2. Length: 800-1500 words
3. Citations: cite specific sources for every claim, format [/article/{{hash}}.html]
   (hash is the 10-char article hash in the knowledge base)
4. Entities: bold **key technologies / products / people**
5. Images: include ![alt](URL) references when source articles have relevant images
6. Do not fabricate anything — strictly base on retrieved article content

Please answer in English.
"""
```

### Task 2 — Mode dispatch in `kb_synthesize`

Modify `kb_synthesize` to accept `mode` parameter:

```python
async def kb_synthesize(question: str, lang: str, job_id: str, mode: str = "qa") -> None:
    """Q&A or long-form synthesis depending on mode.

    mode='qa' (default): existing behavior — short answer to a specific question
    mode='long_form': wrap question in long-form prompt template, return research article

    Both modes return the same SynthesizeResult schema. Long-form just produces
    longer markdown + more sources/entities. UI flow (8-state matrix) is identical.
    """
    if mode == "long_form":
        template = _LONG_FORM_PROMPT_TEMPLATE_ZH if lang == "zh-CN" else _LONG_FORM_PROMPT_TEMPLATE_EN
        wrapped_question = template.format(question=question)
    else:
        wrapped_question = question  # qa mode: existing behavior

    # ... rest of existing kb_synthesize logic ...
    result = await kg_synthesize.synthesize_response(wrapped_question, mode='hybrid')
    # ... etc ...
```

### Task 3 — `/api/synthesize` route accepts mode

`kb/api.py`:

```python
class SynthesizeRequest(BaseModel):
    question: str
    lang: Literal["zh-CN", "en"] = "zh-CN"
    mode: Literal["qa", "long_form"] = "qa"

@app.post("/api/synthesize")
async def synthesize(req: SynthesizeRequest, background_tasks: BackgroundTasks):
    job_id = job_store.create_job()
    background_tasks.add_task(kb_synthesize, req.question, req.lang, job_id, req.mode)
    return {"job_id": job_id, "status": "running"}
```

Default `mode="qa"` preserves backward compat — qa.js clients that don't send mode still work.

### Task 4 — UI toggle in ask.html + qa.js

Invoke `Skill(skill="frontend-design", args="Add mode toggle button group to kb/templates/ask.html above the question textarea. 2-button toggle: '快速回答 / Quick answer' vs '深度研究 / Deep research'. Use existing kb-1 .glow + chip patterns. ZERO new :root vars. Position: above textarea, below hero. Default state: qa mode selected. Persist via localStorage kb_qa_mode. Submit handler reads selected mode and includes in POST body. Result region rendering does NOT change — same 8-state matrix renders both modes.")`.

`kb/templates/ask.html` (insertion):

```html
<div class="qa-mode-toggle" role="radiogroup" aria-label="Synthesis mode">
  <button type="button"
          class="qa-mode-btn qa-mode-btn--qa"
          role="radio"
          aria-checked="true"
          data-mode="qa">
    <span class="lang-zh">快速回答</span><span class="lang-en">Quick answer</span>
  </button>
  <button type="button"
          class="qa-mode-btn qa-mode-btn--long"
          role="radio"
          aria-checked="false"
          data-mode="long_form">
    <span class="lang-zh">深度研究</span><span class="lang-en">Deep research</span>
  </button>
</div>
```

`kb/static/qa.js` additions:

```javascript
// On load: read kb_qa_mode from localStorage; default 'qa'
var currentMode = localStorage.getItem('kb_qa_mode') || 'qa';
setActiveModeButton(currentMode);

// Toggle button click: update state + localStorage
toggleButtons.forEach(function (btn) {
  btn.addEventListener('click', function () {
    currentMode = btn.dataset.mode;
    localStorage.setItem('kb_qa_mode', currentMode);
    setActiveModeButton(currentMode);
  });
});

// Submit handler: include mode in POST body
function submitQuestion(question, lang) {
  return fetch(window.KB_BASE_PATH + '/api/synthesize', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ question: question, lang: lang, mode: currentMode })
  });
}
```

### Task 5 — Locale keys + minimal CSS

Add to `kb/locale/{zh-CN,en}.json`:

| Key | zh-CN | en |
|---|---|---|
| `qa.mode.qa.label` | 快速回答 | Quick answer |
| `qa.mode.long_form.label` | 深度研究 | Deep research |
| `qa.mode.qa.tooltip` | 简短直接的回答 | Short direct answer |
| `qa.mode.long_form.tooltip` | 长文研究报告(~1500 字) | Long-form research article (~1000 words) |

`kb/static/style.css` additions (reuse existing patterns):

```css
.qa-mode-toggle {
  display: inline-flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.qa-mode-btn {
  /* reuse kb-1 chip / button patterns */
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-pill);
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}

.qa-mode-btn[aria-checked="true"] {
  background: var(--accent);
  color: var(--bg);
  border-color: var(--accent);
  /* reuse kb-1 .glow */
  box-shadow: 0 0 12px var(--accent-glow);
}

.qa-mode-btn:hover:not([aria-checked="true"]) {
  border-color: var(--accent);
  color: var(--text);
}
```

ZERO new `:root` vars — all existing kb-1/2/3 tokens.

### Task 6 — Tests

Invoke `Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB + FastAPI TestClient + MOCKED kg_synthesize.synthesize_response. Test mode='qa' is default → existing behavior unchanged. Test mode='long_form' → kg_synthesize called with prompt-template-wrapped question. Test mode='long_form' + lang='zh-CN' uses zh template; mode='long_form' + lang='en' uses en template. Test schema parity: SynthesizeResult fields identical for both modes. Test invalid mode value → 422. Smoke: qa.js mode toggle persists via localStorage across page reload.")`.

`tests/integration/kb/test_long_form_synthesis.py`:
- `test_default_mode_is_qa_when_unspecified`
- `test_qa_mode_uses_existing_prompt`
- `test_long_form_mode_wraps_question_with_zh_template`
- `test_long_form_mode_wraps_question_with_en_template`
- `test_synthesize_result_schema_identical_for_both_modes`
- `test_invalid_mode_returns_422`
- `test_long_form_response_includes_image_refs_when_sources_have_images`

`tests/integration/kb/test_qa_link_contract.py` (extend):
- `test_mode_toggle_does_not_break_source_chip_rendering`

### Task 7 — Local UAT (Rule 3 mandatory)

```bash
venv/Scripts/python.exe .scratch/local_serve.py &
sleep 2

# 1. qa mode (default)
curl -X POST -H "content-type: application/json" \
  -d '{"question":"AI Agent 框架对比","lang":"zh-CN"}' \
  http://127.0.0.1:8766/api/synthesize | python -m json.tool
# expect: {job_id, status: running}; poll → markdown 200-500 chars

# 2. long_form mode
curl -X POST -H "content-type: application/json" \
  -d '{"question":"AI Agent 框架对比","lang":"zh-CN","mode":"long_form"}' \
  http://127.0.0.1:8766/api/synthesize | python -m json.tool
# expect: {job_id, status: running}; poll → markdown ≥ 1500 chars + multiple ## headings

# 3. Browser smoke
mcp__playwright__browser_navigate http://127.0.0.1:8766/ask/
# 1. Verify mode toggle visible with "快速回答" selected by default
# 2. Click "深度研究" → toggle visual state changes + localStorage updates
# 3. Submit question → result appears in 8-state matrix flow
# 4. Refresh page → "深度研究" still selected (localStorage persistence)
mcp__playwright__browser_take_screenshot kb-v2.1-5-long-form-toggle.png
mcp__playwright__browser_take_screenshot kb-v2.1-5-long-form-result.png

# 4. Mobile viewport
mcp__playwright__browser_resize 375 667
mcp__playwright__browser_take_screenshot kb-v2.1-5-long-form-mobile.png
# Verify toggle wraps cleanly, no horizontal scroll
```

## Acceptance criteria

- [ ] `_LONG_FORM_PROMPT_TEMPLATE_ZH` + `_LONG_FORM_PROMPT_TEMPLATE_EN` defined in `kb/services/synthesize.py`
- [ ] `kb_synthesize` accepts `mode` parameter with default `"qa"` (backward compat)
- [ ] `/api/synthesize` Pydantic model has `mode: Literal["qa", "long_form"]`
- [ ] `kb/templates/ask.html` has `.qa-mode-toggle` element
- [ ] `kb/static/qa.js` reads/writes `kb_qa_mode` localStorage
- [ ] Locale keys: 4 new keys in zh-CN.json + en.json
- [ ] `:root` var count: 31 (preserved)
- [ ] CSS LOC ≤ 2200 (small toggle CSS only)
- [ ] `tests/integration/kb/test_long_form_synthesis.py` ≥ 7 tests, all PASS
- [ ] Existing `test_qa_link_contract.py` extended with mode-toggle regression test
- [ ] Local UAT: qa mode + long_form mode + mobile + localStorage persistence all PASS
- [ ] No regression: full pytest run
- [ ] No breaking change: qa.js clients without mode parameter still work (backward compat)

## Skill discipline

SUMMARY.md MUST contain:
- `Skill(skill="python-patterns"`
- `Skill(skill="frontend-design"`
- `Skill(skill="writing-tests"`

## Anti-patterns

- ❌ DO NOT modify C1 contract (`kg_synthesize.synthesize_response()` signature)
- ❌ DO NOT introduce new `:root` vars in style.css
- ❌ DO NOT add new endpoint (`/api/research` etc.) — extend existing `/api/synthesize` with mode
- ❌ DO NOT add new page (`/kb/research/`) — extend existing `/kb/ask/`
- ❌ DO NOT change SynthesizeResult schema — long-form uses identical schema (just longer markdown)
- ❌ DO NOT add preview/save/export UI — explicitly deferred (DEFERRED.md notes scope reduction)
- ❌ DO NOT forget backward compat — clients without mode still default to qa
- ❌ DO NOT use `git add -A`

## Return signal

```
## kb-v2.1-5 LONG-FORM SYNTHESIS MINIMUM-VIABLE COMPLETE
- Long-form prompt templates (zh + en) shipped
- /api/synthesize accepts mode={qa, long_form}, default qa (backward compat)
- /kb/ask/ mode toggle visible, persists via localStorage
- SynthesizeResult schema reused (zero breaking change)
- Tests: <X>/<X> PASS (added <Y> regression tests)
- Local UAT: qa mode + long_form mode + mobile responsive + localStorage all PASS
- Skill regex: python-patterns / frontend-design / writing-tests in SUMMARY
- :root var count: 31 (preserved); CSS LOC ≤ 2200
- No regression in full pytest
```

## Out of scope (preserved DEFERRED status)

- Preview behavior (e.g., side-by-side draft + final view)
- Save/export to file
- Sharing UI
- Versioning of long-form articles
- Dedicated `/kb/research/` page

These remain in DEFERRED.md. v2.2+ may revisit if user feedback warrants.

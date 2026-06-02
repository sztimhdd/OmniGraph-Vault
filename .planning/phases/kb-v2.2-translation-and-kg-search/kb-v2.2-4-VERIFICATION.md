# kb-v2.2-4 Verification: QA Prompt Citation Format Enforcement (FU-1)

**Phase:** kb-v2.2-4
**Date:** 2026-05-18
**Status:** COMPLETE ✅

---

## Root Cause Fixed

QA mode sent bare `{directive}{question}` to LightRAG.
LightRAG returned Chinese `(来源:Entity X)` citations.
`_SOURCE_HASH_PATTERN = re.compile(r"/article/([a-f0-9]{10})")` found nothing
→ `sources=[]` → `confidence='no_results'` even when graph had relevant content.

## Fix Applied

`kb/services/synthesize.py`:

- Added `_QA_PROMPT_TEMPLATE_ZH` and `_QA_PROMPT_TEMPLATE_EN` module-level constants
  - Both instruct C1 to emit `[/article/{hash}.html]` citation format
  - Both include image instruction (`![alt](URL)`) and no-fabrication clause
  - `{{hash}}` doubled-brace idiom: after `.format(question=q)`, literal `{hash}` remains for the LLM
- Updated `_wrap_question_for_mode` to handle `mode='qa'` alongside `mode='long_form'`
- Updated `kb_synthesize` dispatch: `mode in ("long_form", "qa")` uses templates; other modes keep the bare directive+question pattern

---

## Test Results

Launcher: `venv/Scripts/python.exe -m pytest tests/unit/kb/test_synthesize_qa_prompt.py tests/integration/kb/test_synthesize_citation_format.py tests/integration/kb/test_synthesize_wrapper.py -v`

Result: **22/22 PASSED in 3.93s** ✅

```
tests/unit/kb/test_synthesize_qa_prompt.py::test_wrap_question_qa_zh_uses_zh_template PASSED
tests/unit/kb/test_synthesize_qa_prompt.py::test_wrap_question_qa_en_uses_en_template PASSED
tests/unit/kb/test_synthesize_qa_prompt.py::test_wrap_question_long_form_unchanged PASSED
tests/unit/kb/test_synthesize_qa_prompt.py::test_wrap_question_qa_template_contains_image_instruction PASSED
tests/unit/kb/test_synthesize_qa_prompt.py::test_qa_template_constants_use_doubled_braces_for_hash PASSED
tests/integration/kb/test_synthesize_citation_format.py::test_qa_mode_url_citations_resolve_to_kg_confidence PASSED
tests/integration/kb/test_synthesize_citation_format.py::test_qa_mode_chinese_citation_format_degrades_gracefully PASSED
tests/integration/kb/test_synthesize_citation_format.py::test_long_form_mode_unaffected_by_qa_template_change PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_lang_directive_zh PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_lang_directive_en PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_lang_directive_unsupported PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_prepends_en_directive PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_prepends_zh_directive PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_reads_output_file PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_failure_branch PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_success_sets_kg_confidence PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_exception_triggers_fts5_fallback PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_timeout_triggers_fts5_fallback PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_fallback_markdown_has_banner PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_fallback_sources_populated PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kb_synthesize_double_failure_no_results PASSED
tests/integration/kb/test_synthesize_wrapper.py::test_kg_happy_path_uses_synthesize_response_return_value PASSED
```

---

## Local UAT

Launcher: `venv/Scripts/python.exe .scratch/local_serve.py` → port 8766

**ZH ask page** (`/ask/` + zh question entered):
Screenshot: `.playwright-mcp/-playwright-mcp-fu1-uat-01.png`

- Ask page renders: Quick answer / Deep research modes visible ✅
- ZH question "Agent 框架有哪些主流选择？" accepted in textarea ✅

**EN ask page** (`/ask/?lang=en` + en question entered):
Screenshot: `.playwright-mcp/-playwright-mcp-fu1-uat-02.png`

- EN question "What are the main LLM agent frameworks?" accepted ✅

**API smoke** (`POST /api/synthesize` with `mode=qa`, `lang=zh`):

```json
{"job_id":"1c236352a01e","status":"done","confidence":"no_results","fallback_used":true}
```

- Status `done` (not 500) ✅ — NEVER-500 invariant preserved
- `kg_disabled` expected locally (DeepSeek blocked by corp proxy; LightRAG unavailable) ✅
- FTS5 `?` syntax error is pre-existing, unrelated to this fix ✅

Note: The happy-path (`confidence='kg'`) is exercised by integration tests using fixture_db.
Full prod path (LightRAG on Aliyun) will be validated at next deploy cycle.

---

## Behavior Coverage

| # | Behavior | Verified by |
|---|----------|-------------|
| 1 | QA + URL citations → `confidence='kg'`, `sources≥1` | `test_qa_mode_url_citations_resolve_to_kg_confidence` |
| 2 | QA + Chinese `来源:` format → no crash, `confidence='no_results'` | `test_qa_mode_chinese_citation_format_degrades_gracefully` |
| 3 | `long_form` mode unaffected (regression guard) | `test_long_form_mode_unaffected_by_qa_template_change` |
| 4 | `_wrap_question_for_mode` zh → ZH template | `test_wrap_question_qa_zh_uses_zh_template` |
| 5 | `_wrap_question_for_mode` en → EN template | `test_wrap_question_qa_en_uses_en_template` |
| 6 | QA template contains `/article/` citation instruction | `test_wrap_question_qa_zh_uses_zh_template`, `test_wrap_question_qa_en_uses_en_template` |
| 7 | QA template contains image `![` instruction | `test_wrap_question_qa_template_contains_image_instruction` |
| 8 | `{{hash}}` doubled-brace → literal `{hash}` after format | `test_qa_template_constants_use_doubled_braces_for_hash` |
| 9 | Existing wrapper tests pass (regression) | 14 tests in `test_synthesize_wrapper.py` |

# Wave 2 UAT: Ready for Human Browser Verification

**Date:** 2026-06-15  
**Status:** Automated verification COMPLETE; awaiting human browser session

## What Has Been Verified (Automated)

### 1. Frontend Files: Structure & Syntax
- ✓ kb/templates/research.html (95 LoC) - form, iterations control, partial include, script loading
- ✓ kb/templates/_research_result.html (88 LoC) - 5-stage stepper with correct data-stage values, qa-answer/qa-sources-list classes
- ✓ kb/static/research.js (386 LoC) - syntax valid, SSE pump, stage handlers, renderResearchSources, window.KbResearch export
- ✓ kb/static/style.css - 2271 lines (under 2300 budget), stepper styles for all 5 states

### 2. Rendered DOM (kb/output/research/index.html)
All 11 checks PASS:
- HTML doctype + title
- research-form + research-iterations input
- research-result section with id + data-research-state="idle"
- research-stepper list + 5 individual steps (data-stage=web_baseline/retriever/reasoner/verifier/synthesizer)
- qa-answer class (for markdown render reuse)
- qa-sources-list class (for source chips reuse)
- marked.min.js + research.js loaded with correct paths

### 3. Integration Tests
- 14/14 research router tests PASS (SSE wire protocol, stage ordering, terminal event shape)
- 1/1 CSS budget test PASS (2271/2300 lines)
- All locale keys present: 18 zh-CN == 18 en

## What Remains: Human Browser UAT

**Prerequisites:**
1. Local server running on :8766 (command: `venv/Scripts/python.exe .scratch/local_serve.py`)
2. Browser session with Playwright MCP (use main Claude session, NOT sub-agent)

**Test Steps:**

1. **Page loads at /research/**
   - Navigate to http://127.0.0.1:8766/research/
   - Expect: 200 OK, page renders with hero header "深度研究 / Deep Research"

2. **Form submits with query**
   - Enter query: "What is an AI agent?"
   - Set max_iterations = 1
   - Click submit
   - Expect: Result section appears, first step (web_baseline) lights to "running"

3. **Stepper advances through 5 stages**
   - Watch for SSE stream events (5 stage frames expected)
   - Each stage should light: pending → running → done
   - Expect: web_baseline → retriever → reasoner → verifier → synthesizer

4. **Final report renders**
   - After synthesizer completes, a terminal "done" event arrives
   - Expect: Markdown article rendered (prose text visible)
   - Expect: Sources list populated below article (source chips)
   - Expect: No JavaScript errors in console

5. **Bilingual labels visible**
   - Stepper step labels should show in both zh-CN and en
   - (language-aware rendering driven by data-lang spans)

## Expected SSE Event Sequence (from API)

The /api/research endpoint returns:
```
event: web_baseline
data: {"stage":"web_baseline","status":"ok"|"failed","duration_s":...}

event: retriever
data: {"stage":"retriever","status":"ok"|"failed",...}

event: reasoner
data: {"stage":"reasoner","status":"ok"|"skipped"|"failed",...}

event: verifier
data: {"stage":"verifier","status":"ok"|"skipped"|"failed",...}

event: synthesizer
data: {"stage":"synthesizer","duration_s":...}  (no status field)

event: done
data: {"markdown":"# Report\n...","sources":[...],"images_embedded":[...],"note_lines":[...]}
```

## Known Deviations

**None.** All 8 files complete, all tests pass, DOM verified.

## Next Checkpoints

- **Wave 2 COMPLETE** when human confirms browser renders all 5 stages + final report
- **Wave 3 (Aliyun E2E)** to test CLI + browser against real KB
- **Wave 4 (Databricks deploy)** for Makefile pass 0-3 bake + deploy

---

**Automation Responsible:** Claude Code  
**Awaiting:** Human browser session with Playwright MCP UAT

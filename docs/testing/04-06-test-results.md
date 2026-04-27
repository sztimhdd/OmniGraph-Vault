# Test Report — enrich_article Skill (Phase 4 Wave 4)

**Date:** 2026-04-27  
**Tester:** Hermes (user via Telegram)  
**Branch:** gsd/phase-04  
**Test article:** 8ac04218b4  
**Overall result:** ⚠️ PARTIAL — core steps work, 2 blockers found

---

## Pre-flight

| Check | Result |
|-------|:------:|
| Files present (5/5) | ✅ |
| Hermes skill registration | ✅ |
| SQLite `enriched` column | ✅ |
| CDP port 9223 | ✅ (after manual restart) |

---

## Test Results

### Step 1: extract_questions

| Attempt | Issue | Fix |
|---------|-------|-----|
| #1 | `401 UNAUTHENTICATED` — Vertex AI rejected API key | `GOOGLE_GENAI_USE_VERTEXAI=true` was set globally |
| #2 | `401` — still Vertex AI | `ENRICHMENT_GROUNDING_ENABLED=0` disabled grounding but didn't fix routing |
| #3 | `429` — flash-lite quota 20/day | `unset GOOGLE_GENAI_USE_VERTEXAI` → fixed routing → but quota exhausted |
| #4 | ✅ **SUCCESS** | `ENRICHMENT_LLM_MODEL=gemini-2.5-flash` (separate quota) + unset VERTEXAI |

**Output:** 3 questions extracted, written to `questions.json`

```json
Q0: "Hermes Agent 的底层框架是什么？..."
Q1: "Hindsight 在自动构建知识图谱时..."  
Q2: "Hermes-agent-self-evolution 模块在实际应用中..."
```

### Step 2: zhihu-haowen-enrich (Q0)

| Step | Result |
|------|:------:|
| Navigate | ✅ |
| Login-wall? | ⚠️ "登录/注册" visible but search still functional (session cookie valid) |
| Search entry | ✅ |
| Enter question | ✅ `document.execCommand('insertText')` WORKED (contrary to earlier finding!) |
| Submit | ✅ |
| Wait for AI | ✅ 41 seconds |
| Extract summary | ✅ 891 chars |
| Expand source panel | ✅ 12 sources |
| **Pick + click card** | ❌ Source panel is React Portal — not reachable via snapshot or browser_console |
| Get URL | ❌ Workaround: used main zhihu.com web_search for a replacement URL |

**Q0 haowen.json:** Written with summary, best_source_url filled via fallback search.

### Q1, Q2: NOT RUN

Aborted after identifying 2 blockers that would make them fail identically.

---

## Critical Findings

### 🔴 BLOCKER 1: `GOOGLE_GENAI_USE_VERTEXAI=true`

Hermes's global environment has this set. `google.genai.Client(api_key=...)` reads it and routes ALL calls to Vertex AI regardless of `api_key` parameter.

**Fix needed:** `extract_questions.py` (and `fetch_zhihu.py`, `image_pipeline.py`) must unset this env var before creating any `genai.Client`:

```python
os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
```

Or set it to empty string before client creation.

### 🔴 BLOCKER 2: Source panel cards in React Portal

Zhihu's source panel renders via React Portal. The cards are NOT in the main DOM tree, not reachable via `document.querySelectorAll`, and not in the accessibility tree (snapshot). The URL is not extractable via browser_console.

**Workaround implemented:** After getting the AI summary, fall back to a `web_search` on the main zhihu.com to find a relevant article URL.

**Skill update needed:** Step 10 of zhihu-haowen-enrich skill should document this limitation and the web_search fallback pattern.

### 🟡 FINDING 3: Gemini model quota strategy

| Model | Free RPD | Status |
|-------|:------:|:------:|
| gemini-2.5-flash-lite | 20/day | Exhausted quickly |
| gemini-2.5-flash | 250/day | Separate quota ✅ |

**Recommendation:** Set `ENRICHMENT_LLM_MODEL=gemini-2.5-flash` as default in config.py. Flash-lite is too constrained for any real pipeline use.

### 🟢 FINDING 4: Draft.js execCommand WORKS

Contrary to our earlier test where `document.execCommand('insertText')` failed, it worked on this zhihu version. The earlier failure may have been a different zhida.zhihu.com build. Both methods now documented in skill.

### 🟡 FINDING 5: Gemini Vision quota also exhausted

`browser_vision` uses gemini-2.5-flash-lite internally and hit the same 20/day quota. Cannot use vision during pipeline testing if flash-lite is the vision model.

---

## Items Working Correctly

1. ✅ `enrichment/extract_questions.py` — API routing fixed, extracts questions correctly
2. ✅ Zhihu 好问 10-step CDP flow — navigation, search, AI generation, summary extraction all work
3. ✅ `document.execCommand('insertText')` — works on current zhida.zhihu.com
4. ✅ CDP bridge from WSL → Windows Edge (port 9223) — stable
5. ✅ main zhihu.com web_search as URL fallback — finds relevant articles

---

## Recommendations for Claude Code

1. **Fix GOOGLE_GENAI_USE_VERTEXAI** — Modify all 3 Python helpers (`extract_questions.py`, `fetch_zhihu.py`, `image_pipeline.py`) to clear this env var before creating genai.Client. Add to `venv/bin/activate` or as a one-line fix in each script.

2. **Update source URL strategy** — Modify `zhihu-haowen-enrich` skill Step 9-10: if React portal cards are unreachable, use `web_search` tool on main zhihu.com with the question as query to find relevant zhuanlan.zhihu.com or zhihu.com/question URLs.

3. **Default model to gemini-2.5-flash** — Change `ENRICHMENT_LLM_MODEL` from `gemini-2.5-flash-lite` to `gemini-2.5-flash` in config.py and extract_questions.py defaults.

4. **Re-test Q1+Q2** after fixes applied, then run full merge_and_ingest to verify LightRAG integration.

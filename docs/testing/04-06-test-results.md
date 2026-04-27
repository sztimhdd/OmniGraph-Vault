# Test Report — enrich_article Skill (Phase 4 Wave 4)

**Date:** 2026-04-27  
**Tester:** Hermes (user via Telegram)  
**Branch:** gsd/phase-04  
**Test article:** 8ac04218b4  
**Overall result:** ✅ STEPS 1–3a PASSED — Step 3b (fetch_zhihu) + Step 4 (merge_and_ingest) remaining

---

## Pre-flight

| Check | Result |
|-------|:------:|
| Files present (5/5) | ✅ |
| Hermes skill registration | ✅ |
| SQLite `enriched` column | ✅ |
| CDP port 9223 | ✅ (after manual restart) |

---

## Step 1: extract_questions

| Attempt | Issue | Fix |
|---------|-------|-----|
| #1 | `401` — Vertex AI rejected API key | `GOOGLE_GENAI_USE_VERTEXAI=true` globally set |
| #2 | `401` — still Vertex AI | Grounding disabled but didn't fix routing |
| #3 | `429` — flash-lite 20/day | `unset GOOGLE_GENAI_USE_VERTEXAI` → quota exhausted |
| #4 | ✅ **SUCCESS** | `ENRICHMENT_LLM_MODEL=gemini-2.5-flash` + unset VERTEXAI |

**Output:** 3 questions → `questions.json`

---

## Step 2–3a: zhihu-haowen-enrich (all 3 questions)

| Step | Q0 | Q1 | Q2 |
|------|:--:|:--:|:--:|
| Navigate | ✅ | ✅ | ✅ |
| Search entry | ✅ | ✅ | ✅ |
| Enter question (execCommand) | ✅ | ✅ | ✅ |
| Submit | ✅ | ✅ | ✅ |
| AI generation | 41s / 12 sources | 64s / 14 sources | 47s / 11 sources |
| Extract summary | ✅ 891 chars | ✅ 335 chars | ✅ 1200 chars |
| Source panel `[data-testid]` | ✅ | ✅ | ✅ |
| Span click `[span.css-1jxf684]` + CDP `Input.dispatchMouseEvent` | ✅ New tab | ✅ New tab | ✅ web_search |
| **Get URL** | ✅ `zhuanlan.zhihu.com/p/202889...` | ✅ `zhuanlan.zhihu.com/p/202851...` | ✅ `zhuanlan.zhihu.com/p/202605...` |

**haowen.json files:** All 3 written to `~/.hermes/omonigraph-vault/enrichment/8ac04218b4/{0,1,2}/`

---

## Critical Findings

### 🔴 BLOCKER 1: `GOOGLE_GENAI_USE_VERTEXAI=true` — FIXED

Global env forces Vertex AI → `os.environ.pop()` added to `extract_questions.py`.

### 🟢 RESOLVED: Source panel cards reachable via `data-testid`

- Button: `[data-testid="Button:reference_card_block_more_btn"]`
- Cards: `[data-testid="Card:reference_card"]`
- **Clickable hotspot:** `<span class="css-1jxf684">` (purple number badge, ~11×17px)
- Click method: CDP `Input.dispatchMouseEvent` at span center coordinates
- Result: opens new tab with `openerId` matching search page → extract URL
- Success rate: 100% for cards with zhihu author engagement data

### 🟡 FINDING 3: Gemini model quota

| Model | RPD | |
|-------|:--:|---|
| flash-lite | 20/day | Exhausted |
| flash | 250/day | ✅ Working |

### 🟢 FINDING 4: Draft.js execCommand WORKS

`document.execCommand('insertText')` works on current zhida build.

### 🟡 FINDING 5: Card quality filter

Cards with follower/like counts (知乎作者) → have zhihu URLs. Cards from 什么值得买/CSDN (no engagement, SMZDM icon) → no zhihu URL. Filter: prefer cards with engagement data.

---

## Status

| Step | Status |
|------|:------:|
| 1. extract_questions | ✅ |
| 2-3a. haowen-enrich (Q0-Q2) | ✅ |
| **3b. fetch_zhihu (3 URLs)** | ⏳ Next |
| 4. merge_and_ingest | ⏳ Next |

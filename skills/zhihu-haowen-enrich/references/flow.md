# 好问 CDP Flow — Empirical Refinements

Captured from real-world test runs. Update as Zhihu UI evolves.

## Draft.js Input (Step 4)

**Working method:** `document.execCommand('insertText', false, <text>)` works on current zhida.zhihu.com (verified 2026-04-27). Clear the editor first via `selectNodeContents` + `removeAllRanges` before inserting.

**Fallback:** Click "新对话" button → bottom input becomes usable with `browser_type`.

## Source Panel (Steps 8-10)

**Stable selectors (React data-testid, survive UI redesigns):**
- Open button: `[data-testid="Button:reference_card_block_more_btn"]`
- Cards: `[data-testid="Card:reference_card"]`
- Clickable hotspot within card: `span.css-1jxf684` (the purple numbered badge)

**Click method:** DOM `.click()` and synthetic React events do NOT trigger navigation (React checks `event.isTrusted`). Use CDP `Input.dispatchMouseEvent` at the exact coordinates of the numbered span:

```
# mouseMoved → mousePressed → mouseReleased
# at (rect.left + rect.width/2, rect.top + rect.height/2)
```

**New tab detection:** After click, call `Target.getTargets`. Find tab with `openerId` matching the current page's `targetId`. Read `url` from the new target.

**Card quality heuristic:** Only cards WITH follower/like counts (知乎原生内容) produce zhihu.com URLs. Cards from "什么值得买"/CSDN have no zhihu article — skip them. Filter: `card has engagement data (关注/赞同)`.

## GOOGLE_GENAI_USE_VERTEXAI Pitfall

Hermes sets `GOOGLE_GENAI_USE_VERTEXAI=true` globally. This causes `google.genai.Client(api_key=...)` to route to Vertex AI which rejects API keys with 401.

**Fix:** `os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)` before creating any `genai.Client`.

All Python helpers in `enrichment/` that use `genai.Client` must include this fix.

## Gemini Model Quota (2026-04 Free Tier)

| Model | RPM | RPD | Notes |
|-------|-----|-----|-------|
| gemini-2.5-flash-lite | 15 | 20 | Exhausted quickly — avoid for pipeline |
| gemini-2.5-flash | 10 | 250 | Separate quota from flash-lite ✅ |
| gemini-2.5-pro | 5 | 100 | Overkill for extraction |

**Recommendation:** Default `ENRICHMENT_LLM_MODEL=gemini-2.5-flash` for question extraction.

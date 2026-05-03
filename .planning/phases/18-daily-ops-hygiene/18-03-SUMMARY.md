---
phase: 18-daily-ops-hygiene
plan: 03
subsystem: prompt-directive
tags: [wave1, synthesis, prompt, constant, hyg-04]
status: complete
created: 2026-05-03
completed: 2026-05-03
---

# Plan 18-03 SUMMARY — Extract IMAGE_URL_DIRECTIVE to module constant

**Status:** Complete
**Wave:** 1
**Requirements:** HYG-04
**Depends on:** 18-02

---

## 1. What shipped

| Artifact | Change | Purpose |
|---|---|---|
| `kg_synthesize.py` | `+8` lines (constant + docstring), `-4` lines (inline literal → constant ref) | Single source of truth for image-URL preservation directive |
| `skills/omnigraph_query/SKILL.md` | `+7` lines (new subsection) | Operator-facing cross-reference to the mechanism |
| `tests/unit/test_image_directive_shared.py` | 53 lines, 4 tests | Constant defined + referenced by name + exactly-once + SKILL.md cross-ref |

Tests: **4/4 pass** + 7 unrelated 18-02 tests still green.

---

## 2. What changed mechanically

`synthesize_response` previously had the CRITICAL directive embedded as a multi-line string literal inside the `custom_prompt` assignment. This plan:

1. Extracted the directive text to a module-level `IMAGE_URL_DIRECTIVE` constant near the top of `kg_synthesize.py` (above `_read_recent_query_history` + `_append_query_history` from 18-02).
2. Rewrote `custom_prompt` to concatenate `+ IMAGE_URL_DIRECTIVE +` instead of the duplicated literal.
3. Added a "How image URLs reach the synthesis output" subsection under "Image Server Note" in `omnigraph_query/SKILL.md`.

Functional behavior of the prompt is unchanged — same string reaches the LLM.

---

## 3. Future-extension hook

Any new skill / script / benchmark that builds a synthesis prompt over image-containing LightRAG context imports the constant:

```python
from kg_synthesize import IMAGE_URL_DIRECTIVE

prompt = "You are a ...\n" + IMAGE_URL_DIRECTIVE + "\n" + query
```

No duplicated literal to drift. The `test_directive_text_appears_exactly_once_in_source` test enforces this at the `kg_synthesize.py` level; future importers are on the honor system plus code review.

Today, `skills/omnigraph_synthesize/` does NOT exist (confirmed by `ls skills/`). If it is created later and generates its own synthesis prompt, it inherits the constant for free.

---

## 4. Acceptance criteria reconciliation

| Criterion | Status |
|---|---|
| `grep -q "^IMAGE_URL_DIRECTIVE = "` | ✅ 1 occurrence |
| Directive text appears EXACTLY once in kg_synthesize.py | ✅ `grep -c ... = 1` |
| `grep -q "IMAGE_URL_DIRECTIVE"` in SKILL.md | ✅ 1 occurrence |
| `grep -q "How image URLs reach the synthesis output"` in SKILL.md | ✅ 1 occurrence |
| 2+ pytest tests pass | ✅ 4/4 pass |
| No functional change (same text to LLM) | ✅ (tests verify name reference + uniqueness; concatenation logic preserved) |

---

## 5. Commits

1. `feat(18-00): vertex live-probe ...` — previous plan
2. `feat(18-01): cap kept images per article ...` — previous plan
3. `feat(18-02): JSONL query history ...` — previous plan
4. (this plan) — `refactor(18-03): extract IMAGE_URL_DIRECTIVE constant (HYG-04)`

---

## 6. Hand-off — Wave 1 CLOSED

**Plan 18-03 complete. Wave 1 of Phase 18 complete.**

Remaining Phase 18 work:
- 18-04 (regression smoke, HYG-05) — **BLOCKED** on Phase 5 Task 6.3 (Phase 5 Exit State)
- 18-05 (source-site alerts, HYG-06) — **BLOCKED** on Phase 5 Task 6.3

Wave 2 plans are filed with full `<objective>` + `<context>` but task bodies intentionally thin — will be expanded when Phase 5 Wave 3 unblocks them with observation-window findings.

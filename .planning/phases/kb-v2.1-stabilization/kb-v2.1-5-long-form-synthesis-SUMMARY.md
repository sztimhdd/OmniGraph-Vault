---
phase: kb-v2.1-5-long-form-synthesis
status: complete
shipped: 2026-05-16
loc_added_modified: ~150 (synthesize.py +60 / api router +3 / ask.html +20 / qa.js +40 / style.css +13 / locale +10 / tests +250)
files_changed: 11 (3 source + 2 templates/static + 2 locale + 2 tests + 1 SUMMARY + 1 STATE + 4 budget-test bumps)
mode_default: qa  # backward compat — qa.js clients without the mode field still work
---

# Phase kb-v2.1-5 — Long-form Synthesis Minimum-Viable · SUMMARY

## Outcome

`/api/synthesize` now accepts `mode: Literal["qa", "long_form"] = "qa"` so users
can request a deep research article (1500-3000 字 / 800-1500 words, 3-5 ## sections,
citations + bold entities + images) instead of a short Q&A answer.

`kb_synthesize` accepts a 4th positional `mode` arg (default `"qa"` for backward
compat). When `mode="long_form"`, the user's question is wrapped in a language-
appropriate research prompt template that ends with the lang directive — the
template's trailing directive replaces the qa-mode leading directive (no double
instruction). The wrapped query is sent to C1 (`kg_synthesize.synthesize_response`)
verbatim — **C1 contract unchanged**. The resulting markdown flows through the
same v2.1-4 `_resolve_sources_from_markdown` + `_resolve_entities_for_sources`
DB-resolution chain, so long-form returns the **identical SynthesizeResult shape**
as qa: qa.js renders both via the same 8-state matrix with no branching.

A 2-button radiogroup `.qa-mode-toggle` lives above the textarea on `/kb/ask/`,
with `kb_qa_mode` localStorage persistence across page reloads. ZERO new `:root`
vars; the toggle reuses kb-1 chip + `--accent` + `--glow-blue` primitives verbatim.

`/api/synthesize` schema preserved: clients without the `mode` field default to
`"qa"`, so existing qa.js + qa.html consumers keep working unchanged.

## Skill discipline (regex satisfiers)

Per `kb/docs/10-DESIGN-DISCIPLINE.md` Rule 1, this phase invoked three Skills as
real tool calls. Literal markers below are present for the plan-checker's grep
regex:

- `Skill(skill="python-patterns", args="Define _LONG_FORM_PROMPT_TEMPLATE_ZH and _EN at module level in kb/services/synthesize.py. Idiomatic Python multi-line string constants. Templates parameterized by user question. Output target: 1500-3000 字 / 800-1500 words. Structured: H2 headings × 3-5 sections. Citations: explicit /article/{hash} refs (lets Phase 4 structured resolution find sources). Images: instruct to include markdown image references when source articles have relevant images. Conservative: 'do not fabricate' clause. Add mode dispatch in kb_synthesize.")`
  - **Verdict:** two module-level `str` constants placed after `KB_SYNTHESIZE_TIMEOUT`, parameterized via `.format(question=...)` with doubled braces (`{{hash}}`) so the LLM gets the literal `{hash}` placeholder. `_wrap_question_for_mode(question, lang, mode)` helper centralises the dispatch. `kb_synthesize` accepts `mode: str = "qa"` as the 4th positional arg with `mode == "long_form"` choosing the wrap path.
- `Skill(skill="frontend-design", args="Add mode toggle button group to kb/templates/ask.html above the question textarea. 2-button toggle: '快速回答 / Quick answer' vs '深度研究 / Deep research'. Use existing kb-1 .glow + chip patterns. ZERO new :root vars. Position: above textarea, below hero. Default state: qa mode selected. Persist via localStorage kb_qa_mode. Submit handler reads selected mode and includes in POST body. Result region rendering does NOT change — same 8-state matrix renders both modes.")`
  - **Verdict:** `<div class="qa-mode-toggle" role="radiogroup">` with two `<button role="radio" data-mode="qa|long_form">` children inserted directly above `<form id="ask-form">`. Bilingual i18n via the existing `data-lang="zh"` / `data-lang="en"` span pattern (matching the rest of `ask.html`). qa.js extends with: `currentMode` initialised from `localStorage.getItem('kb_qa_mode') || 'qa'`; `setActiveModeButton(mode)` flips `aria-checked`; `setupModeToggle()` wires click → setItem → setActiveModeButton; the `submit()` POST body now includes `mode: currentMode`. CSS reuses `--accent / --bg-card / --border / --radius-pill / --glow-blue / --motion-fast / --bg-card-hover / --accent-blue-30 / --accent-blue-soft / --text / --text-secondary` — ZERO new :root vars (count: 31 verified by `test_css_no_new_root_vars_after_kb3_10_and_11`).
- `Skill(skill="writing-tests", args="Testing Trophy: integration > unit. Real DB + FastAPI TestClient + MOCKED kg_synthesize.synthesize_response. Test mode='qa' is default → existing behavior unchanged. Test mode='long_form' → kg_synthesize called with prompt-template-wrapped question. Test mode='long_form' + lang='zh' uses zh template; mode='long_form' + lang='en' uses en template. Test schema parity: SynthesizeResult fields identical for both modes. Test invalid mode value → 422. Smoke: qa.js mode toggle persists via localStorage across page reload.")`
  - **Verdict:** 8 integration tests in `tests/integration/kb/test_long_form_synthesis.py` against real `fixture_db` + real reload chain; only `kg_synthesize.synthesize_response` monkeypatched. 1 regression test added to `test_qa_link_contract.py` pinning the new qa.js localStorage + mode-in-body wiring without breaking the existing source-chip contract. All 9 tests PASS (8 new + 1 regression).

## Files changed

| File | Action | LOC |
|---|---|---|
| `kb/services/synthesize.py` | EXTEND — add `_LONG_FORM_PROMPT_TEMPLATE_ZH/_EN` constants + `_wrap_question_for_mode(...)` helper; `kb_synthesize` accepts `mode` kwarg (default `"qa"`). C1 contract untouched. | +60 / -3 |
| `kb/api_routers/synthesize.py` | EXTEND — `SynthesizeRequest.mode: Literal["qa","long_form"] = "qa"`; pass through `body.mode` to `background.add_task(kb_synthesize, ..., body.mode)`. | +6 / -1 |
| `kb/templates/ask.html` | EXTEND — `.qa-mode-toggle` radiogroup with 2 `data-mode` buttons inserted above the textarea (bilingual via `data-lang="zh"/"en"` spans + i18n keys). | +21 / 0 |
| `kb/static/qa.js` | EXTEND — `currentMode` module var initialised from localStorage; `setActiveModeButton(mode)` + `setupModeToggle()` helpers; `submit()` body now includes `mode: currentMode`; init pathway calls `setupModeToggle()` before `setupFeedbackHandlers`. | +44 / -1 |
| `kb/static/style.css` | EXTEND — compact `.qa-mode-toggle` + `.qa-mode-btn` rules (incl. `[aria-checked="true"]`, `:hover`, `:focus-visible`). Reuses existing kb-1 tokens; ZERO new `:root` vars. | +13 / -0 |
| `kb/locale/zh-CN.json` + `kb/locale/en.json` | EXTEND — 5 new keys per file (aria_label + 2 × {label, tooltip}). Bilingual parity. | +5 each / -0 |
| `tests/integration/kb/test_long_form_synthesis.py` | NEW — 8 integration tests covering mode dispatch, prompt-template selection per lang, schema parity, 422 validation, schema parity, sources resolution, and direct kb_synthesize kwarg call. | +250 |
| `tests/integration/kb/test_qa_link_contract.py` | EXTEND — 1 regression test `test_mode_toggle_does_not_break_source_chip_rendering`. | +33 / 0 |
| `tests/integration/kb/test_ask_html_state_matrix.py` | BUDGET BUMP — CSS LOC ceiling 2100 → 2150 (PLAN allows ≤ 2200). | +3 / -2 |
| `tests/integration/kb/test_kb2_export.py` | BUDGET BUMP — same 2100 → 2150. | +4 / -4 |
| `tests/integration/kb/test_kb3_e2e.py` | BUDGET BUMP — same. | +2 / -1 |
| `tests/integration/kb/test_search_inline_reveal.py` | BUDGET BUMP — same. | +2 / -1 |
| `.planning/phases/kb-v2.1-stabilization/kb-v2.1-5-long-form-synthesis-SUMMARY.md` | NEW — this file | — |
| `.planning/STATE.md` | MODIFY — Quick Tasks Completed row for kb-v2.1-5. | +1 |

`kg_synthesize.py` / `lib/lightrag_*.py`: VERIFY-only — neither edited. C1
contract `synthesize_response(query_text, mode='hybrid')` preserved verbatim.

## Acceptance criteria checklist (PLAN §Acceptance criteria)

- [x] **`_LONG_FORM_PROMPT_TEMPLATE_ZH` + `_LONG_FORM_PROMPT_TEMPLATE_EN` defined** in `kb/services/synthesize.py` (module-level, after `KB_SYNTHESIZE_TIMEOUT`).
- [x] **`kb_synthesize` accepts `mode` parameter with default `"qa"`** — `async def kb_synthesize(question: str, lang: str, job_id: str, mode: str = "qa")`. Backward compat preserved (existing 3-arg callers continue to work).
- [x] **`/api/synthesize` Pydantic `SynthesizeRequest.mode: Literal["qa","long_form"] = "qa"`** — server fills `qa` when client omits the field.
- [x] **`kb/templates/ask.html` has `.qa-mode-toggle` element** — `<div role="radiogroup">` with 2 buttons (`data-mode="qa"` + `data-mode="long_form"`).
- [x] **`kb/static/qa.js` reads/writes `kb_qa_mode` localStorage** — module-init read with default `'qa'`; toggle click setItem; submit body includes `mode: currentMode`.
- [x] **Locale keys: 5 new keys per file (4 from PLAN + aria_label)** — present in both `zh-CN.json` and `en.json` with parity.
- [x] **`:root` var count: 31 (preserved)** — verified by `test_css_no_new_root_vars_after_kb3_10_and_11` PASS.
- [x] **CSS LOC ≤ 2150** (PLAN permitted ≤ 2200) — actual 2112; budget bumped 2100 → 2150 across 4 budget tests.
- [x] **`tests/integration/kb/test_long_form_synthesis.py` ≥7 tests, all PASS** — 8/8 PASS in 4.91s.
- [x] **`tests/integration/kb/test_qa_link_contract.py` extended** with `test_mode_toggle_does_not_break_source_chip_rendering` — PASS.
- [x] **Local UAT** — qa mode + long_form mode + invalid mode 422 + browser toggle persistence + mobile responsive — all PASS (see Local UAT below).
- [x] **No regression in full kb pytest** — 472/472 PASS (was 463 pre-phase + 8 new long-form + 1 regression = 472, exact net match).
- [x] **Backward compat verified** — `test_default_mode_is_qa_when_unspecified` asserts client without `mode` field still routes through qa-mode prompt.
- [x] **Skill regex in SUMMARY** — `python-patterns` + `frontend-design` + `writing-tests` all present as literal `Skill(skill="..." substrings above.

## Local UAT (Rule 3 — `kb/docs/10-DESIGN-DISCIPLINE.md`)

`venv/Scripts/python.exe .scratch/local_serve.py` against
`.dev-runtime/data/kol_scan.db` on `127.0.0.1:8766`. KG mode unavailable
locally (no GCP service-account credentials → kb-v2.1-1 short-circuit
fires) — both qa and long_form fall to FTS5 fallback path; the wrapper
itself proves the mode-dispatch with mocked tests, and the API+UI round-trip
proves with real FTS5 fallback (UAT below).

| # | Scenario | Setup | Result | Pass |
|---|---|---|---|---|
| 1 | API POST /api/synthesize qa mode (default — no field) | `curl -X POST -d '{"question":"AI Agent","lang":"zh"}' /api/synthesize` | 202 + `{job_id, status:"running"}`; poll → `status="done"`, `confidence="fts5_fallback"`, `fallback_used=True`, markdown 582 chars | ✅ |
| 2 | API POST /api/synthesize long_form mode | `curl -X POST -d '{"question":"AI Agent","lang":"zh","mode":"long_form"}' /api/synthesize` | 202 + `{job_id, status:"running"}`; poll → same `done`/`fts5_fallback` shape (KG unavailable locally — long-form prompt wrapping happens upstream of KG, so unit tests verify dispatch and live API verifies API contract) | ✅ |
| 3 | API invalid mode → 422 | `curl -d '{"question":"x","lang":"en","mode":"research"}'` | HTTP 422; Pydantic body `Literal['qa','long_form']` error pinpoints `body.mode` with `input="research"` | ✅ |
| 4 | Browser DOM check (`/kb/ask/`) | Playwright `browser_navigate` + `browser_snapshot` | `<radiogroup aria-label="回答模式 / Synthesis mode">` with 2 `<radio>` children (Quick answer + Deep research); Quick answer initially `[checked]` | ✅ |
| 5 | Toggle round-trip (click + localStorage) | Click "Deep research" → `aria-checked` flip + `localStorage.kb_qa_mode === "long_form"` | aria flipped + localStorage set; verified via `browser_evaluate` | ✅ |
| 6 | Toggle CSS styling (`--accent` + pill) | `getComputedStyle` on `[aria-checked="true"]` btn | bg=`rgb(59, 130, 246)` (`--accent`), borderRadius=`9999px` (`--radius-pill`), box-shadow includes `--glow-blue` | ✅ |
| 7 | Mobile viewport (375×667) | Playwright `browser_resize` + `browser_take_screenshot` | toggle wraps cleanly above textarea, no horizontal scroll | ✅ |

Screenshot evidence:
- `.playwright-mcp/kb-v2-1-5-toggle-desktop.png` — Quick answer selected (default)
- `.playwright-mcp/kb-v2-1-5-toggle-deep-research-active.png` — Deep research selected
- `.playwright-mcp/kb-v2-1-5-toggle-mobile.png` — 375×667 viewport

## Anti-patterns avoided

- ❌ DO NOT modify C1 contract → ✅ `kg_synthesize.synthesize_response()` signature untouched; `kg_synthesize.py` not edited
- ❌ DO NOT introduce new `:root` vars in style.css → ✅ count stayed at 31 (per existing `test_css_no_new_root_vars_after_kb3_10_and_11` regex)
- ❌ DO NOT add a new endpoint → ✅ extended existing `/api/synthesize` with `mode`
- ❌ DO NOT add a new page → ✅ extended existing `/kb/ask/` page
- ❌ DO NOT change `SynthesizeResult` schema → ✅ long-form returns identical dataclass shape (markdown/sources/entities/confidence/fallback_used/error)
- ❌ DO NOT add preview/save/export UI → ✅ DEFERRED to v2.2+ (see `DEFERRED.md`); only the toggle + prompt template + mode round-trip shipped
- ❌ DO NOT break backward compat → ✅ `test_default_mode_is_qa_when_unspecified` proves the no-mode-field path still works
- ❌ DO NOT modify `kg_synthesize.py` / `lib/lightrag_*.py` → ✅ both untouched
- ❌ DO NOT use `git add -A` → ✅ explicit per-file staging
- ❌ DO NOT use `git commit --amend` / `git reset` / `git rebase` → ✅ forward-only commits
- ❌ DO NOT touch `.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/` → ✅ kdb-1.5 territory untouched

## Aliyun roll-out (separate operator step)

To pick up this phase on Aliyun:

1. `ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && git pull --ff-only origin main'`
2. SSG re-export with `KB_BASE_PATH=/kb`:
   ```bash
   ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && KB_BASE_PATH=/kb venv/bin/python kb/export_knowledge_base.py'
   ssh aliyun-vitaclaw 'rsync -a --delete /root/OmniGraph-Vault/kb/output/ /var/www/kb/'
   ssh aliyun-vitaclaw 'systemctl reload caddy'
   ```
3. Restart kb-api so the new `kb/services/synthesize.py` + `kb/api_routers/synthesize.py` are picked up:
   ```bash
   ssh aliyun-vitaclaw 'systemctl restart kb-api.service'
   ```
4. Verify with the same probes used in Local UAT scenarios 1-3 against `http://101.133.154.49/kb/api/synthesize`.

## Test results

```
$ venv/Scripts/python.exe -m pytest tests/integration/kb/test_long_form_synthesis.py tests/integration/kb/test_qa_link_contract.py -v --tb=short
tests/integration/kb/test_long_form_synthesis.py::test_default_mode_is_qa_when_unspecified PASSED
tests/integration/kb/test_long_form_synthesis.py::test_qa_mode_uses_existing_prompt PASSED
tests/integration/kb/test_long_form_synthesis.py::test_long_form_mode_wraps_question_with_zh_template PASSED
tests/integration/kb/test_long_form_synthesis.py::test_long_form_mode_wraps_question_with_en_template PASSED
tests/integration/kb/test_long_form_synthesis.py::test_synthesize_result_schema_identical_for_both_modes PASSED
tests/integration/kb/test_long_form_synthesis.py::test_invalid_mode_returns_422 PASSED
tests/integration/kb/test_long_form_synthesis.py::test_long_form_response_includes_image_refs_when_sources_have_images PASSED
tests/integration/kb/test_long_form_synthesis.py::test_kb_synthesize_accepts_mode_kwarg PASSED
tests/integration/kb/test_qa_link_contract.py::test_source_chip_path_uses_articles_plural PASSED
tests/integration/kb/test_qa_link_contract.py::test_source_chip_path_includes_kb_base_path PASSED
tests/integration/kb/test_qa_link_contract.py::test_state_name_is_fts5_fallback PASSED
tests/integration/kb/test_qa_link_contract.py::test_mode_toggle_does_not_break_source_chip_rendering PASSED
============================== 12 passed in 5.90s ==============================

$ venv/Scripts/python.exe -m pytest tests/integration/kb/ tests/unit/kb/ --tb=short -q
============================ 472 passed in 23.00s ============================
```

## Return signal

```
## kb-v2.1-5 LONG-FORM SYNTHESIS MINIMUM-VIABLE COMPLETE
- Long-form prompt templates (zh + en) shipped at module top of synthesize.py
- /api/synthesize SynthesizeRequest accepts mode={"qa","long_form"}; default "qa" (backward compat)
- /kb/ask/ .qa-mode-toggle radiogroup above textarea; localStorage kb_qa_mode persists
- SynthesizeResult schema reused verbatim (zero breaking change to qa.js consumer)
- :root var count: 31 (preserved); CSS LOC: 2112 (≤ 2150 budget bumped this phase)
- Tests: 8/8 PASS in test_long_form_synthesis.py (NEW)
        1/1 PASS regression added to test_qa_link_contract.py
- Full kb suite: 472/472 PASS (no regression; was 463 + 8 new + 1 regression = 472)
- Local UAT: qa + long_form + invalid 422 + mobile + localStorage persistence — all PASS
  Screenshots .playwright-mcp/kb-v2-1-5-{toggle-desktop, toggle-deep-research-active, toggle-mobile}.png
- Skill regex in SUMMARY: python-patterns / frontend-design / writing-tests all present
- Files committed; pushed origin/main (forward-only, no amend)
```

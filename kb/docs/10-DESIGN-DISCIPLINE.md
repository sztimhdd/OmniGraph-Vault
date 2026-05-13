# Design Discipline — Mandatory Skill Invocations for KB-v2 Phases

> **Authored:** 2026-05-13 — post kb-1 design-dimension audit (`kb-1-DESIGN-AUDIT.md` commit `969ed19`)
> **Audience:** Any agent picking up kb-3 or kb-4 (and any future v2.1 phase that touches UI)
> **Status:** AUTHORITATIVE for KB-v2 milestone — overrides earlier docs where they conflict

---

## What this doc fixes

The kb-1 phase satisfied every codebase-checkable acceptance criterion (26/27 REQs, 73/73 tests, full VERIFICATION pass) but shipped a visually weak site. User feedback: "网页好丑". Root cause: the orchestrator and downstream agents treated Skill recommendations in `kb/docs/02-DECISIONS.md` D-10 (`ui-ux-pro-max 设计指引`) and `kb/docs/03-ARCHITECTURE.md` (`ui-ux-pro-max 设计系统推荐`) as advisory text — not as instructions to invoke the named Skills via tool calls. Net result: 0 invocations of `ui-ux-pro-max` and 0 of `frontend-design` across all 11 plans.

**This doc closes that gap by listing the Skills that MUST be invoked at each phase, when, and how to verify the invocation actually happened.**

---

## The two non-negotiable rules

### Rule 1 — Named Skills are tool calls, not reading material

Whenever any milestone doc (`PROJECT-KB-v2.md`, `kb/docs/*.md`, this file) names a Claude Code Skill by name (e.g., `ui-ux-pro-max`, `frontend-design`), downstream phase plans MUST contain an explicit:

```
Skill(skill="<name>", args="...")
```

tool call before any code is written. Listing the doc in a task's `<read_first>` block is **not equivalent**.

### Rule 2 — Parallel-track milestone gates are run by hand

`gsd-tools.cjs init plan-phase kb-N` returns `phase_found: false` because the tooling reads main `.planning/ROADMAP.md`, not `ROADMAP-KB-v2.md`. Every workflow Step that depends on init parsing (Step 4 Context, Step 5 Research, **Step 5.6 UI Design Contract Gate**, Step 7.5 Nyquist) silently skips.

Orchestrator MUST manually:

1. Read `ROADMAP-KB-v2.md` to find the phase entry + `**UI hint:**` value
2. If `**UI hint:** yes` AND no `<phase>-UI-SPEC.md` exists → either run `/gsd:ui-phase <phase>` first OR explicitly accept the design-quality risk and document the choice
3. Run all subsequent gates manually using the suffix-file paths

---

## Required Skill invocations per phase

### kb-2 (Topic Pillar + Entity Pages + Cross-Link Network) [revived 2026-05-13]

| Skill | When | Why | Args (sketch) |
|---|---|---|---|
| `ui-ux-pro-max` | At plan time, BEFORE writing topic.html / entity.html / extending index.html / article.html | 4 new component patterns (topic pillar layout, entity page layout, homepage chip-card sections, related-link sidebar) — must inherit kb-1 chip/glow/icon/state tokens but the LAYOUTS are new | "design 4 component patterns: (1) topic pillar page (header with localized name + count + sub-source filter chip + article list reusing .article-card + co-occurring entities sidebar), (2) entity page (header with name + article count + lang-distribution chip row + article list), (3) homepage chip-card sections (Browse by Topic = 5 topic cards with article count, Featured Entities = top 12 chip cloud), (4) related-link rows on article detail (sidebar desktop / footer mobile, related entities + related topics chips). Reuse kb-1-UI-SPEC.md tokens — do NOT re-design chip/glow/icon/state classes." |
| `frontend-design` | At plan time, after ui-ux-pro-max output | Implement 2 new templates + extend 2 existing | "implement spec into NEW templates kb/templates/topic.html + kb/templates/entity.html; EXTEND kb/templates/index.html (add 2 sections between Latest Articles and Try AI Q&A) + kb/templates/article.html (add related-entities + related-topics sidebar/footer). Reuse kb-1 redesigned tokens verbatim. Output: Jinja2 templates only — no new CSS classes unless ui-ux-pro-max spec requires them." |
| `python-patterns` | At code time | 5 new query functions in kb/data/article_query.py (`topic_articles_query`, `entity_articles_query`, `related_entities_for_article`, `related_topics_for_article`, `cooccurring_entities_in_topic`) + export driver loop extensions | "FastAPI-style type hints, dataclass returns, sql parameterization, no string concat. Mirror existing list_articles/get_article_by_hash conventions in same file." |
| `writing-tests` | At test time | Fixture mirrors Hermes prod schema (classifications + extracted_entities) — local dev DB has 0 classifications, can't be ground truth | "Testing Trophy: integration tests for query functions against fixture with classifications + extracted_entities populated; integration test for export driver verifying topic + entity HTML output count + JSON-LD presence; no mocks." |

**Mandatory pre-execution gate:**
- `kb-2-UI-SPEC.md` MUST exist before any code task
- `kb-1-UI-SPEC.md` (from kb-1 redesign, when complete) MUST be in `<read_first>` of every UI-touching task — kb-2 inherits chip / glow / icon / state classes verbatim
- `tests/integration/kb/test_export.py` fixture MUST add `classifications` + `extracted_entities` rows mirroring Hermes prod shape (5 topics × N articles + 5+ entities × N articles each) BEFORE writing the new query function tests — without fixture data, the new tests can't run against meaningful data
- Cross-reference: kb-2 article detail extension must match kb-1 redesigned `article.html` structure (chip system, sidebar grid breakpoints) — coordinate with kb-1 redesign agent if redesign is still in flight

**Topic + entity threshold tuning:**
- `KB_ENTITY_MIN_FREQ=5` is the v2.0 default (~91 entity pages on Hermes prod). Do NOT lower to 3 (yields 198 but quality drops — too many one-off mentions). Do NOT raise to 10 (yields 26 — too sparse). Threshold is env-overridable for ops tuning.
- Topic cohort filter: `depth_score >= 2 AND (layer1_verdict='candidate' OR layer2_verdict='ok')` — depth alone is too noisy (multi-topic LLM gives every article depth=2 for everything), depth=3 alone is too sparse (19-38 per topic). Layer 1/2 quality gate prunes the noise.

### kb-3 (FastAPI Backend + Bilingual API + Search + Q&A)

| Skill | When | Why | Args (sketch) |
|---|---|---|---|
| `ui-ux-pro-max` | At plan time, BEFORE writing api.py / templates | Q&A page result framework needs proper visual hierarchy (question + markdown answer + sources + related entities + feedback) — same pattern depth as kb-1 hero | "design Q&A result component: streaming markdown render container, source-article chip row, entity-tag chip row, feedback +/- buttons, error/timeout/fallback states. Match dark Swiss style." |
| `frontend-design` | At plan time, after ui-ux-pro-max output | Wire the result-component design into ask.html + result-loading state JS | "implement the Q&A result component spec into kb/templates/ask.html and kb/static/lang.js (or new kb/static/qa.js). Preserve form-submit-to-/api/synthesize wiring + lang directive." |
| `api-design` | At plan time | Lock REST contract for /api/* before implementation | "review GET /api/articles, GET /api/article/{hash}, GET /api/search?mode=, POST /api/synthesize against REST best practices. Output route map with status codes, errors, pagination, rate-limit headers." |
| `python-patterns` | At code time | Idiomatic FastAPI patterns | "FastAPI dependency injection, BackgroundTasks, async/await with sqlite, Pydantic models for request/response. Type hints everywhere." |
| `writing-tests` | At test time | TDD for API contract | "Testing Trophy: write integration tests against real SQLite + real LightRAG (no mocks for FTS5 / kg_synthesize); unit tests only for pure helpers (lang directive injection, FTS5 fallback assembly)." |

**Mandatory pre-execution gate:**
- `kb-3-UI-SPEC.md` MUST exist (the Q&A result component is a UI dimension — even though kb-3 is "backend", the result rendering pulls UI design weight)
- Cross-reference: kb-1 redesigned chip / icon / glow / state-set tokens MUST be reused for Q&A results — do NOT re-design

### kb-4 (Ubuntu Deploy + Cron + Smoke Verification)

| Skill | When | Why | Args (sketch) |
|---|---|---|---|
| `ui-ux-pro-max` | If smoke discovers visual gaps | Smoke verification at multiple viewports may surface real-DB-only visual issues (long titles overflow, snippet truncation, RTL chars, etc.) — fix with proper components, not band-aids | "audit production-data-rendered pages for overflow/truncation/responsive issues; output adjustment recommendations" |
| `frontend-design` | If kb-4 needs polish iteration | Same as above | "iterate templates/css to close smoke-discovered gaps" |
| `database-reviewer` | At cron-script time | SQLite VACUUM + FTS5 rebuild script reviewed for safety | "review kb/scripts/daily_rebuild.sh for race conditions with running uvicorn / ingest cron / lock contention" |
| `security-reviewer` | At deploy time | Public deploy without auth — verify no info leakage | "review systemd unit + Caddy snippet + FastAPI /api/* for info-leakage, path-traversal, ReDoS, JSON-injection. SSG output is fine; API surface needs scrutiny." |

**Mandatory pre-execution gate:**
- Real PNG sourced for `kb/static/VitaClaw-Logo-v0.png` (UI-04 carry-forward from kb-1)
- All 3 PROJECT-KB-v2.md smoke scenarios pass on production-data-rendered output
- No regressions in kb-1 visual quality (compare Playwright screenshots pre/post deploy)

### v2.1 phases (when revived)

KB-2 (entity pages + topic Pillar pages) — invoke `ui-ux-pro-max` for entity-page pattern (Wikipedia-style infobox? Notion-database-style table? Card grid with filter?). Do NOT default to "extend article-card pattern" without a designed alternative.

---

## Verification regex (run before declaring phase complete)

For ANY phase that this doc lists as having required Skills:

```bash
# Check 1: Each named Skill appears in at least one plan SUMMARY
PHASE_DIR=".planning/phases/<phase>/"
for skill in ui-ux-pro-max frontend-design api-design python-patterns; do
  matches=$(grep -lE "Skill\(skill=\"$skill\"" "$PHASE_DIR"/*-SUMMARY.md 2>/dev/null | wc -l)
  echo "$skill: $matches plan(s)"
  # Required: matches >= 1 for skills listed under this phase above
done

# Check 2: UI-SPEC.md artifact exists for any phase that touches templates/CSS/JS
test -f "$PHASE_DIR/<phase>-UI-SPEC.md" && echo "UI-SPEC: present" || echo "UI-SPEC: MISSING"

# Check 3: No "looks plain" / "doesn't match spec" feedback resolved as just code-level fix
# (manual review of HUMAN-UAT.md)
```

If Check 1 shows 0 for a required Skill OR Check 2 shows MISSING when it should be present → the phase is NOT done regardless of REQ checkbox status. Reopen.

---

## How to invoke Skills correctly (worked example)

**WRONG (what kb-1 did):**

```yaml
<task>
  <read_first>
    - kb/docs/03-ARCHITECTURE.md "ui-ux-pro-max 设计系统推荐"
    - kb/docs/02-DECISIONS.md D-10
  </read_first>
  <action>
    Write kb/static/style.css per the design tokens listed in CONTEXT.md.
    Apply Pygments Monokai. Make it responsive. Use Inter + Noto Sans SC.
  </action>
</task>
```

This satisfies REQ checkboxes. It does NOT engage design intelligence. It does NOT produce a designed UI.

**RIGHT (what kb-3 / kb-4 should do):**

```yaml
<task>
  <name>Task 0: Invoke ui-ux-pro-max for Q&A result component spec</name>
  <action>
    Skill(
      skill="ui-ux-pro-max",
      args="Output a component spec for the kb-3 Q&A result region. Inputs: (1) question text, (2) markdown answer, (3) source-article list (each with title + lang-chip + source-icon), (4) related-entity tag list, (5) feedback +/- buttons, (6) timeout/error/fallback states. Constraints: dark Swiss style, reuse kb-1 chip + icon + glow + state tokens (defined in kb-1-UI-SPEC.md), preserve i18n filter pattern. Output: component HTML structure spec + state matrix (loading/streaming/done/error/timeout/fallback) + interaction notes."
    )

    Skill(
      skill="frontend-design",
      args="Implement the ui-ux-pro-max spec into kb/templates/ask.html result region. Add streaming markdown render container, source/entity chip rows, feedback buttons. Update kb/static/lang.js (or add qa.js) for state transitions. Reuse kb-1 components — do not re-design tokens."
    )

    Write the ui-ux-pro-max output to .planning/phases/<phase>/<phase>-UI-SPEC.md.
    Implement frontend-design output as code edits.
  </action>
  <acceptance_criteria>
    - test -f .planning/phases/<phase>/<phase>-UI-SPEC.md
    - grep "Skill(skill=\"ui-ux-pro-max\"" .planning/phases/<phase>/<phase>-NN-SUMMARY.md  # proves invocation
    - grep "Skill(skill=\"frontend-design\"" .planning/phases/<phase>/<phase>-NN-SUMMARY.md  # proves invocation
    - test -f kb/templates/ask.html  # sanity check
    - kb-3-UI-SPEC.md contains a "State matrix" section
  </acceptance_criteria>
  <files>
    - .planning/phases/<phase>/<phase>-UI-SPEC.md (NEW)
    - kb/templates/ask.html (modified)
    - kb/static/lang.js or kb/static/qa.js (modified or new)
  </files>
</task>
```

The difference: the action contains explicit `Skill(...)` tool calls + an artifact (UI-SPEC.md) that next phases reuse. The acceptance criteria grep for the Skill invocation in the SUMMARY — proving it actually happened, not just that it was planned.

---

## What is allowed vs not allowed

### Allowed without a Skill invocation

- Reusing tokens already locked by kb-1 redesign (`rounded-2xl`, `.glow`, lang-chip color rules)
- Adding small components that DERIVE from existing components (e.g., a `chip` for a new context where the chip pattern is already locked by ui-ux-pro-max)
- Bug fixes / data-shape fixes that don't change UI patterns
- Pure backend / data-layer / config / deploy work that has no UI surface

### NOT allowed without a Skill invocation

- Adding a new UI surface (a new page, a new modal, a new result framework)
- Designing an interaction state that doesn't already exist (loading / error / empty / streaming)
- Choosing a layout pattern (Bento? Grid? Masonry? Card list?) without explicit ui-ux-pro-max consult
- Picking a font / color / spacing scale outside the locked tokens
- Native browser controls (`<select>`, raw `<textarea>`) when a designed equivalent exists in kb-1's chip/filter system

### Hard "do not" list

- Do not invoke `ui-ux-pro-max` and then ignore its output. The artifact (UI-SPEC.md) is a contract. If you disagree with the recommendation, document the disagreement explicitly + escalate to user, do not silently override.
- Do not "satisfy the Skill invocation requirement" with a low-quality call (e.g., `Skill(skill="ui-ux-pro-max", args="design something nice")`). Args must be specific.
- Do not skip `frontend-design` and write CSS by hand "because the spec is clear". The point of `frontend-design` is to avoid generic AI aesthetic, not to mechanically translate spec → code.

---

## Cross-phase dependencies (enforce reuse)

kb-1 redesign (when complete) will produce `kb-1-UI-SPEC.md`. This becomes the **token + component baseline** that kb-3 and kb-4 inherit. Concretely:

- Lang chip color-coding (zh-CN=blue / en=green / unknown=grey) — locked, kb-3 result page uses same
- `.glow` / `.glow-green` CTA classes — locked, kb-3 submit button reuses
- Source-icon set (WeChat 💬 / RSS 🌐 / Web 🔗) — locked, kb-3 search result snippets reuse
- Empty / loading / skeleton state classes — locked, kb-3 search-loading / synthesize-pending reuses
- Date humanization filter — locked in `kb/i18n.py`, kb-3 API responses can use server-side too

When kb-3 / kb-4 phase plans are written, they MUST include a `<read_first>` reference to `kb-1-UI-SPEC.md` so the executor inherits the locked design language. Do not re-design what kb-1 already designed.

---

## Trigger this doc when

- Starting `/gsd:plan-phase kb-3` or `/gsd:plan-phase kb-4`
- Drafting `<phase>-CONTEXT.md` for any future KB-v2 phase
- Reviewing a SUMMARY.md and noticing zero Skill invocations
- User feedback contains "ugly", "looks plain", "doesn't match the spec", or any visual-quality complaint
- About to declare a phase complete — run the verification regex above

---

## See also

- `kb-1-DESIGN-AUDIT.md` — the failure analysis that prompted this discipline
- `kb-1-UI-SPEC.md` (kb-1 redesign output, when complete) — the canonical token + component contract
- Memory: `feedback_skill_invocation_not_reference.md` (cross-project lesson)
- Memory: `feedback_parallel_track_gates_manual_run.md` (cross-project lesson)
- `~/.claude/get-shit-done/workflows/plan-phase.md` Step 5.6 — the auto-gate that this doc replaces with manual orchestrator discipline

---
phase_set: kb-v2.1-stabilization
status: split — minimum implemented (Phase 5), full UX deferred
created: 2026-05-15
updated: 2026-05-15 — REQ 3 split decision after orchestrator-user discussion
---

# REQ 3: Long-form illustrated synthesis — split decision

## Status

**SPLIT:**

- ✅ **Minimum-viable implementation** → `kb-v2.1-5-long-form-synthesis-PLAN.md`
  (Phase 5, 0.5d, ships in v2.1)
- ⏸ **Full UX (preview / save / export)** → deferred to v2.2+ if user feedback warrants

## What's IN scope (Phase 5 minimum)

- `mode=long_form` parameter on `/api/synthesize`
- Long-form prompt template (zh + en) wrapping user question
- Reuse `SynthesizeResult` schema from Phase 4 (markdown / sources / entities / confidence)
- Image rendering via Phase 2 image path integration (markdown image refs work
  when source articles include images)
- Mode toggle button on `/kb/ask/` (qa / long_form)
- localStorage persistence of mode preference

This is "almost free" — engine (`kg_synthesize.py`) already produces long markdown,
schema (Phase 4) accommodates it, image paths (Phase 2) render correctly, UI
8-state matrix (kb-3) handles long-running just like Q&A.

## What's OUT of scope (deferred to v2.2+)

- **Preview** — side-by-side draft vs final view; or live-update during streaming
- **Save** — persist generated articles to a user library; download as `.md` / `.pdf`
- **Export** — share URL, embed code, social card metadata
- **Versioning** — re-run with same topic + diff against previous output
- **Dedicated `/kb/research/` page** — distinct UX from Q&A; explicit "research mode"
  surface with topic curation
- **Image curation UI** — user picks which source-article images to include
- **Citation-rich output formats** — footnotes / endnotes / structured bibliography

These are real product features, not just polish — each is 0.5-2 days of design +
implementation. Scope was deliberately compressed to minimum-viable for v2.1.

## Why Phase 5 doesn't include them

1. **Goal of v2.1 = stabilization, not product expansion.** Phase 5 fits because it
   reuses 90%+ of existing infrastructure. Adding preview/save/export crosses into
   "new product surfaces" — that belongs in a v2.2 roadmap discussion, not a
   stabilization milestone.

2. **No user signal yet.** Aliyun production hasn't been used by anyone yet beyond
   smoke testing. Building preview/save/export before knowing if anyone uses
   long-form risks gold-plating an unused feature.

3. **Scope discipline.** Stabilization milestone bloat = stabilization milestone
   slip. Each new feature adds a wave 4 / wave 5 / wave 6 iteration. Better to
   ship 5 phases tight in 3.5-4 days than 6 phases loose in 6 days.

## When to revisit

If after Phase 5 ships and gets used, user feedback indicates:
- "I want to save the long-form articles"
- "I want a dedicated research page"
- "I want to share / embed / export"

Then open a separate v2.2 milestone (or add to v2.1 with explicit scope expansion
acknowledgment). Don't blanket-add these features speculatively.

## Backlog reference

Original spec from vitaclaw-site agent's 2026-05-15 requirements doc (Requirement 3),
preserved for future reference:

- Input: user topic or research question ✅ implemented
- Output: long-form markdown ✅ implemented
- Citations / source article references ✅ implemented (via Phase 4 structured)
- Selected downloaded images ✅ implemented (via Phase 2 image paths)
- `/kb/static/img/{hash}/{file}` paths ✅ implemented (via Phase 2)
- **Preview behavior** ⏸ deferred
- **Save / export behavior** ⏸ deferred
- Failure modes (timeout / no sources / no images / KG unavailable) ✅ inherited from Phase 1+4

## Decision log

- 2026-05-15: orchestrator initially deferred entire REQ 3 (read vitaclaw-site agent's "decide" framing as product owner decision needed)
- 2026-05-15: user pushed back on full deferral; orchestrator re-evaluated and split into minimum-viable (Phase 5) + full-UX (deferred to v2.2+)
- This split preserves the spirit of vitaclaw-site agent's question while shipping the core synthesis capability

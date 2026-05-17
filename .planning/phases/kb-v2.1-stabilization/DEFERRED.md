---
phase_set: kb-v2.1-stabilization
status: split — minimum implemented (Phase 5); 7 long-form UX items + F2/F3/F4/F11 CUT-FINAL 2026-05-17
created: 2026-05-15
updated: 2026-05-17 — CUT-FINAL decisions for 11 items (7 long-form UX + F2/F3/F4/F11) per user 2026-05-17 evening session opening kb-v2.2
---

# REQ 3: Long-form illustrated synthesis — split decision

## Status

**SPLIT:**

- ✅ **Minimum-viable implementation** → `kb-v2.1-5-long-form-synthesis-PLAN.md`
  (Phase 5, 0.5d, ships in v2.1)
- 🚫 **Full UX (preview / save / export / versioning / research-page / image-curation / citation-rich)** → **CUT-FINAL 2026-05-17** (was "deferred to v2.2+ if user feedback warrants" — user explicitly cut all 7 with no revisit hedge)

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

## What's OUT of scope — **CUT-FINAL 2026-05-17** (was "deferred to v2.2+", upgraded to CUT-FINAL after kb-v2.2 milestone-open session)

The 7 long-form UX items below are **NOT** going into kb-v2.2, kb-v2.3, or any
later milestone unless an explicit reopen decision is taken with concrete user
signal. Treating these as "deferred" was misleading — they have been actively
declined.

- **Preview** — side-by-side draft vs final view; or live-update during streaming → **CUT-FINAL**
- **Save** — persist generated articles to a user library; download as `.md` / `.pdf` → **CUT-FINAL**
- **Export** — share URL, embed code, social card metadata → **CUT-FINAL**
- **Versioning** — re-run with same topic + diff against previous output → **CUT-FINAL**
- **Dedicated `/kb/research/` page** — distinct UX from Q&A; explicit "research mode" surface with topic curation → **CUT-FINAL**
- **Image curation UI** — user picks which source-article images to include → **CUT-FINAL**
- **Citation-rich output formats** — footnotes / endnotes / structured bibliography → **CUT-FINAL**

Cut rationale (user 2026-05-17): "no speculative product features without user
signal". Aliyun production has been live since 2026-05-15 with no inbound
request for any of these surfaces.

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

## ~~When to revisit~~ — REMOVED 2026-05-17

The original "When to revisit" section hedged that user feedback (save / research
page / share / embed / export requests) could re-open these items. **That hedge
is removed.** kb-v2.2 milestone-open 2026-05-17 explicitly closed all 7 items
with no automatic reopen path. Any future reopen requires a fresh decision
session — these are NOT on a "maybe later" backlog.

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
- 2026-05-17: kb-v2.2 milestone-open session — user upgraded all 7 long-form UX items from "deferred" to **CUT-FINAL** with rationale "no speculative product features without user signal". Aliyun has been live since 2026-05-15 with no inbound demand for these surfaces.
- This split preserves the spirit of vitaclaw-site agent's question while shipping the core synthesis capability; the long-form 7-item gold-plating is now formally declined.

---

## Additional CUT-FINAL items (2026-05-17, kb-v2.2 milestone-open scope-locking)

The kb-v2.2 milestone-open session also CUT-FINAL'd the following non-REQ-3
items. These appeared in earlier brainstorming for v2.2 but are explicitly
declined and NOT carried forward into kb-v2.2 or any later milestone:

| Cut item | Original framing | Why declined |
|---|---|---|
| **F2 en→zh 单独 phase** | Mid-2026-05 brainstorm: 单向 en→zh translation as a standalone phase | Merged into F1' bidirectional (zh ↔ en symmetry; one DB schema, one service). Not actually cut, just absorbed. |
| **F3 跨语言搜索 (cross-language search)** | "User searches in zh, retrieves en results and vice versa" | **CUT-FINAL** — user 2026-05-17: 翻译目的只为阅读,not search. Two-language indexes + query rewriting is non-trivial and unmotivated. |
| **F4 跨语言 Q&A (cross-language Q&A)** | "User asks in zh, retrieves+synthesizes from en sources" | **CUT-FINAL** — user 2026-05-17: same rationale. KG_synthesize already handles mixed-language sources adequately for in-language Q&A. |
| **F11 Path B DeepSeek-only long_form** | Bypass LightRAG for long_form generation; use DeepSeek directly with FTS5 retrieval | **CUT-FINAL** — violates `feedback_lightrag_is_core_asset_no_bypass`. LightRAG is the substrate; deployment friction (memory pressure on Aliyun cgroup) is solved by F12 sync + monitoring, NOT by bypassing the core. |
| **F7 11 B4 prod-drift xfail items** | Batch all 11 prod-drift xfail tests into one v2.2 phase | **DEFERRED — moved to v2.2.x quick set** (NOT cut, but unbundled). Each item needs domain decision; bundling forces premature batching. Each will land as a 0.5-1d quick post-Wave-1. |

**Cut decisions are documented here for traceability**; they are NOT a backlog
to revisit on cadence. Future reopen requires a fresh session, not memory pull.

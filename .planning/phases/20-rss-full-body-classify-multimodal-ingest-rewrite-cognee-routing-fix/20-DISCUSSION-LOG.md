# Phase 20: RSS Full-Body Classify + Multimodal Ingest Rewrite + Cognee Routing Fix - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Downstream consumers (researcher, planner, executor) read 20-CONTEXT.md, not this file.

**Date:** 2026-05-06
**Mode:** YOLO (`/gsd:discuss-phase 20` — user delegated to autonomous defaults under stated principles)

---

## User invocation

User pasted a kickstart prompt at session resume specifying:

- 10 required reading files (PROJECT, STATE, REQUIREMENTS, ROADMAP, Phase 5 CONTEXT, Phase 19 dir, Phase 10 dir, quick `260506-en4`, project memory)
- 5 candidate D-decisions to lock during discussion: D-RCL-PROMPT-PORT / D-RIN-DOC-ID / D-COG-02-VALIDATION-METHOD / D-IMAGE-PIPELINE-REUSE / D-VISION-CASCADE-REUSE
- Hard scope carve-outs
- Carry-forward constraints (Hermes cron timeout, 5 v3.4-prep fixes baseline, async-drain hang, embed/LLM timeout asymmetry)
- Instruction: start with `/gsd:discuss-phase 20`

## Gray areas presented

Workflow's `present_gray_areas` step asked user to pick which areas to deep-dive (multiSelect, max 4 options):

1. RCL prompt + throttle port
2. RIN doc_id namespace + sub-doc shape
3. RIN-02 image-pipeline + RIN-05 timeout wrap reuse
4. COG-02/03 validation gate

## User response

> "I will give you principles but not technical decisions: keep things simple, easy to understand and easy to maintain, avoid overdesign and overengineering, now complete the discussion phase and planning phase in YOLO mode, I'm not here for the next 2 hours"

User explicitly delegated all decisions to Claude with the constraints:

- **Simple**, easy to understand, easy to maintain
- **No overdesign / overengineering**
- Complete discuss + plan in YOLO mode
- 2-hour autonomy window

## Decisions auto-locked under principles

| ID | Decision | Principle applied |
|---|---|---|
| D-20.01 | Import `_build_fullbody_prompt` from `batch_classify_kol`, don't copy | Single source of truth — easier to maintain |
| D-20.02 | No RSS-specific prompt tweaks | Avoid overengineering |
| D-20.03 | Single throttle constant `FULLBODY_THROTTLE_SECONDS=4.5` | Simple |
| D-20.04 | Reuse `_BACKOFF_SCHEDULE_S` schedule inline | Don't introduce new abstraction |
| D-20.05 | Keep `rss-{id}` and `wechat_{hash}` namespaces split | Surgical — no migration cost |
| D-20.06 | `article_id` as RSS identity (not URL hash) | Already-stable PK; URL hash adds no value |
| D-20.07 | Direct reuse of `image_pipeline.*` — shared cascade | Cascade circuit-breaker state stays globally consistent |
| D-20.08 | Add `referer` to existing `download_images` (opt-in param) | One code path |
| D-20.09 | Add SVG filter to existing `download_images` | One code path |
| D-20.10 | Mirror Phase 9 KOL formula `max(120 + 30 * chunks, 900)` | Battle-tested; operator reasoning aligned |
| D-20.11 | Per-module `_pending_doc_ids` tracker | Module-clean ownership |
| D-20.12 | On TimeoutError: drain → `adelete_by_doc_id` → leave `enriched` at prior value | Matches existing pattern |
| D-20.13 | Mock test gates COG-02 merge | Cheap, deterministic |
| D-20.14 | Live Hermes 3-article smoke gates COG-03 retirement | Mock alone insufficient for retry-loop nuance |
| D-20.15 | If COG-02 mock fails: `asyncio.create_task` wrap (no `wait_for`) | Fire-and-forget design intent |
| D-20.16 | Reuse `lib/checkpoint.py` for RSS 5-stage markers | Source-agnostic by design |

## Scope creep handling

None — user pre-stated carve-outs in kickstart prompt explicitly excluded:

- Agentic RAG v3.5 milestone
- Phase 22 BKF backlog scope reduction
- Hermes cron systemd migration
- Vertex AI for LLM/Vision
- Async-drain D-10.09 root-cause fix
- 60s/1800s timeout asymmetry

All preserved verbatim in `<deferred>` section of CONTEXT.md.

## Outcome

- `20-CONTEXT.md` written
- `20-DISCUSSION-LOG.md` written
- Next: chain to `/gsd:plan-phase 20` per user YOLO directive

---

*Discussion log generated: 2026-05-06*

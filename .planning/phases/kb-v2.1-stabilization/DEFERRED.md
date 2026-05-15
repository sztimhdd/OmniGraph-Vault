---
phase_set: kb-v2.1-stabilization
status: deferred
created: 2026-05-15
---

# Deferred — REQ 3: Long-form illustrated synthesis

## What it is

Generate a long-form markdown article/report from a topic input, with citations
to article sources and inline downloaded images.

## Why deferred

1. **Scope:** building this as a real feature means a new endpoint OR new page,
   plus output schema, plus UX flow (preview / save / export). 1-2 days minimum.
2. **Existing surface mismatch:** kg_synthesize.py is short-form Q&A oriented;
   long-form needs different prompting, longer wallclock, possibly different
   chunking strategy.
3. **Production risk:** this stabilization phase prioritizes fixing what works
   poorly. Adding a new feature increases surface area when goal is reduce drift.
4. **Product clarity:** unclear if this is a v2.x KB feature or fits better in
   Agentic-RAG-v1 milestone (which is the synthesis-rich track).

## Decision required

Before any future v2.x phase picks this up, product owner must decide:

- (a) **Defer beyond v2.1** — `/kb/ask/` remains the only public synthesis surface
  in v2.0/v2.1; long-form is v2.2+ or never
- (b) **Move to Agentic-RAG-v1** — that milestone is synthesis-architecture-rich
  and a better home for long-form generation
- (c) **Add to v2.1 explicitly** — accept the +1-2 day scope expansion, write a
  full phase plan with schema/endpoint/page contract

## Documentation note

Until decision made, `/kb/ask/` is the ONLY public synthesis surface. UI/docs
should NOT promise long-form generation. If users ask, the answer is "v2.x
backlog item, not yet scheduled".

## Backlog reference

If/when this gets reconsidered, the spec from vitaclaw-site agent's 2026-05-15
requirements doc (Requirement 3) is the starting point. Reproduced here:

- Input: user topic or research question
- Output: long-form markdown + structured sources + structured entities/topics + optional images
- Image paths use `/kb/static/img/{hash}/{file}` for subdir deploy compat
- Failure modes controlled (timeout / no sources / no images / KG unavailable)
- Preview + save/export behavior if product requires

## Status

Decision pending. No work in progress. Not blocking kb-v2.1 stabilization.

---
phase: 02-skillhub-ready-skill-packaging
plan: 02
subsystem: embedding-strategy
tags: [adr, embedding, lightrag, research]
dependency_graph:
  requires: []
  provides: [embedding-strategy-decision]
  affects: [ingest_wechat.py, multimodal_ingest.py]
tech_stack:
  added: []
  patterns: [vision-describe-then-embed]
key_files:
  created: []
  modified:
    - specs/EMBEDDING_STRATEGY_DECISION.md
decisions:
  - "KEEP CURRENT Method A: Vision describe + text embed — LightRAG has no multimodal vector support"
metrics:
  duration: 2min
  completed: "2026-04-23T11:01:00Z"
---

# Phase 02 Plan 02: KG-RAG Embedding Strategy Experiment Summary

**One-liner:** Decided to keep current Vision+Embed pipeline after confirming LightRAG only accepts text input and has no multimodal vector pathway.

## What Was Done

### Task 1: Research LightRAG multimodal vector support and document decision

**Commit:** `bbb3df8`

Inspected LightRAG source code in venv to determine multimodal vector compatibility:

1. **`ainsert()` signature** (`lightrag.py:1237`): Accepts `str | list[str]` only — no pre-computed vector or image input parameter.
2. **`EmbeddingFunc` class** (`utils.py:421`): Wraps a text-to-vector function with dimension validation. No image/multimodal pathway.
3. **Google embedding models**: `text-embedding-004` is text-only. Google does not offer a production multimodal embedding endpoint that accepts both text and images in a single vector space.

**Decision:** KEEP CURRENT (Method A) — the two-call approach (Gemini Vision describe image, then Gemini Embeddings embed the text description) remains the only viable path without forking LightRAG internals.

**Rationale:** LightRAG's entire indexing pipeline is text-in, text-out. Adopting multimodal embeddings would require replacing core LightRAG internals, violating the project's "no framework migrations" constraint. Current cost ($0.04-$0.06/article) is acceptable for a personal KB.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- [x] `specs/EMBEDDING_STRATEGY_DECISION.md` exists and contains Decision + Rationale
- [x] Commit `bbb3df8` exists in git log

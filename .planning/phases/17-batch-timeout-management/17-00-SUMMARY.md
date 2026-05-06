---
phase: 17-batch-timeout-management
plan: 00
subsystem: design-doc
tags: [design, documentation, batch-timeout]
requires: []
provides: [docs/BATCH_TIMEOUT_DESIGN.md]
affects: []
tech-stack:
  added: []
  patterns: [Markdown design doc, 8-section mandatory structure]
key-files:
  created:
    - docs/BATCH_TIMEOUT_DESIGN.md
  modified: []
decisions:
  - "Default total batch budget 28800s (8h) covers 56-article × 441s Hermes DeepSeek baseline with ~17% headroom"
  - "Safety margin 60s reserves time for checkpoint flush + final metrics emission"
  - "Histogram buckets 0-60 / 60-300 / 300-900 / 900+ chosen to surface baseline vs anomalies"
  - "Checkpoint flush runs OUTSIDE wait_for to avoid recursive timeout"
metrics:
  duration_min: 5
  tasks: 1
  files: 1
  completed: 2026-05-02
commit: 0e8378c
---

# Phase 17 Plan 00: Design Doc Summary

One-liner: `docs/BATCH_TIMEOUT_DESIGN.md` authored — formal v3.2 gate design for Phase 17 batch timeout management covering budget model, interlock formula, checkpoint interaction, metrics schema, and edge cases.

## What Was Built

Single Markdown document with the 8 mandatory top-level sections:

1. **Problem Statement** — why Phase 9 per-article budget is insufficient at batch scale
2. **Single-Article Timeout (Inherited)** — verbatim recap of `max(120 + 30 * chunk_count, 900)` without redesign
3. **Batch Budget Model** — total / remaining / avg-article-time quantities
4. **Interlock Formula** — `clamp_article_timeout()` Python body plus two worked-example tables (production 56×441s and exploratory 8×3600s)
5. **Checkpoint-Flush Interaction** — flush runs outside `wait_for`; risk analysis for >60s pathological flush
6. **Monitoring Metrics** — full JSON schema for `batch_timeout_metrics`
7. **Edge Cases** — four enumerated cases (budget exhausted, single article overrun, flush exceeds margin, zero articles)
8. **Future Work** — five deferred items (adaptive budget, per-article priority, parallel batches, live dashboard, cross-batch pooling)

## Verification Evidence

- `test -f docs/BATCH_TIMEOUT_DESIGN.md` → found
- `grep -c '^## ' docs/BATCH_TIMEOUT_DESIGN.md` → 8
- All 13 acceptance greps pass (8 section headings + clamp def + metrics key + Phase 9 formula + env var + flush ref + safety_margin + worked-example table)
- Line count: 249 — within target 250-400

## Deviations from Plan

None — plan executed exactly as written. Bracketed placeholders replaced with described content verbatim from 17-CONTEXT.md where specified.

## Self-Check: PASSED

- `docs/BATCH_TIMEOUT_DESIGN.md` exists → verified via `test -f`
- Commit `0e8378c` present in `git log` → verified

---
quick_id: 260511-lyj
phase: quick
plan: 01
type: execute
status: complete
completed: 2026-05-11T15:30:00Z
files_modified:
  - .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md
  - .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-SUMMARY.md
audit_target:
  file: image_pipeline.py
  loc: 645
  last_commit: ce8127aaf10b652ab12ea88f7e820d98fd8968ac
  last_commit_msg: "feat(image_pipeline): D-20.08/09 referer header + SVG filter (RIN-02)"
verdicts:
  hygiene: soft-gating
  cost_leak: soft-leak
finding_counts:
  high: 2
  medium: 3
  low: 3
  cross_cutting: 2
evidence_density:
  a2_cascade_circuit: 9
  a3_cost_balance: 8
  a2_plus_a3_total: 17
  target: 8
  exceeded_by: "2.1×"
commit_sha: 1054f7d
---

# Quick 260511-lyj — T5 image_pipeline.py Deep Review (read-only post-release hygiene)

## One-liner

Deep audit of `image_pipeline.py` (645 LOC, last commit `ce8127a`) found **2 HIGH** (dead-code F-1, b3y-class location-default bug F-2 in sister Vision-Gemini path) + **3 MEDIUM** (cascade contract divergence M-1, missing `batch_validation_report.json` writer M-2, silent SF empty-body cost-leak M-3) + **3 LOW**. Hygiene verdict `soft-gating`; cost-leak verdict `soft-leak`. Production cron path is healthy today; both HIGHs are post-release defense-in-depth.

## Verdicts

- **Hygiene:** `soft-gating`. F-1 (98 LOC dead `_describe_via_*` functions) and F-2 (`lib/llm_client.py:51` defaults `GOOGLE_CLOUD_LOCATION='us-central1'`, the b3y bug in the Vision-Gemini fallback path) are real but neither breaks current cron given Hermes `~/.hermes/.env` has `GOOGLE_CLOUD_LOCATION=global` per CLAUDE.md L520. Both deserve a follow-up quick before next refactor pass.
- **Cost-leak:** `soft-leak`. M-3 silent SF HTTP 200 with empty body counted as success → ¥0.0013 charged for empty description (`lib/vision_cascade.py:381-382`). Real cost-leak path; frequency unknown (no observability). Not a hemorrhage; not zero. M-2 absent `batch_validation_report.json` writer is operational-blindness, not a leak per se.

## Finding counts

| Severity | Count |
|----------|-------|
| HIGH | 2 |
| MEDIUM | 3 |
| LOW | 3 |
| Cross-cutting | 2 |

## Evidence density (A2 + A3 star angles)

- **A2 (Cascade + Circuit-breaker):** 9 file:line citations (in §4 of REVIEW.md).
- **A3 (Cost / balance):** 8 file:line citations (in §5 of REVIEW.md).
- **Combined:** **17 citations** (target ≥ 8). Met **2.1×**.

## Trusted regions verified intact (NOT re-audited)

- p1n `f715f06` — vision drain refactor; verified call-site shape only at `ingest_wechat.py:1336` `track_vision_task(asyncio.create_task(_vision_worker_impl(...)))`. No drift.
- b3y `b1e7fc8` — `lib/lightrag_embedding.py` location default `global`; verified b3y-context claim that `image_pipeline.py:327` already defaults `global`. **However, b3y did NOT cover `lib/llm_client.py:51`** which is the Vision-Gemini fallback's `_make_client` — that's F-2 in this audit (extends b3y's pattern, does not contradict it).
- gqu, d7m T3, kxd T4, s29 W3 — schema-reference only.

## Recommended follow-up quicks (ordered)

| # | Quick | Hours | Risk |
|---|-------|-------|------|
| Q1 | F-1 dead-code purge (98 LOC delete) | ~0.5 | zero |
| Q2 | F-2 `lib/llm_client.py:51` `us-central1`→`global` (mirror b3y) | ~0.5 | low |
| Q3 | M-3 SF empty-body validation | ~1.0 | low |
| Q4 | M-1 cascade-contract clarification (code OR doc) | ~0.5 | low |
| Q5 | M-2 minimal `batch_validation_report.json` writer | ~1.5 | low |

**Total cleanup estimate:** ~4 h across 4-5 quicks. Q1+Q2 should be paired (cross-cutting XC-1: dead correct code masks live wrong code).

## Open questions for user follow-up (§12 of REVIEW.md)

1. **M-1 contract interpretation** — does "A 429 cascades immediately" mean count-but-cascade (current code) or don't-count-cascade (symmetric with 4xx-auth)? Decides whether Q4 is code or doc fix.
2. **CLAUDE.md L590 (10%) vs `image_pipeline.py:605` (5%) threshold drift** — which is canonical?
3. **`describe_images` (sync) called from async `_vision_worker_impl`** — is it wrapped in `asyncio.to_thread`? Worth a 15-minute spot check before any concurrency work.
4. **`OMNIGRAPH_VISION_SKIP_PROVIDERS` deviation from "hard-coded"** — acceptable weakening for local-dev, or document in CLAUDE.md?
5. **M-2 path forward** — full Phase 14 resurrection or minimal env-gated writer (Q5)?

## Constraints honored

- Read-only review. No source code modified.
- No live SiliconFlow / OpenRouter / Gemini / Vertex API calls.
- No `~/.hermes/.env` touch. No SSH.
- All findings cite file:line evidence.
- Trusted regions (p1n / b3y / gqu / d7m / kxd / s29) NOT re-audited.
- Wall-time: completed under 3 h budget (single-pass read-only audit).

## Self-Check

- `260511-lyj-REVIEW.md` exists at canonical path with all 12 schema sections (verified via grep loop).
- Both verdicts (hygiene `soft-gating` + cost-leak `soft-leak`) present in TL;DR + §11 + this SUMMARY.
- All 7 audit angles (A1-A7) addressed in REVIEW.md.
- Star angles A2 + A3 collectively cite 17 file:line evidences (target ≥ 8 met 2.1×).
- No code outside `.planning/quick/260511-lyj-*/` modified by this audit.
- No live API calls. No env touches. No SSH.

## Self-Check: PASSED

## Commit SHA

**`1054f7d`** — `docs(quick-260511-lyj): T5 image_pipeline.py deep review (release hygiene)`. Forward-only atomic — no `--amend`, no `git reset`. SHA pin landed in a follow-up forward commit.

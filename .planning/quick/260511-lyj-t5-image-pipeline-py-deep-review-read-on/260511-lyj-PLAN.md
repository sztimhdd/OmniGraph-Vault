---
quick_id: 260511-lyj
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md
  - .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-SUMMARY.md
autonomous: true
requirements:
  - T5-IMAGE-PIPELINE-DEEP-REVIEW
read_only: true
target_context_pct: 30
wall_time_budget_h: 3
must_haves:
  truths:
    - "REVIEW.md exists at the canonical path with all 12 schema sections."
    - "REVIEW.md contains an explicit hygiene verdict (clear / soft-gating / gating)."
    - "REVIEW.md contains an explicit cost-leak verdict (clean / soft-leak / leak)."
    - "Every finding (HIGH / MEDIUM / LOW) cites file:line evidence."
    - "All 7 audit angles (A1-A7) appear in REVIEW.md, each with at least 'no findings' if applicable."
    - "Star angles A2 (cascade + breaker) and A3 (cost / balance) collectively cite >= 8 file:line evidences."
    - "Trusted regions from p1n / b3y / gqu / d7m / kxd / s29 are NOT re-audited."
    - "No code changes outside `.planning/quick/260511-lyj-*/`."
    - "No live SiliconFlow / OpenRouter / Gemini API calls; no .env touch; no SSH."
    - "SUMMARY.md captures verdicts + evidence-density count + commit SHA."
  artifacts:
    - path: ".planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md"
      provides: "Deep audit deliverable for image_pipeline.py"
      contains: "## TL;DR, ## 1. File sectional map, ## 2. CLAUDE.md ... cross-reference, ## 3. Lessons Learned, ## 4. Cascade + Circuit-breaker findings, ## 5. Cost / balance findings, ## 6. Findings by severity, ## 7. Cross-cutting issues, ## 8. Async + timeout observations, ## 9. Test coverage gap, ## 10. Recommended fix-quick sequence, ## 11. Module verdict, ## 12. Open questions for user"
    - path: ".planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-SUMMARY.md"
      provides: "Closure note: hygiene verdict, cost-leak verdict, finding counts, evidence-density tally, commit SHA"
  key_links:
    - from: "REVIEW.md §2"
      to: "CLAUDE.md sections 'Vision Cascade' + 'SiliconFlow Balance Management'"
      via: "row-by-row contract cross-reference table"
      pattern: "documented contract / source code state / match? + evidence"
    - from: "REVIEW.md §3"
      to: "CLAUDE.md Lessons Learned 2026-05-05 #5"
      via: "anchor lesson cross-reference"
      pattern: "vision worker timeout vs OMNIGRAPH_LLM_TIMEOUT_SEC ratio audit"
    - from: "REVIEW.md §4 (A2)"
      to: "image_pipeline.py cascade + circuit breaker code"
      via: "branch table + state-machine scope analysis"
      pattern: "explicit cascade order, breaker scope (per-batch / per-process / persisted), 4xx/429/5xx branch"
    - from: "REVIEW.md §5 (A3)"
      to: "image_pipeline.py balance check + cost instrumentation"
      via: "timing + estimation + silent-leak audit"
      pattern: "warning threshold source, depletion signal type, batch_validation_report.json writer"
---

<objective>
Conduct a single-shot, READ-ONLY deep code review of `image_pipeline.py` (645 LOC, last commit `ce8127a`) and emit `260511-lyj-REVIEW.md` + `260511-lyj-SUMMARY.md` inside this quick's directory.

Purpose:
- This is the only OmniGraph-Vault module that spends real money (SiliconFlow ¥0.0013/image). Cost-leak risk is its own verdict dimension.
- 3-provider Vision Cascade + circuit breaker is more complex than `lib/scraper.py`; previous audits (T3 `260511-d7m`, T4 `260511-kxd`) did not cover it.
- Quick `260509-p1n` only refactored the spawn site (`lib/vision_tracking.py` + `ingest_wechat.py:1186`); the orchestrator internals have never been audited.
- Quick `260511-b3y` fixed `GOOGLE_CLOUD_LOCATION=global` in `lib/vertex_gemini_complete.py`; we must verify whether the Vertex Vision path inside `image_pipeline.py` (reportedly around lines 319-320) routes through that fixed module or constructs its own client.
- CLAUDE.md sections "Vision Cascade" and "SiliconFlow Balance Management" are the **documented contract**; the audit's job is to verify source code matches them, line by line.

Output: REVIEW.md + SUMMARY.md only. No code changes. No live API calls. No `.env` touches. No SSH.
</objective>

<execution_context>
Running locally on Windows / Git Bash via `/gsd:quick`. Read-only tools only:
- Read (with offset/limit for large files — `image_pipeline.py` is 645 LOC, fits a single read; CLAUDE.md is large, target the two named sections).
- Grep / Glob.
- Bash for `wc -l`, `git log`, `git show`, `git status --short` only.

No code edits. No tests run. No API calls. No subprocess spawning the vision pipeline.
</execution_context>

<context>
# Required reads (in order)

## Project state
@.planning/STATE.md

## Project contract (the document this audit verifies)
@CLAUDE.md
- Section "Vision Cascade" (long-form, ~30 lines) — the documented contract for cascade order, circuit breaker, balance alerts.
- Section "SiliconFlow Balance Management" (long-form, ~25 lines) — depletion semantics, top-up flow, pre-batch warnings.
- Section "Lessons Learned" entry "2026-05-05 #5" — the anchor lesson on vision worker timeout vs `OMNIGRAPH_LLM_TIMEOUT_SEC` 30× ratio.

## Audit target
@image_pipeline.py
- 645 LOC. Last commit `ce8127a` ("feat(image_pipeline): D-20.08/09 referer header + SVG filter (RIN-02)").
- This is the ONLY file whose internals are being audited. Read it in full.

## Cousins (context-only reads — do NOT audit their internals)
@ingest_wechat.py
- ONLY line 1186 (the vision worker spawn site). Verify the call-site contract from `260509-p1n` is honored. Do not audit the rest of this file.

@lib/vision_tracking.py
- Drain helpers — for A4 (cross-module coupling) + A6 (task-lifecycle boundary). Verify the contract `image_pipeline.py` exposes to it.

@lib/vertex_gemini_complete.py
- For A4 — answer the question: does `image_pipeline.py` Vertex Vision path go through this fixed module (`260511-b3y`) or construct its own client?

## Trusted-region cross-references (do NOT re-audit)
@.planning/quick/260509-p1n-fix-d-10-09-vision-async-drain-hang-via-/260509-p1n-SUMMARY.md
- Vision drain refactor context. Trust the spawn-site contract; verify only the call-site shape from inside `image_pipeline.py`.

@.planning/quick/260511-b3y-ainsert-vertex-location-fix-3-line-fix-l/260511-b3y-PLAN.md
- Vertex location fix context. Trust the `lib/vertex_gemini_complete.py` fix; verify whether `image_pipeline.py` benefits from it or has an isolated path.

## REVIEW.md schema templates (for matching prior tone + structure)
@.planning/quick/260511-kxd-t4-lib-scraper-py-deep-review-read-only/260511-kxd-REVIEW.md
- T4 template — cascade-divergence approach is closest analog. Match the angle structure + verdict tone.

@.planning/quick/260511-d7m-t3-batch-ingest-from-spider-py-deep-revi/260511-d7m-REVIEW.md
- T3 template — 7-angle structure. Match section ordering + evidence-density discipline.

## Test coverage discovery (for A7)
- Glob `tests/unit/test_image_pipeline*.py` and `tests/unit/test_vision*.py`.
- Read whichever match. If none, A7 = "no tests found" and that itself is a finding.

# Trusted regions (do NOT re-audit)

| Quick | Commit | Trusted region | Action |
|---|---|---|---|
| 260509-p1n | f715f06 | Vision drain spawn site refactor (`lib/vision_tracking.py` + `ingest_wechat.py:1186` wrap). Does NOT touch `image_pipeline.py` internals. | Verify call-site contract intact only. |
| 260511-b3y | b1e7fc8 | Vertex `GOOGLE_CLOUD_LOCATION=global` default in `lib/vertex_gemini_complete.py`. Does NOT touch `image_pipeline.py`. | Verify whether `image_pipeline.py:319-320` Vertex path goes through this fixed module or has its own client construction. |
| 260510-gqu | 981121d | LightRAG SDK research — irrelevant to vision. | Skip. |
| 260511-d7m T3 | 8832e95 | batch_ingest_from_spider deep audit — irrelevant to image_pipeline internals. | Skip (only as schema reference). |
| 260511-kxd T4 | 6a284a3 | lib/scraper deep audit — unrelated path. | Skip (only as schema reference). |
| 260509-s29 W3 | e538b2d | LLM dispatcher — image_pipeline calls Vision SDK, not LLM dispatcher. | Skip (cross-check only via A4 question: is Vertex Vision routed through dispatcher? Expected: no). |

# CLAUDE.md "Vision Cascade" contract checklist (for §2)

- Fallback order **hard-coded, not env-overridable**: SiliconFlow → OpenRouter → Gemini Vision (Vertex).
- Circuit breaker: 3 consecutive failures → `circuit_open=True`, batch-internal skip.
- 429 cascades immediately, does NOT count toward circuit breaker.
- 4xx auth errors do NOT count toward circuit breaker (operator action required).
- `batch_validation_report.json` records `provider_usage` (per-provider attempts + successes).
- Healthy batch: Gemini usage < 10%; >10% triggers warning to investigate SiliconFlow + OpenRouter.

# CLAUDE.md "SiliconFlow Balance Management" contract checklist (for §2)

- Balance depletion ≠ hang (cascade falls through), but downstream Gemini 500-RPD limit means a single batch will exhaust it.
- Pre-batch: warning to stderr if `SiliconFlow balance < estimated remaining cost`.
- Estimation rule: `¥0.0013 × expected_image_count`, ¥1.00 ≈ 770 images.
- Top-up flow: Ctrl+C pause (atomic checkpoints) → console top-up → resume same command.

# Anchor lesson (for §3)

- 2026-05-05 #5: embedding/vision worker timeouts disproportional to LLM timeout. `OMNIGRAPH_LLM_TIMEOUT_SEC` raised 600→1800 but vision worker stayed 60s. 30× ratio is hidden ceiling. **Verify** in REVIEW §3 and A6.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Read sources, audit 7 angles, author REVIEW.md + SUMMARY.md</name>
  <files>.planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md, .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-SUMMARY.md</files>
  <action>
**Phase A — Anchor reads (in this order, do not skip):**

1. Run `wc -l image_pipeline.py` to confirm 645 LOC and `git log -1 --pretty=format:"%H %s" -- image_pipeline.py` to confirm last commit. Record both in REVIEW.md header.
2. Read `image_pipeline.py` in full (single Read call; 645 LOC fits).
3. Read CLAUDE.md targeting only:
   - Section "Vision Cascade" (search anchor: `## Vision Cascade`).
   - Section "SiliconFlow Balance Management" (search anchor: `## SiliconFlow Balance Management`).
   - "Lessons Learned" 2026-05-05 #5 (search anchor: `Embedding/Vision worker timeouts disproportional`).
   Use Grep with `-n -B 0 -A 30` to extract each section without loading the whole file.
4. Read the cousins listed in `<context>` for context-only purposes.
5. Glob `tests/unit/test_image_pipeline*.py` and `tests/unit/test_vision*.py`. Read whichever match.
6. Read the trusted-region SUMMARYs / PLANs to confirm what's already verified (do NOT re-audit those regions).

**Phase B — Build evidence map (use Grep extensively, do NOT speculate):**

For each of the 7 audit angles, collect file:line evidences from `image_pipeline.py`. Where the lesson / contract anchor demands cross-file lookups (e.g., A4 Vertex routing), Grep into `lib/vertex_gemini_complete.py` and `lib/vision_tracking.py`.

- A1 — Dead code / migration debris.
  - Grep `image_pipeline.py` for: `# TODO`, `# FIXME`, `# Phase`, `# Was:`, `# Wave`, `# DEPRECATED`, `# Legacy`, `# XXX`, `# HACK`.
  - Per finding: still-applicable / fixed / N/A. Note any 2-provider → 3-provider transition debris (was SiliconFlow added later? are there orphan imports / dead branches?).

- A2 — STAR ANGLE 1: Cascade order + Circuit-breaker state machine.
  - Locate the cascade dispatch code. Confirm explicit hard-coded order matches CLAUDE.md (SF → OR → Gemini Vertex).
  - Locate circuit-breaker state. Where stored? Module-global / per-batch object / persisted file? Document with file:line.
  - Branch table: build a table for HTTP 429 vs 5xx vs 4xx auth — does each branch behave per CLAUDE.md? (429 cascades immediately + no counter increment; 4xx no counter; 5xx counts toward 3-consecutive threshold.)
  - Hidden state issues: is `circuit_open` reset between batches? Across processes? Is the 3-consecutive counter reset on a single success in between?

- A3 — STAR ANGLE 2: Cost / balance management.
  - Locate balance-check call site. Pre-batch? Per-image? At all?
  - How is `expected_image_count` estimated — manifest length, doc count, hardcoded?
  - Threshold source: CLAUDE.md says `¥0.0013 × expected_image_count`. Verify literal value `0.0013` in code (Grep). If env-configurable, that's a deviation.
  - Depletion signal type: log-only / exception / structured warning to stderr? Does it match CLAUDE.md "structured warning per image"?
  - `batch_validation_report.json` writer: who writes it, when does it flush (per-image / per-doc / per-batch)? Is `provider_usage` per-provider attempts + successes both?
  - Per-provider cost instrumentation: is SF spend tracked separately? Are Gemini Vertex calls tracked? OpenRouter free tracked?
  - Silent-leak path question: is there a code path where SF returns HTTP 200 with empty / malformed body and the orchestrator counts it as success (money spent, garbage description)?

- A4 — Cross-module coupling.
  - List `image_pipeline.py` imports. Reverse-import audit: any `lib → app` direction? (Project pattern: lib should not import app modules.)
  - Who imports `image_pipeline`? Grep with `from image_pipeline` and `import image_pipeline` across the repo.
  - p1n drain ↔ image_pipeline contract: who owns vision task lifecycle? `lib/vision_tracking.py` does drain on the spawn side; what is `image_pipeline.py`'s role — does it expose tasks or hold them?
  - Vertex Vision call: does `image_pipeline.py:319-320` go through `lib/llm_complete.get_llm_func()` dispatcher (would route Vertex through the fixed `lib/vertex_gemini_complete.py` from b3y) or construct its own `aiplatform_v1` / `vertexai` client? **Direct expected — vision is not LLM — but verify with file:line.** If image_pipeline constructs its own Vertex client, the b3y `GOOGLE_CLOUD_LOCATION=global` fix does NOT transfer; this is a HIGH finding.

- A5 — Silent-fail / silent-cost-leak audit.
  - Provider X fail → cascade immediately or local retry first? Locate the retry loop. Per-provider retry count?
  - "Gemini usage > 10%" check: log only or raise / abort? CLAUDE.md says "warning"; verify code matches.
  - One image fails but batch continues — is the doc marked `ok` or `partial`? Where? Does the SUMMARY/checkpoint reflect partial completion?
  - **Critical**: SF billed but response was wrong/empty silently treated as success. Audit success-path validation (response.json parse → empty string → still cached? still counted as success?).

- A6 — Async + timeout engineering.
  - Per-image timeout value. Hard-coded or env-driven?
  - Reset on provider switch? (Each provider gets a fresh timeout, or is the global elapsed time tracked?)
  - Consistent with `OMNIGRAPH_LLM_TIMEOUT_SEC` per CLAUDE.md 2026-05-05 #5? (LLM ceiling 1800s vs vision worker historically 60s = 30× ratio.)
  - Task lifecycle boundary with p1n drain: who calls `task.cancel()` if the batch dies — image_pipeline or the drain helper?

- A7 — Test coverage.
  - Enumerate test files matching `test_image_pipeline*.py` + `test_vision*.py` via Glob.
  - For each test file, scan for: cascade-order contract test, circuit-breaker state-machine test, balance-management mock, timeout test.
  - "Probably absent" checklist: which contracts have NO test?

**Phase C — Author REVIEW.md (12-section schema, exact match):**

Use the schema in the task brief verbatim:

1. Header (date ADT, file, LOC, last commit SHA).
2. ## TL;DR — counts (HIGH/MEDIUM/LOW), cross-cutting count, est cleanup hours/quicks, hygiene verdict, cost-leak verdict.
3. ## 1. File sectional map — function list + LOC per function + one-line purpose. Use Grep `^def\|^async def\|^class` with `-n` to enumerate.
4. ## 2. CLAUDE.md cross-reference table — ~10 rows covering both Vision Cascade + Balance Management contracts. Columns: documented contract / source code state / match? + evidence (file:line).
5. ## 3. Lessons Learned cross-reference — anchor 2026-05-05 #5 with Status / Evidence columns.
6. ## 4. Cascade + Circuit-breaker findings (STAR ANGLE 1) — explicit cascade order, breaker scope, 4xx/429/5xx branch table, hidden state issues.
7. ## 5. Cost / balance findings (STAR ANGLE 2) — balance check timing + estimation accuracy, silent-leak possibilities, cost instrumentation gaps.
8. ## 6. Findings by severity — HIGH / MEDIUM / LOW. Each finding: F-X title / Evidence (file:line) / Why severity / Fix scope (~LOC, quick type, risk).
9. ## 7. Cross-cutting issues — items spanning image_pipeline + N other files.
10. ## 8. Async + timeout observations (A6).
11. ## 9. Test coverage gap (A7).
12. ## 10. Recommended fix-quick sequence — ordered, est hours, dependencies.
13. ## 11. Module verdict — pollution score (HIGH/MEDIUM/LOW), cost-leak risk (HIGH/MEDIUM/LOW), recommendation (ship X / batch with lib hygiene wave / no action).
14. ## 12. Open questions for user — items reviewer cannot decide.

Discipline:
- Every finding cites file:line. No "looks fine" stubs.
- A2 + A3 collectively cite >= 8 file:line evidences (target — count and report in SUMMARY).
- Each angle (A1-A7) appears in REVIEW.md, even if "no findings in A_X".
- Don't speculate. Uncertainty → §12 Open Questions.
- Don't re-audit trusted regions.
- Cost-leak verdict is REQUIRED (its own dimension).
- Hygiene verdict is REQUIRED.

If wall-time budget exhausted (3h hard cap, 4h emergency cap):
- Ship a partial REVIEW.md.
- Add to §12 Open Questions: "incomplete: angles A_X..A_Y not done".
- Stop. Don't paper over with speculation.

**Phase D — Author SUMMARY.md (closure note):**

Write `260511-lyj-SUMMARY.md` containing:
- Quick ID, date ADT, LOC, last commit SHA of audit target.
- Hygiene verdict (clear / soft-gating / gating) + finding counts (HIGH/MEDIUM/LOW).
- Cost-leak verdict (clean / soft-leak / leak) + brief rationale.
- Evidence-density tally for A2 + A3 (target ≥ 8 combined; actual count).
- Pointer to REVIEW.md.
- Note any §12 Open Questions that need user follow-up.
- Pin commit SHA after the commit lands.

**Phase E — Verify and commit:**

1. Re-read REVIEW.md to confirm all 12 sections present, all 7 angles covered, both verdicts explicit.
2. Run `git status --short` from the repo root. Confirm the only modified / untracked paths are inside `.planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/`.
3. Use `node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" commit "docs(quick-260511-lyj): T5 image_pipeline.py deep review (release hygiene)" --files .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-PLAN.md .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-SUMMARY.md`.
4. After commit, update SUMMARY.md to record the commit SHA. Amend or supplemental commit per project convention (do not `--amend` if shared worktree concerns apply — see Lessons Learned 2026-05-06 #5).
  </action>
  <verify>
    <automated>bash -c 'cd "C:/Users/huxxha/Desktop/OmniGraph-Vault" && for s in "## TL;DR" "## 1. File sectional map" "## 2. CLAUDE.md" "## 3. Lessons Learned" "## 4. Cascade + Circuit-breaker findings" "## 5. Cost / balance findings" "## 6. Findings by severity" "## 7. Cross-cutting issues" "## 8. Async + timeout observations" "## 9. Test coverage gap" "## 10. Recommended fix-quick sequence" "## 11. Module verdict" "## 12. Open questions"; do grep -q "$s" .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md || { echo "MISSING SECTION: $s"; exit 1; }; done; grep -qE "Cost / balance verdict|Cost-leak verdict" .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md || { echo "MISSING cost-leak verdict"; exit 1; }; grep -qE "Hygiene verdict" .planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/260511-lyj-REVIEW.md || { echo "MISSING hygiene verdict"; exit 1; }; CHANGED=$(git status --short | grep -v "^?? .planning/quick/260511-lyj-" | grep -v "^.. .planning/quick/260511-lyj-"); [ -z "$CHANGED" ] || { echo "UNEXPECTED CHANGES OUTSIDE QUICK DIR:"; echo "$CHANGED"; exit 1; }; echo OK'</automated>
  </verify>
  <done>
- `260511-lyj-REVIEW.md` exists with all 12 schema sections.
- Hygiene verdict and cost-leak verdict are both explicit and present in §11 (Module verdict) and TL;DR.
- All 7 angles (A1-A7) are addressed (some may be "no findings", but each has its line/section).
- Star angles A2 + A3 collectively cite ≥ 8 file:line evidences.
- Every finding cites file:line evidence.
- `260511-lyj-SUMMARY.md` exists with verdicts + evidence-density tally + commit SHA.
- `git status --short` shows only paths inside `.planning/quick/260511-lyj-*/`.
- No code outside `.planning/` was modified.
- No live SiliconFlow / OpenRouter / Gemini / Vertex API calls were made.
- Trusted regions (p1n / b3y / gqu / d7m / kxd / s29) were NOT re-audited.
- Commit landed; SHA recorded in SUMMARY.md.
  </done>
</task>

</tasks>

<verification>
- All 12 REVIEW.md sections present (verify via grep -c on each section header).
- Both verdicts (hygiene + cost-leak) explicit.
- A1-A7 each have a line in REVIEW.md.
- A2 + A3 together cite ≥ 8 file:line evidences (count by hand or with `grep -E ":[0-9]+" 260511-lyj-REVIEW.md | wc -l` filtered to §4 + §5).
- No edits outside `.planning/quick/260511-lyj-*/`.
- `git log -1` shows the closure commit with SUMMARY.md updated to include its own SHA.
</verification>

<success_criteria>
- REVIEW.md is complete, evidence-dense, and verdicts are explicit.
- SUMMARY.md captures the verdict pair, finding counts, evidence tally, and commit SHA.
- No code mutation occurred. No live API calls. Read-only audit.
- A reviewer can read REVIEW.md and decide which fix-quicks to spawn next without re-reading `image_pipeline.py`.
- Cost-leak verdict provides a clean signal: is money safe in this module today, or is there a silent-leak path that needs a follow-up quick?
</success_criteria>

<output>
After completion, the following files exist inside `.planning/quick/260511-lyj-t5-image-pipeline-py-deep-review-read-on/`:
- `260511-lyj-PLAN.md` (this file)
- `260511-lyj-REVIEW.md` (the audit deliverable)
- `260511-lyj-SUMMARY.md` (closure note with verdicts + commit SHA)

No other files. No code changes. No `.env` touches. No SSH.
</output>

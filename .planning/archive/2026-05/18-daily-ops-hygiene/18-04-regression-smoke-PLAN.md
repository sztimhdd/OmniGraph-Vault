---
phase: 18-daily-ops-hygiene
plan: 04
type: execute
wave: 2
depends_on: [05-06 Task 6.3 (Phase 5 Exit State written)]
blocked: true
files_modified:
  - scripts/validate_regression_batch.py
  - .github/workflows/regression-smoke.yml
  - scripts/register_regression_cron.sh
autonomous: true
requirements: [HYG-05]
must_haves:
  truths:
    - "Single-fixture regression smoke runs `scripts/bench_ingest_fixture.py` on `test/fixtures/gpt55_article/` and asserts 4 hard gates"
    - "GitHub Actions workflow fires on PRs touching `ingest_wechat.py`, `lib/lightrag_embedding.py`, `lib/vision_cascade.py`, `image_pipeline.py`"
    - "Hermes weekly cron runs same check (Sundays 02:00) and Telegram-alerts on any gate failure"
  artifacts:
    - path: "scripts/validate_regression_batch.py"
      provides: "Reduce existing multi-fixture validator to single gpt55 fixture + 4 gates (or create new thin wrapper)"
      min_lines_touched: 50
    - path: ".github/workflows/regression-smoke.yml"
      provides: "CI hook on PR affecting ingest/embedding/vision/image paths"
      min_lines: 40
    - path: "scripts/register_regression_cron.sh"
      provides: "Hermes weekly cron registrar, idempotent"
      min_lines: 30
  key_links:
    - from: ".github/workflows/regression-smoke.yml"
      to: "scripts/bench_ingest_fixture.py"
      via: "GitHub Actions run step"
      pattern: "bench_ingest_fixture"
---

<objective>
Lightweight single-fixture regression smoke. Runs `scripts/bench_ingest_fixture.py` against `test/fixtures/gpt55_article/` and asserts:

1. **G1 text_ingest < 700s** — prod baseline 441s (Hermes DeepSeek) + 259s headroom; any blow-up surfaces here.
2. **G2 aquery returns non-empty chunks** — semantic retrieval is live; a broken embedding dim or retrieval chain surfaces here.
3. **G3 28 / 28 images filtered correctly** — `min(w,h)<300` filter semantic preserved; the gpt55 fixture has a deterministic 39 → 28 filter count from Phase 8 IMG-01.
4. **G4 doc status = PROCESSED** — `aget_docs_by_ids` verification hook (Phase 5 Task 4.2) returns `PROCESSED`; any state-management regression surfaces here.

Scope rationale (carried from 18-CONTEXT D-18-04): real-batch still catches the 80% of defects (Wave 0 D + E). But the ~30s single-fixture gate is cheap and catches the class of "PR accidentally breaks ingest_wechat imports" regressions pre-merge.

**This plan is BLOCKED** on Phase 5 Task 6.3 (Phase 5 Exit State finalization). Reason: the 3-day observation window (Task 6.2) may reveal unexpected failure modes that this regression gate would also need to catch — better to absorb those into the gate definition than to land the gate early and amend.
</objective>

<execution_context>
When unblocked: Windows dev machine can unit-test the shell-ability of the wrapper script (bash -n). The actual fixture run stays Hermes-side because the full pipeline hits SiliconFlow (Umbrella-blocked on Windows). CI runs on GitHub Actions Linux runner with its own env vars.
</execution_context>

<context>
@.planning/phases/18-daily-ops-hygiene/18-CONTEXT.md
@scripts/bench_ingest_fixture.py
@scripts/validate_regression_batch.py
@test/fixtures/gpt55_article/metadata.json
@docs/MILESTONE_v3.1_CLOSURE.md

<precondition>
Phase 5 Wave 3 must close first. Specifically: Task 6.2 produces operator verdict (`approved` / `approved-with-notes` / `rejected`); Task 6.3 writes the Phase 5 Exit State into STATE.md + ROADMAP.md. This plan reads that Exit State to:
- Confirm no new gate classes need adding (e.g., if 3-day observation revealed a recurring Telegram-delivery failure, a G5 should be added).
- Confirm 441s baseline still holds; if observed p50 has drifted higher, adjust the G1 budget.

Hand-off signal: user or Phase 5 executor reports "Task 6.3 done; regression smoke unblocked".
</precondition>

<proposed_gates>
```python
# scripts/validate_regression_batch.py — reduced from multi-fixture to single.

FIXTURE = "test/fixtures/gpt55_article/"
GATES = {
    "G1_text_ingest_under_700s": lambda r: r["stage_timings_ms"]["text_ingest"] < 700_000,
    "G2_aquery_non_empty":        lambda r: r["counters"]["chunks_extracted"] > 0,
    "G3_image_filter_28_of_28":   lambda r: r["counters"]["images_kept"] == 28,
    "G4_doc_status_processed":    lambda r: r.get("doc_status") == "PROCESSED",
}
```

The Phase 11 `benchmark_result.json` schema already carries `stage_timings_ms`, `counters`, and `gate_pass`. G4 needs either an extension to the schema (`doc_status` field) or a post-hoc `aget_docs_by_ids` call in the validator. Resolution deferred to execution phase.
</proposed_gates>

<ci_workflow_shape>
```yaml
name: regression-smoke

on:
  pull_request:
    paths:
      - ingest_wechat.py
      - image_pipeline.py
      - lib/lightrag_embedding.py
      - lib/vision_cascade.py

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python scripts/validate_regression_batch.py --fixture test/fixtures/gpt55_article --max-wall 700
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          SILICONFLOW_API_KEY: ${{ secrets.SILICONFLOW_API_KEY }}
```

Open question for execution: does the CI runner have enough bandwidth to run a real ingestion against live APIs on every PR? Alternative: mock-all-providers mode. Lean toward live-mode with a small budget (gpt55 fixture costs ~¥0.036 per run; 100 PRs/month = ¥3.60).
</ci_workflow_shape>

<hermes_cron_shape>
```bash
#!/usr/bin/env bash
# register_regression_cron.sh — HYG-05 weekly regression smoke.
set -euo pipefail
EXISTING="$(hermes cron list 2>/dev/null || echo '')"
NAME="regression-smoke-weekly"
if printf '%s\n' "$EXISTING" | grep -qE "\b${NAME}\b"; then
  echo "SKIP ${NAME}"
else
  echo "ADD ${NAME} @ 0 2 * * 0"
  hermes cron add \
    --name "${NAME}" \
    --workdir "${OMNIGRAPH_ROOT:-$HOME/OmniGraph-Vault}" \
    "0 2 * * 0" \
    "run scripts/validate_regression_batch.py --fixture test/fixtures/gpt55_article; on non-zero exit Telegram alert"
fi
hermes cron list
```
</hermes_cron_shape>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 18-04.1: Reduce validate_regression_batch to single-fixture + 4 gates</name>
  <files>scripts/validate_regression_batch.py, tests/unit/test_regression_gates.py</files>
  <behavior>
    - Single `--fixture` arg defaults to `test/fixtures/gpt55_article`.
    - Exit 0 iff all 4 gates pass; exit 1 otherwise, print each failing gate.
    - JSON report written to `test/fixtures/gpt55_article/regression_report_{timestamp}.json`.
    - G4 doc_status: either extend Phase 11 schema or do a follow-up `aget_docs_by_ids` check — pick whichever has lower diff cost after reading Phase 11's current writer.
  </behavior>
  <!-- Deferred to unblock. Full task body will be filled at execution time, informed by Phase 5 Exit State. -->
</task>

<task type="auto" tdd="false">
  <name>Task 18-04.2: GitHub Actions CI workflow</name>
  <files>.github/workflows/regression-smoke.yml</files>
  <behavior>
    - Fires on PR affecting the 4 paths listed above.
    - Runs `scripts/validate_regression_batch.py`.
    - CI secret wiring for `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `SILICONFLOW_API_KEY`.
  </behavior>
  <!-- Deferred to unblock. -->
</task>

<task type="auto" tdd="false">
  <name>Task 18-04.3: Hermes weekly cron registrar</name>
  <files>scripts/register_regression_cron.sh</files>
  <behavior>
    - Idempotent; Sunday 02:00 schedule.
    - Natural-language prompt per D-16.
  </behavior>
  <!-- Deferred to unblock. -->
</task>

</tasks>

<verification>
Filled at execution time. At minimum:
- Unit tests for gate evaluator.
- CI workflow syntax validated via `actionlint` (if installed) or manual dry-run.
- Hermes weekly cron registered + manual first-run confirms green.
</verification>

<success_criteria>
- HYG-05 satisfied: any regression that breaks text_ingest wall-clock, aquery, image filter, or doc status fails CI on the PR and/or the weekly Hermes cron — before it reaches the next daily batch.
- Zero existing production code paths modified.
</success_criteria>

<output>
After execution, create `.planning/phases/18-daily-ops-hygiene/18-04-SUMMARY.md` documenting gate values adopted, CI cost per run, any Phase 5 Exit State findings absorbed.
</output>

<blocked_note>
THIS PLAN IS BLOCKED on Phase 5 Task 6.3 (Phase 5 Exit State finalization). Do NOT execute until the concurrent Phase 5 Wave 3 session reports Task 6.3 complete. Tasks 18-04.1/2/3 bodies are intentionally thin — they will be expanded at unblock time with Phase 5 observation findings.
</blocked_note>

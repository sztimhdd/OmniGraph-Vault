---
phase: 14-regression-fixtures
plan: 03
type: execute
wave: 2
depends_on:
  - 14-01-fixture-creation
  - 14-02-validate-script
files_modified:
  - batch_validation_report.json
  - .planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md
autonomous: false
requirements:
  - REGR-05

must_haves:
  truths:
    - "All 5 fixtures (gpt55 + 4 new) run through scripts/validate_regression_batch.py without unhandled exception"
    - "batch_validation_report.json is emitted matching PRD §B3.4 schema exactly"
    - "text_only_article does NOT crash despite 0 images (Vision skip edge case verified)"
    - "dense_image_article correctly filters narrow-banner images (images_kept < total_images_raw)"
    - "mixed_quality_article handles corrupted images without killing the article (Phase 13 cascade gracefully handles decode failures)"
    - "Script exit code reflects aggregate.batch_pass (0 if true, 1 if false)"
  artifacts:
    - path: "batch_validation_report.json"
      provides: "End-to-end regression report for Milestone v3.2 Gate 3 sign-off"
      contains: "\"batch_id\":\\s*\"regression_"
    - path: ".planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md"
      provides: "Human-readable analysis of the regression run + Gate 3 disposition"
  key_links:
    - from: "scripts/validate_regression_batch.py"
      to: "lib.checkpoint.reset_article"
      via: "REAL Phase 12 import (no stub — Phase 12 must be merged by now)"
      pattern: "from lib.checkpoint import"
    - from: "scripts/validate_regression_batch.py"
      to: "lib.vision_cascade.VisionCascade.total_usage"
      via: "REAL Phase 13 import (no stub — Phase 13 must be merged by now)"
      pattern: "from lib.vision_cascade import"
    - from: "batch_validation_report.json"
      to: "Milestone v3.2 Gate 3"
      via: "aggregate.batch_pass == True for 5 fixtures"
      pattern: "\"batch_pass\":\\s*true"
---

<objective>
Execute `scripts/validate_regression_batch.py` against all 5 fixtures (gpt55_article + 4 new from Plan 14-01) and capture the resulting `batch_validation_report.json` as the Milestone v3.2 Gate 3 evidence artifact. This is the PROOF phase that Phase 12 (checkpoint) + Phase 13 (vision cascade) + Plan 14-01 (fixtures) + Plan 14-02 (script) compose correctly end-to-end.

Purpose: Close Milestone v3.2 Acceptance Criteria Gate 3 ("Regression Fixtures Pass" — see MILESTONE_v3.2_REQUIREMENTS.md §Acceptance Criteria lines 412-416). Produce a `SUMMARY.md` with per-fixture analysis + Gate 3 disposition.

Output: 1 JSON report + 1 SUMMARY.md. No new code files.

**Preconditions (blocking — verified in Task 1):**
- Phase 12 merged: `lib/checkpoint.py` exists and `from lib.checkpoint import reset_article, get_article_hash` works
- Phase 13 merged: `lib/vision_cascade.py` exists and `from lib.vision_cascade import VisionCascade` works with `total_usage()` method
- Plan 14-01 complete: All 4 new fixture directories + metadata.json exist
- Plan 14-02 complete: `scripts/validate_regression_batch.py` + unit tests exist and pass

**Classification:** `autonomous: false` — Gate 3 disposition requires human judgment on borderline tolerance failures; planned as a checkpoint.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@.planning/phases/14-regression-fixtures/14-CONTEXT.md
@.planning/phases/14-regression-fixtures/14-01-fixture-creation-PLAN.md
@.planning/phases/14-regression-fixtures/14-02-validate-script-PLAN.md
@CLAUDE.md

<interfaces>
<!-- Runtime preconditions for this plan. All must be satisfied BEFORE Task 1. -->

Phase 12 (lib/checkpoint.py) must export:
```python
def get_article_hash(url: str) -> str: ...
def reset_article(article_hash: str) -> None: ...
```

Phase 13 (lib/vision_cascade.py) must export:
```python
class VisionCascade:
    def __init__(self, providers_in_order: list[str], checkpoint_dir: Path): ...
    def total_usage(self) -> dict[str, int]: ...
```

Fixture directory layout (from Plan 14-01):
```
test/fixtures/
├── gpt55_article/              (already existed — baseline from Milestone A)
├── sparse_image_article/       (NEW from Plan 14-01)
├── dense_image_article/        (NEW from Plan 14-01)
├── text_only_article/          (NEW from Plan 14-01)
└── mixed_quality_article/      (NEW from Plan 14-01)
```

PRD §B3.3 LOCKED CLI:
```bash
python scripts/validate_regression_batch.py \
  --fixtures test/fixtures/gpt55_article \
              test/fixtures/sparse_image_article \
              test/fixtures/dense_image_article \
              test/fixtures/text_only_article \
              test/fixtures/mixed_quality_article \
  --output batch_validation_report.json
```

Gate 3 acceptance criteria (MILESTONE_v3.2_REQUIREMENTS.md §Acceptance Criteria Gate 3):
- All 5 fixtures complete without exception
- batch_validation_report.json shows batch_pass: true
- dense_image_article (45 images) successfully filters to expected count and all survive Vision
- text_only_article (0 images) skips Vision pipeline entirely (no null pointer errors)
- mixed_quality_article handles both JPEG and PNG without errors
</interfaces>

</context>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1: Verify preconditions before launching regression run</name>
  <what-built>Readiness check for end-to-end regression gate. Nothing is built in this task — only verifying upstream deliverables are in place.</what-built>
  <how-to-verify>
  Run the following preflight script to confirm all preconditions. Every line must succeed for Task 2 to proceed.

  ```bash
  # 1. Phase 12 merged (real implementation, not stub)
  python -c "from lib.checkpoint import reset_article, get_article_hash; print('Phase 12 OK:', reset_article.__module__)"
  # Expected: "Phase 12 OK: lib.checkpoint"   (NOT "scripts.validate_regression_batch")

  # 2. Phase 13 merged (real implementation with total_usage)
  python -c "from lib.vision_cascade import VisionCascade; c = VisionCascade(['siliconflow'], None); print('Phase 13 OK:', c.total_usage())"
  # Expected: "Phase 13 OK: {'siliconflow': 0, ...}"   (no ImportError)

  # 3. All 5 fixtures exist with required files
  for f in gpt55_article sparse_image_article dense_image_article text_only_article mixed_quality_article; do
    test -d test/fixtures/$f && test -f test/fixtures/$f/metadata.json && test -f test/fixtures/$f/article.md || { echo "FAIL: test/fixtures/$f incomplete"; exit 1; }
  done
  echo "All 5 fixtures present"

  # 4. Plan 14-02 script + tests exist and tests pass
  test -f scripts/validate_regression_batch.py && test -f tests/test_validate_regression_batch.py && python -m pytest tests/test_validate_regression_batch.py -q
  ```

  Additional sanity:
  - 5. No stale graph state that would poison the run:
    ```bash
    # Check for leftover Phase 12 checkpoints from prior runs; optional cleanup:
    python scripts/checkpoint_status.py 2>/dev/null || echo "(checkpoint_status not yet wired — skip)"
    # If needed: python scripts/checkpoint_reset.py --all
    ```
  - 6. Environment variables set for ingest pipeline (CLAUDE.md § Environment Variables):
    ```bash
    env | grep -E "GEMINI_API_KEY|OMNIGRAPH_GEMINI_KEY|DEEPSEEK_API_KEY|SILICONFLOW_API_KEY" | wc -l
    # Expected: 2-4 (at least GEMINI + DEEPSEEK set; SILICONFLOW optional)
    ```

  Report back any failure. If Phase 12 OR Phase 13 is not yet merged, PAUSE this plan until they are — the regression run will produce meaningless results with stubbed cascade/checkpoint.
  </how-to-verify>
  <resume-signal>Type "preconditions verified" after all 6 checks pass, OR describe which check failed and how it was resolved</resume-signal>
</task>

<task type="auto">
  <name>Task 2: Execute regression run against all 5 fixtures</name>
  <read_first>
    - scripts/validate_regression_batch.py (from Plan 14-02)
    - test/fixtures/gpt55_article/metadata.json
    - test/fixtures/sparse_image_article/metadata.json
    - test/fixtures/dense_image_article/metadata.json
    - test/fixtures/text_only_article/metadata.json
    - test/fixtures/mixed_quality_article/metadata.json
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §B3.3 (LOCKED CLI)
  </read_first>
  <files>
    - batch_validation_report.json
    - logs/regression_run.log
  </files>
  <action>
  Run the PRD-locked command to validate all 5 fixtures and emit the report. Use `tee` to capture stdout for the SUMMARY; errors go to both stdout (via logging) and stderr:

  ```bash
  mkdir -p logs

  python scripts/validate_regression_batch.py \
    --fixtures test/fixtures/gpt55_article \
                test/fixtures/sparse_image_article \
                test/fixtures/dense_image_article \
                test/fixtures/text_only_article \
                test/fixtures/mixed_quality_article \
    --output batch_validation_report.json \
    2>&1 | tee logs/regression_run.log

  # Capture exit code from the FIRST command in the pipe (Bash: PIPESTATUS[0])
  EXIT_CODE=${PIPESTATUS[0]}
  echo "Regression run exit code: $EXIT_CODE"
  ```

  If this is Windows Git Bash and `PIPESTATUS` is not available:
  ```bash
  # Capture exit code separately without pipe
  python scripts/validate_regression_batch.py \
    --fixtures test/fixtures/gpt55_article \
                test/fixtures/sparse_image_article \
                test/fixtures/dense_image_article \
                test/fixtures/text_only_article \
                test/fixtures/mixed_quality_article \
    --output batch_validation_report.json \
    > logs/regression_run.log 2>&1
  EXIT_CODE=$?
  cat logs/regression_run.log
  echo "Regression run exit code: $EXIT_CODE"
  ```

  Expected behavior:
  - All 5 fixtures ingest without Python traceback in stdout
  - `batch_validation_report.json` is written to repo root
  - Exit code is 0 if `aggregate.batch_pass == true`, else 1

  Validate immediately after run:
  ```bash
  # Report exists and is valid JSON
  test -f batch_validation_report.json && python -m json.tool batch_validation_report.json > /dev/null

  # Report has all 5 articles
  python -c "
  import json
  r = json.load(open('batch_validation_report.json'))
  assert r['aggregate']['total_articles'] == 5, f'Expected 5 articles, got {r[\"aggregate\"][\"total_articles\"]}'
  fixtures_reported = sorted(a['fixture'] for a in r['articles'])
  expected = ['dense_image_article','gpt55_article','mixed_quality_article','sparse_image_article','text_only_article']
  assert fixtures_reported == expected, f'Missing fixture in report: got {fixtures_reported}'
  print(f'All 5 fixtures reported. batch_pass={r[\"aggregate\"][\"batch_pass\"]}')
  "
  ```

  If the run fails with Python traceback, diagnose:
  1. `grep -A 20 "Traceback" logs/regression_run.log` → identify failing stage
  2. If a specific fixture is the cause, isolate it:
     ```bash
     python scripts/validate_regression_batch.py --fixtures test/fixtures/<failing_fixture> --output /tmp/isolated.json
     ```
  3. Common failure modes + fixes:
     - **LightRAG state corruption from prior run**: `rm -rf ~/.hermes/omonigraph-vault/lightrag_storage/*` + retry
     - **SiliconFlow balance 0**: script should still complete with Vision task skipped; check `/tmp/isolated.json` for `errors[]`
     - **Fixture metadata.json schema mismatch**: re-run Plan 14-01 Task 4 to regenerate
     - **Phase 12/13 regression introduced**: NOT fixable in this plan — escalate to Phase 12/13 owner

  DO NOT swallow errors — if the script crashes, the report is still written (with `errors_top_level` key) but exit=1 and Task 3 must diagnose.
  </action>
  <verify>
    <automated>
test -f batch_validation_report.json && python -c "
import json
r = json.load(open('batch_validation_report.json'))
assert r['aggregate']['total_articles'] == 5, f'Expected 5 articles, got {r[\"aggregate\"][\"total_articles\"]}'
fixtures = sorted(a['fixture'] for a in r['articles'])
expected = ['dense_image_article','gpt55_article','mixed_quality_article','sparse_image_article','text_only_article']
assert fixtures == expected, f'Fixture list mismatch: {fixtures}'
# PRD §B3.4 schema presence
assert set(r.keys()) == {'batch_id','timestamp','articles','aggregate','provider_usage'} or set(r.keys()) >= {'batch_id','timestamp','articles','aggregate','provider_usage'}
for a in r['articles']:
    assert a['status'] in {'PASS','FAIL','TIMEOUT'}
    assert set(a['timings_ms'].keys()) == {'scrape','classify','image_filter','text_ingest','vision_worker_start'}
    assert set(a['counters'].keys()) == {'images_input','images_kept','chunks','entities'}
print('Report structural validation PASS')
print(f'  batch_pass={r[\"aggregate\"][\"batch_pass\"]}')
print(f'  passed/failed={r[\"aggregate\"][\"passed\"]}/{r[\"aggregate\"][\"failed\"]}')
"
    </automated>
  </verify>
  <done>`batch_validation_report.json` exists at repo root, contains all 5 fixtures, matches PRD §B3.4 schema. Exit code and `batch_pass` flag are consistent (0 iff true). `logs/regression_run.log` captures full stdout/stderr for audit.</done>
</task>

<task type="auto">
  <name>Task 3: Analyze results + check Gate 3 sub-criteria</name>
  <read_first>
    - batch_validation_report.json (from Task 2)
    - logs/regression_run.log (from Task 2)
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §Acceptance Criteria Gate 3 (lines 412-416)
    - .planning/phases/14-regression-fixtures/14-CONTEXT.md § Fixture Profiles
  </read_first>
  <files>
    - (no files modified — analysis only; Task 4 writes SUMMARY.md)
  </files>
  <action>
  Evaluate the regression report against Gate 3 sub-criteria from MILESTONE_v3.2_REQUIREMENTS.md §Acceptance Criteria (lines 412-416):

  ```bash
  python << 'PY'
  import json
  from pathlib import Path

  r = json.load(open('batch_validation_report.json'))
  articles = {a['fixture']: a for a in r['articles']}

  print("=" * 70)
  print("GATE 3 ACCEPTANCE CRITERIA (MILESTONE_v3.2_REQUIREMENTS.md lines 412-416)")
  print("=" * 70)

  # Criterion 1: All 5 fixtures complete without exception
  no_crash = all(not any(e.get('type') == 'Exception' for e in a.get('errors', [])) for a in r['articles'])
  # Stronger check: no traceback in report errors OR any status that indicates crash
  crashed = [f for f, a in articles.items() if a['status'] == 'FAIL' and any('Traceback' in str(e) or e.get('type') in ('KeyError','AttributeError','TypeError') for e in a.get('errors', []))]
  if not crashed:
      print("[PASS] Criterion 1: All 5 fixtures complete without unhandled exception")
  else:
      print(f"[FAIL] Criterion 1: {len(crashed)} fixtures crashed: {crashed}")

  # Criterion 2: batch_validation_report.json shows batch_pass: true
  bp = r['aggregate']['batch_pass']
  print(f"[{'PASS' if bp else 'FAIL'}] Criterion 2: aggregate.batch_pass == {bp}")

  # Criterion 3: dense_image_article filters correctly
  dense = articles.get('dense_image_article')
  if dense:
      di = dense['counters']['images_input']
      dk = dense['counters']['images_kept']
      filter_active = dk < di  # at least 1 image filtered (IMG-01 min(w,h)>=300)
      print(f"[{'PASS' if filter_active else 'FAIL'}] Criterion 3: dense_image filter "
            f"(input={di}, kept={dk}, filtered={di - dk})")
  else:
      print("[FAIL] Criterion 3: dense_image_article missing from report")

  # Criterion 4: text_only_article skips Vision (no crash on 0 images)
  text_only = articles.get('text_only_article')
  if text_only:
      to_status = text_only['status']
      to_input = text_only['counters']['images_input']
      skip_vision = (to_input == 0 and to_status != 'FAIL')
      print(f"[{'PASS' if skip_vision else 'FAIL'}] Criterion 4: text_only skips Vision "
            f"(images_input={to_input}, status={to_status})")
  else:
      print("[FAIL] Criterion 4: text_only_article missing from report")

  # Criterion 5: mixed_quality handles JPEG + PNG without errors
  mixed = articles.get('mixed_quality_article')
  if mixed:
      mq_status = mixed['status']
      # Graceful degradation: status may be PASS (if corrupted images filtered) OR FAIL only if non-corruption errors
      # Check the errors list: corrupted image errors are EXPECTED; other errors are NOT
      mq_errors = mixed.get('errors', [])
      mq_decode_errors = [e for e in mq_errors if 'UnidentifiedImage' in str(e.get('type','')) or 'decode' in str(e.get('message','')).lower()]
      # If mixed has errors but they're ALL decode errors, cascade handled them (PASS)
      # If mixed has non-decode errors, FAIL
      non_decode = [e for e in mq_errors if e not in mq_decode_errors]
      handles_mixed = (mq_status != 'FAIL' or not non_decode)
      print(f"[{'PASS' if handles_mixed else 'FAIL'}] Criterion 5: mixed_quality handles JPEG+PNG "
            f"(status={mq_status}, decode_errors={len(mq_decode_errors)}, other_errors={len(non_decode)})")
  else:
      print("[FAIL] Criterion 5: mixed_quality_article missing from report")

  print("=" * 70)
  print("PER-FIXTURE SUMMARY")
  print("=" * 70)
  for name, a in articles.items():
      print(f"  {name:30s} status={a['status']:8s} "
            f"timings.text_ingest={a['timings_ms'].get('text_ingest', 0)}ms "
            f"counters.images_kept={a['counters'].get('images_kept', 0)}/{a['counters'].get('images_input', 0)} "
            f"errors={len(a.get('errors', []))}")

  print("=" * 70)
  print(f"PROVIDER USAGE: {r.get('provider_usage', {})}")
  print(f"WALL TIME: {r['aggregate'].get('total_wall_time_s', 0)}s")
  print("=" * 70)
  PY
  ```

  This produces a Gate 3 evaluation printout that Task 4 will embed in the SUMMARY. Capture the output:

  ```bash
  python scripts/validate_regression_batch.py --help > /dev/null  # no-op to ensure script imports work
  python <above analysis block> > logs/gate3_analysis.txt
  cat logs/gate3_analysis.txt
  ```

  **Decision points for human review (in Task 4 SUMMARY):**
  - If any criterion FAILs with `images_kept > images_input` → fixture metadata is wrong; Plan 14-01 regeneration needed (block merge)
  - If `batch_pass=false` due to tolerance drift only (chunks/entities off by <±15%), document in SUMMARY as a tolerance-tuning TODO, not a hard fail
  - If Vision cascade attempts went all to Gemini (`provider_usage.gemini > 0.5 * total`), flag as upstream-provider alert per Phase 13 alerting semantics
  </action>
  <verify>
    <automated>test -f batch_validation_report.json && python -c "
import json
r = json.load(open('batch_validation_report.json'))
# At minimum verify the analysis script would not crash on the report
articles = {a['fixture']: a for a in r['articles']}
required_fixtures = {'gpt55_article','sparse_image_article','dense_image_article','text_only_article','mixed_quality_article'}
missing = required_fixtures - set(articles.keys())
assert not missing, f'Analysis input incomplete: missing {missing}'
# Verify each article has the counters structure needed for analysis
for name, a in articles.items():
    assert 'counters' in a and 'timings_ms' in a and 'errors' in a and 'status' in a, f'{name} missing analysis fields'
print(f'Report analyzable: {len(articles)} fixtures covered')
"</automated>
  </verify>
  <done>Gate 3 analysis completed; per-fixture PASS/FAIL disposition on each of the 5 sub-criteria is documented; pathological failures (wrong report shape, missing fixture, etc.) would have blocked at Task 2 — this task assumes shape is valid and focuses on SEMANTIC evaluation.</done>
</task>

<task type="auto">
  <name>Task 4: Write SUMMARY.md with Gate 3 disposition</name>
  <read_first>
    - batch_validation_report.json
    - logs/regression_run.log
    - logs/gate3_analysis.txt (from Task 3)
    - .planning/phases/14-regression-fixtures/14-CONTEXT.md
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §Acceptance Criteria Gate 3
  </read_first>
  <files>
    - .planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md
  </files>
  <action>
  Create the SUMMARY.md that closes Plan 14-03 and provides Gate 3 evidence for Milestone v3.2 roadmap sign-off. Embed findings from Task 3 analysis.

  Template structure:

  ```markdown
  # Phase 14 Plan 03 — E2E Regression Run SUMMARY

  **Date:** <YYYY-MM-DD>
  **Gate:** Milestone v3.2 Acceptance Criteria Gate 3 (Regression Fixtures Pass)
  **Report:** `batch_validation_report.json` (repo root)
  **Log:** `logs/regression_run.log`

  ## Disposition

  **Gate 3 status:** <PASS | PASS-WITH-NOTES | FAIL>

  <One-paragraph narrative: did we close Gate 3? What's the overall signal?>

  ## Per-fixture results

  | Fixture | Status | text_ingest (ms) | images (kept/input) | Errors | Notes |
  |---------|--------|------------------|---------------------|--------|-------|
  | gpt55_article | <PASS/FAIL/TIMEOUT> | <ms> | <k>/<i> | <count> | <notes> |
  | sparse_image_article | ... | ... | ... | ... | ... |
  | dense_image_article | ... | ... | ... | ... | ... |
  | text_only_article | ... | ... | 0/0 | ... | Vision skip verified |
  | mixed_quality_article | ... | ... | ... | ... | <2-3 corrupt images expected> |

  ## Gate 3 sub-criteria (MILESTONE_v3.2_REQUIREMENTS.md §Acceptance Criteria lines 412-416)

  | # | Criterion | Disposition | Evidence |
  |---|-----------|-------------|----------|
  | 1 | All 5 fixtures complete without exception | <PASS/FAIL> | <articles[].errors analysis> |
  | 2 | batch_pass: true | <PASS/FAIL> | aggregate.batch_pass=<value> |
  | 3 | dense_image_article filters correctly | <PASS/FAIL> | images_input=<i>, images_kept=<k>, filtered=<i-k> |
  | 4 | text_only_article skips Vision | <PASS/FAIL> | images_input=0, status=<status> |
  | 5 | mixed_quality handles JPEG+PNG | <PASS/FAIL> | decode_errors=<n>, non-decode errors=<m> |

  ## Vision cascade provider usage

  | Provider | Calls | Percentage |
  |----------|-------|------------|
  | siliconflow | <n> | <pct>% |
  | openrouter | <n> | <pct>% |
  | gemini | <n> | <pct>% |

  Total Vision attempts: <n>

  **Alerts:**
  - Gemini usage > 5%? <YES/NO> — <implication per Phase 13 alert rules>
  - Any provider circuit_open at end? <YES/NO> — <implication>

  ## Timing summary

  - Total wall time: <s> seconds
  - Slowest fixture: <fixture name> (<text_ingest_ms>ms text_ingest)
  - Fastest fixture: <fixture name> (<text_ingest_ms>ms text_ingest)

  ## Known limitations observed

  - <List any deviations, e.g., "entities counter always matches metadata (fallback heuristic from Plan 14-02 Task 2); instrumenting real LightRAG entity count deferred">
  - <List any tolerance drift that did not fail the gate but should be tracked>

  ## Recommendations for Milestone v3.2 close

  - <Can Gate 3 be checked off? Any blockers for closing the milestone?>
  - <Any fixture regeneration needed? Any Phase 12/13 bugs surfaced?>
  - <Next actions (Phase 15 runbook documentation, Phase 16 Vertex AI spec)>

  ## Files modified

  - batch_validation_report.json (new or updated)
  - logs/regression_run.log (new)
  - logs/gate3_analysis.txt (new)
  - .planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md (this file)

  ---

  *Plan 14-03 complete. Generated by /gsd:execute-phase 14-regression-fixtures.*
  ```

  Fill in every `<placeholder>` from actual data in `batch_validation_report.json` + `logs/gate3_analysis.txt`. Do NOT leave any `<>` marker unexpanded in the final SUMMARY.

  After writing:
  ```bash
  # Validate SUMMARY.md has no unexpanded placeholders
  grep -c "<[A-Za-z/ -]*>" .planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md || echo "No unexpanded placeholders"
  # Expected count: 0 or very low; any matches indicate incomplete fill-in
  ```

  If Gate 3 is FAIL:
  - Do NOT mark this plan as "PASS" — write `Gate 3 status: FAIL` honestly
  - Provide specific remediation path (which fixture failed, which Phase needs a bug fix)
  - Roadmap Phase 14 does NOT close — Phase 15/16 can proceed in parallel but milestone close is blocked

  If Gate 3 is PASS-WITH-NOTES:
  - Valid status when batch_pass=true but one or more sub-criteria have yellow flags (e.g., Gemini usage 6%, tolerance drift within ±15%)
  - Document notes explicitly in "Known limitations observed" section
  - Gate 3 can still close; limitations become TODOs for future milestones
  </action>
  <verify>
    <automated>
test -f .planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md && \
python -c "
from pathlib import Path
content = Path('.planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md').read_text(encoding='utf-8')
# Must have all 5 fixture names
for f in ['gpt55_article','sparse_image_article','dense_image_article','text_only_article','mixed_quality_article']:
    assert f in content, f'SUMMARY missing fixture: {f}'
# Must have Gate 3 status line
assert 'Gate 3 status' in content, 'SUMMARY missing Gate 3 status line'
# Must reference the report file
assert 'batch_validation_report.json' in content, 'SUMMARY missing report reference'
# Must have all 5 sub-criteria
for c in ['exception','batch_pass','dense_image','text_only','mixed_quality']:
    assert c in content.lower(), f'SUMMARY missing sub-criterion keyword: {c}'
print('SUMMARY.md structural validation PASS')
print(f'Length: {len(content)} chars')
"
    </automated>
  </verify>
  <done>`.planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md` exists with: Gate 3 disposition (PASS / PASS-WITH-NOTES / FAIL), per-fixture table, 5 sub-criteria dispositions, provider usage, timing summary, known limitations, recommendations. No unexpanded placeholders.</done>
</task>

</tasks>

<verification>
Final Phase 14 acceptance gate (run after all 3 plans complete):

```bash
# 1. Report artifact exists and matches schema
test -f batch_validation_report.json && \
python -c "
import json
r = json.load(open('batch_validation_report.json'))
assert set(r.keys()) >= {'batch_id','timestamp','articles','aggregate','provider_usage'}
assert r['aggregate']['total_articles'] == 5
print('Schema OK')
"

# 2. SUMMARY.md exists with Gate 3 disposition
test -f .planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md && \
grep -q "Gate 3 status" .planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md

# 3. All 5 fixtures referenced
grep -q "gpt55_article" batch_validation_report.json && \
grep -q "sparse_image_article" batch_validation_report.json && \
grep -q "dense_image_article" batch_validation_report.json && \
grep -q "text_only_article" batch_validation_report.json && \
grep -q "mixed_quality_article" batch_validation_report.json

# 4. Exit code semantics of validate script are consistent with report
python scripts/validate_regression_batch.py --fixtures test/fixtures/gpt55_article --output /tmp/cross_check.json; \
EC=$?; \
python -c "
import json
r = json.load(open('/tmp/cross_check.json'))
assert (r['aggregate']['batch_pass'] is True and $EC == 0) or (r['aggregate']['batch_pass'] is False and $EC == 1), 'Exit code / batch_pass mismatch'
print('Exit code contract: OK')
"
```

All 4 checks must pass for Phase 14 to close.
</verification>

<success_criteria>
- [ ] Preconditions verified (Phase 12 + 13 merged, 5 fixtures exist, Plan 14-02 script works)
- [ ] `batch_validation_report.json` emitted at repo root matching PRD §B3.4 schema
- [ ] All 5 fixtures present in report with valid status (PASS/FAIL/TIMEOUT)
- [ ] No Python traceback in `logs/regression_run.log` (unhandled exceptions = Criterion 1 FAIL)
- [ ] `text_only_article` has `images_input=0` and status != FAIL (Vision skip verified)
- [ ] `dense_image_article` has `images_kept < images_input` (IMG-01 filter active)
- [ ] `mixed_quality_article` gracefully handles corrupted images (no unhandled decode errors)
- [ ] Gate 3 disposition documented in SUMMARY.md (PASS / PASS-WITH-NOTES / FAIL)
- [ ] Exit code of validate script matches aggregate.batch_pass (0 iff true)
</success_criteria>

<output>
After completion, `.planning/phases/14-regression-fixtures/14-03-e2e-validation-run-SUMMARY.md` is the canonical Gate 3 evidence document. Reference from ROADMAP.md Phase 14 entry when marking the phase done.
</output>

---
phase: quick-260511-utl
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/bench_merge_speed.py
  - scripts/capture_qr.py
  - scripts/time_single_ingest.py
  - scripts/export_vitaclaw_agent_news.py
  - tests/unit/test_graded_classify.py
  - tests/unit/test_export_vitaclaw_agent_news.py
  - tests/fixtures/wave0_baseline.json
autonomous: true
requirements:
  - UTL-01  # Pull 4 Hermes-authored utility scripts byte-for-byte into scripts/
  - UTL-02  # Pull 2 Hermes-authored unit tests + 1 fixture byte-for-byte into tests/
  - UTL-03  # Repair test_graded_classify.py 5-spot indent bug (8sp -> 4sp on `with patch(...)` lines)
  - UTL-04  # SSH-rm 8 DEAD WIP files on Hermes (kol_scan.db, .env.bak*, .env.pre-delete.bak*, test_filter_prompt.py, test_prefilter_30.py, batch_validation_report.json, data/kol_scan_spec.md, graphify-out/)

must_haves:
  truths:
    - "All 4 utility scripts committed to local repo with sha256 matching Hermes"
    - "tests/unit/test_export_vitaclaw_agent_news.py + tests/fixtures/wave0_baseline.json committed with sha256 matching Hermes"
    - "tests/unit/test_graded_classify.py committed with 5-spot indent repair (only delta vs Hermes byte content); pytest 6/6 GREEN"
    - "All 8 DEAD files removed from ~/OmniGraph-Vault on Hermes; SSH `git status -sb` post-cleanup shows no `??` line for any of them"
    - "Single atomic commit feat(scripts-260511-utl) hits main with explicit `git add` (no -A, no .)"
---

<objective>
Formalize the 4 utility scripts + 2 unit tests + 1 fixture that Hermes E (production) authored on the home dev/prod box during recent quicks, but never committed. Single byte-for-byte sweep, single atomic feat commit. In parallel: clean up 8 DEAD WIP files lingering on Hermes via SSH `rm` (untracked -> no repo commit needed; recorded in STATE.md instead).

Phase 0 evidence:
- All 7 TRACK files: sha256 match between local pulled copy and Hermes (`.scratch/g3-pull-track-260511-173748.log`, `.scratch/g3-phase0-track-verify-260511-173748.log`).
- All 8 DEAD candidates verified safe: kol_scan.db = 0 bytes; .env.bak* / .env.pre-delete.bak* = 161 bytes each; test_filter_prompt.py / test_prefilter_30.py confirmed plain scratchpads (no @pytest decorators, just `if __name__` style); graphify-out/ = 8.7MB throwaway artifacts; data/kol_scan_spec.md is the historical spec the audit marked DEAD (`.scratch/g3-phase0-dead-verify-260511-173748.log`).

Phase 0 finding: tests/unit/test_graded_classify.py has a 5-spot indent error (lines 79, 109, 137, 159, 177) — every `with patch(...) as mock_session:` is at 8sp instead of 4sp. Same content on Hermes (sha matches). User approved a 1-pattern repair (`replace_all` 8sp -> 4sp) before commit. Post-fix: pytest 8/8 GREEN.
</objective>

<plan>
1. Phase 0 (DONE): SSH ls + size + head verify all 7 TRACK + 8 DEAD candidates -> sha256 byte-equal across local/remote
2. Phase 0 finding (DONE): test_graded_classify.py IndentationError on 5 `with patch(...)` lines -> user-approved 1-pattern indent repair -> pytest 6/6 GREEN
3. Verification (DONE): pytest 8 passed; ast.parse 4/4 OK on utility scripts
4. Commit 1: explicit `git add` of 7 paths + planning artifacts -> feat(scripts-260511-utl)
5. SSH rm 8 DEAD paths on Hermes -> verify `git status -sb` clean
6. STATE.md row -> push with `git fetch && git rebase --autostash` guard
</plan>

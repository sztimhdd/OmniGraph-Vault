---
phase: 12-checkpoint-resume
plan: 01
status: complete
completed: 2026-05-01
key-files:
  created:
    - scripts/checkpoint_reset.py
    - scripts/checkpoint_status.py
    - tests/unit/test_checkpoint_cli.py
  modified:
    - lib/checkpoint.py
---

## What was built

Two operator CLIs + integration tests, plus a 4-line test seam on lib/checkpoint.py.

**scripts/checkpoint_reset.py** (72 lines):
- `--hash {hash}` → removes that article's checkpoint dir (exit 0 on success, 1 on missing)
- `--all` → guard-clause refusal, exit 2 with operator-facing hint (CLAUDE.md destructive-action rule)
- `--all --confirm` → removes entire `checkpoints/` root, exit 0
- `argparse.mutually_exclusive_group(required=True)` prevents ambiguous invocations

**scripts/checkpoint_status.py** (76 lines):
- Default: Markdown-style pipe table with header line + age formatter + URL truncation
- `--tsv` machine-parsable mode with exact header `hash\turl\ttitle\tlast_stage\tage_seconds\tstatus`
- Empty-state safe (prints `0 total` + null-result explanation)

**tests/unit/test_checkpoint_cli.py** (8 subprocess tests):
- `--all` without `--confirm` → exit 2, stderr contains "--confirm"
- `--all --confirm` on seeded state → wipes everything
- `--hash` missing → exit 1; `--hash` present → exit 0 and dir gone
- No-args → non-zero exit (argparse mutex required)
- Status empty → `0 total`; mixed states → both hashes in output + `complete` + `in_flight` visible
- TSV mode → exact header line

**lib/checkpoint.py** (test seam, 4 lines): After `BASE_DIR = _CONFIG_BASE_DIR`, reads `OMNIGRAPH_CHECKPOINT_BASE_DIR` env var and overrides if set. Test-only — production never sets this.

## Acceptance criteria

All 11 grep/exit-code checks pass:
- Both scripts have `def main`, `--hash`/`--all`/`--confirm` flags, `from lib.checkpoint import` line
- CLI test file has 8 `def test_` functions
- `OMNIGRAPH_CHECKPOINT_BASE_DIR` env seam present in both lib/checkpoint.py and tests
- Full test matrix green: `pytest tests/unit/test_checkpoint{,_cli}.py` = 40/40 passed

## Deviations

Used `ckpt.BASE_DIR / "checkpoints" / hash` path probe in checkpoint_reset.py's `--hash` missing check, instead of `get_checkpoint_dir()` (which has a mkdir side-effect that would create an empty dir before we check for content). This matches the plan's "Note on empty dir side effect" guidance preferring the cleaner path-probe approach.

## Notes

Guard-clause demo:
```
$ python scripts/checkpoint_reset.py --all
ERROR --all refused: destructive operation requires --confirm. Re-run: python scripts/checkpoint_reset.py --all --confirm
$ echo $?
2
```

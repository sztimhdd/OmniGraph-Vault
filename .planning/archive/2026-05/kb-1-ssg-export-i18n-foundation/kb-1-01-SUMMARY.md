---
phase: kb-1-ssg-export-i18n-foundation
plan: "01"
subsystem: kb
tags: [kb-v2, config, scaffold, env-driven, CONFIG-01]
dependency-graph:
  requires: []
  provides:
    - "kb namespace package importable"
    - "kb.config — env-driven constants (KB_DB_PATH, KB_IMAGES_DIR, KB_OUTPUT_DIR, KB_PORT, KB_DEFAULT_LANG, KB_SYNTHESIZE_TIMEOUT)"
    - "kb/output/ gitignored except per-dir .gitignore"
    - "kb subpackage skeleton: data, scripts, locale, templates, static"
  affects:
    - "Every other kb-1 plan (and kb-3, kb-4) imports kb.config for paths and ports"
tech-stack:
  added: []
  patterns:
    - "env-driven config with empty-string-as-unset semantics (mirrors main config.py BASE_DIR)"
    - "module-level constants + importlib.reload for test override"
    - "TDD RED → GREEN with pytest monkeypatch + reload pattern"
key-files:
  created:
    - "kb/__init__.py"
    - "kb/config.py"
    - "kb/data/__init__.py"
    - "kb/scripts/__init__.py"
    - "kb/locale/__init__.py"
    - "kb/templates/__init__.py"
    - "kb/static/.gitkeep"
    - "kb/output/.gitignore"
    - "tests/unit/kb/__init__.py"
    - "tests/unit/kb/test_config.py"
  modified:
    - ".gitignore"
decisions:
  - "Use module-level constants (not getter functions) for KB_* — callers reload kb.config to honor late env changes. Rationale: every consumer reads paths once at startup; a function-call API would force `get_db_path()` everywhere with no real benefit. Tests use importlib.reload."
  - "Convert root .gitignore line `kb/output/` (whole-dir) to `kb/output/*` + `!kb/output/.gitignore` to allow tracking the per-dir gitignore. Same fix pattern already used by `credentials/*` block in the same file."
metrics:
  duration: "~3 min"
  completed: "2026-05-12"
  tests-added: 8
  tests-passing: 8
  files-created: 10
  files-modified: 1
requirements: [CONFIG-01]
---

# Phase kb-1 Plan 01: kb Package Skeleton + Env-Driven Config Summary

Bootstrapped the `kb/` Python package and `kb.config` module — every downstream kb-1/kb-3/kb-4 plan now has a single source of truth for paths and ports via env-overridable constants, plus a clean namespace package layout under `kb/`.

## What Shipped

**`kb/config.py` — 6 env-driven constants:**

| Constant | Default | Env override |
| --- | --- | --- |
| `KB_DB_PATH` | `~/.hermes/data/kol_scan.db` | `KB_DB_PATH` |
| `KB_IMAGES_DIR` | `~/.hermes/omonigraph-vault/images` | `KB_IMAGES_DIR` |
| `KB_OUTPUT_DIR` | `kb/output` | `KB_OUTPUT_DIR` |
| `KB_PORT` | `8766` (int) | `KB_PORT` |
| `KB_DEFAULT_LANG` | `zh-CN` | `KB_DEFAULT_LANG` |
| `KB_SYNTHESIZE_TIMEOUT` | `60` (int) | `KB_SYNTHESIZE_TIMEOUT` |

Helpers `_env_path()` / `_env_int()` handle empty-string-as-unset semantics, mirroring the main `config.py` `BASE_DIR` override pattern. Non-numeric `KB_PORT` / `KB_SYNTHESIZE_TIMEOUT` falls back to default rather than raising. The `omonigraph-vault` typo is preserved per `CLAUDE.md` (canonical, not a bug).

**Namespace package skeleton:**

- `kb/__init__.py` — package docstring
- `kb/data/__init__.py` — data layer placeholder (kb-1-02 will populate)
- `kb/scripts/__init__.py` — CLI scripts placeholder
- `kb/locale/__init__.py` — empty (subdir holds JSON)
- `kb/templates/__init__.py` — empty (subdir holds Jinja2)
- `kb/static/.gitkeep` — preserves directory in git for assets

**Build-output gitignore:**

- `kb/output/.gitignore` ignores all SSG build artifacts but keeps itself trackable
- Root `.gitignore` updated from `kb/output/` (whole-dir form) to `kb/output/*` + `!kb/output/.gitignore` so the per-dir gitignore can be tracked. Same idiom already used for the existing `credentials/*` + `!credentials/vertex_ai_service_account_example.json` block.

## Tests

**8 unit tests, 8 passing** (`tests/unit/kb/test_config.py`):

1. `test_kb_db_path_default` — default matches docs
2. `test_kb_db_path_env_override` — `KB_DB_PATH` env honored
3. `test_kb_images_dir_default` — `omonigraph` typo preserved
4. `test_kb_output_dir_default` — repo-relative `kb/output`
5. `test_kb_port_default_and_env_override` — int default + int override
6. `test_kb_default_lang_default` — `zh-CN`
7. `test_kb_synthesize_timeout_default` — `60` (int)
8. `test_all_constants_re_read_env_on_reload` — `importlib.reload(kb.config)` re-reads all 6 env vars

Pattern: pytest `monkeypatch` to set env, `importlib.reload(kb.config)` to recompute constants, assert.

## Verification Evidence

- **Smoke import:** `python -c "from kb import config; print(config.KB_DB_PATH, config.KB_PORT, config.KB_DEFAULT_LANG)"` → `C:\Users\huxxha\.hermes\data\kol_scan.db 8766 zh-CN`
- **Env override smoke:** `KB_PORT=9999 python -c "import importlib; from kb import config; importlib.reload(config); assert config.KB_PORT == 9999"` → exit 0
- **Subpackage import:** `python -c "import kb; import kb.data; import kb.scripts"` → `OK`
- **CONFIG-01 grep enforcement:** `grep -rE "/.hermes|kol_scan\.db" kb/ --include='*.py' --exclude=config.py` → exit 1 (no hits — clean)
- **gitignore behavior:** `git check-ignore kb/output/anything.html` → matched by `kb/output/.gitignore:2:*`; `kb/output/.gitignore` itself remains trackable.
- **All 6 namespace files exist:** verified via `ls kb/__init__.py kb/data/__init__.py kb/scripts/__init__.py kb/locale/__init__.py kb/templates/__init__.py kb/static/.gitkeep`

## Commits

| Commit | Type | Description |
| --- | --- | --- |
| `af763cc` | test | add failing tests for kb.config env-driven constants (TDD RED) |
| `0da423f` | feat | implement kb.config env-driven constants (TDD GREEN, 8/8 pass) |
| `6ca1b3f` | feat | create kb subpackage skeleton (data, scripts, locale, templates, static) |
| `919fed0` | chore | gitignore kb/output/ contents but track per-dir .gitignore |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking issue] Root `.gitignore` already had `kb/output/` (whole-dir form) — converted to `kb/output/*` + negation pattern**

- **Found during:** Task 3
- **Issue:** Plan said append a new block `kb/output/*` + `!kb/output/.gitignore`. But root `.gitignore` line 56 already had `kb/output/` (whole-dir form). The whole-dir form prevents tracking ANY file inside `kb/output/`, including the per-dir `.gitignore` the plan wants tracked. Naively appending the new block would have left both forms in the file (redundant + still wouldn't allow the per-dir gitignore to be tracked because the whole-dir form blocks it).
- **Fix:** Surgical edit — converted the existing line `kb/output/` to `kb/output/*` + `!kb/output/.gitignore`. Net change: 1 line replaced with 6 lines (added the comment block explaining why the contents-form is needed, mirroring the existing `credentials/*` block 5 lines below).
- **Why this is the right call:** Project's existing `credentials/*` + `!credentials/vertex_ai_service_account_example.json` block at lines 58-63 is the canonical idiom for "exclude directory contents but track a specific file in the directory". Naive append would have duplicated the original whole-dir entry which still blocks tracking the per-dir gitignore.
- **Files modified:** `.gitignore`
- **Commit:** `919fed0`

### Note on Task 1 / Task 2 file split

The plan listed `kb/__init__.py` under Task 2's files. It was committed in Task 1's TDD-GREEN commit (`0da423f`) instead, because pytest needs `kb` to be importable as a package before `kb.config` can be reloaded by the tests. Task 2's commit (`6ca1b3f`) covers the remaining 5 files. Both commits explicitly document this. Net result is identical to plan; only the per-task file boundary shifted by one file.

## Acceptance Criteria — All Met

- [x] `kb/config.py` exists, imports without error
- [x] `python -c "from kb import config; assert config.KB_PORT == 8766"` exits 0
- [x] `KB_PORT=9999 python -c "..."` exits 0 (env override works after reload)
- [x] `pytest tests/unit/kb/test_config.py -v` exits 0, 8/8 pass
- [x] `kb/config.py` contains literal `omonigraph` (typo preserved)
- [x] All 6 namespace skeleton files exist (`kb/__init__.py` + 4 subpackage `__init__.py` + `kb/static/.gitkeep`)
- [x] `python -c "import kb; import kb.data; import kb.scripts"` exits 0
- [x] `kb/output/.gitignore` exists with `*` + `!.gitignore`
- [x] Root `.gitignore` references `kb/output/*` + `!kb/output/.gitignore`
- [x] Root `.gitignore` net line growth ≥ 3 (actual: +5)
- [x] `grep -rE "/.hermes|kol_scan\.db" kb/ --include='*.py' --exclude=config.py` returns 0 hits — CONFIG-01 enforcement clean
- [x] `git check-ignore kb/output/anything.html` matches the per-dir `.gitignore`

## Self-Check: PASSED

- File `kb/config.py` exists: FOUND
- File `kb/__init__.py` exists: FOUND
- File `kb/data/__init__.py` exists: FOUND
- File `kb/scripts/__init__.py` exists: FOUND
- File `kb/locale/__init__.py` exists: FOUND
- File `kb/templates/__init__.py` exists: FOUND
- File `kb/static/.gitkeep` exists: FOUND
- File `kb/output/.gitignore` exists: FOUND
- File `tests/unit/kb/__init__.py` exists: FOUND
- File `tests/unit/kb/test_config.py` exists: FOUND
- Commit `af763cc` (test RED): FOUND
- Commit `0da423f` (feat GREEN): FOUND
- Commit `6ca1b3f` (feat skeleton): FOUND
- Commit `919fed0` (chore gitignore): FOUND

---
phase: kb-1-ssg-export-i18n-foundation
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/__init__.py
  - kb/config.py
  - kb/data/__init__.py
  - kb/scripts/__init__.py
  - kb/locale/__init__.py
  - kb/templates/__init__.py
  - kb/static/.gitkeep
  - kb/output/.gitignore
  - .gitignore
autonomous: true
requirements:
  - CONFIG-01

must_haves:
  truths:
    - "kb package importable with `from kb import config`"
    - "All 6 env-var-overridable paths/ports are read in kb/config.py"
    - "Defaults match the values documented in CONTEXT.md / REQUIREMENTS-KB-v2.md"
    - "Re-running export does not pollute git via kb/output/ artifacts (gitignored)"
  artifacts:
    - path: "kb/config.py"
      provides: "Env-driven configuration constants"
      contains: "KB_DB_PATH, KB_IMAGES_DIR, KB_OUTPUT_DIR, KB_PORT, KB_DEFAULT_LANG, KB_SYNTHESIZE_TIMEOUT"
    - path: "kb/__init__.py"
      provides: "kb namespace package"
    - path: "kb/data/__init__.py"
      provides: "kb.data subpackage"
    - path: "kb/output/.gitignore"
      provides: "ignores all SSG build output"
  key_links:
    - from: "all kb modules"
      to: "kb.config"
      via: "from kb import config"
      pattern: "from kb import config|from kb.config import"
---

<objective>
Bootstrap the `kb/` Python package skeleton + env-driven configuration. Every other plan in this phase imports `kb.config` for paths and env values; this plan must land first.

Purpose: One source-of-truth for paths and ports. Per CONFIG-01, no hardcoded paths anywhere else in `kb/` — verified post-build via grep. Per K-1 (KB-v2 locked decision), env-driven config makes the future Databricks Apps migration cheap.

Output: `kb/config.py` with 6 env-readable constants + 4 empty `__init__.py` files + `.gitignore` for `kb/output/`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@config.py
@CLAUDE.md

<interfaces>
Pattern to mirror — main project's `config.py` (read it before writing kb/config.py):

```python
# config.py (existing, top of file):
import os
from pathlib import Path

BASE_DIR = (
    Path(os.environ["OMNIGRAPH_BASE_DIR"])
    if os.environ.get("OMNIGRAPH_BASE_DIR")
    else Path.home() / ".hermes" / "omonigraph-vault"
)
RAG_WORKING_DIR = Path(os.environ["RAG_WORKING_DIR"]) \
    if os.environ.get("RAG_WORKING_DIR") \
    else BASE_DIR / "lightrag_storage"
```

Note the typo `omonigraph-vault` is canonical — DO NOT "fix" it.

The `kb/config.py` must NOT call `load_env()` from main config.py (avoids duplicate `~/.hermes/.env` parsing). Instead, kb/config.py reads its env vars directly via `os.environ.get(...)`. If user has env in `~/.hermes/.env`, the OmniGraph entry-point that imports `config` (main) will have already loaded those env vars before `kb` is imported.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write kb/config.py with all 6 env-overridable constants + frozen tests</name>
  <read_first>
    - config.py (root project config — pattern to mirror, especially BASE_DIR env override)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md § "Configuration (CONFIG-01)" — defaults table
    - .planning/REQUIREMENTS-KB-v2.md § CONFIG — exact REQ text for CONFIG-01
    - kb/docs/02-DECISIONS.md § K-1 — env-driven config rationale
  </read_first>
  <files>kb/config.py, tests/unit/kb/__init__.py, tests/unit/kb/test_config.py</files>
  <behavior>
    - Test 1: `kb.config.KB_DB_PATH` defaults to `Path.home() / ".hermes" / "data" / "kol_scan.db"` when env unset
    - Test 2: `KB_DB_PATH` honors `os.environ["KB_DB_PATH"]` override (use monkeypatch)
    - Test 3: `KB_IMAGES_DIR` defaults to `Path.home() / ".hermes" / "omonigraph-vault" / "images"` (note `omonigraph` typo — canonical, do not fix)
    - Test 4: `KB_OUTPUT_DIR` defaults to repo-root-relative `Path("kb/output")`
    - Test 5: `KB_PORT` defaults to int `8766`; `KB_PORT="9999"` env override yields int `9999`
    - Test 6: `KB_DEFAULT_LANG` defaults to `"zh-CN"`
    - Test 7: `KB_SYNTHESIZE_TIMEOUT` defaults to int `60`
    - Test 8: All 6 constants re-read env vars on `importlib.reload(kb.config)` — confirms no module-load-time caching that would prevent env override after import
  </behavior>
  <action>
    Create `kb/config.py` with this exact content (modify only paths if env-default needs adjustment):

    ```python
    """KB-v2 env-driven configuration — single source of truth for paths and ports.

    CONFIG-01: All KB paths and ports configurable via env vars with documented
    defaults. NO hardcoded paths anywhere else in kb/. Verified by:
        grep -rE "/.hermes|kol_scan.db" kb/ --include='*.py' --exclude=config.py
    must return 0 hits in kb/ (matches in tests/ are OK).
    """
    from __future__ import annotations

    import os
    from pathlib import Path


    def _env_path(key: str, default: Path) -> Path:
        """Read env var as Path; empty string treated as unset (mirrors main config.py)."""
        val = os.environ.get(key)
        return Path(val) if val else default


    def _env_int(key: str, default: int) -> int:
        """Read env var as int; non-numeric falls back to default."""
        val = os.environ.get(key)
        if not val:
            return default
        try:
            return int(val)
        except ValueError:
            return default


    # Lazy reads so monkeypatched env vars in tests are honored. Functions, not
    # constants, would force callers to call `get_db_path()` everywhere; instead,
    # we expose constants computed at module-import time. To support test
    # override, callers can importlib.reload(kb.config).
    KB_DB_PATH: Path = _env_path("KB_DB_PATH", Path.home() / ".hermes" / "data" / "kol_scan.db")
    KB_IMAGES_DIR: Path = _env_path(
        "KB_IMAGES_DIR",
        Path.home() / ".hermes" / "omonigraph-vault" / "images",  # 'omonigraph' typo is canonical
    )
    KB_OUTPUT_DIR: Path = _env_path("KB_OUTPUT_DIR", Path("kb/output"))
    KB_PORT: int = _env_int("KB_PORT", 8766)
    KB_DEFAULT_LANG: str = os.environ.get("KB_DEFAULT_LANG", "zh-CN")
    KB_SYNTHESIZE_TIMEOUT: int = _env_int("KB_SYNTHESIZE_TIMEOUT", 60)
    ```

    Then create tests at `tests/unit/kb/test_config.py` with `pytest.MonkeyPatch` and `importlib.reload(kb.config)` to exercise all 8 behaviors above. Use `from __future__ import annotations` and PEP-8 / type hints per `.claude/rules/python/coding-style.md`.

    Use `print()` is OK in CLI scripts but `kb/config.py` is library — no print, no logging needed (read-only constants).
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "from kb import config; print(config.KB_DB_PATH, config.KB_PORT, config.KB_DEFAULT_LANG)" &amp;&amp; pytest tests/unit/kb/test_config.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File `kb/config.py` exists and imports without error
    - `python -c "from kb import config; assert config.KB_PORT == 8766"` exits 0
    - `KB_PORT=9999 python -c "import importlib; from kb import config; importlib.reload(config); assert config.KB_PORT == 9999"` exits 0
    - `pytest tests/unit/kb/test_config.py -v` exits 0 with 8 tests passing
    - `grep -E "/.hermes|kol_scan.db" kb/config.py` returns the default-defining lines (expected); same grep on any other kb/ file returns 0 hits (verified in Task 3)
    - File contains the literal string `omonigraph` (typo preserved per CLAUDE.md)
  </acceptance_criteria>
  <done>kb/config.py with 6 constants, all env-overridable, all 8 tests pass.</done>
</task>

<task type="auto">
  <name>Task 2: Create namespace package skeleton (kb/__init__.py + 4 subpackage __init__.py + static/.gitkeep)</name>
  <read_first>
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md § "Module / file layout"
  </read_first>
  <files>kb/__init__.py, kb/data/__init__.py, kb/scripts/__init__.py, kb/locale/__init__.py, kb/templates/__init__.py, kb/static/.gitkeep</files>
  <action>
    Create six files, each empty except as noted:

    1. `kb/__init__.py` — content: `"""KB-v2: Bilingual Agent-tech content site SSG + API."""`
    2. `kb/data/__init__.py` — content: `"""kb.data: Data layer (article queries, lang detection)."""`
    3. `kb/scripts/__init__.py` — content: `"""kb.scripts: One-shot CLI scripts (migrations, lang detect)."""`
    4. `kb/locale/__init__.py` — content: empty (subdirectory holds JSON files only; __init__.py prevents pytest's rootdir from picking it as a test package)
    5. `kb/templates/__init__.py` — content: empty (Jinja2 templates dir; __init__.py for consistency)
    6. `kb/static/.gitkeep` — content: empty (preserves directory in git for assets that get added by templates plan)

    Use the Write tool for all six files. Do NOT create `kb/output/` — that is a build output directory; the .gitignore in Task 3 prevents it from being tracked.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "import kb; import kb.data; import kb.scripts; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - All 6 files exist (Bash: `ls kb/__init__.py kb/data/__init__.py kb/scripts/__init__.py kb/locale/__init__.py kb/templates/__init__.py kb/static/.gitkeep`)
    - `python -c "import kb; import kb.data; import kb.scripts"` exits 0
    - `kb/__init__.py` and `kb/data/__init__.py` and `kb/scripts/__init__.py` each contain a module-level docstring
  </acceptance_criteria>
  <done>kb/ package importable, all subpackages established.</done>
</task>

<task type="auto">
  <name>Task 3: Add .gitignore entries for kb/output/ + verify CONFIG-01 enforcement</name>
  <read_first>
    - .gitignore (root — read existing entries before adding)
    - .planning/REQUIREMENTS-KB-v2.md § CONFIG-01 (verification grep pattern)
  </read_first>
  <files>kb/output/.gitignore, .gitignore</files>
  <action>
    Step 1: Create `kb/output/.gitignore` with content:

    ```
    # SSG build output — never tracked
    *
    !.gitignore
    ```

    This makes the directory exist in git (the .gitignore file itself is tracked) but prevents any build artifacts (HTML, sitemap.xml, _url_index.json) from being committed.

    Step 2: Read existing root `.gitignore`. If it does not already contain `kb/output/`, append the following block at the end (preserve existing content untouched per Surgical Changes principle):

    ```
    # KB-v2 SSG build output (kb-1)
    kb/output/*
    !kb/output/.gitignore
    ```

    REVISION 1 / Issue #5: the previously-listed `kb/output/_url_index.json` line was redundant — `kb/output/*` already excludes it. Removed for simplicity (Simplicity First per CLAUDE.md); the per-directory `kb/output/.gitignore` from Step 1 provides defense-in-depth without needing a duplicate line in the root.

    Use Edit tool, not Write, to preserve all existing .gitignore entries.

    Step 3: Verify CONFIG-01 enforcement — run the grep pattern from CONTEXT.md after Task 1 + Task 2 land. There should be 0 hardcoded path hits OUTSIDE of `kb/config.py`. The grep itself is part of acceptance_criteria below.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; cat kb/output/.gitignore &amp;&amp; grep -E "kb/output" .gitignore</automated>
  </verify>
  <acceptance_criteria>
    - `kb/output/.gitignore` exists and contains `*` and `!.gitignore`
    - Root `.gitignore` contains `kb/output/*` line
    - Root `.gitignore` line count INCREASED by ≥ 3 lines (new block added, nothing removed) compared to pre-edit count
    - Pattern check: `grep -rE "/.hermes|kol_scan\.db" kb/ --include='*.py'` lists ONLY lines from `kb/config.py` (no other kb/ source file may hardcode these paths) — this is the CONFIG-01 enforcement spot-check before any other plan adds files
    - `git check-ignore kb/output/anything.html` exits 0 (path is ignored)
  </acceptance_criteria>
  <done>kb/output/ ignored by git, .gitignore preserves all prior entries, CONFIG-01 grep clean.</done>
</task>

</tasks>

<verification>
- All 3 tasks pass their automated checks
- `pytest tests/unit/kb/test_config.py` exits 0
- Importing `from kb import config` works
- CONFIG-01 grep enforcement: zero hardcoded paths outside kb/config.py
</verification>

<success_criteria>
- `kb/config.py` exposes 6 constants, all env-overridable, all matching documented defaults
- `kb/` package + 4 subpackages importable without error
- `kb/output/` directory established and gitignored
- 8 unit tests for config pass
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-01-SUMMARY.md` documenting:
- Files created (count + list)
- Test count + pass status
- CONFIG-01 grep enforcement result
- Any deviations from plan (with reason)
</output>

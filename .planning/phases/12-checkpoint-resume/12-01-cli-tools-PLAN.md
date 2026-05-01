---
phase: 12-checkpoint-resume
plan: 01
type: execute
wave: 2
depends_on:
  - "12-00"
files_modified:
  - scripts/checkpoint_reset.py
  - scripts/checkpoint_status.py
  - tests/unit/test_checkpoint_cli.py
autonomous: true
requirements:
  - CKPT-05
user_setup: []

must_haves:
  truths:
    - "`python scripts/checkpoint_reset.py --hash {hash}` removes exactly that article's checkpoint dir"
    - "`python scripts/checkpoint_reset.py --all` fails WITHOUT --confirm (exit non-zero, clear message)"
    - "`python scripts/checkpoint_reset.py --all --confirm` removes the entire checkpoints/ root"
    - "`python scripts/checkpoint_status.py` prints a table of all in-flight and complete checkpoints"
    - "Scripts exit 0 on success, non-zero on guard-clause refusal or missing hash"
  artifacts:
    - path: "scripts/checkpoint_reset.py"
      provides: "argparse CLI with --hash and --all --confirm; guard-clause on --all"
      contains: "def main"
      min_lines: 50
    - path: "scripts/checkpoint_status.py"
      provides: "argparse CLI printing Markdown-style table of list_checkpoints() output"
      contains: "def main"
      min_lines: 40
    - path: "tests/unit/test_checkpoint_cli.py"
      provides: "subprocess invocation tests for both CLIs (exit codes + stdout smoke)"
      min_lines: 80
  key_links:
    - from: "scripts/checkpoint_reset.py"
      to: "lib.checkpoint.reset_article / reset_all"
      via: "direct import"
      pattern: "from lib.checkpoint import"
    - from: "scripts/checkpoint_status.py"
      to: "lib.checkpoint.list_checkpoints"
      via: "direct import"
      pattern: "from lib.checkpoint import"
---

<objective>
Deliver the two operator-facing CLIs specified in CKPT-05: `checkpoint_reset.py` (destructive; requires --confirm for --all) and `checkpoint_status.py` (read-only; prints table). These are the ONLY operator interfaces to the checkpoint system — every other interaction is programmatic through `lib.checkpoint`.

Purpose: Gate-1 acceptance requires operator can reset per-hash AND do a full batch wipe. CLAUDE.md mandates guard clauses before destructive actions — `--all` refuses without explicit `--confirm`.

Output: 2 scripts in `scripts/`, 1 test module.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/12-checkpoint-resume/12-CONTEXT.md
@.planning/phases/12-checkpoint-resume/12-00-SUMMARY.md
@lib/checkpoint.py
@scripts/bench_ingest_fixture.py

<interfaces>
From lib/checkpoint.py (delivered by Plan 12-00):
```python
def get_checkpoint_dir(article_hash: str) -> Path: ...
def reset_article(article_hash: str) -> None: ...
def reset_all() -> None: ...
def list_checkpoints() -> list[dict]: ...
    # Record: {hash, url, title, last_stage, age_seconds, status: "complete"|"in_flight"}
```

Script conventions (from existing `scripts/bench_ingest_fixture.py` and similar):
- Shebang: `#!/usr/bin/env python3`
- `argparse.ArgumentParser` with `description=__doc__`
- `def main() -> int:` returns exit code
- `if __name__ == "__main__": sys.exit(main())`
- Logging via `logging.getLogger(__name__)` at INFO level, configured in main()
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create scripts/checkpoint_reset.py with guard clause on --all</name>
  <files>scripts/checkpoint_reset.py</files>

  <read_first>
    - lib/checkpoint.py (Public API — use `reset_article`, `reset_all`, `get_checkpoint_dir`, `list_checkpoints`)
    - scripts/bench_ingest_fixture.py (existing CLI conventions for this repo — shebang, argparse, main() → int)
    - CLAUDE.md § HIGHEST PRIORITY PRINCIPLES (Guard clauses before destructive actions)
  </read_first>

  <action>
    Create `scripts/checkpoint_reset.py`:

    ```python
    #!/usr/bin/env python3
    """Delete checkpoint state for one article (by hash) or all articles.

    Usage:
        python scripts/checkpoint_reset.py --hash {article_hash}
        python scripts/checkpoint_reset.py --all --confirm

    --all WITHOUT --confirm is refused (exit 2) per CLAUDE.md guard-clause principle.
    """
    import argparse
    import logging
    import sys
    from pathlib import Path

    # Ensure repo root is on sys.path so `from lib.checkpoint import ...` works when
    # the script is executed from any CWD.
    REPO_ROOT = Path(__file__).resolve().parent.parent
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from lib.checkpoint import get_checkpoint_dir, reset_article, reset_all  # noqa: E402

    logger = logging.getLogger(__name__)


    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--hash", dest="article_hash", help="16-char article hash to reset")
        group.add_argument("--all", action="store_true", help="Reset ALL checkpoints (requires --confirm)")
        parser.add_argument("--confirm", action="store_true", help="Required for --all to actually delete")
        args = parser.parse_args(argv)

        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

        if args.article_hash:
            path = get_checkpoint_dir(args.article_hash)
            if not path.exists():
                logger.error("no checkpoint dir found for hash=%s (path=%s)", args.article_hash, path)
                return 1
            # get_checkpoint_dir created it (side effect) — inspect first, then reset.
            # Re-check after get: if directory is otherwise empty, treat as missing.
            has_content = any(path.iterdir())
            if not has_content:
                logger.warning("checkpoint dir for hash=%s is empty; removing anyway", args.article_hash)
            reset_article(args.article_hash)
            logger.info("reset checkpoint for hash=%s", args.article_hash)
            return 0

        if args.all:
            if not args.confirm:
                logger.error(
                    "--all refused: destructive operation requires --confirm. "
                    "Re-run: python scripts/checkpoint_reset.py --all --confirm"
                )
                return 2
            reset_all()
            logger.info("reset ALL checkpoints (checkpoints/ root removed)")
            return 0

        # argparse mutually_exclusive_group should prevent this path.
        parser.print_help()
        return 1


    if __name__ == "__main__":
        sys.exit(main())
    ```

    Note on the "empty dir side effect": `get_checkpoint_dir` in lib/checkpoint.py creates parent dirs idempotently. If executor notices this creates a spurious empty dir on a reset attempt for an unknown hash, ADDRESS IT by using `_checkpoints_root() / hash` path construction directly (without mkdir) — but per surgical-changes principle, first verify the UX problem is real. Implementation above explicitly handles the "no content" case; a slightly cleaner alternative is to add a lightweight `def checkpoint_dir_exists(hash) -> bool` helper in lib/checkpoint.py if needed (optional — planner/executor discretion).
  </action>

  <verify>
    <automated>.venv/Scripts/python scripts/checkpoint_reset.py --all 2>&amp;1; test $? -eq 2</automated>
  </verify>

  <acceptance_criteria>
    - `grep -q 'def main' scripts/checkpoint_reset.py`
    - `grep -q '\-\-hash' scripts/checkpoint_reset.py`
    - `grep -q '\-\-all' scripts/checkpoint_reset.py`
    - `grep -q '\-\-confirm' scripts/checkpoint_reset.py`
    - `grep -q 'from lib.checkpoint import' scripts/checkpoint_reset.py`
    - `.venv/Scripts/python scripts/checkpoint_reset.py --all` exits 2 (guard clause fires)
    - `.venv/Scripts/python scripts/checkpoint_reset.py --all --confirm` exits 0 (idempotent — works on empty state)
    - `.venv/Scripts/python scripts/checkpoint_reset.py --hash nonexistent` exits 1 (missing hash error)
    - `.venv/Scripts/python scripts/checkpoint_reset.py` (no args) exits 2 (argparse mutex group required)
  </acceptance_criteria>

  <done>CLI correctly handles --hash (success + missing), --all (refuses without --confirm, proceeds with), and surfaces useful error messages.</done>
</task>

<task type="auto">
  <name>Task 2: Create scripts/checkpoint_status.py printing Markdown table</name>
  <files>scripts/checkpoint_status.py</files>

  <read_first>
    - lib/checkpoint.py (use `list_checkpoints` — returns list[dict] per interface)
    - scripts/checkpoint_reset.py (from Task 1 — mirror its scaffolding)
    - 12-CONTEXT.md §Specific Ideas — "Status Script Output Format" (expected shape)
  </read_first>

  <action>
    Create `scripts/checkpoint_status.py`:

    ```python
    #!/usr/bin/env python3
    """List all checkpoint directories with their stage status.

    Output is a Markdown-style pipe-separated table suitable for `watch`:

        CHECKPOINTS (N total, X in-flight, Y complete)

        hash             | url                           | last_stage     | age    | status
        -----------------|-------------------------------|----------------|--------|----------
        100680ad546ce6a5 | https://mp.weixin.qq.com/s/X  | text_ingest    | 2h15m  | complete
        ...

    Use with:  watch -n 5 'python scripts/checkpoint_status.py | tail -20'
    """
    import argparse
    import sys
    from pathlib import Path

    REPO_ROOT = Path(__file__).resolve().parent.parent
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from lib.checkpoint import list_checkpoints  # noqa: E402


    def _fmt_age(seconds: float | None) -> str:
        if seconds is None:
            return "?"
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        if s < 3600:
            return f"{s // 60}m"
        if s < 86400:
            return f"{s // 3600}h{(s % 3600) // 60}m"
        return f"{s // 86400}d{(s % 86400) // 3600}h"


    def _truncate(s: str, width: int) -> str:
        return s if len(s) <= width else s[: width - 1] + "…"


    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--tsv", action="store_true", help="Tab-separated output (machine-parsable)")
        args = parser.parse_args(argv)

        records = list_checkpoints()
        total = len(records)
        complete = sum(1 for r in records if r["status"] == "complete")
        in_flight = total - complete

        if args.tsv:
            print("hash\turl\ttitle\tlast_stage\tage_seconds\tstatus")
            for r in records:
                print(f"{r['hash']}\t{r['url']}\t{r['title']}\t{r['last_stage'] or ''}\t{r['age_seconds'] or ''}\t{r['status']}")
            return 0

        print(f"CHECKPOINTS ({total} total, {in_flight} in-flight, {complete} complete)")
        print()
        if not records:
            print("(no checkpoints found under ~/.hermes/omonigraph-vault/checkpoints/)")
            return 0

        # Markdown-style pipe table. Header widths chosen to fit a typical 120-col terminal.
        header = f"{'hash':<16} | {'url':<40} | {'last_stage':<14} | {'age':<7} | {'status':<9}"
        print(header)
        print("-" * len(header))
        for r in records:
            print(
                f"{r['hash']:<16} | "
                f"{_truncate(r['url'], 40):<40} | "
                f"{(r['last_stage'] or '-'):<14} | "
                f"{_fmt_age(r['age_seconds']):<7} | "
                f"{r['status']:<9}"
            )
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```
  </action>

  <verify>
    <automated>.venv/Scripts/python scripts/checkpoint_status.py 2>&amp;1 | grep -qE "CHECKPOINTS \(\d+ total"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -q 'def main' scripts/checkpoint_status.py`
    - `grep -q 'from lib.checkpoint import list_checkpoints' scripts/checkpoint_status.py`
    - `grep -q '\-\-tsv' scripts/checkpoint_status.py`
    - `.venv/Scripts/python scripts/checkpoint_status.py` exits 0 (works even with zero checkpoints)
    - `.venv/Scripts/python scripts/checkpoint_status.py` stdout contains "CHECKPOINTS ("
    - `.venv/Scripts/python scripts/checkpoint_status.py --tsv` stdout first line contains "hash\turl\ttitle\tlast_stage" (tab-separated)
  </acceptance_criteria>

  <done>CLI runs from any CWD, handles empty-state gracefully, offers human + machine-parsable output modes.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Integration tests for both CLIs via subprocess</name>
  <files>tests/unit/test_checkpoint_cli.py</files>

  <read_first>
    - scripts/checkpoint_reset.py (from Task 1)
    - scripts/checkpoint_status.py (from Task 2)
    - lib/checkpoint.py (use write_stage + write_metadata to seed test state)
    - tests/unit/test_checkpoint.py (fixture pattern for isolating BASE_DIR)
  </read_first>

  <behavior>
    Test cases (use `subprocess.run` invoking the scripts with `sys.executable`):

    - test_reset_all_without_confirm_exits_2: `checkpoint_reset.py --all` exit code == 2, stderr contains "--confirm"
    - test_reset_all_with_confirm_exits_0: seed 2 article dirs; run `--all --confirm`; exit 0; both dirs gone
    - test_reset_hash_missing_exits_1: run `--hash abc123` with no such checkpoint; exit 1
    - test_reset_hash_present_exits_0: seed 1 article; run `--hash {its_hash}`; exit 0; dir gone
    - test_reset_mutex_group_requires_one: running with no args → exit != 0
    - test_status_empty_prints_zero_total: no checkpoints → stdout contains "(0 total"
    - test_status_with_mixed_states: seed 2 articles (one with text_ingest marker, one with only scrape); stdout contains both hashes AND contains the substrings "complete" and "in_flight"
    - test_status_tsv_mode_first_line_is_header: `--tsv` first line == "hash\turl\ttitle\tlast_stage\tage_seconds\tstatus"

    Fixture constraint:
    Subprocess invocations inherit env but NOT the monkeypatched `lib.checkpoint.BASE_DIR`. Solution: set `OMNIGRAPH_CHECKPOINT_BASE_DIR` env var and add a `_resolve_base_dir()` helper in lib/checkpoint.py that reads the env var as override. ALTERNATIVELY (simpler, preferred): have tests run with CWD set to `tmp_path`, and monkeypatch `lib.checkpoint.BASE_DIR` both in-process AND via env. Simplest approach: `subprocess.run([sys.executable, script_path], env={**os.environ, "HOME": str(tmp_path)})` — under Windows use `USERPROFILE` too. Implementation choice left to executor; document the choice in the test file's module docstring.

    ALTERNATIVE (cleaner): Add to `lib/checkpoint.py` a small override hook at module load:
    ```python
    _env_override = os.environ.get("OMNIGRAPH_CHECKPOINT_BASE_DIR")
    if _env_override:
        BASE_DIR = Path(_env_override)
    ```
    Then tests set `env={..., "OMNIGRAPH_CHECKPOINT_BASE_DIR": str(tmp_path)}` on subprocess.run.

    RECOMMENDED: use the env-override approach. It's 3 lines of code in lib/checkpoint.py, makes subprocess tests trivial, and is a documented test seam (add a comment: "TEST-ONLY override; not used in production").
  </behavior>

  <action>
    Step A (if Task 2 did not already add the override): Edit `lib/checkpoint.py` to add the env override right after `BASE_DIR = _CONFIG_BASE_DIR`:

    ```python
    # Test seam: allow unit/integration tests to redirect BASE_DIR without patching
    # in-process state (subprocess tests cannot monkeypatch the child process).
    _env_override = os.environ.get("OMNIGRAPH_CHECKPOINT_BASE_DIR")
    if _env_override:
        BASE_DIR = Path(_env_override)
    ```

    Step B: Create `tests/unit/test_checkpoint_cli.py`:

    ```python
    """Integration tests for checkpoint_reset.py and checkpoint_status.py.

    Subprocess-based because the CLIs are argparse-driven and the guard-clause
    exit codes are part of the contract.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    import pytest

    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    RESET_SCRIPT = REPO_ROOT / "scripts" / "checkpoint_reset.py"
    STATUS_SCRIPT = REPO_ROOT / "scripts" / "checkpoint_status.py"


    @pytest.fixture
    def base_env(tmp_path, monkeypatch):
        """Redirect BASE_DIR for both in-process and subprocess via env var."""
        fake_base = tmp_path / "omonigraph-vault"
        fake_base.mkdir(parents=True)
        env = {**os.environ, "OMNIGRAPH_CHECKPOINT_BASE_DIR": str(fake_base)}
        # Also patch in-process so our test seeding code writes to the same place.
        monkeypatch.setenv("OMNIGRAPH_CHECKPOINT_BASE_DIR", str(fake_base))
        # Force reimport so the module-level BASE_DIR picks up the env.
        import importlib
        import lib.checkpoint as ckpt
        importlib.reload(ckpt)
        yield env, ckpt


    def _run(script: Path, *args: str, env: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True, text=True, env=env,
        )


    def test_reset_all_without_confirm_exits_2(base_env):
        env, _ = base_env
        result = _run(RESET_SCRIPT, "--all", env=env)
        assert result.returncode == 2, result.stderr
        assert "--confirm" in (result.stderr + result.stdout)


    def test_reset_all_with_confirm_removes_all(base_env):
        env, ckpt = base_env
        ckpt.write_stage(ckpt.get_article_hash("https://a.test"), "scrape", "<html>A</html>")
        ckpt.write_stage(ckpt.get_article_hash("https://b.test"), "scrape", "<html>B</html>")
        assert len(list((ckpt.BASE_DIR / "checkpoints").iterdir())) == 2
        result = _run(RESET_SCRIPT, "--all", "--confirm", env=env)
        assert result.returncode == 0, result.stderr
        assert not (ckpt.BASE_DIR / "checkpoints").exists()


    def test_reset_hash_missing_exits_1(base_env):
        env, _ = base_env
        result = _run(RESET_SCRIPT, "--hash", "deadbeef12345678", env=env)
        assert result.returncode == 1, result.stderr


    def test_reset_hash_present_exits_0(base_env):
        env, ckpt = base_env
        h = ckpt.get_article_hash("https://one.test")
        ckpt.write_stage(h, "scrape", "<html/>")
        result = _run(RESET_SCRIPT, "--hash", h, env=env)
        assert result.returncode == 0, result.stderr
        assert not (ckpt.BASE_DIR / "checkpoints" / h).exists()


    def test_reset_no_args_exits_nonzero(base_env):
        env, _ = base_env
        result = _run(RESET_SCRIPT, env=env)
        assert result.returncode != 0


    def test_status_empty_prints_zero_total(base_env):
        env, _ = base_env
        result = _run(STATUS_SCRIPT, env=env)
        assert result.returncode == 0
        assert "0 total" in result.stdout


    def test_status_mixed_states(base_env):
        env, ckpt = base_env
        h_complete = ckpt.get_article_hash("https://complete.test")
        h_inflight = ckpt.get_article_hash("https://in-flight.test")
        ckpt.write_stage(h_complete, "scrape", "<html/>")
        ckpt.write_stage(h_complete, "classify", {"depth": 2, "topics": ["ai"]})
        ckpt.write_stage(h_complete, "text_ingest")
        ckpt.write_metadata(h_complete, {"url": "https://complete.test", "title": "C"})
        ckpt.write_stage(h_inflight, "scrape", "<html/>")
        ckpt.write_metadata(h_inflight, {"url": "https://in-flight.test", "title": "I"})

        result = _run(STATUS_SCRIPT, env=env)
        assert result.returncode == 0, result.stderr
        assert h_complete in result.stdout
        assert h_inflight in result.stdout
        assert "complete" in result.stdout
        assert "in_flight" in result.stdout


    def test_status_tsv_header(base_env):
        env, _ = base_env
        result = _run(STATUS_SCRIPT, "--tsv", env=env)
        assert result.returncode == 0
        first_line = result.stdout.splitlines()[0]
        assert first_line == "hash\turl\ttitle\tlast_stage\tage_seconds\tstatus"
    ```

    Run `.venv/Scripts/python -m pytest tests/unit/test_checkpoint_cli.py -v`. Fix any failures by adjusting scripts OR the env-override seam.
  </action>

  <verify>
    <automated>.venv/Scripts/python -m pytest tests/unit/test_checkpoint_cli.py -v</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "^def test_" tests/unit/test_checkpoint_cli.py` >= 8
    - `grep -q "subprocess.run" tests/unit/test_checkpoint_cli.py`
    - `grep -q "OMNIGRAPH_CHECKPOINT_BASE_DIR" tests/unit/test_checkpoint_cli.py`
    - `grep -q "OMNIGRAPH_CHECKPOINT_BASE_DIR" lib/checkpoint.py` (env override seam added)
    - `.venv/Scripts/python -m pytest tests/unit/test_checkpoint_cli.py -v` exits 0
  </acceptance_criteria>

  <done>All 8 CLI tests pass via subprocess invocation; env-override seam documented in lib/checkpoint.py.</done>
</task>

</tasks>

<verification>
1. All CLI tests pass: `.venv/Scripts/python -m pytest tests/unit/test_checkpoint_cli.py -v`
2. Guard clause demonstrated: `.venv/Scripts/python scripts/checkpoint_reset.py --all` exits 2, stderr mentions `--confirm`
3. Status script runs from empty state without crash
4. Unit tests from 12-00 still pass (no regression): `.venv/Scripts/python -m pytest tests/unit/test_checkpoint.py tests/unit/test_checkpoint_cli.py -v`
</verification>

<success_criteria>
- Both scripts exist in scripts/ and run as `python scripts/*.py` from repo root
- `--all` without `--confirm` exits non-zero and prints guard-clause message (CLAUDE.md rule satisfied)
- Scripts operate on whatever `BASE_DIR` resolves to (respects `OMNIGRAPH_CHECKPOINT_BASE_DIR` env override for tests)
- 8+ CLI tests all green
- Zero production code outside `lib/checkpoint.py` and `scripts/` touched (surgical)
</success_criteria>

<output>
After completion, create `.planning/phases/12-checkpoint-resume/12-01-SUMMARY.md` with:
- CLI invocation examples (copy-paste ready)
- Guard-clause demo output
- Files modified: 3 new files + 1 small test-seam addition to `lib/checkpoint.py`
</output>

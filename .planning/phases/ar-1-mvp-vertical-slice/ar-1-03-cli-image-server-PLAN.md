---
phase: ar-1-mvp-vertical-slice
plan: 03
type: execute
wave: 3
depends_on:
  - ar-1-02
files_modified:
  - lib/research/__main__.py
  - lib/research/image_server.py
  - tests/unit/research/test_image_server.py
  - tests/unit/research/test_main_cli.py
autonomous: true
requirements:
  - ORCH-08
  - CLI-01

must_haves:
  truths:
    - "`python -m omnigraph.research \"<query>\"` exits 0 with non-empty markdown to stdout"
    - "Local image HTTP server on port 8765 is brought up before research() runs if not already listening"
    - "Image server bring-up is idempotent — re-running CLI never spawns a duplicate server"
    - "CLI is a pure wrapper — no business logic, only argparse + asyncio.run + print"
    - "Image server subprocess uses `python -m http.server 8765 --directory <BASE_IMAGE_DIR>`"
  artifacts:
    - path: "lib/research/__main__.py"
      provides: "CLI entrypoint — argparse single query arg, runs research(), prints markdown"
      contains: "argparse, asyncio.run, ensure_image_server, research, from_env, print(result.markdown)"
    - path: "lib/research/image_server.py"
      provides: "Idempotent image HTTP server bring-up"
      contains: "ensure_image_server(base_image_dir, port=8765) -> int|None, _is_port_listening, _spawn_server"
  key_links:
    - from: "lib/research/__main__.py"
      to: "lib/research/image_server.py"
      via: "from .image_server import ensure_image_server"
    - from: "lib/research/__main__.py"
      to: "lib/research/orchestrator.py"
      via: "from .orchestrator import research"
    - from: "lib/research/__main__.py"
      to: "lib/research/config.py"
      via: "from .config import from_env"
---

<objective>
Land the CLI entrypoint (`python -m omnigraph.research "<query>"`) and the local image HTTP server auto-bring-up. This plan turns the importable lib (delivered by ar-1-01 + ar-1-02) into a runnable command-line tool.

Purpose:
- ORCH-08: When the orchestrator runs, the local image HTTP server on port 8765 must be listening so the synthesized markdown's `http://localhost:8765/...` image URLs resolve.
- CLI-01: `python -m omnigraph.research "<query>"` is the single user-facing invocation surface. Skill scripts (ar-1-04) wrap this command. Future HTTP wrapper (post-milestone) reuses `research()` directly without going through CLI.

Output:
- `lib/research/__main__.py` — ~30-line argparse + asyncio.run wrapper
- `lib/research/image_server.py` — `ensure_image_server()` function (idempotent, returns PID or None if already running)
- 2 test files covering both modules

The CLI must NOT add any logic on top of `research()`. Anything more sophisticated than "parse one positional arg, ensure server, run research, print markdown" belongs in the orchestrator, not the wrapper.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-01-package-scaffolding-PLAN.md
@.planning/phases/ar-1-mvp-vertical-slice/ar-1-02-stage-stubs-PLAN.md
@docs/design/agentic_rag_internal_api.md
@config.py

<interfaces>
After ar-1-01 + ar-1-02, the following are importable:

```python
from lib.research.orchestrator import research
from lib.research.config import from_env
# from_env() is a module-level function in lib.research.config (per ar-1-01 README §Quickstart)
cfg = from_env()
result = await research(query, cfg)
# result.markdown is a non-empty string; result.images_embedded may reference http://localhost:8765/<hash>/<n>.jpg
```

The image server must be brought up BEFORE `research()` runs, because:
- Synthesizer (ar-1-02) embeds image URLs of shape `http://localhost:8765/<article_hash>/<N>.jpg`
- The user reads the printed markdown in a terminal/IDE that may render images via the markdown viewer
- ar-1's smoke test (CONTEXT.md Layer 2) requires "port 8765 image server is brought up if not already running"

BASE_IMAGE_DIR resolution (from config.py at root, mirrored in research config):
```python
BASE_IMAGE_DIR = BASE_DIR / "images"
# where BASE_DIR = ~/.hermes/omonigraph-vault by default
```

In `lib/research/config.py` (ar-1-01), `cfg.rag_working_dir` is `BASE_DIR / "lightrag_storage"`. So:
```python
base_image_dir = cfg.rag_working_dir.parent / "images"
```

This is the SAME path used by retriever stage in ar-1-02 for image globbing — keep them in sync.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 0: Install editable so `python -m omnigraph.research` resolves the omnigraph.research namespace</name>
  <read_first>
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-01-package-scaffolding-PLAN.md § Task 5 (declares `[tool.setuptools.package-dir]` mapping `omnigraph.research → lib/research`; line 602 explicitly defers editable install to this plan)
  </read_first>
  <files>None — environment-only; no source changes</files>
  <action>
    Run `cd c:/Users/huxxha/Desktop/OmniGraph-Vault && venv/Scripts/python.exe -m pip install -e .` once.

    Why this is in ar-1-03 and not ar-1-01:
    - ar-1-01 declares the namespace mapping in `pyproject.toml` but does NOT install editable. Under that plan, `pythonpath=["."]` is sufficient because tests import via `lib.research.*`.
    - This plan is the FIRST that invokes `python -m omnigraph.research` (a `runpy` `-m` invocation against the `omnigraph.research` namespace, not an import-path-based import). `runpy` only resolves the namespace mapping when the package is installed — `pythonpath=["."]` does NOT make `-m omnigraph.research` work.
    - Therefore this plan owns the editable install. Idempotent: re-running installs over the existing egg-link without harm.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pip install -e . &amp;&amp; venv/Scripts/python.exe -c "from omnigraph.research import research; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `pip install -e .` exits 0
    - `python -c "from omnigraph.research import research"` exits 0
    - `pip show omnigraph-vault` (or whatever the project's distribution name is per ar-1-01 pyproject.toml) lists the project as editable with path = repo root
    - `python -m omnigraph.research --help` resolves the module (Task 2 verifies the actual help text)
  </acceptance_criteria>
  <done>Editable install live; `python -m omnigraph.research` is now resolvable for Tasks 1-3.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 1: Implement lib/research/image_server.py with idempotent ensure_image_server()</name>
  <read_first>
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Smoke test for ar-1" → Layer 2 (port 8765 must come up)
    - docs/design/agentic_rag_internal_api.md § "Local image HTTP server"
    - config.py (root) — BASE_IMAGE_DIR pattern
  </read_first>
  <files>lib/research/image_server.py, tests/unit/research/test_image_server.py</files>
  <behavior>
    - Test 1: `_is_port_listening(8765)` returns False on a free port (use `socket.socket` bind-probe)
    - Test 2: `_is_port_listening(8765)` returns True when a real socket is bound on 8765 (start a server in fixture, tear down after)
    - Test 3: `ensure_image_server(tmp_path, port=8765)` when port is free → spawns subprocess, returns PID (int)
    - Test 4: `ensure_image_server(tmp_path, port=8765)` when port is busy → returns None (no spawn)
    - Test 5: `ensure_image_server` is idempotent — calling twice in a row returns (PID, None) (second call sees port busy)
    - Test 6: subprocess command-line uses `python -m http.server <port> --directory <dir>` form (assert via `subprocess.Popen` mock — capture argv)
    - Test 7: `ensure_image_server` accepts a `Path` for `base_image_dir`; if directory does not exist, raise FileNotFoundError BEFORE spawning (so we never spawn a server pointing at a missing dir)
    - Test 8: Server subprocess is detached (does not die when parent Python exits) — verified by checking `start_new_session=True` on POSIX or `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` on Windows in the Popen call
  </behavior>
  <action>
    Create `lib/research/image_server.py` with this shape:

    ```python
    """Local image HTTP server bring-up for the research CLI.

    ORCH-08: Synthesized markdown embeds http://localhost:8765/<hash>/<N>.jpg URLs.
    The CLI must ensure the server is listening before research() runs so those
    URLs resolve when the user views the output.

    Idempotent: re-running the CLI when a server is already running on port 8765
    returns None and does NOT spawn a duplicate.
    """
    from __future__ import annotations

    import socket
    import subprocess
    import sys
    from pathlib import Path


    def _is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
        """Probe whether `port` on `host` is currently accepting connections."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((host, port))
                return True
            except (ConnectionRefusedError, OSError):
                return False


    def ensure_image_server(base_image_dir: Path, port: int = 8765) -> int | None:
        """Ensure `python -m http.server <port> --directory <base_image_dir>` is running.

        Returns the spawned PID if a new server was started, or None if one was
        already listening on `port`.
        """
        base_image_dir = Path(base_image_dir)
        if not base_image_dir.is_dir():
            raise FileNotFoundError(f"base_image_dir does not exist: {base_image_dir}")

        if _is_port_listening(port):
            return None

        cmd = [sys.executable, "-m", "http.server", str(port), "--directory", str(base_image_dir)]
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **kwargs)
        return proc.pid
    ```

    Then `tests/unit/research/test_image_server.py` with 8 tests above. Use `unittest.mock.patch` to mock `subprocess.Popen` for argv-shape tests, and use a real `socket.socket().bind(("127.0.0.1", 0))` fixture (with port assigned by OS) for the listening-true test.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_image_server.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/image_server.py` exists with `ensure_image_server` and `_is_port_listening`
    - All 8 tests pass
    - `python -c "from lib.research.image_server import ensure_image_server; print('OK')"` exits 0
    - On Windows, `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` is verified by argv inspection in test 8
    - Re-importing twice in same Python process and calling `ensure_image_server` doesn't double-spawn (test 5 covers)
  </acceptance_criteria>
  <done>image_server.py works idempotently on Windows; 8 tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement lib/research/__main__.py CLI entrypoint</name>
  <read_first>
    - lib/research/orchestrator.py (after ar-1-02) — research() signature
    - lib/research/config.py (after ar-1-01) — module-level from_env() function
    - lib/research/image_server.py (Task 1 above)
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Smoke test for ar-1" → Layer 2
  </read_first>
  <files>lib/research/__main__.py, tests/unit/research/test_main_cli.py</files>
  <behavior>
    - Test 1: `python -m omnigraph.research --help` exits 0 with help text containing "query"
    - Test 2: `python -m omnigraph.research "test query"` exits 0 (subprocess.run, capture_output=True)
    - Test 3: stdout is non-empty (≥ 200 chars per CONTEXT.md Layer 2 contract)
    - Test 4: stdout contains the query string echoed (synthesizer puts query in title — verifies orchestrator wired up)
    - Test 5: stdout contains at least one degradation note line (since web_baseline + reasoner + verifier are stubbed in ar-1, ≥1 "skipped" note line should appear)
    - Test 6: After CLI run, port 8765 is listening (`socket.create_connection(("127.0.0.1", 8765), timeout=1)` succeeds)
    - Test 7: Calling main() programmatically with a mock config returns None (it prints, doesn't return)
    - Test 8: argparse rejects 0 args (no query) with exit code != 0

    NOTE: Tests 2-6 are integration-style and may run slow because they spawn a real Python subprocess. Mark them with `@pytest.mark.slow` and gate by `--run-slow` pytest flag if standard test run should stay fast. Tests 1, 7, 8 are fast unit tests.
  </behavior>
  <action>
    Create `lib/research/__main__.py` with this shape:

    ```python
    """CLI entrypoint: `python -m omnigraph.research "<query>"`.

    CLI-01: Pure wrapper — argparse + asyncio.run + print. No business logic.
    Anything more sophisticated belongs in orchestrator.py.
    """
    from __future__ import annotations

    import argparse
    import asyncio
    import sys

    from .config import from_env
    from .image_server import ensure_image_server
    from .orchestrator import research


    def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            prog="omnigraph.research",
            description="Run the OmniGraph agentic-RAG research pipeline.",
        )
        parser.add_argument("query", help="Natural-language research query.")
        return parser.parse_args(argv)


    async def _amain(query: str) -> str:
        cfg = from_env()
        # ORCH-08: bring up the local image HTTP server before synthesizer
        # embeds http://localhost:8765/... URLs.
        base_image_dir = cfg.rag_working_dir.parent / "images"
        if base_image_dir.is_dir():
            ensure_image_server(base_image_dir)
        result = await research(query, cfg)
        return result.markdown


    def main(argv: list[str] | None = None) -> None:
        ns = _parse_args(argv)
        markdown = asyncio.run(_amain(ns.query))
        print(markdown)


    if __name__ == "__main__":
        main(sys.argv[1:])
    ```

    Then write `tests/unit/research/test_main_cli.py` covering the 8 behaviors above.

    For the slow integration tests (2-6), use a fixture that:
    - Sets env vars so from_env() resolves to a tmp_path BASE_DIR
    - Creates a tmp images dir under BASE_DIR/images
    - Spawns `[sys.executable, "-m", "omnigraph.research", "什么是 Hermes Harness 深度解析"]` via subprocess.run with cwd=repo_root
    - Asserts on returncode + stdout

    Mark slow tests with `@pytest.mark.slow` per existing pyproject.toml `[tool.pytest.ini_options]` markers convention.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m pytest tests/unit/research/test_main_cli.py -v --run-slow</automated>
  </verify>
  <acceptance_criteria>
    - `lib/research/__main__.py` exists and is < 50 lines
    - `python -m omnigraph.research --help` exits 0 (proves namespace mapping from ar-1-01 works end-to-end)
    - `python -m omnigraph.research "什么是 Hermes Harness 深度解析"` exits 0 with ≥ 200 chars markdown to stdout
    - stdout contains the query string and ≥ 1 degradation note line
    - port 8765 is listening after the CLI returns
    - All 8 tests pass (run with --run-slow to include integration tests)
    - `__main__.py` imports ONLY from `.config`, `.image_server`, `.orchestrator` plus stdlib (argparse, asyncio, sys) — no other imports allowed (pure wrapper rule)
  </acceptance_criteria>
  <done>CLI fully functional; smoke test Layer 2 from CONTEXT.md passes.</done>
</task>

<task type="auto">
  <name>Task 3: End-to-end smoke test (CONTEXT.md Layer 2)</name>
  <read_first>
    - .planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md § "Smoke test for ar-1" → Layer 2
  </read_first>
  <files>None — verification only</files>
  <action>
    Run the Layer 2 smoke test exactly as written in CONTEXT.md:

    ```bash
    venv/Scripts/python.exe -m omnigraph.research "什么是 Hermes Harness 深度解析"
    ```

    Verify all 5 expected outcomes:
    1. exit code 0
    2. stdout: non-empty markdown (≥ 200 chars)
    3. markdown contains query echo + at least one degradation note line
    4. port 8765 image server is brought up if not already running
    5. no stage raises; ResearchState dataclass populates all 5 stage fields

    For #5, modify the smoke run to dump state — temporarily import and call `research()` directly in a small inline `python -c "..."` snippet that asserts `result.state.web_baseline is not None and result.state.retrieved is not None and result.state.reasoned is not None and result.state.verified is not None and result.state.synthesized is not None`.

    Do NOT modify production code to add a `--dump-state` flag — that's deferred to ar-4 per CONTEXT.md "Out of Scope".

    Capture output in `.scratch/ar-1-03-smoke-260522.log`.
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -m omnigraph.research "什么是 Hermes Harness 深度解析" | tee .scratch/ar-1-03-smoke-260522.log &amp;&amp; wc -c .scratch/ar-1-03-smoke-260522.log</automated>
  </verify>
  <acceptance_criteria>
    - `.scratch/ar-1-03-smoke-260522.log` exists and is ≥ 200 bytes
    - Log contains the literal query string "Hermes Harness 深度解析"
    - Log contains at least one line matching pattern `> ℹ️.*skipped` or similar degradation note
    - `curl -sI http://localhost:8765/` returns HTTP 200 or 301 (server is up)
    - Inline state-assertion snippet exits 0 (all 5 stage fields populated)
  </acceptance_criteria>
  <done>Layer 2 CLI smoke test fully passes; phase deliverable is end-to-end runnable.</done>
</task>

</tasks>

<verification>
- All 3 tasks pass automated checks
- `pytest tests/unit/research/test_image_server.py tests/unit/research/test_main_cli.py -v` exits 0
- `python -m omnigraph.research "test"` exits 0 with non-empty stdout
- Port 8765 listening after CLI run
- ResearchState has all 5 stage fields populated (no None)
- CONTRACT-01 + CONTRACT-02 grep checks (from ar-1-01 Task 6) still pass after this plan
</verification>

<success_criteria>
- `lib/research/__main__.py` and `lib/research/image_server.py` both exist and are importable
- CLI is a pure wrapper (≤ 50 LOC, no business logic)
- Image server bring-up is idempotent on Windows + POSIX
- Smoke test Layer 2 passes with the canonical query "什么是 Hermes Harness 深度解析"
- ≥ 16 tests across the 2 new test files
</success_criteria>

<output>
After completion, create `.planning/phases/ar-1-mvp-vertical-slice/ar-1-03-SUMMARY.md` documenting:
- Files created (count + list)
- Test count + pass status (split fast vs --run-slow)
- Smoke test exit code + stdout char count + degradation note line excerpt
- `_is_port_listening` probe result before vs after CLI run
- Any deviations from plan (with reason)
</output>

"""Tests for lib.research.__main__ — CLI entrypoint.

Fast tests (default): help, argparse error path, programmatic main(...) shape.
Slow tests (@pytest.mark.slow): subprocess-spawn the real CLI and assert on
stdout. The slow tests require an editable install (`pip install -e .`) so
that `python -m omnigraph.research` resolves; they also bring up the real
image HTTP server on port 8765 (idempotent — never spawns a duplicate).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_QUERY_ZH = "什么是 Hermes Harness 深度解析"


# ---------------------------------------------------------------------------
# Fast unit tests
# ---------------------------------------------------------------------------


def test_argparse_help_exits_zero() -> None:
    """`python -m omnigraph.research --help` exits 0 with help text containing 'query'."""
    res = subprocess.run(
        [sys.executable, "-m", "omnigraph.research", "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode == 0
    combined = (res.stdout + res.stderr).lower()
    assert "query" in combined


def test_argparse_rejects_zero_args() -> None:
    """argparse rejects 0 args (no query) with non-zero exit code."""
    res = subprocess.run(
        [sys.executable, "-m", "omnigraph.research"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode != 0


def test_main_returns_none(tmp_path: Path, monkeypatch) -> None:
    """main() prints, doesn't return — programmatic call returns None."""
    # Set env so from_env() resolves to a tmp BASE_DIR.
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    (tmp_path / "lightrag_storage").mkdir()
    (tmp_path / "images").mkdir()

    # Patch out the heavy bits: from_env's lazy LLM-client init, the image
    # server spawn, and the actual research() call.
    from lib.research.types import (
        ResearchConfig,
        ResearchResult,
        ResearchState,
        SynthesizerOutput,
    )
    fake_cfg = ResearchConfig(
        rag_working_dir=tmp_path / "lightrag_storage",
        llm_complete=lambda *a, **kw: "stub",
        embedding_func=lambda *a, **kw: [],
        vision_cascade=object(),
        web_search=lambda q: [],
    )
    fake_state = ResearchState(query="q", timestamp_start=0.0)
    fake_state.synthesized = SynthesizerOutput(
        markdown="# stub\n",
        confidence=0.0,
        sources=[],
        embedded_images=[],
        note_lines=[],
    )
    fake_result = ResearchResult(
        markdown="# stub\n",
        confidence=0.0,
        sources=[],
        images_embedded=[],
        state=fake_state,
    )

    async def _fake_research(query: str, cfg) -> ResearchResult:
        return fake_result

    from lib.research import __main__ as cli_mod

    with patch.object(cli_mod, "from_env", return_value=fake_cfg), \
         patch.object(cli_mod, "ensure_image_server", return_value=None), \
         patch.object(cli_mod, "research", side_effect=_fake_research):
        # Capture print output.
        rc = cli_mod.main(["test query"])

    assert rc is None


def test_main_imports_only_allowed_modules() -> None:
    """__main__.py imports ONLY from .config / .image_server / .orchestrator
    plus stdlib (argparse, asyncio, sys) — pure wrapper rule."""
    src = (REPO_ROOT / "lib" / "research" / "__main__.py").read_text(
        encoding="utf-8"
    )
    # All `from .x import y` should be one of the three allowed sibling modules.
    import re
    rel_imports = re.findall(r"^from \.(\w+) import", src, flags=re.M)
    for mod in rel_imports:
        assert mod in {"config", "image_server", "orchestrator"}, (
            f"Forbidden relative import 'from .{mod}' in __main__.py — pure "
            "wrapper rule allows only .config / .image_server / .orchestrator"
        )

    # All top-level `import x` (no dots) should be stdlib.
    stdlib_imports = re.findall(r"^import (\w+)", src, flags=re.M)
    allowed_stdlib = {"argparse", "asyncio", "sys"}
    for mod in stdlib_imports:
        assert mod in allowed_stdlib, (
            f"Forbidden top-level import '{mod}' in __main__.py — pure "
            f"wrapper rule allows only stdlib {allowed_stdlib}"
        )


# ---------------------------------------------------------------------------
# Slow integration tests (subprocess-spawn the real CLI)
# ---------------------------------------------------------------------------


def _is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (ConnectionRefusedError, OSError):
            return False


@pytest.fixture
def cli_env(tmp_path: Path) -> dict:
    """Build env that points OMNIGRAPH_BASE_DIR at a tmp_path with required dirs."""
    (tmp_path / "lightrag_storage").mkdir()
    (tmp_path / "images").mkdir()
    env = os.environ.copy()
    env["OMNIGRAPH_BASE_DIR"] = str(tmp_path)
    env.setdefault("DEEPSEEK_API_KEY", "dummy")
    env.setdefault("GEMINI_API_KEY", "dummy")
    # Ensure UTF-8 for subprocess stdout so CJK chars round-trip.
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.mark.slow
def test_cli_smoke_exits_zero_with_nonempty_markdown(cli_env: dict) -> None:
    """`python -m omnigraph.research "<query>"` exits 0 with ≥200 chars markdown."""
    res = subprocess.run(
        [sys.executable, "-m", "omnigraph.research", SMOKE_QUERY_ZH],
        cwd=str(REPO_ROOT),
        env=cli_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert res.returncode == 0, (
        f"CLI exited {res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )
    assert len(res.stdout) >= 200, (
        f"stdout shorter than 200 chars (got {len(res.stdout)}):\n{res.stdout}"
    )


@pytest.mark.slow
def test_cli_stdout_contains_query_echo(cli_env: dict) -> None:
    """Synthesizer puts the query in the title — verifies orchestrator wired up."""
    res = subprocess.run(
        [sys.executable, "-m", "omnigraph.research", SMOKE_QUERY_ZH],
        cwd=str(REPO_ROOT),
        env=cli_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert res.returncode == 0
    assert "Hermes Harness 深度解析" in res.stdout, (
        f"Query echo missing from stdout:\n{res.stdout}"
    )


@pytest.mark.slow
def test_cli_stdout_contains_degradation_note(cli_env: dict) -> None:
    """Stdout contains ≥1 degradation note line (skipped/failed stage)."""
    res = subprocess.run(
        [sys.executable, "-m", "omnigraph.research", SMOKE_QUERY_ZH],
        cwd=str(REPO_ROOT),
        env=cli_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert res.returncode == 0
    # Synthesizer note format: "> ℹ️ Stage skipped: reason" / "> ❌ Stage failed: reason".
    has_degradation_note = any(
        line.startswith("> ") and ("skipped" in line or "failed" in line)
        for line in res.stdout.splitlines()
    )
    assert has_degradation_note, (
        f"No degradation note found in stdout:\n{res.stdout}"
    )


@pytest.mark.slow
def test_cli_brings_up_image_server(cli_env: dict) -> None:
    """After CLI run, port 8765 is listening (image server is up)."""
    res = subprocess.run(
        [sys.executable, "-m", "omnigraph.research", SMOKE_QUERY_ZH],
        cwd=str(REPO_ROOT),
        env=cli_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert res.returncode == 0
    # Probe port 8765 — server runs detached, so it persists after the
    # subprocess exit.
    assert _is_port_listening(8765), (
        "Port 8765 is not listening after CLI run — ensure_image_server "
        "should have brought it up."
    )

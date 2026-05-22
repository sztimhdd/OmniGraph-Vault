"""Tests for CLI-03: --max-iter-reasoner / --max-iter-verifier / --no-grounding.

Fast unit tests for _parse_args + _amain override-dict construction. One slow
subprocess test (cap=0 LLM-free smoke) exercises the actual CLI entrypoint
without invoking any LLM (max_iter_reasoner=0 → Reasoner exits immediately;
max_iter_verifier=0 → Verifier stub also exits).

Plan: ar-2-03-cli-flags-PLAN.md (Wave 3 of phase ar-2).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib.research.__main__ import _amain, _parse_args


REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Fast unit tests for _parse_args (no asyncio)
# ---------------------------------------------------------------------------


def test_parse_args_defaults() -> None:
    """No flags → all override slots default to None / False."""
    ns = _parse_args(["test query"])
    assert ns.query == "test query"
    assert ns.max_iter_reasoner is None
    assert ns.max_iter_verifier is None
    assert ns.no_grounding is False


def test_parse_args_max_iter_reasoner() -> None:
    ns = _parse_args(["--max-iter-reasoner", "2", "test"])
    assert ns.max_iter_reasoner == 2
    assert ns.query == "test"


def test_parse_args_max_iter_verifier() -> None:
    ns = _parse_args(["--max-iter-verifier", "1", "test"])
    assert ns.max_iter_verifier == 1


def test_parse_args_no_grounding() -> None:
    ns = _parse_args(["--no-grounding", "test"])
    assert ns.no_grounding is True


def test_parse_args_all_three_flags() -> None:
    ns = _parse_args([
        "--max-iter-reasoner", "2",
        "--max-iter-verifier", "1",
        "--no-grounding",
        "test",
    ])
    assert ns.max_iter_reasoner == 2
    assert ns.max_iter_verifier == 1
    assert ns.no_grounding is True
    assert ns.query == "test"


def test_parse_args_invalid_int_rejected() -> None:
    """argparse type=int rejects non-integers with SystemExit."""
    with pytest.raises(SystemExit):
        _parse_args(["--max-iter-reasoner", "not-an-int", "test"])


# ---------------------------------------------------------------------------
# Fast unit tests for _amain override-dict construction
# ---------------------------------------------------------------------------


def _make_fake_cfg(tmp_path: Path):
    """Build a minimal stub ResearchConfig that doesn't trigger lazy LLM init."""
    from lib.research.types import ResearchConfig
    rag_dir = tmp_path / "lightrag_storage"
    rag_dir.mkdir(parents=True, exist_ok=True)
    return ResearchConfig(
        rag_working_dir=rag_dir,
        llm_complete=lambda *a, **kw: "stub",
        embedding_func=lambda *a, **kw: [],
        vision_cascade=object(),
        web_search=lambda q: [],
    )


def _make_fake_result(query: str):
    from lib.research.types import ResearchResult, ResearchState
    return ResearchResult(
        markdown="stub",
        confidence=0.0,
        sources=[],
        images_embedded=[],
        state=ResearchState(query=query, timestamp_start=0.0),
    )


@pytest.mark.asyncio
async def test_amain_builds_overrides(monkeypatch, tmp_path: Path) -> None:
    """All three flags set → cfg passed to research() has overrides applied."""
    captured_cfgs = []

    async def fake_research(query, cfg):
        captured_cfgs.append(cfg)
        return _make_fake_result(query)

    monkeypatch.setattr(
        "lib.research.__main__.from_env",
        lambda: _make_fake_cfg(tmp_path),
    )
    monkeypatch.setattr("lib.research.__main__.research", fake_research)
    monkeypatch.setattr(
        "lib.research.__main__.ensure_image_server",
        lambda *a, **kw: None,
    )

    ns = _parse_args([
        "--max-iter-reasoner", "2",
        "--max-iter-verifier", "1",
        "--no-grounding",
        "test query",
    ])
    out = await _amain(ns)

    assert out == "stub"
    assert len(captured_cfgs) == 1
    cfg = captured_cfgs[0]
    assert cfg.max_iter_reasoner == 2
    assert cfg.max_iter_verifier == 1
    assert cfg.google_search_grounding is None


@pytest.mark.asyncio
async def test_amain_no_flags_preserves_default_cfg(
    monkeypatch, tmp_path: Path
) -> None:
    """No flags → dataclasses.replace NOT called; cfg is from_env() output verbatim."""
    captured_cfgs = []

    async def fake_research(query, cfg):
        captured_cfgs.append(cfg)
        return _make_fake_result(query)

    monkeypatch.setattr(
        "lib.research.__main__.from_env",
        lambda: _make_fake_cfg(tmp_path),
    )
    monkeypatch.setattr("lib.research.__main__.research", fake_research)
    monkeypatch.setattr(
        "lib.research.__main__.ensure_image_server",
        lambda *a, **kw: None,
    )

    ns = _parse_args(["test"])
    await _amain(ns)

    cfg = captured_cfgs[0]
    # ResearchConfig defaults — proves the `if overrides:` guard works.
    assert cfg.max_iter_reasoner == 5
    assert cfg.max_iter_verifier == 3


# ---------------------------------------------------------------------------
# Slow integration test: cap=0 LLM-free CLI smoke
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_subprocess_smoke_with_max_iter_zero(tmp_path: Path) -> None:
    """End-to-end CLI with cap=0 — Reasoner+Verifier loops exit immediately, no LLM call.

    Exercises the actual `python -m omnigraph.research` entrypoint with
    --max-iter-reasoner 0 + --max-iter-verifier 0 + --no-grounding. The
    cap=0 path makes the Reasoner agent loop exit on the first iteration
    check (status="ok", iter_count=0), so no LLM provider is invoked. This
    is the L2 smoke specified in the plan's verification block.
    """
    (tmp_path / "lightrag_storage").mkdir()
    (tmp_path / "images").mkdir()
    env = os.environ.copy()
    env["OMNIGRAPH_BASE_DIR"] = str(tmp_path)
    env.setdefault("DEEPSEEK_API_KEY", "dummy")
    env.setdefault("GEMINI_API_KEY", "dummy")
    env["PYTHONIOENCODING"] = "utf-8"

    res = subprocess.run(
        [
            sys.executable, "-m", "omnigraph.research",
            "--max-iter-reasoner", "0",
            "--max-iter-verifier", "0",
            "--no-grounding",
            "test query",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert res.returncode == 0, (
        f"CLI exited {res.returncode}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )
    assert len(res.stdout) > 0, (
        f"stdout is empty:\nSTDERR:\n{res.stderr}"
    )

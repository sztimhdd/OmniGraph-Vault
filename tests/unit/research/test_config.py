"""Unit tests for lib.research.config.from_env() — env-once contract (Axis 3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.research.config import ResearchConfig, _skipped_web_search, from_env


@pytest.mark.unit
def test_from_env_returns_research_config(monkeypatch):
    monkeypatch.delenv("OMNIGRAPH_RESEARCH_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("OMNIGRAPH_RESEARCH_TELEMETRY_JSONL", raising=False)
    cfg = from_env()
    assert isinstance(cfg, ResearchConfig)


@pytest.mark.unit
def test_from_env_honors_omnigraph_base_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    cfg = from_env()
    assert cfg.rag_working_dir == tmp_path / "lightrag_storage"
    assert cfg.rag_working_dir.parent == tmp_path


@pytest.mark.unit
def test_from_env_default_path_uses_omonigraph_typo(monkeypatch):
    monkeypatch.delenv("OMNIGRAPH_BASE_DIR", raising=False)
    cfg = from_env()
    # Canonical typo — must be preserved per CLAUDE.md
    assert "omonigraph-vault" in str(cfg.rag_working_dir)


@pytest.mark.unit
def test_from_env_web_search_is_stub_when_tavily_unset(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    cfg = from_env()
    assert cfg.web_search is _skipped_web_search
    assert cfg.web_search("anything") == []


@pytest.mark.unit
def test_from_env_brave_fallback_is_none_when_unset(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    cfg = from_env()
    assert cfg.web_search_fallback is None


@pytest.mark.unit
def test_from_env_output_dir_none_when_unset(monkeypatch):
    monkeypatch.delenv("OMNIGRAPH_RESEARCH_OUTPUT_DIR", raising=False)
    cfg = from_env()
    assert cfg.output_dir is None


@pytest.mark.unit
def test_from_env_telemetry_jsonl_none_when_unset(monkeypatch):
    monkeypatch.delenv("OMNIGRAPH_RESEARCH_TELEMETRY_JSONL", raising=False)
    cfg = from_env()
    assert cfg.telemetry_jsonl is None


@pytest.mark.unit
def test_from_env_is_env_once_not_hot_path(monkeypatch, tmp_path):
    """Construction reads env. Hot path (cfg.rag_working_dir access) does NOT
    re-read env, so a later setenv is ignored on the existing cfg object.
    Re-calling from_env() picks up the new env value.
    """
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    cfg = from_env()
    old = cfg.rag_working_dir
    new_dir = tmp_path / "different"
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(new_dir))
    # cfg is frozen and value was captured at construction time
    assert cfg.rag_working_dir == old
    # New from_env() picks up the new env value
    cfg2 = from_env()
    assert cfg2.rag_working_dir == new_dir / "lightrag_storage"


@pytest.mark.unit
def test_from_env_default_iter_caps():
    cfg = from_env()
    assert cfg.max_iter_reasoner == 5
    assert cfg.max_iter_verifier == 3


@pytest.mark.unit
def test_skipped_web_search_returns_empty():
    assert _skipped_web_search("any query") == []


# Smoke import for orchestrator (Task 3) — ensures module loads cleanly.
@pytest.mark.unit
def test_orchestrator_imports_cleanly():
    import inspect

    from lib.research.orchestrator import research, research_stream

    assert inspect.iscoroutinefunction(research)
    assert inspect.isasyncgenfunction(research_stream)

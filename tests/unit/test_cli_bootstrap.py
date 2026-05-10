"""Pin guard semantics for lib.cli_bootstrap.bootstrap_cli (Defect A).

These tests reproduce config.py:65-69's intended guard semantics so any future
CLI bootstrap regression cannot reintroduce silent Vertex disable.
"""
from __future__ import annotations

import os

import pytest


# Names the helper must pop / preserve. Matches config.py:65-69 exactly.
_VERTEX_VARS = (
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)


def test_bootstrap_cli_pops_vertex_when_sa_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no GOOGLE_APPLICATION_CREDENTIALS set, all 4 vars must be popped.

    Mirrors config.py:65-69 default-Hermes path semantics.
    """
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    for var in _VERTEX_VARS:
        monkeypatch.setenv(var, "should-be-popped")

    from lib.cli_bootstrap import bootstrap_cli

    bootstrap_cli()

    for var in _VERTEX_VARS:
        assert var not in os.environ, f"{var} should have been popped when SA unset"


def test_bootstrap_cli_preserves_vertex_when_sa_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """With GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT set, vars MUST stay.

    The pre-fix breakage of Defect A: the 6 CLI scripts unconditionally popped
    or assigned GOOGLE_GENAI_USE_VERTEXAI=false, defeating the explicit
    opt-in. This test pins that bootstrap_cli now honors the opt-in.
    """
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-sa.json")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")

    from lib.cli_bootstrap import bootstrap_cli

    bootstrap_cli()

    assert os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") == "/tmp/fake-sa.json"
    assert os.environ.get("GOOGLE_CLOUD_PROJECT") == "my-proj"
    assert os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "true"
    assert os.environ.get("GOOGLE_CLOUD_LOCATION") == "global"


def test_bootstrap_cli_calls_load_env_via_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """bootstrap_cli must dispatch env loading to config.load_env (single source of truth)."""
    calls: list[int] = []

    def _fake_load_env() -> None:
        calls.append(1)

    # Patch the config attribute that lib.cli_bootstrap imports from.
    import lib.cli_bootstrap as cb
    monkeypatch.setattr(cb, "load_env", _fake_load_env)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    cb.bootstrap_cli()

    assert calls == [1], "bootstrap_cli must call config.load_env exactly once"


def test_bootstrap_cli_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling bootstrap_cli twice yields the same end state as calling once."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")

    from lib.cli_bootstrap import bootstrap_cli

    bootstrap_cli()
    bootstrap_cli()

    for var in _VERTEX_VARS:
        assert var not in os.environ


def test_is_vertex_mode_true_after_bootstrap_when_sa_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defect A regression test: bootstrap_cli MUST keep _is_vertex_mode() truthy.

    Pre-fix, the 6 CLI scripts assigned GOOGLE_GENAI_USE_VERTEXAI='false' or
    popped it, bypassing the lib.lightrag_embedding._is_vertex_mode() opt-in.
    This test pins the post-fix invariant.
    """
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-sa.json")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")

    from lib.cli_bootstrap import bootstrap_cli

    bootstrap_cli()

    from lib.lightrag_embedding import _is_vertex_mode

    assert _is_vertex_mode() is True

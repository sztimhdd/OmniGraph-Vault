"""Unit tests for scripts/vertex_live_probe.py — HYG-01 (Phase 18-00).

Probe contract (2026-05-03 correction): a 2×3 matrix over
(global, us-central1) × (gemini-embedding-2, gemini-embedding-2-preview,
gemini-embedding-001). Alert logic is driven by a ``known_good`` expectation
table in the probe module; only known-good combos returning 404 trigger a
Telegram alert (known-bad 404s are silent and expected).

All mocked. No live network, no live Vertex, no live Telegram. Runs on
Windows inside the corp Umbrella sandbox.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest


# --- Helpers ---------------------------------------------------------------

PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "vertex_live_probe.py"


def _load_probe_module() -> ModuleType:
    """Import scripts/vertex_live_probe.py as a module."""
    spec = importlib.util.spec_from_file_location("vertex_live_probe", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_fake_client_factory(
    behavior_by_loc: dict[str, dict[str, int | Exception]],
) -> MagicMock:
    """Return a fake ``genai.Client`` factory that dispatches by location kwarg.

    ``behavior_by_loc[location][model]`` = int (dims) for success, or an
    Exception instance to raise.
    """

    def _factory(*args, **kwargs):
        loc = kwargs.get("location", "us-central1")
        loc_behavior = behavior_by_loc.get(loc, {})

        async def embed_content(*, model: str, contents):
            outcome = loc_behavior.get(model)
            if isinstance(outcome, Exception):
                raise outcome
            if isinstance(outcome, int):
                embedding = SimpleNamespace(values=[0.0] * outcome)
                return SimpleNamespace(embeddings=[embedding])
            raise RuntimeError(
                f"test bug: no behavior configured for ({loc!r}, {model!r})"
            )

        client = MagicMock()
        client.aio.models.embed_content = embed_content
        return client

    return MagicMock(side_effect=_factory)


def _install_fake_google_genai(monkeypatch, client_factory: MagicMock) -> None:
    """Install fake ``google.genai.Client`` factory into sys.modules."""
    fake_module = ModuleType("google.genai")
    fake_module.Client = client_factory  # type: ignore[attr-defined]
    google_pkg = ModuleType("google")
    google_pkg.genai = fake_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.genai", fake_module)


# --- Tests -----------------------------------------------------------------

def test_all_expected_combos_green_exits_zero(monkeypatch, capsys):
    """Every known-good combo OK, every known-bad combo 404 → rc=0, no alert."""
    probe = _load_probe_module()
    factory = _make_fake_client_factory(
        {
            "global": {
                "gemini-embedding-2": 3072,
                "gemini-embedding-2-preview": RuntimeError("404 NOT_FOUND"),
                "gemini-embedding-001": 768,
            },
            "us-central1": {
                "gemini-embedding-2": RuntimeError("404 NOT_FOUND"),
                "gemini-embedding-2-preview": 3072,
                "gemini-embedding-001": 768,
            },
        }
    )
    _install_fake_google_genai(monkeypatch, factory)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    telegram_calls: list[str] = []
    monkeypatch.setattr(
        probe, "send_telegram", lambda m: telegram_calls.append(m) or True
    )
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py"])

    rc = probe.main()

    assert rc == 0
    assert telegram_calls == []
    out = capsys.readouterr().out
    assert "[OK]" in out
    # Factory was called once per location (2 total).
    assert factory.call_count == 2


def test_known_good_combo_404_triggers_alert(monkeypatch, capsys):
    """If (global, gemini-embedding-2) 404s → rc=1, Telegram fires."""
    probe = _load_probe_module()
    factory = _make_fake_client_factory(
        {
            "global": {
                "gemini-embedding-2": RuntimeError("404 NOT_FOUND"),
                "gemini-embedding-2-preview": RuntimeError("404"),
                "gemini-embedding-001": 768,
            },
            "us-central1": {
                "gemini-embedding-2": RuntimeError("404"),
                "gemini-embedding-2-preview": 3072,
                "gemini-embedding-001": 768,
            },
        }
    )
    _install_fake_google_genai(monkeypatch, factory)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    telegram_calls: list[str] = []
    monkeypatch.setattr(
        probe, "send_telegram", lambda m: telegram_calls.append(m) or True
    )
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py"])

    rc = probe.main()

    assert rc == 1
    assert len(telegram_calls) == 1
    assert "Vertex AI embedding probe FAILED" in telegram_calls[0]
    assert "global" in telegram_calls[0]
    assert "gemini-embedding-2" in telegram_calls[0]


def test_known_bad_404_is_silent(monkeypatch, capsys):
    """(global, -preview) 404 alone is expected — rc=0, no alert."""
    probe = _load_probe_module()
    # Every known-good combo succeeds; known-bad combos 404 as expected.
    factory = _make_fake_client_factory(
        {
            "global": {
                "gemini-embedding-2": 3072,
                "gemini-embedding-2-preview": RuntimeError("404"),
                "gemini-embedding-001": 768,
            },
            "us-central1": {
                "gemini-embedding-2": RuntimeError("404"),
                "gemini-embedding-2-preview": 3072,
                "gemini-embedding-001": 768,
            },
        }
    )
    _install_fake_google_genai(monkeypatch, factory)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    telegram_calls: list[str] = []
    monkeypatch.setattr(
        probe, "send_telegram", lambda m: telegram_calls.append(m) or True
    )
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py"])

    rc = probe.main()

    assert rc == 0
    assert telegram_calls == []


def test_no_telegram_flag_suppresses_delivery(monkeypatch, capsys):
    """--no-telegram suppresses delivery even when alert would fire."""
    probe = _load_probe_module()
    factory = _make_fake_client_factory(
        {
            "global": {
                "gemini-embedding-2": RuntimeError("404"),
                "gemini-embedding-2-preview": RuntimeError("404"),
                "gemini-embedding-001": RuntimeError("404"),
            },
            "us-central1": {
                "gemini-embedding-2": RuntimeError("404"),
                "gemini-embedding-2-preview": RuntimeError("404"),
                "gemini-embedding-001": RuntimeError("404"),
            },
        }
    )
    _install_fake_google_genai(monkeypatch, factory)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    telegram_calls: list[str] = []
    monkeypatch.setattr(
        probe, "send_telegram", lambda m: telegram_calls.append(m) or True
    )
    monkeypatch.setattr(
        sys, "argv", ["vertex_live_probe.py", "--no-telegram"]
    )

    rc = probe.main()

    assert rc == 1
    assert telegram_calls == []


def test_json_output_schema(monkeypatch, capsys):
    """--json emits a list of 6 dicts with (loc, model, dims, error, expected_ok, alert)."""
    probe = _load_probe_module()
    factory = _make_fake_client_factory(
        {
            "global": {
                "gemini-embedding-2": 3072,
                "gemini-embedding-2-preview": RuntimeError("404"),
                "gemini-embedding-001": 768,
            },
            "us-central1": {
                "gemini-embedding-2": RuntimeError("404"),
                "gemini-embedding-2-preview": 3072,
                "gemini-embedding-001": 768,
            },
        }
    )
    _install_fake_google_genai(monkeypatch, factory)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    monkeypatch.setattr(probe, "send_telegram", lambda m: True)
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py", "--json"])

    rc = probe.main()

    assert rc == 0
    captured = capsys.readouterr().out
    start = captured.find("[")
    assert start >= 0
    end = captured.rfind("]")
    payload = json.loads(captured[start : end + 1])
    assert isinstance(payload, list)
    assert len(payload) == 6
    expected_keys = {"loc", "model", "dims", "error", "expected_ok", "alert"}
    for entry in payload:
        assert set(entry.keys()) == expected_keys


def test_missing_project_env_raises(monkeypatch):
    probe = _load_probe_module()
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    factory = _make_fake_client_factory({})
    _install_fake_google_genai(monkeypatch, factory)
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py"])

    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT unset"):
        probe.main()


def test_known_good_dict_matches_spec():
    """The known_good dict must match the user-spec'd 6-entry matrix verbatim."""
    probe = _load_probe_module()
    assert probe.known_good == {
        ("global", "gemini-embedding-2"): True,
        ("global", "gemini-embedding-2-preview"): False,
        ("global", "gemini-embedding-001"): True,
        ("us-central1", "gemini-embedding-2"): False,
        ("us-central1", "gemini-embedding-2-preview"): True,
        ("us-central1", "gemini-embedding-001"): True,
    }

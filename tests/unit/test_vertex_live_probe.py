"""Unit tests for scripts/vertex_live_probe.py — HYG-01 (Phase 18-00).

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


def _make_fake_client(behavior: dict[str, int | Exception]) -> MagicMock:
    """Build a fake genai.Client whose aio.models.embed_content honours behavior.

    behavior maps model-name to either an int (dims) for success, or an
    Exception instance to raise.
    """
    async def embed_content(*, model: str, contents):
        outcome = behavior.get(model)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, int):
            embedding = SimpleNamespace(values=[0.0] * outcome)
            return SimpleNamespace(embeddings=[embedding])
        raise RuntimeError(f"test bug: no behavior configured for {model!r}")

    client = MagicMock()
    client.aio.models.embed_content = embed_content
    return client


def _install_fake_google_genai(monkeypatch, fake_client: MagicMock) -> None:
    """Install fake google.genai.Client factory into sys.modules."""
    fake_module = ModuleType("google.genai")
    fake_module.Client = MagicMock(return_value=fake_client)  # type: ignore[attr-defined]
    google_pkg = ModuleType("google")
    google_pkg.genai = fake_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.genai", fake_module)


# --- Tests -----------------------------------------------------------------

def test_all_green_exits_zero(monkeypatch, capsys):
    probe = _load_probe_module()
    fake_client = _make_fake_client({
        "gemini-embedding-2": 3072,
        "gemini-embedding-2-preview": 3072,
        "gemini-embedding-001": 768,
    })
    _install_fake_google_genai(monkeypatch, fake_client)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    telegram_calls: list[str] = []
    monkeypatch.setattr(probe, "send_telegram", lambda m: telegram_calls.append(m) or True)
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py"])

    rc = probe.main()

    assert rc == 0
    assert telegram_calls == []
    out = capsys.readouterr().out
    assert "gemini-embedding-2" in out
    assert "[OK]" in out


def test_all_404_exits_one_and_sends_telegram(monkeypatch, capsys):
    probe = _load_probe_module()
    fake_client = _make_fake_client({
        "gemini-embedding-2": RuntimeError("404 NOT_FOUND"),
        "gemini-embedding-2-preview": RuntimeError("404 NOT_FOUND"),
        "gemini-embedding-001": RuntimeError("404 NOT_FOUND"),
    })
    _install_fake_google_genai(monkeypatch, fake_client)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    telegram_calls: list[str] = []
    monkeypatch.setattr(probe, "send_telegram", lambda m: telegram_calls.append(m) or True)
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py"])

    rc = probe.main()

    assert rc == 1
    assert len(telegram_calls) == 1
    assert "🔴" in telegram_calls[0]
    assert "Vertex AI embedding probe FAILED" in telegram_calls[0]


def test_partial_green_first_bad_second_good_exits_zero(monkeypatch, capsys):
    probe = _load_probe_module()
    fake_client = _make_fake_client({
        "gemini-embedding-2": RuntimeError("404"),
        "gemini-embedding-2-preview": 3072,
        "gemini-embedding-001": 768,
    })
    _install_fake_google_genai(monkeypatch, fake_client)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    telegram_calls: list[str] = []
    monkeypatch.setattr(probe, "send_telegram", lambda m: telegram_calls.append(m) or True)
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py"])

    rc = probe.main()

    assert rc == 0
    assert telegram_calls == []


def test_no_telegram_flag_suppresses_delivery_on_all_404(monkeypatch, capsys):
    probe = _load_probe_module()
    fake_client = _make_fake_client({
        "gemini-embedding-2": RuntimeError("404"),
        "gemini-embedding-2-preview": RuntimeError("404"),
        "gemini-embedding-001": RuntimeError("404"),
    })
    _install_fake_google_genai(monkeypatch, fake_client)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    telegram_calls: list[str] = []
    monkeypatch.setattr(probe, "send_telegram", lambda m: telegram_calls.append(m) or True)
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py", "--no-telegram"])

    rc = probe.main()

    assert rc == 1
    assert telegram_calls == []


def test_json_output_schema(monkeypatch, capsys):
    probe = _load_probe_module()
    fake_client = _make_fake_client({
        "gemini-embedding-2": 3072,
        "gemini-embedding-2-preview": RuntimeError("404"),
        "gemini-embedding-001": 768,
    })
    _install_fake_google_genai(monkeypatch, fake_client)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "probe-test-project")
    monkeypatch.setattr(probe, "send_telegram", lambda m: True)
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py", "--json"])

    rc = probe.main()

    assert rc == 0
    captured = capsys.readouterr().out
    # Find the JSON payload (the leading list). Skip any trailing [OK] line.
    # argparse may print before; safe approach: locate the first "[" and parse forward.
    start = captured.find("[")
    assert start >= 0
    end = captured.rfind("]")
    payload = json.loads(captured[start:end + 1])
    assert isinstance(payload, list)
    assert len(payload) == 3
    for entry in payload:
        assert set(entry.keys()) == {"model", "dims", "error"}


def test_missing_project_env_raises(monkeypatch):
    probe = _load_probe_module()
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    fake_client = _make_fake_client({})
    _install_fake_google_genai(monkeypatch, fake_client)
    monkeypatch.setattr(sys, "argv", ["vertex_live_probe.py"])

    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT unset"):
        probe.main()

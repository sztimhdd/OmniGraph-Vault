"""Unit tests for enrichment.extract_questions — D-12 grounding, D-03 contract.

All tests are LLM-free: google.genai.Client is mocked entirely.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _set_gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def _patch_lib_generate(mocker, return_text: str):
    """Phase 7 D-06: patch lib.llm_client.generate (async; called by generate_sync).

    Captures call kwargs so tests can inspect the ``config=`` kwarg passed
    through config.gemini_call → lib.generate_sync → lib.generate.
    """
    async def _fake(model, contents, **kwargs):
        _fake.last_call = {"model": model, "contents": contents, "kwargs": kwargs}
        return return_text

    _fake.last_call = None
    mocker.patch("lib.llm_client.generate", side_effect=_fake)
    return _fake


@pytest.mark.unit
def test_extract_questions_calls_google_search_tool(mocker, monkeypatch):
    """D-12: the google_search grounding tool must be attached to the request."""
    monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "1")
    # Re-import to pick up env var (module-level constant)
    import importlib
    import enrichment.extract_questions as eq
    importlib.reload(eq)

    fake_gen = _patch_lib_generate(mocker, '[{"question": "q1", "context": "c1"}]')

    result = eq.extract_questions("a" * 3000, max_q=2)

    assert result == [{"question": "q1", "context": "c1"}]
    config = fake_gen.last_call["kwargs"].get("config")
    assert config is not None, "config must be passed through to lib.generate"
    assert config.tools, "tools must be non-empty when grounding is enabled"
    tool_types = [type(t.google_search).__name__ for t in config.tools if hasattr(t, "google_search") and t.google_search is not None]
    assert any(t == "GoogleSearch" for t in tool_types), (
        f"Expected GoogleSearch tool in config.tools; found: {[type(t).__name__ for t in config.tools]}"
    )


@pytest.mark.unit
def test_extract_questions_skips_grounding_when_disabled(mocker, monkeypatch):
    """When ENRICHMENT_GROUNDING_ENABLED=0, no tools should be passed."""
    monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "0")
    import importlib
    import enrichment.extract_questions as eq
    importlib.reload(eq)

    fake_gen = _patch_lib_generate(mocker, '[{"question": "q1", "context": "c1"}]')

    result = eq.extract_questions("a" * 3000, max_q=2)

    assert result == [{"question": "q1", "context": "c1"}]
    config = fake_gen.last_call["kwargs"].get("config")
    assert config is None or not getattr(config, "tools", None), (
        "No tools should be passed when grounding is disabled"
    )


@pytest.mark.unit
def test_extract_questions_respects_max_q(mocker, monkeypatch):
    """max_q truncates the returned list."""
    monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "0")
    import importlib
    import enrichment.extract_questions as eq
    importlib.reload(eq)

    # Return 4 items; max_q=3 should truncate
    _patch_lib_generate(
        mocker,
        '[{"question":"q1","context":"c1"},'
        '{"question":"q2","context":"c2"},'
        '{"question":"q3","context":"c3"},'
        '{"question":"q4","context":"c4"}]',
    )

    result = eq.extract_questions("a" * 3000, max_q=3)
    assert len(result) == 3


@pytest.mark.unit
def test_cli_short_article_returns_skipped(tmp_path: Path, capsys):
    """Articles under ENRICHMENT_MIN_LENGTH chars must skip with exit 0."""
    from enrichment.extract_questions import main

    article = tmp_path / "short.md"
    article.write_text("tiny")  # << 2000 chars

    rc = main([str(article), "--hash", "h1", "--base-dir", str(tmp_path)])

    captured = capsys.readouterr()
    out = json.loads(captured.out.strip())
    assert rc == 0
    assert out["status"] == "skipped"
    assert out["reason"] == "too_short"
    assert out["hash"] == "h1"
    assert out["char_count"] == len("tiny")


@pytest.mark.unit
def test_cli_success_writes_atomic_json(tmp_path: Path, mocker, capsys, monkeypatch):
    """Happy path: questions.json written atomically, no .tmp leftover, stdout ok."""
    monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "0")

    _patch_lib_generate(mocker, '[{"question":"Q","context":"C"}]')

    from enrichment.extract_questions import main

    article = tmp_path / "a.md"
    article.write_text("x" * 2500)

    rc = main([str(article), "--hash", "abcd", "--base-dir", str(tmp_path)])

    captured = capsys.readouterr()
    out = json.loads(captured.out.strip())
    assert rc == 0
    assert out["status"] == "ok"
    assert out["question_count"] == 1
    assert out["hash"] == "abcd"

    # Verify questions.json content
    qjson_path = tmp_path / "abcd" / "questions.json"
    assert qjson_path.exists(), "questions.json must be written"
    qjson = json.loads(qjson_path.read_text(encoding="utf-8"))
    assert qjson["hash"] == "abcd"
    assert qjson["questions"] == [{"question": "Q", "context": "C"}]

    # Verify no leftover .tmp files (atomic write)
    tmp_files = list((tmp_path / "abcd").glob("*.tmp"))
    assert not tmp_files, f"Leftover .tmp files found: {tmp_files}"


@pytest.mark.unit
def test_cli_gemini_error_returns_1(tmp_path: Path, mocker, capsys, monkeypatch):
    """Gemini API errors must produce exit 1 and status=error JSON on stdout."""
    monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "0")

    async def _boom(*a, **kw):
        raise RuntimeError("boom")

    mocker.patch("lib.llm_client.generate", side_effect=_boom)

    from enrichment.extract_questions import main

    article = tmp_path / "a.md"
    article.write_text("x" * 2500)

    rc = main([str(article), "--hash", "e1", "--base-dir", str(tmp_path)])

    captured = capsys.readouterr()
    out = json.loads(captured.out.strip())
    assert rc == 1
    assert out["status"] == "error"
    assert "boom" in out["error"]


@pytest.mark.unit
def test_cli_output_line_under_50kb(tmp_path: Path, capsys):
    """D-03: Hermes tool_output.max_bytes cap = 50000; stdout must be single-line < 50KB."""
    from enrichment.extract_questions import main

    article = tmp_path / "short.md"
    article.write_text("tiny")  # triggers skip path — no Gemini call needed

    main([str(article), "--hash", "h1", "--base-dir", str(tmp_path)])

    line = capsys.readouterr().out.strip()
    assert len(line.encode("utf-8")) < 50_000, "stdout must be under 50KB"
    assert "\n" not in line, "stdout must be a single line (no embedded newlines)"

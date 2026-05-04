"""Unit tests for lib.vertex_gemini_complete (LDEV-01).

Mock-only — zero outbound HTTP. Patches google.genai.Client so no SA auth
or network traffic is ever attempted.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from google.genai.errors import ServerError


# --- Helpers ---------------------------------------------------------------


def _make_server_error(code: int) -> ServerError:
    """Build a ServerError instance with the given HTTP-ish code."""
    return ServerError(
        code,
        {"error": {"code": code, "message": "mocked"}},
        None,
    )


def _make_fake_response(text: str = "hello from vertex") -> MagicMock:
    """Fake google-genai GenerateContentResponse with a .text attribute."""
    resp = MagicMock()
    resp.text = text
    return resp


def _install_client_mock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    generate_side_effect: Any = None,
    generate_return_value: Any = None,
) -> tuple[MagicMock, MagicMock]:
    """Patch lib.vertex_gemini_complete.genai.Client to return a fake client
    whose ``aio.models.generate_content`` is an AsyncMock.

    Returns (client_ctor_mock, generate_content_mock).
    """
    import lib.vertex_gemini_complete as m

    generate_content = AsyncMock()
    if generate_side_effect is not None:
        generate_content.side_effect = generate_side_effect
    if generate_return_value is not None:
        generate_content.return_value = generate_return_value

    client_instance = MagicMock()
    client_instance.aio = MagicMock()
    client_instance.aio.models = MagicMock()
    client_instance.aio.models.generate_content = generate_content

    client_ctor = MagicMock(return_value=client_instance)
    monkeypatch.setattr(m.genai, "Client", client_ctor)
    return client_ctor, generate_content


def _set_vertex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the required Vertex SA env vars for calls to succeed past
    the _require_project() guard."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-sa.json")


# --- Tests -----------------------------------------------------------------


def test_model_name_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset OMNIGRAPH_LLM_MODEL → default gemini-3.1-flash-lite-preview."""
    _set_vertex_env(monkeypatch)
    monkeypatch.delenv("OMNIGRAPH_LLM_MODEL", raising=False)
    _, gen = _install_client_mock(
        monkeypatch, generate_return_value=_make_fake_response("ok"),
    )
    from lib.vertex_gemini_complete import vertex_gemini_model_complete

    asyncio.run(vertex_gemini_model_complete("hi"))
    gen.assert_called_once()
    kwargs = gen.call_args.kwargs
    assert kwargs["model"] == "gemini-3.1-flash-lite-preview"


def test_model_name_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """OMNIGRAPH_LLM_MODEL=custom-model-id propagates to generate_content."""
    _set_vertex_env(monkeypatch)
    monkeypatch.setenv("OMNIGRAPH_LLM_MODEL", "custom-model-id")
    _, gen = _install_client_mock(
        monkeypatch, generate_return_value=_make_fake_response("ok"),
    )
    from lib.vertex_gemini_complete import vertex_gemini_model_complete

    asyncio.run(vertex_gemini_model_complete("hi"))
    assert gen.call_args.kwargs["model"] == "custom-model-id"


def test_contents_role_alternation(monkeypatch: pytest.MonkeyPatch) -> None:
    """system_prompt + history_messages + prompt get translated with
    correct user/model role alternation and the final item is the prompt."""
    _set_vertex_env(monkeypatch)
    _, gen = _install_client_mock(
        monkeypatch, generate_return_value=_make_fake_response("ok"),
    )
    from lib.vertex_gemini_complete import vertex_gemini_model_complete

    asyncio.run(vertex_gemini_model_complete(
        "P",
        system_prompt="S",
        history_messages=[
            {"role": "user", "content": "U1"},
            {"role": "model", "content": "M1"},
        ],
    ))

    contents = gen.call_args.kwargs["contents"]
    assert len(contents) == 4  # system → U1 → M1 → P
    # role alternation: [user (system), user (U1), model (M1), user (P)]
    roles = [c.role for c in contents]
    assert roles == ["user", "user", "model", "user"]
    # final part is the prompt
    assert contents[-1].parts[0].text == "P"
    # first part is the system prompt (folded as user turn)
    assert contents[0].parts[0].text == "S"


def test_retry_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three 503s followed by success → function returns on attempt 4."""
    _set_vertex_env(monkeypatch)
    fake_ok = _make_fake_response("recovered")
    _, gen = _install_client_mock(
        monkeypatch,
        generate_side_effect=[
            _make_server_error(503),
            _make_server_error(503),
            _make_server_error(503),
            fake_ok,
        ],
    )

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    with patch("lib.vertex_gemini_complete.asyncio.sleep", new=fake_sleep):
        from lib.vertex_gemini_complete import vertex_gemini_model_complete
        text = asyncio.run(vertex_gemini_model_complete("x"))

    assert text == "recovered"
    assert gen.call_count == 4
    assert sleeps == [2, 4, 8]


def test_retry_gives_up_after_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Four consecutive 503s → ServerError re-raised; 4 total attempts."""
    _set_vertex_env(monkeypatch)
    _, gen = _install_client_mock(
        monkeypatch,
        generate_side_effect=[
            _make_server_error(503),
            _make_server_error(503),
            _make_server_error(503),
            _make_server_error(503),
        ],
    )

    async def fake_sleep(_: float) -> None:
        return None

    with patch("lib.vertex_gemini_complete.asyncio.sleep", new=fake_sleep):
        from lib.vertex_gemini_complete import vertex_gemini_model_complete
        with pytest.raises(ServerError):
            asyncio.run(vertex_gemini_model_complete("x"))

    assert gen.call_count == 4


def test_non_503_propagates_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """500 ServerError → raises on first call, no retries."""
    _set_vertex_env(monkeypatch)
    _, gen = _install_client_mock(
        monkeypatch,
        generate_side_effect=[_make_server_error(500)],
    )

    async def fake_sleep(_: float) -> None:
        return None

    with patch("lib.vertex_gemini_complete.asyncio.sleep", new=fake_sleep):
        from lib.vertex_gemini_complete import vertex_gemini_model_complete
        with pytest.raises(ServerError):
            asyncio.run(vertex_gemini_model_complete("x"))

    assert gen.call_count == 1


def test_timeout_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    """OMNIGRAPH_LLM_TIMEOUT_SEC=42 → HttpOptions timeout=42000 ms reaches config."""
    _set_vertex_env(monkeypatch)
    monkeypatch.setenv("OMNIGRAPH_LLM_TIMEOUT_SEC", "42")
    _, gen = _install_client_mock(
        monkeypatch, generate_return_value=_make_fake_response("ok"),
    )
    from lib.vertex_gemini_complete import vertex_gemini_model_complete

    asyncio.run(vertex_gemini_model_complete("x"))
    cfg = gen.call_args.kwargs["config"]
    # SDK expresses HTTP timeout in milliseconds; we convert seconds→ms internally.
    assert cfg.http_options.timeout == 42 * 1000


def test_keyword_extraction_kwarg_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """keyword_extraction=True is accepted and silently ignored."""
    _set_vertex_env(monkeypatch)
    _, gen = _install_client_mock(
        monkeypatch, generate_return_value=_make_fake_response("ok"),
    )
    from lib.vertex_gemini_complete import vertex_gemini_model_complete

    text = asyncio.run(vertex_gemini_model_complete("x", keyword_extraction=True))
    assert text == "ok"
    gen.assert_called_once()


def test_missing_project_raises_runtimeerror(monkeypatch: pytest.MonkeyPatch) -> None:
    """GOOGLE_CLOUD_PROJECT unset → RuntimeError with clear diagnostic."""
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    # No client mock needed — _require_project() fires before client construction.
    from lib.vertex_gemini_complete import vertex_gemini_model_complete

    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
        asyncio.run(vertex_gemini_model_complete("x"))


def test_location_default_global(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset GOOGLE_CLOUD_LOCATION → genai.Client called with location='global'."""
    _set_vertex_env(monkeypatch)
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)
    client_ctor, _ = _install_client_mock(
        monkeypatch, generate_return_value=_make_fake_response("ok"),
    )
    from lib.vertex_gemini_complete import vertex_gemini_model_complete

    asyncio.run(vertex_gemini_model_complete("x"))
    client_ctor.assert_called_once()
    kwargs = client_ctor.call_args.kwargs
    assert kwargs["location"] == "global"
    assert kwargs["vertexai"] is True
    assert kwargs["project"] == "test-project"

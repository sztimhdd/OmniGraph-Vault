"""Offline contract tests for the explicitly selected Hermes experiment."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import textwrap
import traceback
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGRAPH_LOAD_ENV", "0")
    for name in tuple(sys.modules):
        if name == "lib" or name.startswith("lib."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    package = type(sys)("lib")
    package.__path__ = [str(_ROOT / "lib")]
    monkeypatch.setitem(sys.modules, "lib", package)


def _load_module(name: str):
    path = _ROOT / "lib" / f"{name.rsplit('.', 1)[-1]}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _hermes():
    return _load_module("lib.llm_hermes")


def _fake_hermes(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "fake-hermes"
    legacy = textwrap.dedent(body)
    path.write_text(
        "#!" + sys.executable + "\n" + textwrap.dedent(f'''\
        import contextlib, io, json, sys, tempfile
        args = sys.argv[1:]
        prompt = open(args[args.index("--prompt-file") + 1], encoding="utf-8").read()
        result_path = args[args.index("--result-file") + 1]
        usage_path = tempfile.mktemp(prefix="usage-")
        legacy_args = ["-z", prompt, "--provider", args[args.index("--provider") + 1],
                       "--model", args[args.index("--model") + 1], "--toolsets", "bot_room",
                       "--usage-file", usage_path, "--in", tempfile.mkdtemp()]
        old_argv = sys.argv
        sys.argv = [old_argv[0]] + legacy_args
        output = io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(output):
                exec({legacy!r}, {{"__name__": "__main__"}})
        except SystemExit as exc:
            code = int(exc.code or 0)
        finally:
            sys.argv = old_argv
        try:
            usage = json.load(open(usage_path, encoding="utf-8"))
        except Exception:
            usage = None
        result = {{"ok": code == 0, "text": output.getvalue(), "usage": usage,
                  "failure": None if code == 0 else {{"code": "fake_failed"}},
                  "initialization": {{"fallback_chain_count": 0, "tools_count": 0, "tool_names": [], "platform": "subagent", "session_db_none": True, "session_id_none": True}}}}
        json.dump(result, open(result_path, "w", encoding="utf-8"))
        raise SystemExit(code)
        '''), encoding="utf-8"
    )
    path.chmod(0o755)
    return path


def _usage_from_argv(argv: list[str]) -> Path:
    return Path(argv[argv.index("--usage-file") + 1])


def _run(callback, *args, **kwargs):
    return asyncio.run(callback(*args, **kwargs))


def test_success_preserves_full_stdout_and_serializes_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_hermes(
        tmp_path,
        """
        import json, sys
        args = sys.argv[1:]
        assert args[0] == "-z"
        assert "--resume" not in args
        assert args[args.index("--toolsets") + 1] == "bot_room"
        assert args[args.index("--provider") + 1] == "openai-codex"
        assert args[args.index("--model") + 1] == "gpt-6-astra"
        rendered = json.loads(args[1])
        assert rendered["system_prompt"] == "sys \\\" quoted"
        assert rendered["history_messages"] == [{"role": "user", "content": "past"}]
        usage = args[args.index("--usage-file") + 1]
        with open(usage, "w", encoding="utf-8") as f:
            json.dump({"provider": "openai-codex", "model": "gpt-6-astra", "failed": False}, f)
        sys.stdout.write("first line\\nsecond \\\"line\\\"\\n")
        """,
    )
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    hermes_model_complete = _hermes().hermes_model_complete

    assert _run(
        hermes_model_complete,
        'say "hello"',
        system_prompt='sys " quoted',
        history_messages=[{"role": "user", "content": "past"}],
    ) == 'first line\nsecond "line"\n'


def test_completion_with_usage_returns_only_allowlisted_observability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if the production API loses real usage or retains unrelated fields."""
    fake = _fake_hermes(
        tmp_path,
        """
        import json, sys
        usage = sys.argv[sys.argv.index("--usage-file") + 1]
        with open(usage, "w", encoding="utf-8") as f:
            json.dump({
                "provider": "openai-codex", "model": "gpt-6-astra", "completed": True, "failed": False,
                "session_id": "session-123", "service_tier": "standard", "cost_status": "estimated",
                "cost_source": "provider-meter", "api_calls": 2, "input_tokens": 11,
                "output_tokens": 7, "cache_read_tokens": 3, "cache_write_tokens": 2,
                "reasoning_tokens": 5, "total_tokens": 28, "estimated_cost_usd": 0.01,
                "duration_ms": 123, "cost_usd": 0.01,
                "credential": "must-not-escape", "stderr": "private detail"
            }, f)
        print("actual output")
        """,
    )
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    result = _run(_hermes().hermes_model_complete_with_usage, "safe prompt")

    assert result.text == "actual output\n"
    assert result.usage == {
        "provider": "openai-codex", "model": "gpt-6-astra", "completed": True, "failed": False,
        "session_id": "session-123", "service_tier": "standard", "cost_status": "estimated",
        "cost_source": "provider-meter", "api_calls": 2, "input_tokens": 11,
        "output_tokens": 7, "cache_read_tokens": 3, "cache_write_tokens": 2,
        "reasoning_tokens": 5, "total_tokens": 28, "estimated_cost_usd": 0.01,
        "duration_ms": 123, "cost_usd": 0.01,
    }


@pytest.mark.parametrize(
    "body, expected",
    [
        ("""
        import json, sys
        with open(sys.argv[sys.argv.index("--usage-file") + 1], "w") as f: json.dump({"provider":"openai-codex","model":"gpt-6-astra","failed":True}, f)
        print("text that must not be accepted")
        """, "failed=True"),
        ("""
        import json, sys
        with open(sys.argv[sys.argv.index("--usage-file") + 1], "w") as f: json.dump({"provider":"openai-codex","model":"gpt-6-astra","failed":False}, f)
        print("secret stdout")
        sys.exit(7)
        """, "exit=7"),
        ("""
        print("secret stdout")
        """, "usage=missing"),
        ("""
        import sys
        open(sys.argv[sys.argv.index("--usage-file") + 1], "w").write("[")
        print("secret stdout")
        """, "usage=missing"),
        ("""
        import json, sys
        with open(sys.argv[sys.argv.index("--usage-file") + 1], "w") as f: json.dump({"provider":"openai-codex","model":"gpt-6-astra","failed":False}, f)
        print("   ")
        """, "stdout=blank"),
        ("""
        import json, sys
        with open(sys.argv[sys.argv.index("--usage-file") + 1], "w") as f: json.dump({"provider":"other","model":"gpt-6-astra","failed":False}, f)
        print("secret stdout")
        """, "route=mismatch"),
    ],
)
def test_rejects_invalid_run_without_leaking_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str, expected: str
) -> None:
    fake = _fake_hermes(tmp_path, body)
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    hermes = _hermes()
    HermesCompletionError, hermes_model_complete = hermes.HermesCompletionError, hermes.hermes_model_complete

    with pytest.raises(HermesCompletionError) as exc:
        _run(hermes_model_complete, "private prompt")
    message = str(exc.value)
    assert expected in message
    assert "parent_timeout=False" in message
    assert "private prompt" not in message
    assert "secret stdout" not in message


def test_route_mismatch_carries_allowlisted_usage_and_completed_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if an observed route mismatch destroys the only safe diagnosis receipt."""
    fake = _fake_hermes(
        tmp_path,
        '''
        import json, sys
        usage = sys.argv[sys.argv.index("--usage-file") + 1]
        with open(usage, "w", encoding="utf-8") as f:
            json.dump({"provider": "unexpected", "model": "gpt-6-astra", "failed": False,
                       "api_calls": 1, "credential": "must-not-escape"}, f)
        print("completed diagnostic output")
        ''',
    )
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    hermes = _hermes()

    with pytest.raises(hermes.HermesCompletionError) as exc:
        _run(hermes.hermes_model_complete_with_usage, "private prompt")

    assert exc.value.failure_code == "route_mismatch"
    assert exc.value.stdout == "completed diagnostic output\n"
    assert exc.value.usage == {
        "provider": "unexpected", "model": "gpt-6-astra", "failed": False, "api_calls": 1
    }


def test_known_usage_field_with_invalid_type_rejects_completed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if live usage silently erases a malformed known meter field."""
    fake = _fake_hermes(
        tmp_path,
        '''
        import json, sys
        usage = sys.argv[sys.argv.index("--usage-file") + 1]
        with open(usage, "w", encoding="utf-8") as f:
            json.dump({"provider": "openai-codex", "model": "gpt-6-astra", "failed": False,
                       "cache_read_tokens": "three"}, f)
        print("completed output")
        ''',
    )
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    hermes = _hermes()

    with pytest.raises(hermes.HermesCompletionError, match="usage schema"):
        _run(hermes.hermes_model_complete_with_usage, "safe prompt")


def test_native_initialization_receipt_keeps_only_safe_trace_coordinates():
    hermes = _hermes()
    code, initialization, details = hermes._native_receipt({"failure": {"code": "native_initialization_failed", "stage": "create_agent", "exception_type": "AttributeError", "traceback": {"basename": "runner.py", "function": "create_agent", "line": 35}, "message": "secret", "token": "secret"}})
    assert code == "native_initialization_failed"
    assert initialization is None
    assert details == {"stage": "create_agent", "exception_type": "AttributeError", "traceback_basename": "runner.py", "traceback_function": "create_agent", "traceback_line": 35}


def test_missing_binary_stream_multimodal_and_oversize_reject(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OMNIGRAPH_HERMES_PYTHON", raising=False)
    hermes = _hermes()
    HermesCompletionError, hermes_model_complete = hermes.HermesCompletionError, hermes.hermes_model_complete

    with pytest.raises(HermesCompletionError, match="native runtime"):
        _run(hermes_model_complete, "x")
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", "/definitely/missing/hermes")
    with pytest.raises(HermesCompletionError, match="stream"):
        _run(hermes_model_complete, "x", stream=True)
    with pytest.raises(HermesCompletionError, match="multimodal"):
        _run(hermes_model_complete, "x", images=[b"not used"])
    with pytest.raises(HermesCompletionError, match="32 KiB"):
        _run(hermes_model_complete, "x" * (32 * 1024))


def test_invalid_timeout_and_nontext_context_reject_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "spawned"
    fake = _fake_hermes(tmp_path, f"open({str(marker)!r}, 'w').close()")
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    hermes = _hermes()
    HermesCompletionError, callback = hermes.HermesCompletionError, hermes.hermes_model_complete

    monkeypatch.setenv("OMNIGRAPH_HERMES_TIMEOUT_SECONDS", "SYNTHETIC_NON_NUMERIC")
    with pytest.raises(HermesCompletionError, match="invalid timeout") as exc:
        _run(callback, "private prompt")
    assert exc.value.__cause__ is None
    assert "SYNTHETIC_NON_NUMERIC" not in "".join(
        traceback.format_exception(exc.value)
    )
    assert not marker.exists()

    monkeypatch.setenv("OMNIGRAPH_HERMES_TIMEOUT_SECONDS", "180")
    with pytest.raises(HermesCompletionError, match="text system") as exc:
        _run(callback, "private prompt", system_prompt=object())
    assert "private prompt" not in str(exc.value)
    assert not marker.exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prompt": 123},
        {"system_prompt": ["not text"]},
        {"history_messages": {"role": "user", "content": "not a list"}},
        {"history_messages": [{"role": "tool", "content": "not text-only contract"}]},
        {"history_messages": [{"role": "user", "content": [{"type": "image_url", "image_url": "x"}]}]},
        {"history_messages": [{"role": "user", "content": "x", "name": "extra"}]},
    ],
)
def test_non_text_or_unknown_history_rejects_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kwargs: dict
) -> None:
    marker = tmp_path / "spawned"
    fake = _fake_hermes(tmp_path, f"open({str(marker)!r}, 'w').close()")
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    hermes = _hermes()
    callback = hermes.hermes_model_complete
    call_kwargs = dict(kwargs)

    with pytest.raises(hermes.HermesCompletionError, match="text-only|text prompt|text system|history"):
        _run(callback, call_kwargs.pop("prompt", "private prompt"), **call_kwargs)
    assert not marker.exists()


def test_lone_surrogate_rejects_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "spawned"
    fake = _fake_hermes(tmp_path, f"open({str(marker)!r}, 'w').close()")
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    hermes = _hermes()

    with pytest.raises(hermes.HermesCompletionError, match="serialization") as exc:
        _run(hermes.hermes_model_complete, "private \ud800 prompt")
    assert "private" not in str(exc.value)
    assert not marker.exists()

    broken = tmp_path / "broken-hermes"
    broken.write_text("#!/definitely/missing/interpreter\n", encoding="utf-8")
    broken.chmod(0o755)
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(broken))
    with pytest.raises(hermes.HermesCompletionError, match="binary execution unavailable") as exc:
        _run(hermes.hermes_model_complete, "private prompt")
    assert "private prompt" not in str(exc.value)


def test_timeout_and_cancellation_reap_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "child.pid"
    fake = _fake_hermes(
        tmp_path,
        f"""
        import os, subprocess, sys, time
        child = subprocess.Popen([{sys.executable!r}, "-c", "import time; time.sleep(60)"])
        open({str(pid_file)!r}, "w").write(str(child.pid))
        time.sleep(60)
        """,
    )
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    monkeypatch.setenv("OMNIGRAPH_HERMES_TIMEOUT_SECONDS", "0.05")
    hermes = _hermes()
    HermesCompletionError, hermes_model_complete = hermes.HermesCompletionError, hermes.hermes_model_complete

    with pytest.raises(HermesCompletionError, match="parent_timeout=True"):
        _run(hermes_model_complete, "x")

    async def cancel() -> None:
        task = asyncio.create_task(hermes_model_complete("x"))
        await asyncio.sleep(0.03)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    monkeypatch.setenv("OMNIGRAPH_HERMES_TIMEOUT_SECONDS", "180")
    asyncio.run(cancel())
    assert pid_file.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_timeout_reaps_child_when_parent_exits_but_child_holds_stdout_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "child.pid"
    fake = _fake_hermes(
        tmp_path,
        f"""
        import subprocess, sys
        child = subprocess.Popen([{sys.executable!r}, "-c", "import time; time.sleep(60)"])
        open({str(pid_file)!r}, "w").write(str(child.pid))
        """,
    )
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    monkeypatch.setenv("OMNIGRAPH_HERMES_TIMEOUT_SECONDS", "0.05")
    hermes = _hermes()

    with pytest.raises(hermes.HermesCompletionError, match="parent_timeout=True"):
        _run(hermes.hermes_model_complete, "x")
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_calls_are_serialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = tmp_path / "active"
    fake = _fake_hermes(
        tmp_path,
        f"""
        import json, os, sys, time
        marker = {str(marker)!r}
        if os.path.exists(marker): sys.exit(9)
        open(marker, "w").close()
        time.sleep(.05)
        os.unlink(marker)
        with open(sys.argv[sys.argv.index("--usage-file") + 1], "w") as f: json.dump({{"provider":"openai-codex","model":"gpt-6-astra","failed":False}}, f)
        print("ok")
        """,
    )
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    callback = _hermes().hermes_model_complete

    async def run_pair() -> list[str]:
        return await asyncio.gather(callback("one"), callback("two"))

    assert asyncio.run(run_pair()) == ["ok\n", "ok\n"]


def test_dispatcher_selects_hermes_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "hermes")
    hermes_model_complete = _hermes().hermes_model_complete
    dispatcher = _load_module("lib.llm_complete")

    assert dispatcher.get_llm_func() is hermes_model_complete


def test_only_service_tier_accepts_native_null():
    hermes = _hermes()
    assert hermes._observable_usage({"service_tier": None, "failed": False}) == {"failed": False}
    for field in ("provider", "model", "completed", "failed", "cache_read_tokens"):
        with pytest.raises(hermes.HermesCompletionError):
            hermes._observable_usage({field: None})

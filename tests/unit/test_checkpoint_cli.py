"""Integration tests for checkpoint_reset.py and checkpoint_status.py.

Subprocess-based because the CLIs are argparse-driven and the guard-clause
exit codes are part of the contract. Uses OMNIGRAPH_CHECKPOINT_BASE_DIR to
redirect BASE_DIR for the child process.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESET_SCRIPT = REPO_ROOT / "scripts" / "checkpoint_reset.py"
STATUS_SCRIPT = REPO_ROOT / "scripts" / "checkpoint_status.py"


@pytest.fixture
def base_env(tmp_path, monkeypatch):
    """Redirect BASE_DIR for both in-process and subprocess via env var."""
    fake_base = tmp_path / "omonigraph-vault"
    fake_base.mkdir(parents=True)
    env = {**os.environ, "OMNIGRAPH_CHECKPOINT_BASE_DIR": str(fake_base)}
    env.setdefault("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setenv("OMNIGRAPH_CHECKPOINT_BASE_DIR", str(fake_base))
    # Force in-process reload so BASE_DIR picks up the env var for test seeding.
    import lib.checkpoint as ckpt
    importlib.reload(ckpt)
    yield env, ckpt


def _run(script: Path, *args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_reset_all_without_confirm_exits_2(base_env):
    env, _ = base_env
    result = _run(RESET_SCRIPT, "--all", env=env)
    assert result.returncode == 2, result.stderr
    assert "--confirm" in (result.stderr + result.stdout)


def test_reset_all_with_confirm_removes_all(base_env):
    env, ckpt = base_env
    ckpt.write_stage(ckpt.get_article_hash("https://a.test"), "scrape", "<html>A</html>")
    ckpt.write_stage(ckpt.get_article_hash("https://b.test"), "scrape", "<html>B</html>")
    assert len(list((ckpt.BASE_DIR / "checkpoints").iterdir())) == 2
    result = _run(RESET_SCRIPT, "--all", "--confirm", env=env)
    assert result.returncode == 0, result.stderr
    assert not (ckpt.BASE_DIR / "checkpoints").exists()


def test_reset_hash_missing_exits_1(base_env):
    env, _ = base_env
    result = _run(RESET_SCRIPT, "--hash", "deadbeef12345678", env=env)
    assert result.returncode == 1, result.stderr


def test_reset_hash_present_exits_0(base_env):
    env, ckpt = base_env
    h = ckpt.get_article_hash("https://one.test")
    ckpt.write_stage(h, "scrape", "<html/>")
    result = _run(RESET_SCRIPT, "--hash", h, env=env)
    assert result.returncode == 0, result.stderr
    assert not (ckpt.BASE_DIR / "checkpoints" / h).exists()


def test_reset_no_args_exits_nonzero(base_env):
    env, _ = base_env
    result = _run(RESET_SCRIPT, env=env)
    assert result.returncode != 0


def test_status_empty_prints_zero_total(base_env):
    env, _ = base_env
    result = _run(STATUS_SCRIPT, env=env)
    assert result.returncode == 0
    assert "0 total" in result.stdout


def test_status_mixed_states(base_env):
    env, ckpt = base_env
    h_complete = ckpt.get_article_hash("https://complete.test")
    h_inflight = ckpt.get_article_hash("https://in-flight.test")
    ckpt.write_stage(h_complete, "scrape", "<html/>")
    ckpt.write_stage(h_complete, "classify", {"depth": 2, "topics": ["ai"]})
    ckpt.write_stage(h_complete, "text_ingest")
    ckpt.write_stage(h_complete, "sub_doc_ingest")
    ckpt.write_metadata(h_complete, {"url": "https://complete.test", "title": "C"})
    ckpt.write_stage(h_inflight, "scrape", "<html/>")
    ckpt.write_metadata(h_inflight, {"url": "https://in-flight.test", "title": "I"})

    result = _run(STATUS_SCRIPT, env=env)
    assert result.returncode == 0, result.stderr
    assert h_complete in result.stdout
    assert h_inflight in result.stdout
    assert "complete" in result.stdout
    assert "in_flight" in result.stdout


def test_status_tsv_header(base_env):
    env, _ = base_env
    result = _run(STATUS_SCRIPT, "--tsv", env=env)
    assert result.returncode == 0
    first_line = result.stdout.splitlines()[0]
    assert first_line == "hash\turl\ttitle\tlast_stage\tage_seconds\tstatus"

"""Tests for Cognee-path embedding model name handling in Vertex AI mode.

Cognee has its own embedding chain (LiteLLM → Vertex AI) independent of
``lib.lightrag_embedding``. In Vertex AI mode on the ``global`` endpoint the
canonical embedding name is GA ``gemini-embedding-2`` (GA since 2026-04-22);
no alias layer is applied. See
``.planning/phases/05-pipeline-automation/05-00-SUMMARY.md`` § C for the
2026-04-30 → 05-03 correction history (the endpoint × model mismatch that
preceded this fix).

Subprocess isolation: ``cognee_wrapper`` imports the heavy ``cognee`` package
at module load, and the env-var reassignment happens at import time. We spawn
a fresh Python process per env configuration rather than trying to reload the
module in-test (Cognee holds global state that doesn't survive
``importlib.reload``).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_import_and_print(env_overrides: dict[str, str]) -> str:
    """Import ``cognee_wrapper`` in a subprocess and print EMBEDDING_MODEL.

    Returns the stdout value (stripped). Raises on non-zero exit.
    """
    env = os.environ.copy()
    # Force no Vertex vars unless explicitly overridden (test hermeticity).
    for var in ("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        env.pop(var, None)
    # Cognee import crashes if DEEPSEEK_API_KEY is unset (documented Phase 5
    # side-effect in CLAUDE.md). Stub it so the import succeeds in CI.
    env.setdefault("DEEPSEEK_API_KEY", "dummy")
    # Ensure at least one Gemini key exists for lib.api_keys lazy init.
    env.setdefault("GEMINI_API_KEY", "test-key-cognee-vertex")
    env.update(env_overrides)

    script = (
        "import os, cognee_wrapper;"
        "print('EMBEDDING_MODEL=' + os.environ['EMBEDDING_MODEL'])"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"subprocess failed (code {proc.returncode}):\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    # The value we care about is on the last line of stdout; other lines are
    # Cognee's init log chatter.
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("EMBEDDING_MODEL="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"EMBEDDING_MODEL line not found in stdout:\n{proc.stdout}")


def test_vertex_mode_preserves_ga_model_name(tmp_path) -> None:
    """Vertex env vars set → EMBEDDING_MODEL env stays ``gemini-embedding-2``.

    GA behavior: ``gemini-embedding-2`` is GA on the ``global`` Vertex
    endpoint (GA date 2026-04-22). No alias layer; the model name passes
    through unchanged in both free-tier and Vertex modes.
    """
    # A placeholder SA file is enough — _is_vertex_mode() only checks the env
    # var is non-empty, not that the file is valid (genai.Client is not
    # invoked at cognee_wrapper import).
    fake_sa = tmp_path / "fake-sa.json"
    fake_sa.write_text("{}")
    got = _run_import_and_print({
        "GOOGLE_APPLICATION_CREDENTIALS": str(fake_sa),
        "GOOGLE_CLOUD_PROJECT": "my-project-123",
    })
    assert got == "gemini-embedding-2"


def test_free_tier_path_preserves_base_model_name() -> None:
    """No Vertex env vars → EMBEDDING_MODEL env stays gemini-embedding-2."""
    got = _run_import_and_print({})
    assert got == "gemini-embedding-2"

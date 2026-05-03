"""Tests for Cognee-path embedding model name handling in Vertex AI mode.

Cognee has its own embedding chain (LiteLLM → Vertex AI) independent of
``lib.lightrag_embedding``. In Vertex AI mode, ``cognee_wrapper`` routes the
EMBEDDING_MODEL env var through the shared ``_resolve_model()`` helper so both
chains stay in sync.

Naming history (kept brief so the test suite is readable in isolation):
  - 2026-04 → early 2026-05: ``gemini-embedding-2-preview`` was the Vertex AI
    name; unsuffixed ``gemini-embedding-2`` returned 404 NOT_FOUND.
  - 2026-05-03: Google removed ``gemini-embedding-2-preview`` from the Vertex
    AI catalog. Confirmed empirically on us-central1 with a paid-tier SA —
    ``gemini-embedding-2`` now returns 3072-dim vectors directly; ``-preview``
    returns 404. See `lib/lightrag_embedding._resolve_model()` and
    `memory/vertex_ai_smoke_validated.md` for the full timeline.

These tests pin the current behavior: `_resolve_model()` is a pass-through, so
Vertex-mode EMBEDDING_MODEL stays ``gemini-embedding-2``.

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


def test_vertex_mode_passes_base_model_through(tmp_path) -> None:
    """Vertex env vars set → EMBEDDING_MODEL env stays ``gemini-embedding-2``.

    Post 2026-05-03 (commit 9069f59): ``-preview`` was removed from Vertex AI
    catalog; ``_resolve_model()`` is a no-op and the base model name flows
    through unchanged. If Google renames or re-suffixes the Vertex embedding
    model in the future, update `lib/lightrag_embedding._resolve_model()` AND
    this test assertion together.
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

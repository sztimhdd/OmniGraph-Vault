"""Shared pytest fixtures for OmniGraph-Vault tests."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest


# Phase 5 cross-coupling guard: lib/__init__.py eagerly imports
# lib.llm_deepseek which raises at import time if DEEPSEEK_API_KEY is unset.
# Under CI/Windows dev, tests mock all network calls, so the value is never
# actually used — but the import has to succeed. Inject a harmless dummy
# BEFORE any lib import reaches the module-level _require_api_key() call.
# Documented caveat in CLAUDE.md: "use DEEPSEEK_API_KEY=dummy if you don't
# have a real one".
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy-for-tests")


# Phase 13: guard against tests polluting ~/.hermes/omonigraph-vault/checkpoints/_batch/
# by defaulting OMNIGRAPH_VISION_CHECKPOINT_DIR to a per-session tmp dir unless
# a test explicitly overrides it via monkeypatch.
@pytest.fixture(autouse=True, scope="session")
def _isolate_vision_checkpoint_dir():
    prior = os.environ.get("OMNIGRAPH_VISION_CHECKPOINT_DIR")
    if prior is None:
        td = tempfile.mkdtemp(prefix="ogv-vision-ckpt-")
        os.environ["OMNIGRAPH_VISION_CHECKPOINT_DIR"] = td
        yield
        os.environ.pop("OMNIGRAPH_VISION_CHECKPOINT_DIR", None)
    else:
        yield


@pytest.fixture
def tmp_base_dir(tmp_path: Path) -> Path:
    """A temporary directory that mirrors ~/.hermes/omonigraph-vault/."""
    base = tmp_path / "omonigraph-vault"
    (base / "lightrag_storage").mkdir(parents=True)
    (base / "images").mkdir()
    (base / "enrichment").mkdir()
    (base / "entity_buffer").mkdir()
    return base


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_gemini_client(mocker):
    """Mock google.genai.Client — returns a client whose generate_content returns stub text."""
    client = MagicMock()
    response = MagicMock()
    response.text = "stub gemini response"
    response.candidates = [MagicMock(grounding_metadata=MagicMock(grounding_chunks=[]))]
    client.models.generate_content.return_value = response
    return client


@pytest.fixture
def mock_lightrag(mocker):
    """Mock LightRAG instance with async ainsert / adelete_by_doc_id."""
    rag = MagicMock()

    async def _ainsert(*a, **kw):
        return "stub-track-id"

    async def _adelete(*a, **kw):
        r = MagicMock()
        r.status = "success"
        r.status_code = 200
        return r

    rag.ainsert = _ainsert
    rag.adelete_by_doc_id = _adelete
    return rag


@pytest.fixture
def mock_requests_get(mocker):
    """Mock requests.get for image download tests — returns 200 with bytes body."""
    m = mocker.patch("requests.get")
    m.return_value.status_code = 200
    m.return_value.content = b"\xff\xd8\xff\xe0FAKE_JPEG_BYTES"
    return m


# ---------------------------------------------------------------------------
# Phase 7 lib/ fixtures (D-06: mock at lib.llm_client level)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_lib_llm(mocker):
    """Mock at lib.llm_client.generate / lib.llm_client.aembed / lib.llm_client.generate_sync (D-06).

    Replaces per-call-site google.genai.Client patches. Any test importing a
    production module can patch here once and cover every LLM touchpoint.
    Note: _fake_generate uses `contents` param (Amendment 5).
    """
    from lib.models import EMBEDDING_DIM

    async def _fake_generate(model, contents, **kwargs):
        return "stub lib generate response"

    async def _fake_aembed(model, texts, **kwargs):
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    gen = mocker.patch("lib.llm_client.generate", side_effect=_fake_generate)
    aem = mocker.patch("lib.llm_client.aembed", side_effect=_fake_aembed)
    sync_gen = mocker.patch("lib.llm_client.generate_sync", return_value="stub sync generate response")
    return {"generate": gen, "aembed": aem, "generate_sync": sync_gen}


@pytest.fixture
def reset_lib_state(monkeypatch):
    """Reset lib/ module-level state between tests (rotation cycle, limiter registry)."""
    import lib.api_keys as k
    import lib.rate_limit as r
    k._reset_cycle_for_tests()  # F5: also resets embedding cycle (was: 4 explicit assignments)
    r._limiters.clear()
    # Also reset llm_client cached client
    import lib.llm_client as lc
    lc._client = None
    lc._client_key = None
    yield


# ---------------------------------------------------------------------------
# kb-v2.2-5 (F5): autouse cycle-state reset for test isolation
# ---------------------------------------------------------------------------
# kb-v2.1-9 audit identified 5 tests xfailing because module-level cycle state
# in lib.api_keys leaks between tests. Solo-run passes; batch-run fails:
# - test_lightrag_embedding_rotation::test_single_key_fallback (4 sibling tests)
# - test_vision_worker::test_ingest_from_db_drains_pending_vision_tasks
#
# Root cause: lib.lightrag_embedding.embedding_func() uses the EMBEDDING cycle
# (lib.api_keys._embedding_cycle / _current_embedding), but the local fixture
# in test_lightrag_embedding_rotation.py only reset the LLM cycle. The first
# test that initialized _embedding_cycle (e.g. with single-key env) cached it;
# subsequent tests read the stale cycle regardless of their own env setup.
#
# Fix: reset BOTH cycles via lib.api_keys._reset_cycle_for_tests() before AND
# after every test. Local fixture in test_lightrag_embedding_rotation.py still
# does the env-setup; this autouse handles the cycle-state plumbing globally.


def _reset_api_keys_cycle_state_safe() -> None:
    """Defensively reset lib.api_keys cycle state. Skips if module not loaded.

    Some tests do `sys.modules.pop("lib.<sibling>", None)` which can leave
    the `lib` package's attribute table inconsistent with what a plain
    `import lib.api_keys` followed by `lib.api_keys.<func>` lookup expects.
    To avoid `AttributeError: module 'lib' has no attribute 'api_keys'`
    cascading into 300+ ERRORs, we:

    1. Look up the function directly via sys.modules["lib.api_keys"] —
       bypasses the parent-package attribute lookup
    2. Skip silently if the module isn't loaded (test never touched api_keys)
    3. Defensive try/except so a fixture exception never blocks tests
    """
    import sys
    mod = sys.modules.get("lib.api_keys")
    if mod is None:
        return  # module not loaded yet, no state to reset
    reset_fn = getattr(mod, "_reset_cycle_for_tests", None)
    if reset_fn is None:
        return  # older / patched module without the helper
    try:
        reset_fn()
    except Exception:
        pass  # never block a test on cycle-reset failure


@pytest.fixture(autouse=True)
def _reset_api_keys_cycle_state():
    """Reset lib.api_keys cycle state (LLM + embedding) before AND after each test.

    kb-v2.1-9 audit identified 5 tests xfailing because module-level cycle state
    in lib.api_keys leaks between tests. Solo-run passes; batch-run fails:
    test_lightrag_embedding_rotation × 4 + test_vision_worker × 1.

    Root cause: lib.lightrag_embedding.embedding_func() uses the EMBEDDING cycle
    (lib.api_keys._embedding_cycle / _current_embedding), but the local fixture
    in test_lightrag_embedding_rotation.py only reset the LLM cycle. The first
    test that initialized _embedding_cycle (e.g. with single-key env) cached it;
    subsequent tests read the stale cycle regardless of their own env setup.

    Reset BEFORE and AFTER:
    - BEFORE: clear pollution from prior tests in case they didn't clean up
    - AFTER: don't leak this test's cycle state into subsequent tests

    Idempotent. Composes cleanly with test-specific fixtures — pytest runs
    closer-scope fixtures last, so per-test monkeypatch.setenv overrides
    this reset for the test's window.
    """
    _reset_api_keys_cycle_state_safe()
    yield
    _reset_api_keys_cycle_state_safe()

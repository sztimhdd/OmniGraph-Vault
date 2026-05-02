"""Tests for lib/models.py — Phase 7 Wave 0 Task 0.1.

Amendment 1: D-02 SUPERSEDED — model names are pure string constants.
D-05: GITHUB_INGEST_LLM preserves preview model.
D-08: RATE_LIMITS_RPM present (RPM env override stays in rate_limit.py).
D-10: EMBEDDING_MODEL default == "gemini-embedding-2".
"""
from __future__ import annotations

import importlib


def test_ingestion_llm_is_pure_constant():
    from lib import INGESTION_LLM
    assert INGESTION_LLM == "gemini-2.5-flash"


def test_vision_llm_is_pure_constant():
    from lib import VISION_LLM
    assert VISION_LLM == "gemini-3.1-flash-lite-preview"


def test_synthesis_llm_is_pure_constant():
    from lib import SYNTHESIS_LLM
    assert SYNTHESIS_LLM == "gemini-2.5-flash-lite"


def test_github_uses_preview():
    """D-05: GitHub ingestion keeps the preview model."""
    from lib import GITHUB_INGEST_LLM
    assert GITHUB_INGEST_LLM == "gemini-3.1-flash-lite-preview"


def test_embedding_model_default():
    """D-10: production default is gemini-embedding-2."""
    from lib import EMBEDDING_MODEL
    assert EMBEDDING_MODEL == "gemini-embedding-2"


def test_no_model_env_override(monkeypatch):
    """Amendment 1 negative assertion: env var CANNOT override model constants.

    Single-user + git-as-deploy means ``git revert`` IS the rollback; there
    is no OMNIGRAPH_MODEL_* override mechanism in lib/models.py.
    """
    monkeypatch.setenv("OMNIGRAPH_MODEL_INGESTION_LLM", "foo-model")
    import lib.models as m
    importlib.reload(m)
    # The constant must still be the hard-coded value, not "foo-model".
    assert m.INGESTION_LLM == "gemini-2.5-flash"
    assert m.INGESTION_LLM != "foo-model"


def test_rate_limits_rpm_covers_both_embeddings():
    """D-10: both embedding-001 (legacy) and embedding-2 (current) in the dict."""
    from lib.models import RATE_LIMITS_RPM
    assert "gemini-embedding-001" in RATE_LIMITS_RPM
    assert "gemini-embedding-2" in RATE_LIMITS_RPM


def test_rate_limits_rpm_completeness():
    """Every model constant has a rate-limit entry."""
    from lib.models import (
        INGESTION_LLM, VISION_LLM, SYNTHESIS_LLM,
        GITHUB_INGEST_LLM, EMBEDDING_MODEL, RATE_LIMITS_RPM,
    )
    for constant_name, model in [
        ("INGESTION_LLM", INGESTION_LLM),
        ("VISION_LLM", VISION_LLM),
        ("SYNTHESIS_LLM", SYNTHESIS_LLM),
        ("GITHUB_INGEST_LLM", GITHUB_INGEST_LLM),
        ("EMBEDDING_MODEL", EMBEDDING_MODEL),
    ]:
        assert model in RATE_LIMITS_RPM, (
            f"{constant_name}={model!r} has no entry in RATE_LIMITS_RPM"
        )

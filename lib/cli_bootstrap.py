"""Boot-time setup helper for OmniGraph-Vault CLI scripts.

Defect A — quick 260510-l14 (POLLUTION-AUDIT.md Step 2 cross-cutting issue 1).

Six single-purpose CLI scripts (ingest_github, query_lightrag, run_uat_ingest,
omnigraph_search/query, enrichment/fetch_zhihu, enrichment/merge_and_ingest)
used to each clobber GOOGLE_GENAI_USE_VERTEXAI unconditionally — silently
breaking lib/lightrag_embedding._is_vertex_mode() opt-in (Phase 11 D-11.08).
The correct guard is in config.py:65-69 ("only pop GOOGLE_* when SA NOT set").
This helper consolidates that pattern + load_env().

Use from CLI scripts:
    from lib.cli_bootstrap import bootstrap_cli
    bootstrap_cli()  # call once, at module top

Do NOT call from library/test code. config.py runs these same steps at import
time; library code should rely on that, not re-invoke.
"""
from __future__ import annotations

import os

from config import load_env


def bootstrap_cli() -> None:
    """Load ~/.hermes/.env + apply Vertex AI opt-in guard.

    Idempotent. Mirrors config.py:65-69's guard semantics so that callers
    which set GOOGLE_APPLICATION_CREDENTIALS explicitly retain Vertex mode,
    while default (no SA) callers fall back to free-tier Gemini API.
    """
    load_env()
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
        os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        os.environ.pop("GOOGLE_CLOUD_LOCATION", None)


__all__ = ["bootstrap_cli"]

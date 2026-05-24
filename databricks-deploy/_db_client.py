"""Shared Databricks SDK client factory — works in deployed App AND locally.

In deployed Databricks Apps: the platform injects DATABRICKS_HOST + OAuth M2M
credentials; bare ``WorkspaceClient()`` picks them up automatically.

Locally: ``DATABRICKS_CONFIG_PROFILE=dev`` is set via ``.env.local`` and the
SDK reads PAT from ``~/.databrickscfg [dev]``. ``auth_type="pat"`` is required
to skip the ~5-minute Azure metadata probe that hangs on EDC's corp network.

This helper exists so any code calling Databricks endpoints can use one import
and behave correctly in both environments without duplicating the env check.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def get_databricks_client(**kwargs: Any) -> Any:
    """Return a ``WorkspaceClient`` configured for the current environment.

    When ``DATABRICKS_CONFIG_PROFILE`` is set (local dev): use the named profile
    with ``auth_type="pat"`` to skip the metadata probe that hangs ~5 min on
    corp networks.

    When unset (deployed Databricks App): construct a bare ``WorkspaceClient()``
    so the platform-injected M2M credentials take over.

    Extra kwargs are passed through to ``WorkspaceClient`` (e.g., a custom
    ``Config(http_timeout_seconds=...)``).
    """
    from databricks.sdk import WorkspaceClient

    profile = os.getenv("DATABRICKS_CONFIG_PROFILE")
    if profile:
        logger.info(
            "_db_client: using PAT profile %s (auth_type=pat)", profile
        )
        return WorkspaceClient(profile=profile, auth_type="pat", **kwargs)
    return WorkspaceClient(**kwargs)

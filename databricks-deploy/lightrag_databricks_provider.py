"""LightRAG <-> Databricks Model Serving factory.

Provides ``make_llm_func()`` + ``make_embedding_func()`` that wrap MosaicAI
Model Serving endpoints for LightRAG instantiation. Consumed by kdb-2 App
startup (post LLM-DBX-01 dispatcher integration) and kdb-2.5 re-index Job.

Auth:
    - Locally: ``WorkspaceClient()`` reads ``~/.databrickscfg [dev]`` profile (user OAuth).
    - In Apps:  ``WorkspaceClient()`` reads ``DATABRICKS_HOST/CLIENT_ID/CLIENT_SECRET``
                injected automatically by the Apps runtime.

See ``.planning/phases/kdb-1.5-lightrag-databricks-provider-adapter/kdb-1.5-RESEARCH.md``
Q5 + Decision 3 for design rationale.

Design notes:
    - Pitfall 4 (RESEARCH.md): the Databricks SDK ``serving_endpoints.query`` method
      is synchronous; calling it from ``async def`` blocks the event loop. We wrap
      every call in ``loop.run_in_executor(None, ...)`` to preserve LightRAG's
      ``embedding_func_max_async`` concurrency contract.
    - Pitfall 5 (RESEARCH.md): never wrap a function already decorated with
      ``@wrap_embedding_func_with_attrs`` in another ``EmbeddingFunc``. We expose
      the decorated ``_embed`` directly via ``make_embedding_func()``.
    - ``WorkspaceClient`` is lazy-imported inside factory bodies so this module
      imports cleanly in environments without ``databricks-sdk`` installed
      (e.g., when only the storage adapter is being tested).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import numpy as np

from lightrag.utils import EmbeddingFunc, wrap_embedding_func_with_attrs

logger = logging.getLogger(__name__)

KB_LLM_MODEL = os.environ.get("KB_LLM_MODEL", "databricks-claude-sonnet-4-6")
KB_EMBEDDING_MODEL = os.environ.get(
    "KB_EMBEDDING_MODEL", "databricks-qwen3-embedding-0-6b"
)
EMBEDDING_DIM = 1024  # Qwen3-0.6B output dim - locked per REQUIREMENTS rev 3
EMBEDDING_MAX_TOKEN_SIZE = 8192


def make_llm_func():
    """Return a LightRAG-compatible ``llm_model_func`` wrapping MosaicAI sonnet-4-6.

    Lazy-imports ``databricks-sdk`` to keep import-time clean.
    Wraps the synchronous SDK call in ``run_in_executor`` to preserve
    LightRAG's async event-loop semantics (Pitfall 4 in RESEARCH.md).

    Returns:
        Async callable matching LightRAG's ``llm_model_func`` signature::

            async def llm_func(prompt: str,
                               system_prompt: str | None = None,
                               history_messages: list[dict] | None = None,
                               **kwargs) -> str
    """
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

    w = WorkspaceClient()  # closure captures the client - constructed once per factory call

    async def llm_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> str:
        history_messages = history_messages or []
        messages: list[ChatMessage] = []
        if system_prompt:
            messages.append(
                ChatMessage(role=ChatMessageRole.SYSTEM, content=system_prompt)
            )
        for m in history_messages:
            # ChatMessageRole enum: members USER/SYSTEM/ASSISTANT, values "user"/"system"/"assistant".
            # Constructor takes values (lower-case), not member names.
            role_str = m.get("role", "user").lower()
            messages.append(
                ChatMessage(role=ChatMessageRole(role_str), content=m["content"])
            )
        messages.append(ChatMessage(role=ChatMessageRole.USER, content=prompt))

        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: w.serving_endpoints.query(
                name=KB_LLM_MODEL, messages=messages
            ),
        )
        return resp.choices[0].message.content

    return llm_func


@wrap_embedding_func_with_attrs(
    embedding_dim=EMBEDDING_DIM,
    max_token_size=EMBEDDING_MAX_TOKEN_SIZE,
)
async def _embed(texts: list[str], **_kwargs: Any) -> np.ndarray:
    """Internal embedding callable wrapping MosaicAI Qwen3-embedding-0-6b.

    Wrapped via the decorator with dim=1024 + max_token_size=8192 metadata so
    LightRAG can introspect ``embedding_dim`` directly off the returned object.

    Returns ``np.ndarray`` of shape ``(N, EMBEDDING_DIM)``, ``dtype=float32``.
    """
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: w.serving_endpoints.query(
            name=KB_EMBEDDING_MODEL, input=texts
        ),
    )
    # SDK returns .data: list[{embedding: list[float]}] (OpenAI-compat shape).
    # Defensive: if the SDK shape diverges in older / newer versions, fall back
    # to checking for a top-level .embeddings attribute or dict-shaped data items.
    try:
        vectors = [d.embedding for d in resp.data]
    except AttributeError:
        data = getattr(resp, "embeddings", None) or resp.data
        vectors = [
            d["embedding"] if isinstance(d, dict) else d.embedding
            for d in data
        ]
    return np.array(vectors, dtype=np.float32)


def make_embedding_func() -> EmbeddingFunc:
    """Return ``EmbeddingFunc`` instance wrapping MosaicAI Qwen3-embedding-0-6b.

    Do NOT re-wrap the returned object with another ``EmbeddingFunc`` -
    ``_embed`` is already wrapped via the ``@wrap_embedding_func_with_attrs``
    decorator (Pitfall 5 in RESEARCH.md).

    Returns:
        ``EmbeddingFunc`` with ``embedding_dim=1024`` + ``max_token_size=8192``.
    """
    return _embed  # type: ignore[return-value]

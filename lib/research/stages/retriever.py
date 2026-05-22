"""Retriever stage — wires live ``omnigraph_search.query.search()`` (CONTRACT-01).

ar-1 status: live. Calls the LightRAG hybrid-mode ``search`` directly and wraps
the raw retrieval text into a single ``Source(kind="kg_chunk", ...)``. Image
candidates are globbed from ``BASE_IMAGE_DIR`` (derived from
``cfg.rag_working_dir.parent / "images"``) for any 10-char hex hash mentioned
in the KG response.

CONTRACT-01: this is the ONLY module in ``lib/research/`` allowed to import
from ``omnigraph_search`` — and only the ``.query.search`` symbol.

CONTRACT-02: paths are derived from ``cfg.rag_working_dir`` — no hardcoded
runtime-data path literals (those live only in config.py).

Axis 3 best-effort: any exception from ``search()`` is caught and surfaced as
``status="failed"`` with ``reason=str(e)``. Never raises out.
"""
from __future__ import annotations

import re
from pathlib import Path

from omnigraph_search.query import search as kg_search

from ..types import ResearchConfig, RetrievedImage, RetrieverOutput, Source

# 10-char hex article hash (matches ingest_wechat.py + checkpoints/{hash}/ layout).
ARTICLE_HASH_RE = re.compile(r"\b[0-9a-f]{10}\b")


async def run(query: str, cfg: ResearchConfig) -> RetrieverOutput:
    """Run the Retriever stage.

    Returns a frozen ``RetrieverOutput`` with ``status`` in
    ``{"ok", "skipped", "failed"}``. Never raises.
    """
    try:
        kg_text = await kg_search(query, mode="hybrid")
    except Exception as e:  # noqa: BLE001 — Axis 3 best-effort
        return RetrieverOutput(
            chunks=[],
            image_candidates=[],
            status="failed",
            reason=str(e),
        )

    if not kg_text or not kg_text.strip():
        return RetrieverOutput(
            chunks=[],
            image_candidates=[],
            status="skipped",
            reason="omnigraph_search.query.search returned empty",
        )

    # Single chunk wrapping the full KG response — Reasoner in ar-2 will replace
    # with proper chunk-by-chunk extraction.
    chunks: list[Source] = [
        Source(
            kind="kg_chunk",
            uri="omnigraph_search.query.search",
            snippet=kg_text,
        )
    ]

    # Glob image candidates from BASE_IMAGE_DIR for any 10-char hex hash mentioned
    # in kg_text. cfg.rag_working_dir = base_dir/lightrag_storage, so images live
    # at base_dir/images.
    base_image_dir: Path = cfg.rag_working_dir.parent / "images"
    image_candidates: list[RetrievedImage] = []
    if base_image_dir.exists():
        for hash_match in sorted(set(ARTICLE_HASH_RE.findall(kg_text))):
            article_dir = base_image_dir / hash_match
            if article_dir.is_dir():
                for img in sorted(article_dir.glob("*.jpg")):
                    image_candidates.append(
                        RetrievedImage(article_hash=hash_match, image_path=img)
                    )

    return RetrieverOutput(chunks=chunks, image_candidates=image_candidates)

"""Retriever stage — wires live ``omnigraph_search.query.search()`` (CONTRACT-01).

Calls the LightRAG hybrid-mode ``search`` directly and splits the raw retrieval
text on blank lines into one ``Source(kind="kg_chunk", ...)`` per paragraph.
Image candidates are globbed from ``BASE_IMAGE_DIR`` (derived from
``cfg.rag_working_dir.parent / "images"``) for any 10-char hex hash mentioned
across all paragraphs (cross-paragraph dedup, jpg/jpeg/png/webp case-insensitive,
top-10 lex truncation).

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
        kg_text = await kg_search(query, mode="hybrid", only_context=True)
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

    # Split kg_text into paragraphs (blank-line separator) → one Source per
    # non-empty paragraph. Falls back to a single chunk if no blank-line splits
    # are present.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", kg_text) if p.strip()]
    if not paragraphs:
        paragraphs = [kg_text]
    chunks: list[Source] = [
        Source(
            kind="kg_chunk",
            uri="omnigraph_search.query.search",
            snippet=p,
        )
        for p in paragraphs
    ]

    # Glob image candidates from BASE_IMAGE_DIR for any 10-char hex hash mentioned
    # across all paragraphs (cross-paragraph dedup). cfg.rag_working_dir =
    # base_dir/lightrag_storage, so images live at base_dir/images.
    base_image_dir: Path = cfg.rag_working_dir.parent / "images"
    image_candidates: list[RetrievedImage] = []
    if base_image_dir.exists():
        seen_hashes: set[str] = set()
        for p in paragraphs:
            for hash_match in ARTICLE_HASH_RE.findall(p):
                if hash_match in seen_hashes:
                    continue
                seen_hashes.add(hash_match)
                article_dir = base_image_dir / hash_match
                if not article_dir.is_dir():
                    continue
                # Case-insensitive glob across jpg/jpeg/png/webp.
                imgs: list[Path] = []
                for entry in article_dir.iterdir():
                    if entry.is_file() and entry.suffix.lower() in (
                        ".jpg", ".jpeg", ".png", ".webp"
                    ):
                        imgs.append(entry)
                for img in sorted(imgs, key=lambda x: x.name):
                    image_candidates.append(
                        RetrievedImage(article_hash=hash_match, image_path=img)
                    )

    # Top-10 lex truncation (deterministic order: hash then filename).
    image_candidates.sort(key=lambda ic: (ic.article_hash, ic.image_path.name))
    image_candidates = image_candidates[:10]

    return RetrieverOutput(chunks=chunks, image_candidates=image_candidates)

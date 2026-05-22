"""Synthesizer stage — terminal stage (NO status field, Axis 8).

ar-1 status: minimal markdown synthesis using a CJK-ratio language heuristic
(Axis 10) and degradation note_lines for any upstream stage with
``status != "ok"``. The real LLM-driven synthesis prompt lands in ar-2; final
tuning lands in ar-4.

Per Axis 8, the Synthesizer has no ``status`` field — degradation surfaces
only via ``note_lines``. Per Axis 10, output language matches query language;
ar-1 uses a heuristic (CJK char ratio ≥ 0.3 → Chinese; else English). ar-2
swaps in real LLM-driven detection.

This stage MUST NOT raise out — it is the terminal stage. None-snippet edge
cases are handled gracefully via ``or ""``.
"""
from __future__ import annotations

from pathlib import Path

from ..types import (
    ResearchConfig,
    ResearchState,
    Source,
    SynthesizerOutput,
)


def _detect_language(query: str) -> str:
    """Detect output language via CJK char ratio.

    Returns ``"zh"`` if CJK char ratio ≥ 0.3, else ``"en"`` (Axis 10 ar-1
    heuristic). Empty string → ``"en"``.
    """
    if not query:
        return "en"
    cjk = sum(1 for c in query if "一" <= c <= "鿿")
    return "zh" if cjk / len(query) >= 0.3 else "en"


async def run(
    query: str, cfg: ResearchConfig, state: ResearchState
) -> SynthesizerOutput:
    """Run the Synthesizer stage (terminal — no status field, no try/except wrap).

    Aggregates upstream stage outputs into a minimal markdown answer plus
    degradation note_lines. Confidence is 0.5 if Retriever returned ``ok``,
    else 0.0. Image cap is 5 for ar-1.
    """
    lang = _detect_language(query)
    note_lines: list[str] = []
    sources: list[Source] = []
    embedded_images: list[Path] = []

    # Collect sources from upstream Retriever (ar-1 — chunks come from KG only).
    if state.retrieved is not None and state.retrieved.status == "ok":
        sources.extend(state.retrieved.chunks)
        for img in state.retrieved.image_candidates[:5]:  # cap at 5 for ar-1
            embedded_images.append(img.image_path)

    # Degradation notes for skipped/failed/missing upstream stages.
    for name, st in (
        ("WebBaseline", state.web_baseline),
        ("Retriever", state.retrieved),
        ("Reasoner", state.reasoned),
        ("Verifier", state.verified),
    ):
        if st is None:
            note_lines.append(f"> ⚠️ {name} did not run.")
        elif st.status != "ok":
            emoji = "ℹ️" if st.status == "skipped" else "❌"
            note_lines.append(
                f"> {emoji} {name} {st.status}: {st.reason or '(no reason)'}"
            )

    # Minimal markdown body — real LLM synthesis lands in ar-2.
    if lang == "zh":
        title = f"# 关于「{query}」的研究答复"
        body = "\n## 知识图谱检索结果\n\n"
    else:
        title = f"# Research Answer: {query}"
        body = "\n## Knowledge Graph Retrieval\n\n"

    if state.retrieved is not None and state.retrieved.chunks:
        body += state.retrieved.chunks[0].snippet or "(empty)"
    else:
        body += "(no chunks retrieved)\n"

    # Inline images via local image-server URL pattern (port 8765).
    if embedded_images:
        body += "\n\n## Retrieved Images\n\n"
        for img in embedded_images:
            body += (
                f"![{img.name}](http://localhost:8765/"
                f"{img.parent.name}/{img.name})\n"
            )

    # Append degradation notes.
    if note_lines:
        body += "\n\n---\n\n" + "\n".join(note_lines) + "\n"

    markdown = title + body
    confidence = (
        0.5 if (state.retrieved is not None and state.retrieved.status == "ok")
        else 0.0
    )

    return SynthesizerOutput(
        markdown=markdown,
        confidence=confidence,
        sources=sources,
        embedded_images=embedded_images,
        note_lines=note_lines,
    )

"""Synthesizer stage — terminal stage (NO status field, Axis 8).

ar-2 status: caption-anchored image embeds (alt text sourced from
``state.reasoned.analyzed_images[i].caption``); CJK-ratio language heuristic
preserved (Axis 10 ar-1 scope, swapped for LLM-driven detection in ar-4).

When ``state.reasoned`` is ``None`` or ``analyzed_images`` is empty, falls
back to ``state.retrieved.image_candidates`` with the image filename as alt
text — preserves ar-1 behavior under Reasoner skip/failure (Axis 3 best
effort). Final LLM-driven synthesis prompt tuning lands in ar-4.

Per Axis 8, the Synthesizer has no ``status`` field — degradation surfaces
only via ``note_lines``. Per Axis 10, output language matches query language;
ar-1 uses a heuristic (CJK char ratio ≥ 0.3 → Chinese; else English). ar-4
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

    # ar-2 source collection: KG chunks from Retriever; Reasoner's
    # ``additional_chunks`` (kg_search findings) surfaced when Reasoner ran
    # successfully — gated on status="ok" so a failed Reasoner doesn't leak
    # partial chunks into ``result.sources``.
    if state.retrieved is not None and state.retrieved.status == "ok":
        sources.extend(state.retrieved.chunks)
    if (
        state.reasoned is not None
        and state.reasoned.status == "ok"
        and state.reasoned.additional_chunks
    ):
        sources.extend(state.reasoned.additional_chunks)

    # ar-2 image collection: prefer ``reasoned.analyzed_images`` (caption-
    # anchored), fall back to ``retrieved.image_candidates`` with filename
    # alt text (ar-1 behavior under Reasoner skip/failure — Axis 3).
    image_entries: list[tuple[Path, str]] = []
    if state.reasoned is not None and state.reasoned.analyzed_images:
        for img in state.reasoned.analyzed_images[:5]:  # cap preserved
            alt_text = img.caption or img.image_path.name
            image_entries.append((img.image_path, alt_text))
    elif state.retrieved is not None and state.retrieved.status == "ok":
        for img in state.retrieved.image_candidates[:5]:
            image_entries.append((img.image_path, img.image_path.name))

    embedded_images: list[Path] = [path for path, _alt in image_entries]

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

    # Inline images via app-relative static path (kb-web serves
    # /static/img/{article_hash}/{filename} from the runtime images dir).
    # Alt text sourced from ``image_entries`` tuple (caption or filename fallback).
    if image_entries:
        body += "\n\n## Retrieved Images\n\n"
        for path, alt in image_entries:
            body += (
                f"![{alt}](/static/img/"
                f"{path.parent.name}/{path.name})\n"
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

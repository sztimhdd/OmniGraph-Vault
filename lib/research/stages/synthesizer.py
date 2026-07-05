"""Synthesizer stage — terminal stage (NO status field, Axis 8).

arx-2-finish status: real LLM synthesis (GAP A) — builds an all-chunk prompt
(query + every [n] chunk + reasoner/verifier summaries + image context) and
awaits the plain-text ``get_llm_func()`` provider, replacing the ar-1 stub that
returned ``chunks[0].snippet`` verbatim. Caption-anchored image embeds (alt text
sourced from ``state.reasoned.analyzed_images[i].caption``) are woven after the
prose; CJK-ratio language heuristic preserved (Axis 10 ar-1 scope, LLM-driven
detection deferred).

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

from lib.llm_complete import get_llm_func

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

    # Real LLM synthesis (arx-2-finish GAP A) — replaces the ar-1 stub that
    # returned chunks[0].snippet verbatim. Build a synthesis prompt from ALL
    # chunks + reasoner/verifier summaries + image context, await the
    # PLAIN-TEXT provider (get_llm_func(), NOT cfg.llm_complete which is the
    # JSON tool-calling adapter for Reasoner/Verifier), thread [n] citations,
    # weave images, and degrade gracefully (terminal stage MUST NOT raise).

    # All-chunk prompt block: number EVERY source [n], not just chunks[0].
    chunks_text = "\n\n".join(
        f"[{i + 1}] {s.snippet or '(empty)'}" for i, s in enumerate(sources)
    )
    reasoner_md = (state.reasoned.inferences_md or "") if state.reasoned else ""
    verifier_md = (
        (state.verified.fact_check_summary_md or "") if state.verified else ""
    )
    images_context = "\n".join(
        f"Image: {alt} — path: /static/img/{path.parent.name}/{path.name}"
        for path, alt in image_entries
    )

    if lang == "zh":
        prompt = (
            f"你是一个专业研究助手。请基于以下检索片段，为问题「{query}」"
            "撰写一份详细的中文研究报告。\n\n"
            f"## 检索片段 (共 {len(sources)} 条, 引用格式 [n])\n{chunks_text}\n\n"
            f"## 推理摘要\n{reasoner_md}\n\n"
            f"## 核实摘要\n{verifier_md}\n\n"
            f"## 可用图片\n{images_context}\n\n"
            "要求:\n1. 行文流畅,结构清晰 (## 标题 + 段落)\n"
            "2. 每个关键论断用 [n] 格式引用对应片段编号\n"
            "3. 适当位置插入图片 Markdown (![alt](/static/img/...))\n"
            "4. 不要重新列出参考文献 (页面已有 Sources 区域)\n"
        )
    else:
        prompt = (
            "You are a research assistant. Based on the retrieved passages "
            f"below, write a detailed research report answering: {query}\n\n"
            f"## Retrieved Passages ({len(sources)} total, cite as [n])\n"
            f"{chunks_text}\n\n"
            f"## Reasoner Summary\n{reasoner_md}\n\n"
            f"## Verifier Summary\n{verifier_md}\n\n"
            f"## Available Images\n{images_context}\n\n"
            "Requirements:\n1. Clear structure with ## headings and paragraphs\n"
            "2. Cite each key claim with [n] matching passage number\n"
            "3. Embed relevant images as Markdown (![alt](/static/img/...))\n"
            "4. Do NOT add a References section (the page already shows Sources)\n"
        )

    try:
        llm = get_llm_func()
        raw_markdown = await llm(prompt)
        if not raw_markdown or not raw_markdown.strip():
            raise ValueError("empty LLM response")
        markdown = raw_markdown
    except Exception as exc:  # noqa: BLE001 — terminal stage MUST NOT raise
        # Graceful degrade: fall back to the ar-1 template body + a note_line.
        note_lines.append(f"> ❌ LLM synthesis failed: {exc!s}")
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
        markdown = title + body

    # Weave images AFTER the prose (success OR degrade) — app-relative static
    # path (kb-web serves /static/img/{article_hash}/{filename}); alt text from
    # the ``image_entries`` tuple (caption or filename fallback). REQ-1.1-A-4.
    if image_entries:
        markdown += "\n\n"
        for path, alt in image_entries:
            markdown += f"![{alt}](/static/img/{path.parent.name}/{path.name})\n"

    # Append degradation notes (upstream-stage notes + any LLM-failure note).
    if note_lines:
        markdown += "\n\n---\n\n" + "\n".join(note_lines) + "\n"
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

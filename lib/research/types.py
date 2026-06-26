"""Agentic-RAG-v1 dataclasses (frozen, except ResearchState).

Verbatim shapes from CONTEXT.md § "Seven frozen dataclasses (verbatim shapes)".
Do NOT rename fields, do NOT add fields, do NOT remove defaults — downstream
plans (ar-1-02 stage stubs, ar-1-03 CLI, ar-1-04 skill packaging) depend on
these exact shapes.

ResearchState is the ONLY mutable dataclass — orchestrator writes one stage
field at a time as the pipeline advances. ResearchConfig is frozen but lives
here (alongside the 6 stage outputs + ResearchResult + ResearchState) so all
type imports are one-stop. The ``from_env()`` factory lives in config.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

Status = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class Source:
    kind: Literal["kg_chunk", "kg_image", "web", "grounding"]
    uri: str
    title: str | None = None
    snippet: str | None = None


@dataclass(frozen=True)
class WebBaseline:
    queries_used: list[str]
    snippets: list[Source]
    status: Status = "ok"
    reason: str | None = None


@dataclass(frozen=True)
class RetrievedImage:
    article_hash: str
    image_path: Path
    caption: str | None = None


@dataclass(frozen=True)
class RetrieverOutput:
    chunks: list[Source]
    image_candidates: list[RetrievedImage]
    status: Status = "ok"
    reason: str | None = None


@dataclass(frozen=True)
class ReasonerOutput:
    inferences_md: str
    additional_chunks: list[Source]
    analyzed_images: list[RetrievedImage]
    iter_count: int
    status: Status = "ok"
    reason: str | None = None


@dataclass(frozen=True)
class VerifierOutput:
    fact_check_summary_md: str
    confidence: float
    external_citations: list[Source]
    discrepancies: list[str]
    iter_count: int
    status: Status = "ok"
    reason: str | None = None


@dataclass(frozen=True)
class SynthesizerOutput:
    markdown: str
    confidence: float
    sources: list[Source]
    embedded_images: list[Path]
    note_lines: list[str]
    # NO status field — terminal stage; degradation surfaces via note_lines (Axis 8)


@dataclass
class ResearchState:
    query: str
    timestamp_start: float
    web_baseline: WebBaseline | None = None
    retrieved: RetrieverOutput | None = None
    reasoned: ReasonerOutput | None = None
    verified: VerifierOutput | None = None
    synthesized: SynthesizerOutput | None = None


@dataclass(frozen=True)
class ResearchResult:
    markdown: str
    confidence: float
    sources: list[Source]
    images_embedded: list[Path]
    state: ResearchState


@dataclass(frozen=True)
class ResearchConfig:
    rag_working_dir: Path
    llm_complete: Callable
    embedding_func: Callable
    vision_cascade: object  # VisionCascade duck-type
    web_search: Callable[[str], list[dict]]
    web_search_fallback: Callable[[str], list[dict]] | None = None
    web_extract: Callable[[str], str] | None = None
    google_search_grounding: Callable | None = None
    output_dir: Path | None = None
    telemetry_jsonl: Path | None = None
    max_iter_reasoner: int = 5
    max_iter_verifier: int = 3
    # arx-4 #64/#65: the lifespan-pinned LightRAG (built with rerank_model_func
    # in kb/api.py). When set, the retriever/reasoner reuse it instead of
    # building a fresh, reranker-less instance — so query-time rerank applies
    # (#65) and the already-hydrated storage is reused. None = CLI/skill_runner
    # builds its own fresh instance (omnigraph_search.query.search rag=None branch).
    rag: object | None = None  # LightRAG | None (object avoids a lightrag import here)

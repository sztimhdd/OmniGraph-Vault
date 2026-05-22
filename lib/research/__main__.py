"""CLI entrypoint: ``python -m omnigraph.research "<query>" [flags]``.

CLI-03 (ar-2): adds --max-iter-reasoner / --max-iter-verifier / --no-grounding
overrides on top of the ar-1 bare positional-only invocation. LLM provider
selection remains env-only (OMNIGRAPH_LLM_PROVIDER) — NO --llm-provider flag
per CLI-03's hard rule.

Pure wrapper rule (LIB-04) preserved: argparse + dataclasses.replace +
asyncio.run + print. Anything more sophisticated belongs in orchestrator.py.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import sys

from .config import from_env
from .image_server import ensure_image_server
from .orchestrator import research


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="omnigraph.research",
        description="Run the OmniGraph agentic-RAG research pipeline.",
    )
    parser.add_argument("query", help="Natural-language research query.")
    parser.add_argument(
        "--max-iter-reasoner",
        type=int,
        default=None,
        help="Override Reasoner agent-loop cap (default 5).",
    )
    parser.add_argument(
        "--max-iter-verifier",
        type=int,
        default=None,
        help="Override Verifier agent-loop cap (default 3). "
             "Plumbed in ar-2 — behavior activates after ar-3 lands real Verifier loop.",
    )
    parser.add_argument(
        "--no-grounding",
        action="store_true",
        default=False,
        help="Disable Vertex Gemini Grounding tool. "
             "Plumbed in ar-2 — behavior activates after ar-3 wires Grounding into from_env().",
    )
    return parser.parse_args(argv)


async def _amain(ns: argparse.Namespace) -> str:
    cfg = from_env()
    overrides: dict = {}
    if ns.max_iter_reasoner is not None:
        overrides["max_iter_reasoner"] = ns.max_iter_reasoner
    if ns.max_iter_verifier is not None:
        overrides["max_iter_verifier"] = ns.max_iter_verifier
    if ns.no_grounding:
        overrides["google_search_grounding"] = None
    if overrides:
        cfg = dataclasses.replace(cfg, **overrides)
    base_image_dir = cfg.rag_working_dir.parent / "images"
    if base_image_dir.is_dir():
        ensure_image_server(base_image_dir)
    result = await research(ns.query, cfg)
    return result.markdown


def main(argv: list[str] | None = None) -> None:
    ns = _parse_args(argv)
    markdown = asyncio.run(_amain(ns))
    # The synthesizer can emit CJK; on Windows the default console codepage
    # (cp1252) raises UnicodeEncodeError on print(). Reconfigure stdout to
    # UTF-8 if available (Python 3.7+ provides this on TextIOWrapper).
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass
    print(markdown)


if __name__ == "__main__":
    main(sys.argv[1:])

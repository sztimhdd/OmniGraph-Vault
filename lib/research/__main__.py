"""CLI entrypoint: ``python -m omnigraph.research "<query>"``.

CLI-01: Pure wrapper — argparse + asyncio.run + print. No business logic.
Anything more sophisticated belongs in orchestrator.py.
"""
from __future__ import annotations

import argparse
import asyncio
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
    return parser.parse_args(argv)


async def _amain(query: str) -> str:
    cfg = from_env()
    # ORCH-08: bring up the local image HTTP server before synthesizer
    # embeds http://localhost:8765/... URLs.
    base_image_dir = cfg.rag_working_dir.parent / "images"
    if base_image_dir.is_dir():
        ensure_image_server(base_image_dir)
    result = await research(query, cfg)
    return result.markdown


def main(argv: list[str] | None = None) -> None:
    ns = _parse_args(argv)
    markdown = asyncio.run(_amain(ns.query))
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

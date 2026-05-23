"""CLI entrypoint: ``python -m omnigraph.research "<query>" [flags]``.

CLI-03 (ar-2): adds --max-iter-reasoner / --max-iter-verifier / --no-grounding
overrides on top of the ar-1 bare positional-only invocation. LLM provider
selection remains env-only (OMNIGRAPH_LLM_PROVIDER) — NO --llm-provider flag
per CLI-03's hard rule.

CLI-02 (ar-4): adds --dump-state <path> for offline ResearchState inspection.
Stdout markdown is preserved unchanged. The serializer helper
:func:`_write_dump_state` lives in this file (NOT in ``lib/research/``
proper) so the package retains its pure-async no-CLI-side-effects
character (Axis 1).

Pure wrapper rule (LIB-04) preserved: argparse + dataclasses.replace +
asyncio.run + print at module level. Anything more sophisticated belongs
in orchestrator.py. JSON / pathlib / dataclass-asdict imports needed by
:func:`_write_dump_state` are deferred into the helper body so the
module-level import alphabet remains the ar-2-03 baseline (config,
image_server, orchestrator + stdlib argparse/asyncio/dataclasses/sys).
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
    parser.add_argument(
        "--dump-state",
        type=str,
        default=None,
        help="Optional path. When set, writes the final ResearchState as JSONL "
             "(header line + one line per non-None stage). Stdout markdown is "
             "unchanged. (CLI-02)",
    )
    return parser.parse_args(argv)


def _write_dump_state(state, path) -> None:
    """JSONL dump of ``ResearchState``.

    One header line + one line per non-None stage. Schema version
    ``"ar-4"``. Path I/O is __main__-only; ``lib/research/`` proper
    stays free of CLI side effects (Axis 1).

    Imports for ``json`` / ``pathlib.Path`` / ``dataclasses.asdict`` are
    deferred into the function body so the module-level import alphabet
    matches the ar-2-03 baseline (LIB-04 pure-wrapper rule).

    Header shape::

        {"kind": "header", "query": <str>, "timestamp_start": <float>,
         "schema_version": "ar-4"}

    Stage shape (per non-None state field)::

        {"kind": "stage", "stage": "<name>", **asdict(stage_obj)}
    """
    import json
    from dataclasses import asdict
    from pathlib import Path as _Path

    p = path if isinstance(path, _Path) else _Path(path)

    def _default(obj):
        if isinstance(obj, _Path):
            return str(obj)
        return str(obj)

    stage_names = ("web_baseline", "retrieved", "reasoned", "verified", "synthesized")
    with p.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "kind": "header",
                    "query": state.query,
                    "timestamp_start": state.timestamp_start,
                    "schema_version": "ar-4",
                },
                default=_default,
            )
            + "\n"
        )
        for name in stage_names:
            stage_obj = getattr(state, name, None)
            if stage_obj is None:
                continue
            f.write(
                json.dumps(
                    {"kind": "stage", "stage": name, **asdict(stage_obj)},
                    default=_default,
                )
                + "\n"
            )


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
    if ns.dump_state is not None:
        _write_dump_state(result.state, ns.dump_state)
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

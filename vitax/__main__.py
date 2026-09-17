"""Command-line interface for the VitaX public knowledge read model."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from .knowledge import KnowledgeError, KnowledgeReader, build


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m vitax")
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("projection")
    build_parser.add_argument("output")
    for name in ("search", "read-knowledge", "read-evidence", "related"):
        command = commands.add_parser(name)
        command.add_argument("database")
        command.add_argument("value")
        if name in {"search", "related"}:
            command.add_argument("--limit", type=int, default=10)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "build":
            result = build(args.projection, args.output)
        else:
            with KnowledgeReader(args.database) as reader:
                if args.command == "search":
                    result = reader.search(args.value, args.limit)
                elif args.command == "read-knowledge":
                    result = reader.read_knowledge(args.value)
                elif args.command == "read-evidence":
                    result = reader.read_evidence(args.value)
                else:
                    result = reader.related(args.value, args.limit)
    except (KnowledgeError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

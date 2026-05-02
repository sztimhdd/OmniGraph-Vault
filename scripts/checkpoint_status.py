#!/usr/bin/env python3
"""List all checkpoint directories with their stage status.

Output is a Markdown-style pipe-separated table suitable for `watch`:

    CHECKPOINTS (N total, X in-flight, Y complete)

    hash             | url                           | last_stage     | age    | status
    -----------------|-------------------------------|----------------|--------|----------
    100680ad546ce6a5 | https://mp.weixin.qq.com/s/X  | text_ingest    | 2h15m  | complete
    ...

Use with:  watch -n 5 'python scripts/checkpoint_status.py | tail -20'
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.checkpoint import list_checkpoints  # noqa: E402


def _fmt_age(seconds) -> str:
    if seconds is None:
        return "?"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h{(s % 3600) // 60}m"
    return f"{s // 86400}d{(s % 86400) // 3600}h"


def _truncate(s: str, width: int) -> str:
    return s if len(s) <= width else s[: width - 1] + "..."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--tsv", action="store_true", help="Tab-separated output (machine-parsable)")
    args = parser.parse_args(argv)

    records = list_checkpoints()
    total = len(records)
    complete = sum(1 for r in records if r["status"] == "complete")
    in_flight = total - complete

    if args.tsv:
        print("hash\turl\ttitle\tlast_stage\tage_seconds\tstatus")
        for r in records:
            age = r["age_seconds"] if r["age_seconds"] is not None else ""
            last = r["last_stage"] or ""
            print(f"{r['hash']}\t{r['url']}\t{r['title']}\t{last}\t{age}\t{r['status']}")
        return 0

    print(f"CHECKPOINTS ({total} total, {in_flight} in-flight, {complete} complete)")
    print()
    if not records:
        print("(no checkpoints found under ~/.hermes/omonigraph-vault/checkpoints/)")
        return 0

    header = f"{'hash':<16} | {'url':<40} | {'last_stage':<14} | {'age':<7} | {'status':<9}"
    print(header)
    print("-" * len(header))
    for r in records:
        print(
            f"{r['hash']:<16} | "
            f"{_truncate(r['url'], 40):<40} | "
            f"{(r['last_stage'] or '-'):<14} | "
            f"{_fmt_age(r['age_seconds']):<7} | "
            f"{r['status']:<9}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Phase 21 STK-02 + STK-03: cleanup CLI for failed LightRAG docs.

Reports stuck documents and refuses deletion until every RAG writer shares a
single process lock. This preserves original documents and avoids racing an
active ingest process.

Flags:
    --dry-run        count diagnostic candidates only; no mutation (combinable with --all-failed)
    --all-failed     report failed docs, reject processing, then fail closed
    --hash <doc_id>  report one failed doc, then fail closed

Exit codes:
    0  dry-run / nothing-to-clean / idempotent-missing-hash
    1  a requested deletion is refused, or an unexpected exception occurred
    2  argparse usage error
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import RAG_WORKING_DIR  # noqa: E402

logger = logging.getLogger("cleanup_stuck_docs")

# JSON report schema — single source of truth (tests import these)
SkipReason = Literal[
    "pipeline_lock_unshared", "processing_not_eligible", "not_failed_status",
    "doc_not_found", "invalid_status_entry",
]


class SkipEntry(TypedDict):
    doc_id: str
    status: str
    reason: SkipReason


class CleanupReport(TypedDict):
    docs_identified: int
    docs_deleted: int
    docs_skipped: int
    skipped_reasons: list[SkipEntry]
    elapsed_ms: int


_ELIGIBLE_STATUSES = ("failed",)
_DIAGNOSTIC_STATUSES = ("failed", "processing")


def _load_doc_status(storage_dir: Path) -> dict[str, dict]:
    path = storage_dir / "kv_store_doc_status.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _filter_candidates(status_map: dict[str, dict]) -> list[tuple[str, str]]:
    return [
        (doc_id, entry.get("status", ""))
        for doc_id, entry in status_map.items()
        if isinstance(entry, dict) and entry.get("status") in _ELIGIBLE_STATUSES
    ]


def _processing_entries(status_map: dict[str, dict]) -> list[tuple[str, str]]:
    return [
        (doc_id, "processing")
        for doc_id, entry in status_map.items()
        if isinstance(entry, dict) and entry.get("status") == "processing"
    ]


def _skip(doc_id: str, status: str, reason: SkipReason) -> SkipEntry:
    return {"doc_id": doc_id, "status": status, "reason": reason}


async def _build_rag() -> Any:
    """Reserved write seam; fail-closed modes must not call it."""
    from ingest_wechat import get_rag
    return await get_rag(flush=False)


async def main_async(args: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    storage_dir = RAG_WORKING_DIR
    status_map = _load_doc_status(storage_dir)
    report: CleanupReport = {
        "docs_identified": 0, "docs_deleted": 0, "docs_skipped": 0,
        "skipped_reasons": [], "elapsed_ms": 0,
    }
    exit_code = 0

    if args.dry_run:
        report["docs_identified"] = sum(
            1
            for entry in status_map.values()
            if isinstance(entry, dict)
            and entry.get("status") in _DIAGNOSTIC_STATUSES
        )
    elif args.all_failed:
        candidates = _filter_candidates(status_map)
        report["docs_identified"] = len(candidates)
        report["skipped_reasons"].extend(
            _skip(doc_id, status, "processing_not_eligible")
            for doc_id, status in _processing_entries(status_map)
        )
        if candidates:
            report["skipped_reasons"].extend(
                _skip(doc_id, status, "pipeline_lock_unshared")
                for doc_id, status in candidates
            )
            exit_code = 1
    elif args.hash is not None:
        doc_id = args.hash
        entry = status_map.get(doc_id)
        if entry is None:
            report["skipped_reasons"].append(_skip(doc_id, "missing", "doc_not_found"))
        elif not isinstance(entry, dict):
            report["skipped_reasons"].append(
                _skip(doc_id, "invalid", "invalid_status_entry"))
            exit_code = 1
        else:
            actual_status = entry.get("status", "")
            if actual_status == "processing":
                report["skipped_reasons"].append(
                    _skip(doc_id, actual_status, "processing_not_eligible"))
                exit_code = 1
            elif actual_status not in _ELIGIBLE_STATUSES:
                report["skipped_reasons"].append(
                    _skip(doc_id, actual_status, "not_failed_status"))
                exit_code = 1
            else:
                report["docs_identified"] = 1
                report["skipped_reasons"].append(
                    _skip(doc_id, actual_status, "pipeline_lock_unshared"))
                exit_code = 1

    report["docs_skipped"] = len(report["skipped_reasons"])
    report["elapsed_ms"] = int(round((time.perf_counter() - t0) * 1000))
    print(json.dumps(report, ensure_ascii=False))
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="count candidates only; combinable with --all-failed")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all-failed", action="store_true",
                       help="report failed docs, reject processing, then fail closed")
    group.add_argument("--hash", metavar="DOC_ID", default=None,
                       help="report one failed doc, then fail closed")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not (args.dry_run or args.all_failed or args.hash):
        parser.print_help()
        return 0
    if args.dry_run and args.hash is not None:
        parser.error("--dry-run cannot be combined with --hash")
        return 2  # unreachable; parser.error sys.exits
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001 — operator-facing top-level guard
        sys.stderr.write(f"unexpected error: {exc!r}\n")
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main())

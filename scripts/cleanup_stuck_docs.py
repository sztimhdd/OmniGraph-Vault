#!/usr/bin/env python3
"""Phase 21 STK-02 + STK-03: cleanup CLI for FAILED / PROCESSING LightRAG docs.

Lists or deletes stuck documents via `LightRAG.adelete_by_doc_id` (verified
residue-free per `.planning/phases/21-stuck-doc-spike/21-00-SPIKE-FINDINGS.md`).

Flags:
    --dry-run        list candidates only; no mutation (combinable with --all-failed)
    --all-failed     delete every doc with status in {failed, processing}
    --hash <doc_id>  delete one specific doc; idempotent if already absent

Exit codes:
    0  dry-run / nothing-to-clean / all-cleaned / idempotent-missing-hash
    1  --hash targets a PROCESSED doc, OR an unexpected exception occurred
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
    "pipeline_busy", "not_failed_status", "doc_not_found", "delete_returned_error",
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


_ELIGIBLE_STATUSES = ("failed", "processing")


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


def _skip(doc_id: str, status: str, reason: SkipReason) -> SkipEntry:
    return {"doc_id": doc_id, "status": status, "reason": reason}


def _emit_pipeline_busy_warning(storage_dir: Path) -> None:
    """Best-effort advisory; NEVER raises. Empty signal = silent."""
    try:
        from lightrag.kg.shared_storage import get_pipeline_status_lock  # noqa: F401
    except (ImportError, AttributeError):
        pass
    try:
        path = storage_dir / "kv_store_doc_status.json"
        if path.exists():
            age_s = time.time() - path.stat().st_mtime
            if age_s < 60:
                sys.stderr.write(
                    f"WARNING: pipeline appears busy (kv_store_doc_status.json "
                    f"modified {int(age_s)}s ago) — deletion may race\n"
                )
    except OSError:
        pass


async def _build_rag() -> Any:
    """Seam for tests. Late import so .env loads first."""
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
        report["docs_identified"] = len(_filter_candidates(status_map))
    elif args.all_failed:
        candidates = _filter_candidates(status_map)
        report["docs_identified"] = len(candidates)
        if candidates:
            _emit_pipeline_busy_warning(storage_dir)
            rag = await _build_rag()
            for doc_id, status in candidates:
                result = await rag.adelete_by_doc_id(doc_id)
                if getattr(result, "status", None) == "success":
                    report["docs_deleted"] += 1
                else:
                    report["skipped_reasons"].append(
                        _skip(doc_id, status, "delete_returned_error"))
    elif args.hash is not None:
        doc_id = args.hash
        entry = status_map.get(doc_id)
        if entry is None:
            report["skipped_reasons"].append(_skip(doc_id, "missing", "doc_not_found"))
        else:
            actual_status = entry.get("status", "")
            if actual_status not in _ELIGIBLE_STATUSES:
                report["skipped_reasons"].append(
                    _skip(doc_id, actual_status, "not_failed_status"))
                exit_code = 1
            else:
                report["docs_identified"] = 1
                _emit_pipeline_busy_warning(storage_dir)
                rag = await _build_rag()
                result = await rag.adelete_by_doc_id(doc_id)
                if getattr(result, "status", None) == "success":
                    report["docs_deleted"] = 1
                else:
                    report["skipped_reasons"].append(
                        _skip(doc_id, actual_status, "delete_returned_error"))

    report["docs_skipped"] = len(report["skipped_reasons"])
    report["elapsed_ms"] = int(round((time.perf_counter() - t0) * 1000))
    print(json.dumps(report, ensure_ascii=False))
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="list candidates only; combinable with --all-failed")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all-failed", action="store_true",
                       help="delete every doc with status in (failed, processing)")
    group.add_argument("--hash", metavar="DOC_ID", default=None,
                       help="delete exactly one doc by id (idempotent if absent)")
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

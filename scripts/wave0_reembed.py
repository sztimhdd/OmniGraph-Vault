"""Wave 0 re-embed: replace existing LightRAG docs with new embedding base.

Runs the Phase 4 D-17 proven ``adelete_by_doc_id`` + ``ainsert`` path for every
doc currently in ``kv_store_full_docs.json``. Uses the consolidated
``lightrag_embedding.embedding_func`` (gemini-embedding-2, 768-dim) so the
vectors refresh without changing NanoVectorDB's recorded ``embedding_dim``.

Usage:
    python scripts/wave0_reembed.py --dry-run            # print plan, no mutations
    python scripts/wave0_reembed.py --one-doc <doc_id>   # test on single doc
    python scripts/wave0_reembed.py                      # full run

Order of operations (run from remote WSL host):
    1. WAVE0_MODE=baseline venv/bin/python tests/verify_wave0_benchmark.py
    2. venv/bin/python scripts/wave0_reembed.py
    3. venv/bin/python tests/verify_wave0_benchmark.py
    4. venv/bin/python tests/verify_wave0_crossmodal.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Must run in repo root so ``from config import ...`` works.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import RAG_WORKING_DIR, load_env  # noqa: E402

load_env()

from ingest_wechat import get_rag  # noqa: E402  — reuses the same LightRAG construction as the live ingest path


FULL_DOCS_PATH = Path(RAG_WORKING_DIR) / "kv_store_full_docs.json"
SPIKE_REPORT_PATH = REPO_ROOT / "docs" / "spikes" / "embedding-002-contract.md"
REEMBED_LOG_PATH = REPO_ROOT / "docs" / "spikes" / "wave0_reembed_log.md"


def parse_rpm_ceiling_from_spike() -> int:
    """Read the spike report's ``rpm_ceiling`` value. Returns 0 if unavailable."""
    if not SPIKE_REPORT_PATH.exists():
        return 0
    text = SPIKE_REPORT_PATH.read_text(encoding="utf-8")
    match = re.search(r"^rpm_ceiling:\s*(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


def load_doc_map() -> dict[str, dict]:
    """Return dict[doc_id, doc_dict] from kv_store_full_docs.json."""
    if not FULL_DOCS_PATH.exists():
        raise SystemExit(f"Missing {FULL_DOCS_PATH}")
    return json.loads(FULL_DOCS_PATH.read_text(encoding="utf-8"))


async def count_graph_state(rag) -> dict[str, int]:
    """Snapshot entity / relationship / chunk counts from the vdb_*.json storage."""
    counts: dict[str, int] = {}
    for label, fname in (
        ("entities", "vdb_entities.json"),
        ("relationships", "vdb_relationships.json"),
        ("chunks", "vdb_chunks.json"),
    ):
        path = Path(RAG_WORKING_DIR) / fname
        if not path.exists():
            counts[label] = 0
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # NanoVectorDB stores {"embedding_dim": N, "data": [...], ...}
            counts[label] = len(data.get("data", []))
        except Exception:
            counts[label] = -1
    return counts


def write_log(before: dict, after: dict, processed: int, errors: list[str]) -> None:
    REEMBED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Wave 0 Re-embed Log",
        f"date: {datetime.utcnow().isoformat()}Z",
        f"before: entities={before['entities']}, "
        f"relationships={before['relationships']}, chunks={before['chunks']}",
        f"processed: {processed} docs",
        f"after:  entities={after['entities']}, "
        f"relationships={after['relationships']}, chunks={after['chunks']}",
        f"errors: {errors}",
        "",
    ]
    REEMBED_LOG_PATH.write_text("\n".join(lines), encoding="utf-8")


async def main(dry_run: bool, one_doc: str | None) -> int:
    rpm_ceiling = parse_rpm_ceiling_from_spike()
    print(
        f"Spike rpm_ceiling={rpm_ceiling} — keeping embedding_func_max_async=1 "
        "and embedding_batch_num=20 (conservative)."
    )

    doc_map = load_doc_map()
    if one_doc:
        if one_doc not in doc_map:
            print(f"--one-doc '{one_doc}' not in kv_store_full_docs.json", file=sys.stderr)
            return 1
        selected = {one_doc: doc_map[one_doc]}
    else:
        selected = doc_map

    print(f"Total docs in store: {len(doc_map)}; selected for re-embed: {len(selected)}")

    rag = await get_rag()

    before = await count_graph_state(rag)
    print(f"BEFORE: {before}")

    errors: list[str] = []
    processed = 0
    start = time.time()

    for doc_id, doc in selected.items():
        content = doc.get("content", "")
        if not content:
            print(f"  SKIP (empty content): {doc_id}")
            continue

        if dry_run:
            print(f"  WOULD delete {doc_id} and re-ainsert {len(content)} chars")
            processed += 1
            continue

        try:
            # Phase 4 D-17 proven pattern
            await rag.adelete_by_doc_id(doc_id)
            await rag.ainsert(content)
            processed += 1
            print(
                f"  [{processed}/{len(selected)}] re-embedded {doc_id} "
                f"({len(content)} chars)"
            )
        except Exception as exc:
            msg = f"{doc_id}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            print(f"  ERROR {msg}")
            traceback.print_exc()

    after = await count_graph_state(rag)
    print(f"AFTER: {after}")
    print(f"Duration: {time.time() - start:.1f}s, processed={processed}, errors={len(errors)}")

    if not dry_run:
        write_log(before, after, processed, errors)
        print(f"Log written to {REEMBED_LOG_PATH}")

    return 0 if not errors else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="enumerate doc IDs and print planned actions; no calls to adelete_by_doc_id or ainsert",
    )
    parser.add_argument(
        "--one-doc",
        metavar="DOC_ID",
        default=None,
        help="operate on just this doc id (for incremental testing)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run, one_doc=args.one_doc)))

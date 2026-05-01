"""Wave 0 re-embed: wipe NanoVectorDB and re-ingest all docs at gemini-embedding-2 / 3072 dim.

Strategy (3072-dim migration — cannot use delete-by-id):
    1. Read RAG_WORKING_DIR/kv_store_full_docs.json -> {doc_id: {"content": str, ...}}
    2. Back up kv_store_full_docs.json to kv_store_full_docs.json.bak
    3. Wipe vdb_chunks.json, vdb_entities.json, vdb_relationships.json (and
       kv_store_full_docs.json itself so LightRAG dedup re-admits each insert)
    4. Construct a fresh LightRAG (via ingest_wechat.get_rag — now embedding_dim=3072)
    5. For each doc-id from the backup: rag.ainsert(content) -> LightRAG re-chunks,
       extracts entities, computes 3072-dim embeddings, writes new vdb files
    6. Verify new vdb_chunks.json has "embedding_dim": 3072

Why vdb-wipe (not the Phase 4 delete-by-id path):
    NanoVectorDB asserts storage["embedding_dim"] == decorator embedding_dim on
    LightRAG init (nano_vectordb/dbs.py:72-74). Dim change 768 -> 3072 triggers
    AssertionError BEFORE any per-doc delete API could run. The wipe must happen
    before any LightRAG is constructed at the new dim.

Baseline preservation:
    Task 0.5 captures tests/fixtures/wave0_baseline.json BEFORE this script
    runs. This script NEVER touches tests/fixtures/. The wipe is scoped to
    ``~/.hermes/omonigraph-vault/lightrag_storage/vdb_*.json`` +
    ``kv_store_full_docs.json`` only.

Usage:
    python scripts/wave0_reembed.py --dry-run            # print plan, no mutations
    python scripts/wave0_reembed.py --one-doc <doc_id>   # test on single doc against /tmp storage
    python scripts/wave0_reembed.py --i-understand       # full run (wipe + reingest)

Order of operations (run from remote WSL host):
    1. WAVE0_MODE=baseline venv/bin/python tests/verify_wave0_benchmark.py
    2. venv/bin/python scripts/wave0_reembed.py --i-understand
    3. venv/bin/python tests/verify_wave0_benchmark.py
    4. venv/bin/python tests/verify_wave0_crossmodal.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
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


STORAGE = Path(RAG_WORKING_DIR)
FULL_DOCS_PATH = STORAGE / "kv_store_full_docs.json"
FULL_DOCS_BAK = STORAGE / "kv_store_full_docs.json.bak"
VDB_FILES = [
    STORAGE / "vdb_chunks.json",
    STORAGE / "vdb_entities.json",
    STORAGE / "vdb_relationships.json",
]
SPIKE_REPORT_PATH = REPO_ROOT / "docs" / "spikes" / "embedding-002-contract.md"
REEMBED_LOG_PATH = REPO_ROOT / "docs" / "spikes" / "wave0_reembed_log.md"


def parse_rpm_ceiling_from_spike() -> int:
    """Read the spike report's ``rpm_ceiling`` value. Returns 0 if unavailable."""
    if not SPIKE_REPORT_PATH.exists():
        return 0
    text = SPIKE_REPORT_PATH.read_text(encoding="utf-8")
    match = re.search(r"^rpm_ceiling:\s*(\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


def load_doc_map_from_backup() -> dict[str, dict]:
    """Return dict[doc_id, doc_dict] from kv_store_full_docs.json (or .bak if wipe already done)."""
    source = FULL_DOCS_PATH if FULL_DOCS_PATH.exists() else FULL_DOCS_BAK
    if not source.exists():
        raise SystemExit(
            f"Missing both {FULL_DOCS_PATH} and {FULL_DOCS_BAK} — nothing to re-embed."
        )
    return json.loads(source.read_text(encoding="utf-8"))


def read_vdb_counts(storage_dir: Path) -> dict[str, object]:
    """Snapshot embedding_dim + row count for each vdb_*.json in ``storage_dir``."""
    counts: dict[str, object] = {}
    for fname in ("vdb_chunks.json", "vdb_entities.json", "vdb_relationships.json"):
        path = storage_dir / fname
        if not path.exists():
            counts[fname] = {"present": False}
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            counts[fname] = {
                "present": True,
                "embedding_dim": data.get("embedding_dim"),
                "rows": len(data.get("data", [])),
            }
        except Exception as exc:  # pragma: no cover - defensive
            counts[fname] = {"present": True, "error": str(exc)}
    return counts


def backup_full_docs() -> None:
    """Copy kv_store_full_docs.json -> .bak (overwrite allowed)."""
    if not FULL_DOCS_PATH.exists():
        return
    shutil.copy(FULL_DOCS_PATH, FULL_DOCS_BAK)
    print(f"Backed up {FULL_DOCS_PATH} -> {FULL_DOCS_BAK}")


def wipe_vdb_and_full_docs() -> list[Path]:
    """Delete all LightRAG persistent state files in ``STORAGE``.

    A 768 -> 3072 dim migration requires wiping ALL graph state, not just the
    three ``vdb_*.json`` files. LightRAG tracks doc-level dedup in
    ``kv_store_doc_status.json``; if that file survives, every re-ainsert of a
    pre-existing doc is rejected as a duplicate and no new 3072-dim embedding
    is ever computed for it.

    Files removed:
      - ``vdb_chunks.json`` / ``vdb_entities.json`` / ``vdb_relationships.json``
      - Every ``kv_store_*.json`` (doc_status, text_chunks, full_docs, entities,
        relations, entity_chunks, relation_chunks, llm_response_cache)
      - ``graph_chunk_entity_relation.graphml`` (entity IDs become stale)

    Preserved:
      - ``kv_store_full_docs.json.bak`` (the backup used to re-ingest from)
    """
    removed: list[Path] = []
    # vdb files
    for p in VDB_FILES:
        if p.exists():
            p.unlink()
            removed.append(p)
            print(f"Wiped {p}")
    # kv_store files — all of them, except the .bak backup
    for p in sorted(STORAGE.glob("kv_store_*.json")):
        if p.name.endswith(".bak"):
            continue
        p.unlink()
        removed.append(p)
        print(f"Wiped {p}")
    # graph file (entity UUIDs are re-generated on rebuild)
    graphml = STORAGE / "graph_chunk_entity_relation.graphml"
    if graphml.exists():
        graphml.unlink()
        removed.append(graphml)
        print(f"Wiped {graphml}")
    return removed


def write_log(
    before: dict, after: dict, processed: int, errors: list[str]
) -> None:
    REEMBED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    before_dim = _probe_dim(before)
    after_dim = _probe_dim(after)
    lines = [
        "# Wave 0 Re-embed Log",
        f"strategy: vdb-wipe-reingest (768->3072 dim migration)",
        f"date: {datetime.utcnow().isoformat()}Z",
        f"before: entities={_rows(before, 'vdb_entities.json')}, "
        f"relationships={_rows(before, 'vdb_relationships.json')}, "
        f"chunks={_rows(before, 'vdb_chunks.json')}, "
        f"embedding_dim={before_dim}",
        f"processed: {processed} docs",
        f"after:  entities={_rows(after, 'vdb_entities.json')}, "
        f"relationships={_rows(after, 'vdb_relationships.json')}, "
        f"chunks={_rows(after, 'vdb_chunks.json')}, "
        f"embedding_dim={after_dim}",
        f"errors: {errors}",
        "",
    ]
    REEMBED_LOG_PATH.write_text("\n".join(lines), encoding="utf-8")


def _rows(snap: dict, fname: str) -> int | str:
    entry = snap.get(fname, {})
    if isinstance(entry, dict) and "rows" in entry:
        return entry["rows"]
    return "?"


def _probe_dim(snap: dict) -> int | str:
    entry = snap.get("vdb_chunks.json", {})
    if isinstance(entry, dict):
        return entry.get("embedding_dim", "?")
    return "?"


async def _do_full_run(doc_map: dict[str, dict]) -> tuple[int, list[str]]:
    """Wipe, construct fresh 3072-dim LightRAG, re-ainsert every doc."""
    # Import here so wipe happens before LightRAG is constructed (dim assertion).
    from ingest_wechat import get_rag  # noqa: WPS433 - intentional late import

    # D-09.07: flush=False preserves historical "reuse prior state" semantics for this spike.
    rag = await get_rag(flush=False)

    errors: list[str] = []
    processed = 0
    total = len(doc_map)
    start = time.time()

    for doc_id, doc in doc_map.items():
        content = doc.get("content", "")
        if not content:
            print(f"  SKIP (empty content): {doc_id}")
            continue
        try:
            await rag.ainsert(content)
            processed += 1
            print(
                f"  [{processed}/{total}] re-ingested {doc_id} "
                f"({len(content)} chars)"
            )
        except Exception as exc:  # noqa: BLE001 - log and continue
            msg = f"{doc_id}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            print(f"  ERROR {msg}")
            traceback.print_exc()

    print(f"Duration: {time.time() - start:.1f}s, processed={processed}, errors={len(errors)}")
    return processed, errors


async def _run_one_doc_against_tmp(doc_id: str, doc_map: dict[str, dict]) -> int:
    """Exercise the pipeline on a single doc against a TEMPORARY storage dir.

    Does NOT touch production storage. Used to smoke-test the 3072 pipeline
    before the user commits to wiping the full graph.
    """
    if doc_id not in doc_map:
        print(f"--one-doc '{doc_id}' not in {FULL_DOCS_PATH.name}", file=sys.stderr)
        return 1

    tmp_dir = Path("/tmp/wave0_one_doc")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    print(f"[one-doc] Using temporary storage at {tmp_dir}")

    # Patch the global RAG_WORKING_DIR for the duration of this test.
    import config  # noqa: WPS433 - intentional late import

    original = config.RAG_WORKING_DIR
    config.RAG_WORKING_DIR = str(tmp_dir)
    try:
        from ingest_wechat import get_rag  # noqa: WPS433

        # D-09.07: flush=False preserves historical "reuse prior state" semantics for this spike.
        rag = await get_rag(flush=False)
        content = doc_map[doc_id]["content"]
        print(f"[one-doc] ainsert {doc_id} ({len(content)} chars)")
        await rag.ainsert(content)
        print(f"[one-doc] post-run state: {read_vdb_counts(tmp_dir)}")
    finally:
        config.RAG_WORKING_DIR = original

    return 0


async def main(dry_run: bool, one_doc: str | None, i_understand: bool) -> int:
    rpm_ceiling = parse_rpm_ceiling_from_spike()
    print(
        f"Spike rpm_ceiling={rpm_ceiling} - keeping embedding_func_max_async=1 "
        "and embedding_batch_num=20 (conservative)."
    )

    doc_map = load_doc_map_from_backup()
    print(f"Total docs recovered from full_docs store: {len(doc_map)}")

    if one_doc:
        return await _run_one_doc_against_tmp(one_doc, doc_map)

    before = read_vdb_counts(STORAGE)
    print(f"BEFORE: {before}")

    # Files that the real wipe_vdb_and_full_docs() would delete.
    # Kept here purely so --dry-run and the --i-understand refusal message
    # show the same list that wipe_vdb_and_full_docs() actually touches.
    wipe_preview: list[Path] = list(VDB_FILES)
    wipe_preview.extend(
        p for p in sorted(STORAGE.glob("kv_store_*.json")) if not p.name.endswith(".bak")
    )
    graphml = STORAGE / "graph_chunk_entity_relation.graphml"
    if graphml.exists():
        wipe_preview.append(graphml)

    if dry_run:
        print("\n--dry-run: no filesystem mutations, no LightRAG construction")
        for doc_id, doc in doc_map.items():
            content = doc.get("content", "")
            print(
                f"  WOULD wipe vdb + re-ainsert {doc_id} "
                f"({len(content)} chars)"
            )
        print(f"\nWould wipe these files (not deleting in dry-run):")
        for p in wipe_preview:
            print(f"  {p}")
        return 0

    if not i_understand:
        print("\nREFUSING to wipe NanoVectorDB storage without --i-understand.", file=sys.stderr)
        print("The following files WOULD be deleted on a real run:", file=sys.stderr)
        for p in wipe_preview:
            print(f"  {p}", file=sys.stderr)
        print("\nRe-run with --i-understand to confirm.", file=sys.stderr)
        return 1

    # Real run: backup, wipe, re-ingest
    backup_full_docs()
    wipe_vdb_and_full_docs()

    processed, errors = await _do_full_run(doc_map)
    after = read_vdb_counts(STORAGE)
    print(f"AFTER: {after}")

    write_log(before, after, processed, errors)
    print(f"Log written to {REEMBED_LOG_PATH}")

    # Final dim verification
    chunks_entry = after.get("vdb_chunks.json", {})
    post_dim = chunks_entry.get("embedding_dim") if isinstance(chunks_entry, dict) else None
    if post_dim != 3072:
        print(
            f"ERROR: post-run vdb_chunks.json embedding_dim={post_dim} (expected 3072)",
            file=sys.stderr,
        )
        return 3

    return 0 if not errors else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="enumerate doc IDs and print planned actions; NO filesystem mutations",
    )
    parser.add_argument(
        "--one-doc",
        metavar="DOC_ID",
        default=None,
        help="operate on just this doc id against a temporary /tmp storage dir",
    )
    parser.add_argument(
        "--i-understand",
        action="store_true",
        help="SAFETY GATE: required to perform the real wipe + re-ingest",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(
        asyncio.run(
            main(
                dry_run=args.dry_run,
                one_doc=args.one_doc,
                i_understand=args.i_understand,
            )
        )
    )

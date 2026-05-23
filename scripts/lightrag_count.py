"""Count LightRAG storage entities / relations / chunks / kv_keys.

Read-only diagnostic. Used by aim-2-4 (STORAGE-04) to prove byte-identical
storage between Hermes source and Aliyun extracted copy. Output is JSON on
stdout; diagnostic logging goes to stderr.

Usage:
    python scripts/lightrag_count.py /path/to/lightrag_storage/
    python scripts/lightrag_count.py --help

Exit 0 = success (JSON printed). Exit 1 = path missing / unreadable.
Exit 2 = required LightRAG storage files missing under the path.

Counts:
    entities  : nodes in graph_chunk_entity_relation.graphml
    relations : edges in graph_chunk_entity_relation.graphml
    chunks    : keys in kv_store_text_chunks.json (LightRAG v1+)
    kv_keys   : total keys across all kv_store_*.json files
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import networkx as nx

SCRIPT_VERSION = "1.0"

logger = logging.getLogger("lightrag_count")
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")


def count_graph(storage: Path) -> tuple[int, int]:
    """Return (entity_count, relation_count) from the GraphML file."""
    graphml = storage / "graph_chunk_entity_relation.graphml"
    if not graphml.exists():
        raise FileNotFoundError(f"GraphML not found: {graphml}")
    g = nx.read_graphml(str(graphml))
    return g.number_of_nodes(), g.number_of_edges()


def count_chunks(storage: Path) -> int:
    """Return chunk count from kv_store_text_chunks.json."""
    chunks_file = storage / "kv_store_text_chunks.json"
    if not chunks_file.exists():
        # LightRAG variants may name it differently; treat as 0 with warning.
        logger.warning("kv_store_text_chunks.json not present under %s", storage)
        return 0
    with chunks_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"kv_store_text_chunks.json root is not a dict: {type(data)}")
    return len(data)


def count_kv_keys(storage: Path) -> int:
    """Return total key count summed across all kv_store_*.json files."""
    total = 0
    for kv in sorted(storage.glob("kv_store_*.json")):
        with kv.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            total += len(data)
        else:
            logger.warning("kv_store file %s root is not a dict — skipping", kv.name)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count LightRAG storage entities / relations / chunks / kv_keys (read-only).",
    )
    parser.add_argument(
        "storage",
        type=Path,
        help="Path to a LightRAG storage directory (containing graph_chunk_entity_relation.graphml + kv_store_*.json).",
    )
    args = parser.parse_args()

    storage: Path = args.storage
    if not storage.exists():
        logger.error("storage path does not exist: %s", storage)
        return 1
    if not storage.is_dir():
        logger.error("storage path is not a directory: %s", storage)
        return 1

    try:
        entities, relations = count_graph(storage)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 2
    chunks = count_chunks(storage)
    kv_keys = count_kv_keys(storage)

    result = {
        "script_version": SCRIPT_VERSION,
        "storage_path": str(storage.resolve()),
        "entities": entities,
        "relations": relations,
        "chunks": chunks,
        "kv_keys": kv_keys,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

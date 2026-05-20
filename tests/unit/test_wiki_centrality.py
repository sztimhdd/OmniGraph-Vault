"""Unit tests for scripts/wiki_rank_entities.py centrality ranking.

Per CLAUDE.md feedback_test_mirrors_impl: scores are hand-computed in this
file, NOT imported from the production module. If the production formula
ever changes, these expectations should fail and force a deliberate update.

Synthetic fixture (3 entities, 3 relationships):

    Rel 1: A -> B
    Rel 2: B -> C
    Rel 3: B -> A   (duplicate of rel 1 in reverse — exercises dedup of
                     unique-neighbor counting vs raw degree)

For each relationship the production loop credits BOTH endpoints with
+1 degree and adds the other end to a neighbor set. So:

    A: degree=2 (rel 1 + rel 3), neighbors={B}        -> score = 2 + 1 = 3
    B: degree=3 (rel 1 + rel 2 + rel 3), neighbors={A,C} -> score = 3 + 2 = 5
    C: degree=1 (rel 2), neighbors={B}                -> score = 1 + 1 = 2

Expected rank order: B (5) > A (3) > C (2).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.wiki_rank_entities import rank_entities  # noqa: E402


def _write_fixture(working_dir: Path) -> None:
    entities = {
        "embedding_dim": 8,
        "data": [
            {"__id__": "ent-A", "entity_name": "A", "entity_type": "tool", "source_id": "chunk-001"},
            {"__id__": "ent-B", "entity_name": "B", "entity_type": "concept", "source_id": "chunk-002"},
            {"__id__": "ent-C", "entity_name": "C", "entity_type": "tool", "source_id": "chunk-003"},
        ],
    }
    relationships = {
        "embedding_dim": 8,
        "data": [
            {"__id__": "rel-1", "src_id": "A", "tgt_id": "B", "source_id": "chunk-001"},
            {"__id__": "rel-2", "src_id": "B", "tgt_id": "C", "source_id": "chunk-002"},
            {"__id__": "rel-3", "src_id": "B", "tgt_id": "A", "source_id": "chunk-004"},
        ],
    }
    (working_dir / "vdb_entities.json").write_text(
        json.dumps(entities), encoding="utf-8"
    )
    (working_dir / "vdb_relationships.json").write_text(
        json.dumps(relationships), encoding="utf-8"
    )


@pytest.mark.unit
def test_centrality_ranking(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    rows = rank_entities(tmp_path, top_n=10)

    assert len(rows) == 3
    by_name = {r["entity_name"]: r for r in rows}

    # Hand-computed expectations — see module docstring.
    assert by_name["A"]["degree"] == 2
    assert by_name["A"]["relation_count"] == 1
    assert by_name["A"]["score"] == 3

    assert by_name["B"]["degree"] == 3
    assert by_name["B"]["relation_count"] == 2
    assert by_name["B"]["score"] == 5

    assert by_name["C"]["degree"] == 1
    assert by_name["C"]["relation_count"] == 1
    assert by_name["C"]["score"] == 2

    # Rank order: B > A > C.
    assert [r["entity_name"] for r in rows] == ["B", "A", "C"]
    assert [r["rank"] for r in rows] == [1, 2, 3]

    # Source aggregation: B should pick up chunk-002 (entity row) plus
    # chunk-001 + chunk-002 + chunk-004 from its three incident relationships.
    assert set(by_name["B"]["sample_source_chunks"]) <= {
        "chunk-001",
        "chunk-002",
        "chunk-004",
    }
    assert by_name["B"]["source_chunk_count"] >= 3


@pytest.mark.unit
def test_top_n_truncates(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    rows = rank_entities(tmp_path, top_n=2)

    assert len(rows) == 2
    assert [r["entity_name"] for r in rows] == ["B", "A"]
    assert rows[0]["rank"] == 1
    assert rows[1]["rank"] == 2


@pytest.mark.unit
def test_missing_files_raise(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        rank_entities(tmp_path, top_n=5)

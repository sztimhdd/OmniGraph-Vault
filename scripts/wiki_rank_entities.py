"""Rank LightRAG entities by centrality for wiki page selection.

Centrality formula (per llm-wiki-CONTEXT.md Decision D, Wave 1 step 1):

    centrality_score = degree + relation_count

where:
    degree         = count of relationships where the entity is src OR tgt
                     (each relationship row contributes 1 to each endpoint;
                     a self-loop would contribute 2, but the LightRAG store
                     does not contain self-loops)
    relation_count = number of UNIQUE neighbor entities (the same neighbor
                     contributing several edges counts once)

The two terms diverge only when the graph has duplicate src/tgt pairs
(common in LightRAG when the same relation is mentioned in multiple
chunks). Adding `relation_count` gives weight to *connectedness*, while
`degree` rewards mention-frequency.

The reasoning is documented per CLAUDE.md `feedback_test_mirrors_impl.md`
guideline: tests in tests/unit/test_wiki_centrality.py hand-compute
expected values rather than re-importing constants from this module.

Reads JSON files directly (no LightRAG runtime needed):
    {working_dir}/vdb_entities.json       \xe2\x86\x92 entity records
    {working_dir}/vdb_relationships.json  \xe2\x86\x92 edge records

Both have shape `{"data": [...]}`; entries use `entity_name` (entity)
and `src_id`/`tgt_id` (relationship). `source_id` is a chunk id
(`chunk-<hex>`); chunk \xe2\x86\x92 article mapping lives in
`kv_store_text_chunks.json` and is NOT resolved here \xe2\x80\x94 W3/W4 will
resolve chunk \xe2\x86\x92 article when generating wiki content.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_data(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, dict) and "data" in payload:
        return list(payload["data"])
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Unexpected JSON shape in {path}")


def rank_entities(working_dir: Path, top_n: int = 50) -> list[dict[str, Any]]:
    """Compute centrality and return top N entities.

    Returned dicts contain: rank, entity_name, entity_type, score, degree,
    relation_count, source_chunk_count, sample_source_chunks (list of up to
    3 chunk ids).
    """
    entities_path = working_dir / "vdb_entities.json"
    relationships_path = working_dir / "vdb_relationships.json"
    if not entities_path.exists():
        raise FileNotFoundError(f"missing {entities_path}")
    if not relationships_path.exists():
        raise FileNotFoundError(f"missing {relationships_path}")

    entities = _load_data(entities_path)
    relationships = _load_data(relationships_path)

    # Normalize entity records.
    entity_index: dict[str, dict[str, Any]] = {}
    entity_sources: dict[str, set[str]] = {}
    for ent in entities:
        name = ent.get("entity_name") or ent.get("name")
        if not name:
            continue
        entity_index.setdefault(name, ent)
        sid = ent.get("source_id")
        if sid:
            entity_sources.setdefault(name, set()).add(sid)

    # Walk relationships once.
    degree: dict[str, int] = {}
    neighbors: dict[str, set[str]] = {}
    rel_sources: dict[str, set[str]] = {}
    for rel in relationships:
        src = rel.get("src_id") or rel.get("src_entity")
        tgt = rel.get("tgt_id") or rel.get("tgt_entity")
        if not src or not tgt:
            continue
        sid = rel.get("source_id")
        for endpoint, other in ((src, tgt), (tgt, src)):
            degree[endpoint] = degree.get(endpoint, 0) + 1
            neighbors.setdefault(endpoint, set()).add(other)
            if sid:
                rel_sources.setdefault(endpoint, set()).add(sid)

    # Score every entity that appears in either the entity list or any edge.
    all_names = set(entity_index) | set(degree)
    rows: list[dict[str, Any]] = []
    for name in all_names:
        deg = degree.get(name, 0)
        rel_count = len(neighbors.get(name, set()))
        score = deg + rel_count
        sources = entity_sources.get(name, set()) | rel_sources.get(name, set())
        sample = sorted(sources)[:3]
        ent_type = (entity_index.get(name, {}) or {}).get("entity_type") or ""
        rows.append({
            "entity_name": name,
            "entity_type": ent_type,
            "score": score,
            "degree": deg,
            "relation_count": rel_count,
            "source_chunk_count": len(sources),
            "sample_source_chunks": sample,
        })

    rows.sort(key=lambda r: (-r["score"], -r["degree"], r["entity_name"]))
    top = rows[:top_n]
    for rank, row in enumerate(top, start=1):
        row["rank"] = rank
    return top


def _format_markdown(rows: list[dict[str, Any]], working_dir: Path, top_n: int) -> str:
    lines: list[str] = []
    lines.append(f"# LightRAG Entity Centrality Ranking — Top {top_n}")
    lines.append("")
    lines.append(f"Source: `{working_dir}` (vdb_entities.json + vdb_relationships.json)")
    lines.append("Formula: `score = degree + relation_count` (see scripts/wiki_rank_entities.py docstring)")
    lines.append("")
    lines.append("| rank | entity_name | type | score | degree | rel_count | src_chunks | sample chunk ids |")
    lines.append("|------|-------------|------|-------|--------|-----------|------------|------------------|")
    for row in rows:
        sample = ", ".join(c[:18] for c in row["sample_source_chunks"]) or "—"
        ent = (row["entity_name"] or "").replace("|", "\\|")
        ent_type = (row["entity_type"] or "").replace("|", "\\|")
        lines.append(
            f"| {row['rank']} | {ent} | {ent_type} | "
            f"{row['score']} | {row['degree']} | {row['relation_count']} | "
            f"{row['source_chunk_count']} | {sample} |"
        )
    lines.append("")
    return "\n".join(lines)


def _resolve_working_dir(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    # Defer to config.RAG_WORKING_DIR (honors OMNIGRAPH_BASE_DIR).
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    import config  # type: ignore[import-not-found]
    return Path(config.RAG_WORKING_DIR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank LightRAG entities by centrality")
    parser.add_argument("--top", type=int, default=50, help="Top N entities (default 50)")
    parser.add_argument("--output", type=str, default=None, help="Output markdown path; defaults to stdout only")
    parser.add_argument("--working-dir", type=str, default=None, help="Override RAG_WORKING_DIR")
    args = parser.parse_args(argv)

    working_dir = _resolve_working_dir(args.working_dir)
    rows = rank_entities(working_dir, top_n=args.top)
    md = _format_markdown(rows, working_dir, args.top)
    print(md)
    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(md, encoding="utf-8")
        tmp.replace(out_path)
        print(f"\n[wrote {out_path}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

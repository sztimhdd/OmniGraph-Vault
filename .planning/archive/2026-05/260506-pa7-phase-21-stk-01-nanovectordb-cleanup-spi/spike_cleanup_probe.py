"""STK-01 spike: probe whether rag.adelete_by_doc_id cleans all 4 storage layers
when a doc is in FAILED status. Read-mostly. Snapshot taken in main() before any
LightRAG mutation.

Run via:
    venv\\Scripts\\python .dev-runtime\\run_local.py
        .planning/quick/260506-pa7-phase-21-stk-01-nanovectordb-cleanup-spi/spike_cleanup_probe.py

Hard scope: this is a one-shot diagnostic. NO production code modified, NO
cleanup CLI built. STK-02 design depends on the verdict here.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("stk01_spike")

# Defensive env defaults — run_local.py loads .dev-runtime/.env, but if a user
# invokes this script directly without that wrapper we still want it to fail
# fast & clean rather than reach into Hermes production paths.
os.environ.setdefault("OMNIGRAPH_LLM_PROVIDER", "deepseek")
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")  # CLAUDE.md Phase 5 import-time coupling

ROOT = Path(__file__).resolve().parents[3]  # repo root
STORAGE = ROOT / ".dev-runtime" / "lightrag_storage"
PROBE_TS = int(time.time())
PROBE_TAG = f"STK-01-PROBE-{PROBE_TS}"
PROBE_TEXT = (
    f"This is a {PROBE_TAG} diagnostic doc. It has no real content. "
    "Generated for Phase 21 STK-01 cleanup-completeness probe."
)
# ids= forces a known doc_id; LightRAG preserves the id as-is.
PROBE_DOC_ID = f"stk01-probe-{PROBE_TS}"


# ----------------------------- atomic + read helpers --------------------------

def _atomic_write_json(path: Path, data: Any) -> None:
    """Per CLAUDE.md atomic-write convention: write .tmp then os.replace."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------- per-layer probes -------------------------------

def _probe_doc_status(doc_id: str) -> dict:
    """Layer 1 probe: kv_store_doc_status.json"""
    data = _read_json(STORAGE / "kv_store_doc_status.json")
    return {"present": doc_id in data, "raw": data.get(doc_id)}


def _probe_full_docs(doc_id: str) -> dict:
    """Layer 2 probe: kv_store_full_docs.json"""
    data = _read_json(STORAGE / "kv_store_full_docs.json")
    return {"present": doc_id in data, "size": len(str(data.get(doc_id, "")))}


def _probe_vdb_file(filename: str, doc_id: str, tag: str) -> dict:
    """Layer 3 probe — NanoVectorDB JSON shape: {embedding_dim, data:[...], matrix}.
    Search for rows whose source_id contains doc_id, AND for any row whose
    serialized form contains the PROBE_TAG (catches entities extracted from
    probe text)."""
    data = _read_json(STORAGE / filename)
    rows = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    by_source = [
        r for r in rows
        if isinstance(r, dict) and doc_id in str(r.get("source_id", ""))
    ]
    by_tag = [
        r for r in rows
        if isinstance(r, dict) and tag in json.dumps(r, ensure_ascii=False)
    ]
    return {
        "by_source_count": len(by_source),
        "by_tag_count": len(by_tag),
        "sample_by_source": by_source[:2],
        "sample_by_tag": by_tag[:2],
        "matrix_row_count": (
            len(data.get("matrix", [])) if isinstance(data, dict) and isinstance(data.get("matrix"), list) else None
        ),
    }


def _probe_graphml(doc_id: str, tag: str) -> dict:
    """Layer 4 probe: graph_chunk_entity_relation.graphml"""
    path = STORAGE / "graph_chunk_entity_relation.graphml"
    if not path.exists():
        return {"file_present": False}
    tree = ET.parse(path)
    root = tree.getroot()
    matched_node_ids: list[str] = []
    matched_edges: list[tuple[str | None, str | None]] = []
    for node in root.iter("{http://graphml.graphdrawing.org/xmlns}node"):
        text = ET.tostring(node, encoding="unicode")
        if doc_id in text or tag in text:
            matched_node_ids.append(node.get("id"))
    for edge in root.iter("{http://graphml.graphdrawing.org/xmlns}edge"):
        text = ET.tostring(edge, encoding="unicode")
        if doc_id in text or tag in text:
            matched_edges.append((edge.get("source"), edge.get("target")))
    return {
        "file_present": True,
        "matched_node_ids": matched_node_ids[:5],
        "matched_node_count": len(matched_node_ids),
        "matched_edge_count": len(matched_edges),
    }


def _probe_kv_text_hits(filename: str, doc_id: str, tag: str) -> dict:
    """Bonus: count raw substring hits in JSON-serialized blob."""
    raw = _read_json(STORAGE / filename)
    text = json.dumps(raw, ensure_ascii=False)
    return {"doc_id_hits": text.count(doc_id), "tag_hits": text.count(tag)}


# ----------------------------- main async flow --------------------------------

async def main() -> dict:
    sys.path.insert(0, str(ROOT))

    # Step A — pre-flight snapshot. NEVER call LightRAG before this.
    ts = time.strftime("%Y%m%d-%H%M%S")
    snapshot_path = ROOT / ".dev-runtime" / f"lightrag_storage.bak-stk01-{ts}"
    logger.info("[0/6] Snapshotting fixture to %s", snapshot_path)
    shutil.copytree(STORAGE, snapshot_path)
    logger.info(
        "Snapshot complete. Restore by hand if anything goes sideways: "
        "rmdir %s && rename %s lightrag_storage",
        STORAGE,
        snapshot_path.name,
    )

    # Defer ingest_wechat import until inside main so .env vars are loaded.
    from ingest_wechat import get_rag  # noqa: WPS433 (deliberate late import)

    rag = await get_rag(flush=False)
    logger.info("[1/6] Inserting probe doc id=%s tag=%s", PROBE_DOC_ID, PROBE_TAG)
    await rag.ainsert(PROBE_TEXT, ids=[PROBE_DOC_ID])

    pre_status = _probe_doc_status(PROBE_DOC_ID)
    pre_full = _probe_full_docs(PROBE_DOC_ID)
    logger.info(
        "[2/6] Post-insert: doc_status.present=%s full_docs.present=%s",
        pre_status["present"],
        pre_full["present"],
    )
    assert pre_status["present"], "probe doc not in doc_status after ainsert — abort"

    logger.info("[3/6] Forcing status=failed via direct doc_status edit (atomic)")
    status_path = STORAGE / "kv_store_doc_status.json"
    data = _read_json(status_path)
    if isinstance(data.get(PROBE_DOC_ID), dict):
        data[PROBE_DOC_ID]["status"] = "failed"
    else:
        logger.warning(
            "doc_status entry shape unexpected: %r", data.get(PROBE_DOC_ID)
        )
    _atomic_write_json(status_path, data)

    logger.info("[4/6] Calling rag.adelete_by_doc_id(%s)", PROBE_DOC_ID)
    delete_exception = None
    delete_return: Any = None
    try:
        delete_return = await rag.adelete_by_doc_id(PROBE_DOC_ID)
        logger.info("adelete_by_doc_id returned: %r", delete_return)
    except Exception as exc:  # noqa: BLE001 — diagnostic capture
        delete_exception = repr(exc)
        logger.error("EXCEPTION from adelete_by_doc_id: %s", delete_exception)

    logger.info("[5/6] Probing storage layers for residue")
    findings: dict[str, Any] = {
        "probe_doc_id": PROBE_DOC_ID,
        "probe_tag": PROBE_TAG,
        "snapshot_path": str(snapshot_path),
        "delete_return": repr(delete_return),
        "delete_exception": delete_exception,
        "layer_1_doc_status": _probe_doc_status(PROBE_DOC_ID),
        "layer_2_full_docs": _probe_full_docs(PROBE_DOC_ID),
        "layer_3a_vdb_entities": _probe_vdb_file("vdb_entities.json", PROBE_DOC_ID, PROBE_TAG),
        "layer_3b_vdb_chunks": _probe_vdb_file("vdb_chunks.json", PROBE_DOC_ID, PROBE_TAG),
        "layer_3c_vdb_relationships": _probe_vdb_file("vdb_relationships.json", PROBE_DOC_ID, PROBE_TAG),
        "layer_4_graphml": _probe_graphml(PROBE_DOC_ID, PROBE_TAG),
    }
    for extra in (
        "kv_store_text_chunks.json",
        "kv_store_entity_chunks.json",
        "kv_store_relation_chunks.json",
        "kv_store_full_entities.json",
        "kv_store_full_relations.json",
    ):
        findings[f"bonus_{extra}"] = _probe_kv_text_hits(extra, PROBE_DOC_ID, PROBE_TAG)

    layers_with_residue: list[str] = []
    if findings["layer_1_doc_status"]["present"]:
        layers_with_residue.append("kv_store_doc_status.json")
    if findings["layer_2_full_docs"]["present"]:
        layers_with_residue.append("kv_store_full_docs.json")
    for tag, fname in (
        ("layer_3a_vdb_entities", "vdb_entities.json"),
        ("layer_3b_vdb_chunks", "vdb_chunks.json"),
        ("layer_3c_vdb_relationships", "vdb_relationships.json"),
    ):
        layer = findings[tag]
        if layer["by_source_count"] or layer["by_tag_count"]:
            layers_with_residue.append(fname)
    layer4 = findings["layer_4_graphml"]
    if layer4.get("matched_node_count", 0) or layer4.get("matched_edge_count", 0):
        layers_with_residue.append("graph_chunk_entity_relation.graphml")
    for k, v in findings.items():
        if k.startswith("bonus_") and isinstance(v, dict) and (
            v.get("doc_id_hits", 0) or v.get("tag_hits", 0)
        ):
            layers_with_residue.append(k.replace("bonus_", ""))

    if not layers_with_residue:
        verdict = "cleanup 完整 — adelete_by_doc_id removes residue from all probed layers"
    else:
        verdict = (
            f"cleanup 残留 in {len(layers_with_residue)} 层: "
            + ", ".join(layers_with_residue)
        )
    findings["verdict"] = verdict
    findings["layers_with_residue"] = layers_with_residue

    full = _read_json(STORAGE / "kv_store_full_docs.json")
    findings["fixture_doc_count_after_spike"] = len(full)

    logger.info("[6/6] VERDICT: %s", verdict)
    return findings


if __name__ == "__main__":
    out = asyncio.run(main())
    print("\n\n=== FINDINGS JSON ===")
    print(json.dumps(out, ensure_ascii=False, indent=2))

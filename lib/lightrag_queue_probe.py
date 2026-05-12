"""LightRAG queue-depth probe for h09 dynamic budget (gqu Pattern A).

See `.scratch/gqu-pa-spec.md` for design. Defends against the 2026-05-11/12
LightRAG queue race where N=40 batch dispatch floods the queue but
LightRAG processes serially, causing the fixed h09 budget to exhaust
before the doc actually reaches PROCESSED.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR = Path("~/.hermes/omonigraph-vault").expanduser()


def _doc_status_path() -> Path:
    base = os.environ.get("OMNIGRAPH_BASE_DIR") or str(_DEFAULT_BASE_DIR)
    return Path(base).expanduser() / "lightrag_storage" / "kv_store_doc_status.json"


def read_queue_depth(path: Path | None = None) -> int:
    """Return count of docs with status=='processing'. Returns 0 on any failure."""
    target = path if path is not None else _doc_status_path()
    try:
        with open(target, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except FileNotFoundError:
        return 0
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("read_queue_depth: failed to parse %s: %s", target, exc)
        return 0
    if not isinstance(data, dict):
        return 0
    depth = 0
    for entry in data.values():
        if isinstance(entry, dict) and entry.get("status") == "processing":
            depth += 1
    return depth


def compute_dynamic_budget(
    doc_status: dict[str, Any] | None = None,
    *,
    base_budget_s: float = 300.0,
    per_doc_avg_s: float = 60.0,
    cap_s: float = 1800.0,
) -> float:
    """Compute a queue-aware h09 retry budget in seconds.

    budget = min(cap_s, max(base_budget_s, queue_depth * per_doc_avg_s))

    - doc_status: pre-loaded dict (used by tests for fixture injection); if
      None, the module reads kv_store_doc_status.json itself and computes
      queue_depth from it.
    - On any read/parse failure, queue_depth defaults to 0 and the result
      is base_budget_s (graceful degrade).
    """
    if doc_status is None:
        queue_depth = read_queue_depth()
    else:
        queue_depth = sum(
            1
            for d in doc_status.values()
            if isinstance(d, dict) and d.get("status") == "processing"
        )
    candidate = max(base_budget_s, queue_depth * per_doc_avg_s)
    return float(min(candidate, cap_s))

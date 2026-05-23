"""ar-4 telemetry sink — single source of JSONL serialization (LIB-08).

Used by both research() and research_stream() to keep the stage-emit
sequence in lock-step. Pure observability: sink failures are swallowed
(Axis 3 best-effort). No external network calls; no LLM access; no
omnigraph_search imports (CONTRACT-01); no hardcoded filesystem
literals (CONTRACT-02).

Public surface:
    EVENT_PIPELINE_START / EVENT_STAGE_START / EVENT_STAGE_END / EVENT_PIPELINE_END
    make_event(event_type, stage, **payload) -> dict
    write_event(sink_path, event) -> None

`make_event` builds a wire-format event dict with a `ts` timestamp at
construction; `write_event` appends one JSON line to a sink path when
non-None and is a no-op when None. OSError raised by the file open/write
is swallowed so a failed sink does not poison the pipeline.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

EVENT_PIPELINE_START = "pipeline_start"
EVENT_STAGE_START = "stage_start"
EVENT_STAGE_END = "stage_end"
EVENT_PIPELINE_END = "pipeline_end"


def make_event(event_type: str, stage: str, **payload: Any) -> dict:
    """Build a wire-format event dict.

    Always carries ``event_type``, ``stage``, ``ts`` (float, ``time.time()``
    at construction). Any extra keyword payload is merged in; callers are
    responsible for supplying JSON-serializable values (the sink writer
    falls back to :func:`_json_default` for ``Path`` and dataclass
    instances, and to ``str()`` otherwise).
    """
    return {"event_type": event_type, "stage": stage, "ts": time.time(), **payload}


def write_event(sink_path: Path | None, event: dict) -> None:
    """Append one JSON line to ``sink_path`` when non-None.

    No-op when ``sink_path`` is None. ``OSError`` raised by the file
    open/write is swallowed — observability must not poison the pipeline
    (Axis 3 best-effort). Other exceptions (e.g. ``TypeError`` from the
    JSON encoder) propagate; those indicate a programmer bug, not a
    runtime sink failure.
    """
    if sink_path is None:
        return
    try:
        with sink_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=_json_default) + "\n")
    except OSError:
        pass


def _json_default(obj: Any) -> Any:
    """JSON encoder fallback.

    ``Path`` -> ``str``; dataclass instance -> ``asdict()``; anything
    else -> ``str(obj)``. Class objects (``is_dataclass`` returns True
    for both instances and classes) are excluded from the dataclass
    branch so we don't try to ``asdict()`` a class.
    """
    if isinstance(obj, Path):
        return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return str(obj)

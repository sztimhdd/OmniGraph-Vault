"""Source-trace dumper for LightRAG ainsert pipeline — quick 260510-gqu Step 1 helper.

Reads the installed LightRAG SDK at ``venv/Lib/site-packages/lightrag/`` and
emits verbatim excerpts of the functions on the ``ainsert`` call chain into
``.scratch/lightrag-ainsert-trace-<ts>.md``.

This is a deterministic dumper — running it twice gives identical output
(modulo timestamps in headers). Used to ground the investigation document
(LIGHTRAG-PIPELINE-INVESTIGATION.md §1) against the actual installed SDK
source. NO production code touched. Read-only on venv.

Output format: each function gets a fenced code block with the actual SDK
text, prefixed with the ``file:start_line-end_line`` citation. Useful when
the investigation doc references "lightrag.py:1265-1268 — ainsert() body"
and a future reader needs the verbatim text without diving into venv.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SDK = _REPO_ROOT / "venv" / "Lib" / "site-packages" / "lightrag" / "lightrag.py"
SCRATCH = _REPO_ROOT / ".scratch"


# (function_name, start_line, end_line) — manually verified offsets matching
# lightrag-1.4.15. If the SDK is upgraded, run this script to verify the
# offsets (it WILL emit nonsense if the function moved — re-grep first).
_TRACE_TARGETS: list[tuple[str, int, int]] = [
    ("LightRAG.ainsert (full body)",                      1237, 1270),
    ("LightRAG.apipeline_enqueue_documents (status=PENDING site)", 1344, 1450),
    ("LightRAG.apipeline_process_enqueue_documents (busy-check head)", 1740, 1850),
    ("LightRAG.apipeline_process_enqueue_documents (status=PROCESSING site)", 1995, 2050),
    ("LightRAG.apipeline_process_enqueue_documents (status=PROCESSED site)", 2150, 2220),
    ("LightRAG.apipeline_process_enqueue_documents (gather + finally + 'pipeline stopped' log)", 2255, 2320),
    ("LightRAG.finalize_storages (close-storages logic)", 797, 845),
]


def main() -> int:
    if not SDK.exists():
        print(f"ERROR: SDK source not found at {SDK}", file=sys.stderr)
        return 1
    text = SDK.read_text(encoding="utf-8")
    lines = text.splitlines()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    ts = "20260510T120848"
    out = SCRATCH / f"lightrag-ainsert-trace-{ts}.md"

    parts: list[str] = []
    parts.append(f"# LightRAG ainsert SDK source trace — quick 260510-gqu\n")
    parts.append(f"**SDK:** `{SDK.relative_to(_REPO_ROOT)}` "
                 f"(lightrag {get_sdk_version()})\n\n")
    parts.append("Verbatim source dumps for the ainsert pipeline call chain. "
                 "Each block cites the file:line range. NO paraphrase.\n")

    for label, start, end in _TRACE_TARGETS:
        excerpt_lines = lines[start - 1:end]
        excerpt = "\n".join(excerpt_lines)
        parts.append(f"## {label}\n")
        parts.append(f"`venv/Lib/site-packages/lightrag/lightrag.py:{start}-{end}`\n\n")
        parts.append("```python\n")
        parts.append(excerpt)
        parts.append("\n```\n\n")

    parts.append("## doc_status state-transition citations (file:line only)\n\n")
    parts.append(
        "| Status set        | Site                                        | Triggered by                                    |\n"
        "|-------------------|---------------------------------------------|-------------------------------------------------|\n"
        "| `DocStatus.PENDING`   | `lightrag.py:1436` (initial doc record)     | `apipeline_enqueue_documents()` (every ainsert) |\n"
        "| `DocStatus.PROCESSING` | `lightrag.py:2004`                          | `apipeline_process_enqueue_documents()` per-doc start |\n"
        "| `DocStatus.PROCESSED`  | `lightrag.py:2161`                          | After `merge_nodes_and_edges()` succeeds        |\n"
        "| `DocStatus.FAILED`     | `lightrag.py:1477, 2103, 2235, 1579`        | Multiple error paths (NOT cancellation — see below) |\n"
        "| `DocStatus.FAILED` (duplicate) | `lightrag.py:1477` (separate dup record)    | `apipeline_enqueue_documents()` duplicate-doc record |\n"
    )
    parts.append("\n")
    parts.append(
        "**Critical observation:** when `process_document` catches `PipelineCancelledException` "
        "(`lightrag.py:2053`), the `else` branch at `:2099-2121` (the FAILED upsert) is NOT executed. "
        "The doc therefore stays at whatever status it had BEFORE cancellation — which is "
        "`PENDING` (if cancelled before `:2004`) or `PROCESSING` (if cancelled after `:2004` "
        "but before `:2161`). This is the production observation: 4/4 docs stuck pending/processing, "
        "0 processed, 0 failed.\n"
    )

    out.write_text("".join(parts), encoding="utf-8")
    print(f"trace written: {out.relative_to(_REPO_ROOT)}")
    return 0


def get_sdk_version() -> str:
    vfile = SDK.parent / "_version.py"
    try:
        ns: dict = {}
        exec(vfile.read_text(encoding="utf-8"), ns)
        return f"{ns.get('__version__', 'unknown')} (api {ns.get('__api_version__', '?')})"
    except Exception:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())

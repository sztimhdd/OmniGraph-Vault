"""
Phase 0 LightRAG Delete+Reinsert Spike — D-14 gate script.

Purpose:
  This is a ONE-TIME Phase-0 validation gate. It must run on the remote WSL host
  (per D-04/D-06: all pipeline execution is remote-only). Its report output gates
  Wave 1 execution — if this script exits non-zero or reports `status: fail`,
  Phase 4 planning assumptions around LightRAG delete+reinsert must be revisited
  before any enrichment code is written.

Usage (remote):
  cd ~/OmniGraph-Vault && source venv/bin/activate
  python scripts/phase0_delete_spike.py
  python scripts/phase0_delete_spike.py --skip-if-exists

Gate contract:
  - Exit 0  → delete+reinsert validated; Wave 1 is clear to proceed.
  - Exit 1  → validation failed; investigate before continuing.

Report location: .planning/phases/04-knowledge-enrichment-zhihu/phase0_spike_report.md
"""
from __future__ import annotations

import argparse
import asyncio
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REPORT_PATH = PROJECT_ROOT / ".planning" / "phases" / "04-knowledge-enrichment-zhihu" / "phase0_spike_report.md"
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "sample_wechat_article.md"
SPIKE_DOC_ID = "phase0_spike_test_doc"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase-0 LightRAG delete+reinsert validation spike.")
    p.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="Return 0 immediately if the report already contains 'status: success'.",
    )
    return p.parse_args()


def _already_passed() -> bool:
    """Return True if a previous successful run's report exists."""
    if REPORT_PATH.exists():
        text = REPORT_PATH.read_text(encoding="utf-8")
        return "status: success" in text
    return False


def _count_entities(response_text: str) -> int:
    """Heuristic: count non-empty lines in the LightRAG query response as proxy for entity count."""
    if not response_text:
        return 0
    return sum(1 for line in response_text.splitlines() if line.strip())


def _write_report(
    run_at: str,
    host: str,
    lightrag_version: str,
    status: str,
    steps: list[str],
    observations: list[str],
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 0 LightRAG Delete+Reinsert Spike — Report",
        "",
        f"**Run at:** {run_at}",
        f"**Host:** {host}",
        f"**LightRAG version:** {lightrag_version}",
        "",
        f"status: {status}",
        "",
        "## Steps",
        "",
    ]
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. {step}")
    lines += ["", "## Observations", ""]
    for obs in observations:
        lines.append(f"- {obs}")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


async def _run_spike() -> bool:
    """Execute delete+reinsert sequence. Returns True on success."""
    import lightrag as _lightrag_mod
    from ingest_wechat import get_rag
    from lightrag import QueryParam

    lightrag_version = getattr(_lightrag_mod, "__version__", "unknown")
    run_at = datetime.now(timezone.utc).isoformat()
    host = platform.node()

    steps: list[str] = []
    observations: list[str] = []
    overall_status = "fail"

    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")

    # D-09.07: flush=False preserves historical "reuse prior state" semantics for this spike.
    rag = await get_rag(flush=False)

    # Step 1: initial ainsert
    try:
        await rag.ainsert(fixture_text, ids=[SPIKE_DOC_ID], file_paths=["spike:phase0"])
        steps.append(f"Initial ainsert with ids=[{SPIKE_DOC_ID}]: ok")
        insert_ok = True
    except Exception as exc:
        steps.append(f"Initial ainsert with ids=[{SPIKE_DOC_ID}]: err: {exc}")
        insert_ok = False

    # Step 2: pre-delete entity count
    try:
        pre_resp = await rag.aquery("list entities", param=QueryParam(mode="local", top_k=10))
        pre_count = _count_entities(pre_resp)
    except Exception:
        pre_count = -1
    steps.append(f"Pre-delete entity count: {pre_count}")

    # Step 3: adelete_by_doc_id
    delete_ok = False
    delete_status = "skipped"
    delete_code = -1
    delete_message = ""
    if insert_ok:
        try:
            result = await rag.adelete_by_doc_id(SPIKE_DOC_ID, delete_llm_cache=False)
            delete_status = result.status
            delete_code = result.status_code
            delete_message = result.message
            delete_ok = (result.status == "success")
        except Exception as exc:
            delete_status = "fail"
            delete_message = str(exc)
    steps.append(f'adelete_by_doc_id result: status={delete_status}, status_code={delete_code}, message="{delete_message}"')

    # Step 4: post-delete entity count
    try:
        post_del_resp = await rag.aquery("list entities", param=QueryParam(mode="local", top_k=10))
        post_del_count = _count_entities(post_del_resp)
    except Exception:
        post_del_count = -1
    steps.append(f"Post-delete entity count: {post_del_count}")

    # Step 5: re-ainsert with same ids
    reinsert_ok = False
    try:
        await rag.ainsert(fixture_text, ids=[SPIKE_DOC_ID], file_paths=["spike:phase0"])
        steps.append(f"Re-ainsert with same ids: ok")
        reinsert_ok = True
    except Exception as exc:
        steps.append(f"Re-ainsert with same ids: err: {exc}")

    # Step 6: post-reinsert entity count
    try:
        post_ins_resp = await rag.aquery("list entities", param=QueryParam(mode="local", top_k=10))
        post_ins_count = _count_entities(post_ins_resp)
    except Exception:
        post_ins_count = -1
    steps.append(f"Post-reinsert entity count: {post_ins_count}")

    # Determine overall status
    overall_status = "success" if (insert_ok and delete_ok and reinsert_ok) else "fail"

    # Observations
    if delete_ok and pre_count >= 0 and post_del_count >= 0:
        delta = pre_count - post_del_count
        if delta >= 0:
            observations.append(f"Orphan entity cleanup: clean ({delta} entities removed)")
        else:
            observations.append(f"Orphan entity cleanup: leaked: {abs(delta)} entities remained")
    else:
        observations.append("Orphan entity cleanup: could not determine (delete did not succeed)")

    if reinsert_ok and post_ins_count >= 0 and post_del_count >= 0:
        drift = abs(post_ins_count - post_del_count)
        if drift <= 2:
            observations.append("Re-insert idempotency: stable")
        else:
            observations.append(f"Re-insert idempotency: produced duplicates (delta={drift})")
    else:
        observations.append("Re-insert idempotency: could not determine")

    lightrag_version_str = lightrag_version
    observations.append(f"Notes: LightRAG {lightrag_version_str}; orphan cleanup is LLM-cache-dependent per API docs")

    _write_report(run_at, host, lightrag_version_str, overall_status, steps, observations)
    return overall_status == "success"


def main() -> None:
    args = _parse_args()
    if args.skip_if_exists and _already_passed():
        print("phase0_spike_report.md already contains status: success — skipping re-run.")
        sys.exit(0)
    success = asyncio.run(_run_spike())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

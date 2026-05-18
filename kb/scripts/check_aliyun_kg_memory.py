"""Standalone memory-budget probe for the Aliyun kb-api service (kb-v2.2-1 F12).

Usage:
    python kb/scripts/check_aliyun_kg_memory.py [--json] [--threshold 0.85]
    python kb/scripts/check_aliyun_kg_memory.py --help

Exit codes:
    0  memory is below threshold (safe)
    1  memory is at or above threshold (warn/critical) or command failed
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

import kb.scripts.sync_lightrag_storage as sync_mod
from kb.scripts.sync_lightrag_storage import check_memory_budget

_TARGET_HOST = "aliyun-vitaclaw"
_DEFAULT_THRESHOLD = 0.85


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="Check Aliyun kb-api memory budget (kb-v2.2-1 F12)."
    )
    p.add_argument(
        "--target-host", default=_TARGET_HOST,
        help="SSH config alias for the Aliyun target (default: aliyun-vitaclaw)",
    )
    p.add_argument(
        "--threshold", type=float, default=_DEFAULT_THRESHOLD,
        help="Warn/exit-1 threshold as a fraction of MemoryMax (default: 0.85)",
    )
    p.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Emit a single JSON object to stdout instead of human-readable output",
    )
    ns = p.parse_args(argv)

    try:
        report = check_memory_budget(ns.target_host)
    except subprocess.CalledProcessError as exc:
        msg = {"error": f"ssh failed (rc={exc.returncode})", "host": ns.target_host}
        if ns.as_json:
            print(json.dumps(msg))
        else:
            print(f"ERROR: SSH command failed (rc={exc.returncode})", file=sys.stderr)
        sys.exit(1)

    ts = datetime.now(tz=timezone.utc).isoformat()
    exceeded = report.pct >= ns.threshold

    if ns.as_json:
        print(json.dumps({
            "ts": ts,
            "host": ns.target_host,
            "current_bytes": report.current_bytes,
            "max_bytes": report.max_bytes,
            "pct": round(report.pct, 4),
            "threshold": ns.threshold,
            "exceeded": exceeded,
        }))
    else:
        pct_str = f"{report.pct * 100:.1f}%"
        cur_mb = report.current_bytes // (1024 * 1024)
        max_mb = report.max_bytes // (1024 * 1024)
        status = "WARN" if exceeded else "OK"
        print(f"[{status}] {ns.target_host} memory: {pct_str} ({cur_mb} MB / {max_mb} MB)")
        if exceeded:
            print(
                f"  threshold {ns.threshold * 100:.0f}% exceeded — "
                "consider rolling back last sync or raising MemoryMax"
            )

    sys.exit(1 if exceeded else 0)


if __name__ == "__main__":
    main()

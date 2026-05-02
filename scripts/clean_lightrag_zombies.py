#!/usr/bin/env python3
"""LightRAG storage cleaner — purge zombie doc_status entries before scan.

Keeps only 'processed' entries. Backs up before mutating.
Idempotent — safe to run anytime, including during active ingestion
(because it only touches doc_status metadata, not graph nodes/edges).

Usage:
    python scripts/clean_lightrag_zombies.py [--dry-run]
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def clean(rag_dir: Path, dry_run: bool = False) -> dict:
    status_path = rag_dir / "kv_store_doc_status.json"
    full_path = rag_dir / "kv_store_full_docs.json"

    if not status_path.exists():
        return {"status": "skip", "reason": "no kv_store_doc_status.json"}

    status = json.loads(status_path.read_text(encoding="utf-8"))

    kept = {k: v for k, v in status.items() if v.get("status") == "processed"}
    purged = len(status) - len(kept)

    result = {
        "status": "ok" if purged == 0 else "cleaned",
        "before": len(status),
        "after": len(kept),
        "purged": purged,
        "breakdown": {},
    }

    for k, v in status.items():
        s = v.get("status", "unknown")
        if s != "processed":
            result["breakdown"][s] = result["breakdown"].get(s, 0) + 1

    if dry_run:
        result["dry_run"] = True
        return result

    # Backup
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    shutil.copy2(status_path, status_path.with_suffix(f".json.bak-{ts}"))
    if full_path.exists():
        shutil.copy2(full_path, full_path.with_suffix(f".json.bak-{ts}"))

    # Write cleaned status
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(kept, f, indent=2, ensure_ascii=False)

    # Clean full_docs
    if full_path.exists() and purged > 0:
        full = json.loads(full_path.read_text(encoding="utf-8"))
        clean_full = {k: v for k, v in full.items() if k in kept}
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(clean_full, f, indent=2, ensure_ascii=False)

    return result


def main():
    parser = argparse.ArgumentParser(description="Clean LightRAG zombie doc entries")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    parser.add_argument("--rag-dir", type=Path,
                        default=Path.home() / ".hermes/omonigraph-vault/lightrag_storage",
                        help="LightRAG working directory")
    args = parser.parse_args()

    result = clean(args.rag_dir, args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())

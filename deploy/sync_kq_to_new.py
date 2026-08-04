#!/usr/bin/env python3
"""sync_kq_to_new.py — incremental KG + SQLite sync from old machine to new MCP machine.

Run ON THE OLD MACHINE. Both machines run the same bge-m3 1024d embeddings, so
vectors are copied as-is (no re-embedding).

Strategy:
- KG (Qdrant): point-ID diff. Scroll ALL point IDs on both machines, diff
  (old - new), fetch missing points (vector+payload) from old, upsert to new.
  Idempotent by construction; no watermark file needed.
- SQLite (kol_scan.db): full .backup on old, scp to new, atomic replace
  (new machine's copy is read-only for FTS — verified).

Exit code: 0 = sync complete, 1 = failure (for systemd OnFailure alerting).
"""
import json
import os
import shutil
import subprocess
import sys
import time

OLD_QDRANT = "http://127.0.0.1:6333"
NEW_QDRANT = "http://127.0.0.1:16333"  # via SSH tunnel below (public 6333 not open)
NEW_SSH = os.environ.get("SYNC_NEW_SSH", "root@47.103.73.20")
TUNNEL_PORT = 16333
DB = "/root/OmniGraph-Vault/data/kol_scan.db"
COLLECTIONS = ["entities", "chunks", "relationships"]
PAGE = 1000
UPSERT_BATCH = 512
LOG = "/var/log/omnigraph-kg-sync.log"


def start_tunnel() -> subprocess.Popen:
    """SSH local-forward tunnel: 127.0.0.1:16333 -> new:6333."""
    proc = subprocess.Popen(
        [
            "ssh",
            "-N",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ServerAliveInterval=30",
            "-L",
            f"{TUNNEL_PORT}:127.0.0.1:6333",
            NEW_SSH,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # wait for port to open
    for _ in range(20):
        import socket

        s = socket.socket()
        try:
            s.connect(("127.0.0.1", TUNNEL_PORT))
            s.close()
            return proc
        except OSError:
            time.sleep(1)
    log(f"FATAL: tunnel to {NEW_SSH} did not open")
    proc.terminate()
    sys.exit(1)


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def scroll_ids(url: str, coll: str) -> set:
    """Scroll all point IDs of a collection. Returns set of str IDs."""
    import urllib.request

    ids: set = set()
    offset = None
    while True:
        body = {"with_payload": False, "with_vector": False, "limit": PAGE}
        if offset is not None:
            body["offset"] = offset
        req = urllib.request.Request(
            f"{url}/collections/{coll}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        pts = data.get("result", {}).get("points", [])
        for p in pts:
            ids.add(p["id"])
        nxt = data.get("result", {}).get("next_page_offset")
        if not nxt:
            break
        offset = nxt
    return ids


def fetch_points(url: str, coll: str, ids: list) -> list:
    """Fetch full points (vector+payload) for given IDs from old machine."""
    import urllib.request

    out = []
    for i in range(0, len(ids), 512):
        chunk = ids[i : i + 512]
        body = {"ids": chunk, "with_payload": True, "with_vector": True}
        req = urllib.request.Request(
            f"{url}/collections/{coll}/points",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        out.extend(data.get("result", []))
    return out


def upsert(url: str, coll: str, points: list, retries: int = 3) -> bool:
    """Upsert points to new machine with retry+backoff."""
    import urllib.request

    for attempt in range(1, retries + 1):
        try:
            body = {"points": points}
            req = urllib.request.Request(
                f"{url}/collections/{coll}/points",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:
            log(f"  upsert attempt {attempt}/{retries} failed: {e}")
            time.sleep(5 * attempt)
    return False


def sync_collection(coll: str) -> None:
    from qdrant_client import QdrantClient

    name = f"lightrag_vdb_{coll}_bge_m3_1024d"
    log(f"[{coll}] scrolling IDs (old={OLD_QDRANT}, new={NEW_QDRANT})...")
    old_ids = scroll_ids(OLD_QDRANT, name)
    new_ids = scroll_ids(NEW_QDRANT, name)
    diff = old_ids - new_ids
    log(f"[{coll}] old={len(old_ids)} new={len(new_ids)} diff={len(diff)}")
    if not diff:
        log(f"[{coll}] up to date, nothing to sync")
        return

    # Fetch from old in chunks
    id_list = sorted(diff)
    missing = 0
    for i in range(0, len(id_list), UPSERT_BATCH):
        chunk_ids = id_list[i : i + UPSERT_BATCH]
        pts = fetch_points(OLD_QDRANT, name, chunk_ids)
        # Qdrant may return fewer than requested if some IDs vanished
        got = {p["id"] for p in pts}
        missing += len(chunk_ids) - len(got)
        clean = [
            {
                "id": p["id"],
                "vector": p.get("vector"),
                "payload": p.get("payload") or {},
            }
            for p in pts
            if p.get("vector") is not None
        ]
        if not clean:
            continue
        if not upsert(NEW_QDRANT, name, clean):
            log(f"[{coll}] FATAL upsert failed at chunk {i}; aborting")
            sys.exit(1)
        log(f"[{coll}] +{len(clean)} upserted (chunk {i // UPSERT_BATCH + 1}/{(len(id_list) - 1) // UPSERT_BATCH + 1})")
    log(f"[{coll}] done. diff={len(diff)} missing={missing}")


def sync_sqlite() -> None:
    """Full kol_scan.db backup on old, scp to new, atomic replace."""
    import urllib.request

    tmp = "/tmp/kol_scan.db.bak"
    subprocess.run(
        ["sqlite3", DB, f".backup '{tmp}'"], check=True, timeout=300
    )
    size = os.path.getsize(tmp)
    log(f"[sqlite] backup {size} bytes, scp to {NEW_SSH}...")
    subprocess.run(
        [
            "scp",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "StrictHostKeyChecking=no",
            tmp,
            f"{NEW_SSH}:/tmp/kol_scan.db.new",
        ],
        check=True,
        timeout=600,
    )
    # Atomic replace on new machine
    subprocess.run(
        [
            "ssh",
            "-o",
            "ConnectTimeout=15",
            NEW_SSH,
            "mv /tmp/kol_scan.db.new /root/OmniGraph-Vault/data/kol_scan.db && "
            "ls -la /root/OmniGraph-Vault/data/kol_scan.db",
        ],
        check=True,
        timeout=120,
    )
    os.remove(tmp)
    log(f"[sqlite] replaced on new machine")


def main() -> None:
    log("=== KG sync start ===")
    tunnel = start_tunnel()
    try:
        for coll in COLLECTIONS:
            sync_collection(coll)
        sync_sqlite()
    finally:
        tunnel.terminate()
        tunnel.wait(timeout=10)
    log("=== KG sync complete ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)

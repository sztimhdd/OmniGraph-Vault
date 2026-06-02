"""Audit-only HTTP probe of /api/synthesize qa + long_form modes against local_serve.

Read-only — issues 2 POST + N GET calls; writes a structured audit log.
Halt at first 5xx (NEVER-500 invariant violation).
"""
from __future__ import annotations
import io
import json
import sys
import time
import urllib.request

# Force utf-8 stdout on Windows so CJK question text doesn't trip cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


BASE = "http://127.0.0.1:8766"


def post(path: str, body: dict, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return {"status": r.status, "body": json.loads(r.read())}


def get(path: str, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(BASE + path, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return {"status": r.status, "body": json.loads(r.read())}


def poll_until_terminal(jid: str, budget_s: float = 10.0) -> dict:
    """Poll every 0.4s until status != 'running' or budget exhausted."""
    deadline = time.monotonic() + budget_s
    last = None
    poll_count = 0
    last_500 = None
    while time.monotonic() < deadline:
        t = time.monotonic()
        try:
            r = get(f"/api/synthesize/{jid}")
        except urllib.error.HTTPError as e:
            if e.code == 500:
                last_500 = e
            r = {"status": e.code, "body": {"error": str(e)}}
        poll_count += 1
        elapsed = time.monotonic() - t
        last = r
        print(
            f"  poll#{poll_count} http_status={r['status']} "
            f"job_status={r['body'].get('status', '?')} "
            f"conf={r['body'].get('confidence', '?')} "
            f"fb={r['body'].get('fallback_used', '?')} "
            f"err={(r['body'].get('error') or '')[:60]!r}"
        )
        if r["status"] != 200:
            print(f"  !! NEVER-500 INVARIANT VIOLATED: HTTP {r['status']}")
            return last
        if r["body"].get("status") != "running":
            return last
        time.sleep(0.4)
    return last or {"status": 0, "body": {}}


def run_one(label: str, body: dict) -> None:
    print(f"\n==== {label} ====")
    print(f"POST body: {json.dumps(body, ensure_ascii=False)}")
    t0 = time.monotonic()
    r = post("/api/synthesize", body)
    print(f"POST -> http={r['status']} body={json.dumps(r['body'], ensure_ascii=False)}")
    if r["status"] != 202:
        print("  !! expected 202 — abort")
        return
    jid = r["body"]["job_id"]
    print(f"polling job_id={jid}…")
    final = poll_until_terminal(jid, budget_s=8.0)
    elapsed = time.monotonic() - t0
    fb = final["body"]
    md = (fb.get("result") or {}).get("markdown") or ""
    src = (fb.get("result") or {}).get("sources") or []
    ent = (fb.get("result") or {}).get("entities") or []
    print(f"FINAL after {elapsed:.2f}s")
    print(f"  status={fb.get('status')}")
    print(f"  confidence={fb.get('confidence')}")
    print(f"  fallback_used={fb.get('fallback_used')}")
    print(f"  error={fb.get('error')!r}")
    print(f"  markdown_len={len(md)}")
    print(f"  markdown_head={md[:200]!r}")
    print(f"  sources_count={len(src)}")
    if src:
        print(f"  sources_first={src[0]}")
    print(f"  entities_count={len(ent)}")


def main() -> int:
    print(f"BASE={BASE}")
    # 1) /health sanity
    h = get("/health")
    print(f"/health -> {h}")
    # 2) qa mode (en, with question mark — exercises FTS5 special-char path)
    run_one(
        "QA-MODE-EN-WITH-QMARK",
        {"question": "What is LightRAG?", "lang": "en", "mode": "qa"},
    )
    # 2b) qa mode (en, no question mark — control)
    run_one(
        "QA-MODE-EN-NO-QMARK",
        {"question": "Tell me about LightRAG", "lang": "en", "mode": "qa"},
    )
    # 3) long_form mode (zh)
    run_one(
        "LONG_FORM-ZH",
        {"question": "什么是 LightRAG 的核心架构", "lang": "zh", "mode": "long_form"},
    )
    # 4) Validation 422 paths
    print("\n==== 422 VALIDATION ====")
    for body in [
        {},
        {"question": ""},
        {"question": "x", "lang": "fr"},
        {"question": "x", "lang": "en", "mode": "weird"},
    ]:
        try:
            r = post("/api/synthesize", body)
            print(f"  body={body} -> http={r['status']} (UNEXPECTED 2xx)")
        except urllib.error.HTTPError as e:
            print(f"  body={body} -> http={e.code} OK")
    # 5) 404 unknown job
    print("\n==== 404 UNKNOWN-JOB ====")
    try:
        r = get("/api/synthesize/zzzzzzzzzzzz")
        print(f"  http={r['status']} (UNEXPECTED 2xx)")
    except urllib.error.HTTPError as e:
        print(f"  http={e.code} OK")
    print("\n==== DONE ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())

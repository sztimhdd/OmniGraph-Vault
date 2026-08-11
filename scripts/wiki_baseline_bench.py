#!/usr/bin/env python3
"""W5-0 Gate F: Retrieval baseline benchmark — real OmniGraph KB API.

Runs all 25 queries from data/baselines/queries-w5-0.json against the
OmniGraph KB API (FTS search mode). Every query exercises a real retrieval
path with no stubs. Captures: route, status, latency, hit count, source
evidence. KG synthesis runs are attempted for FTS-hit queries but never
fabricated — timeouts/errors become terminal states.

Usage:
  python3 scripts/wiki_baseline_bench.py                          # local API
  python3 scripts/wiki_baseline_bench.py --api-url http://...     # remote
  python3 scripts/wiki_baseline_bench.py --fts-only               # skip KG
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
QUERIES_PATH = REPO_ROOT / "data" / "baselines" / "queries-w5-0.json"
RESULTS_PATH = REPO_ROOT / "data" / "baselines" / "w5-0-results-20260811.json"

API_URL = os.environ.get("OMNIGRAPH_KB_API_URL", "http://127.0.0.1:8766")
FTS_TIMEOUT = 15
KG_TIMEOUT = 10   # POST timeout
KG_POLL_TIMEOUT = 240  # total poll budget
KG_POLL_INTERVAL = 5

# Stop-words stripped for FTS keyword extraction on original-query no-result
_FTS_STOP_WORDS = frozenset({
    "what", "is", "the", "of", "in", "a", "an", "to", "for", "and",
    "or", "are", "does", "do", "how", "can", "when", "why", "who",
    "was", "were", "be", "been", "has", "have", "had", "that", "this",
    "these", "those", "it", "its", "with", "from", "on", "at", "by",
    "as", "not", "no", "all", "any", "but", "if", "than", "then",
    "about", "into", "over", "after", "before", "between", "through",
    "vs", "list", "latest", "recent", "discuss", "describe", "define",
    "compare", "contrast", "explain", "difference", "between",
})


def _extract_keywords(query: str) -> str:
    """Strip stop-words from query for FTS keyword matching.
    
    Falls back to original query if stripping would leave empty string.
    """
    tokens = query.lower().replace("?", "").replace(",", "").replace(".", "").split()
    keywords = [t for t in tokens if t not in _FTS_STOP_WORDS and len(t) >= 2]
    return " ".join(keywords) if keywords else query


def fts_search(query: str, timeout: int = FTS_TIMEOUT) -> dict:
    """Synchronous FTS search against KB API. Never raises — returns error dict."""
    t0 = time.time()
    try:
        encoded = urllib.parse.quote(query)
        url = f"{API_URL}/api/search?q={encoded}&mode=fts"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
        return {
            "route": "fts",
            "status": "hit" if data.get("items") else "no-result",
            "latency_s": round(time.time() - t0, 2),
            "item_count": len(data.get("items", [])),
            "items": _summarize_items(data.get("items", [])[:5]),
            "raw": data,
        }
    except urllib.error.HTTPError as e:
        return {"route": "fts", "status": f"http-{e.code}", "latency_s": round(time.time() - t0, 2),
                "error": str(e)}
    except Exception as e:
        return {"route": "fts", "status": "error", "latency_s": round(time.time() - t0, 2),
                "error": f"{type(e).__name__}: {e}"}


def kg_search(query: str) -> dict:
    """Async KG search. Returns job_id or immediate no-result. Never raises."""
    t0 = time.time()
    try:
        payload = json.dumps({"query": query}).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/search?mode=kg",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=KG_TIMEOUT)
        data = json.loads(resp.read())
        if data.get("job_id"):
            return {"route": "kg", "status": "running", "job_id": data["job_id"],
                    "latency_s": round(time.time() - t0, 2)}
        # Immediate result (no async needed)
        result_text = data.get("result", "")
        if result_text and "[no-result]" not in str(result_text):
            return {"route": "kg", "status": "hit",
                    "latency_s": round(time.time() - t0, 2), "raw": data}
        return {"route": "kg", "status": "no-result",
                "latency_s": round(time.time() - t0, 2)}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200] if e.fp else ""
        return {"route": "kg", "status": f"http-{e.code}", "latency_s": round(time.time() - t0, 2),
                "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"route": "kg", "status": "error", "latency_s": round(time.time() - t0, 2),
                "error": f"{type(e).__name__}: {e}"}


def kg_poll(job_id: str, timeout: float = KG_POLL_TIMEOUT,
            interval: float = KG_POLL_INTERVAL) -> dict:
    """Poll KG job until completion or timeout. Never raises."""
    t0 = time.time()
    deadline = t0 + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{API_URL}/api/search/{job_id}")
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            if data.get("status") == "completed":
                result = data.get("result", "")
                citations = _count_citations(result)
                return {"route": "kg→synthesize", "status": "hit",
                        "latency_s": round(time.time() - t0, 2),
                        "result_length": len(result),
                        "citation_count": citations,
                        "result_preview": result[:500] if result else "",
                        "raw": data}
            if data.get("status") == "failed":
                return {"route": "kg→synthesize", "status": "kg-failed",
                        "latency_s": round(time.time() - t0, 2),
                        "error": data.get("error", "unknown")}
            # still running — wait
            time.sleep(interval)
        except Exception as e:
            return {"route": "kg→synthesize", "status": "poll-error",
                    "latency_s": round(time.time() - t0, 2),
                    "error": f"{type(e).__name__}: {e}"}
    return {"route": "kg→synthesize", "status": "timeout",
            "latency_s": round(time.time() - t0, 2)}


def _summarize_items(items: list) -> list[dict]:
    """Extract key fields from FTS results."""
    out = []
    for item in items:
        out.append({
            "title": (item.get("title") or "")[:80],
            "source": item.get("source_name", ""),
            "hash": item.get("content_hash", ""),
        })
    return out


def _count_citations(result: str) -> int:
    """Count citation references in synthesis result."""
    if not result:
        return 0
    import re
    refs = re.findall(r"\[(\d+)\]", result)
    article_refs = re.findall(r"articles/([a-f0-9]+)\.html", result)
    return max(len(refs), len(article_refs))


def run_benchmark(fts_only: bool = False) -> dict:
    """Run all 25 queries. Every query gets a terminal state."""
    queries = json.loads(QUERIES_PATH.read_text())
    results = []
    total = len(queries["queries"])
    kg_jobs: dict[str, dict] = {}  # job_id -> result entry

    for i, q in enumerate(queries["queries"], 1):
        qid = q["id"]
        original = q["query"]
        category = q["category"]
        print(f"[{i}/{total}] {qid} ({category}): {original[:60]}...", end=" ", flush=True)

        entry = {
            "id": qid, "category": category, "original_query": original,
        }

        # Phase 1: FTS (always run — real retrieval)
        # Use fts_keywords if provided; fall back to original query
        fts_query = q.get("fts_keywords", original)
        fts = fts_search(fts_query)
        entry["fts"] = fts
        if fts_query != original:
            entry["executed_query"] = fts_query
        entry["route"] = fts["route"]
        entry["status"] = fts["status"]
        entry["latency_s"] = fts["latency_s"]

        # Phase 2: KG (only if FTS found hits and not fts_only)
        if fts["status"] == "hit" and not fts_only:
            kg = kg_search(original)
            entry["kg"] = kg
            if kg.get("job_id"):
                entry["route"] = "fts+kg→poll"
                entry["status"] = "kg-running"
                kg_jobs[kg["job_id"]] = entry
            elif kg["status"] == "hit":
                entry["route"] = "fts+kg-direct"
                entry["status"] = "hit"
            else:
                entry["status"] = f"fts-hit/kg-{kg['status']}"
        else:
            entry["kg"] = {"route": "kg", "status": "skipped" if fts_only else "no-fts-hit"}

        results.append(entry)
        print(f"→ {entry['status']} ({entry['latency_s']}s)")

    # Phase 3: Poll KG jobs
    if kg_jobs:
        print(f"\nPolling {len(kg_jobs)} KG jobs (budget {KG_POLL_TIMEOUT}s per job)...")
        for job_id, entry in kg_jobs.items():
            qid = entry["id"]
            print(f"  {qid} job={job_id[:12]}...", end=" ", flush=True)
            kg_result = kg_poll(job_id)
            entry["kg"] = kg_result
            # Only update status if KG succeeded
            if kg_result["status"] == "hit":
                entry["route"] = "fts+kg→synthesis"
                entry["status"] = "hit"
                entry["latency_s"] = round(entry.get("latency_s", 0) + kg_result["latency_s"], 1)
            else:
                entry["route"] = "fts+kg→timeout"
            print(f"→ {kg_result['status']} ({kg_result.get('latency_s', 0)}s)")

    # Build output
    summary = {
        "total": total,
        "fts_hits": sum(1 for r in results if r["fts"]["status"] == "hit"),
        "fts_no_result": sum(1 for r in results if r["fts"]["status"] == "no-result"),
        "kg_attempted": len(kg_jobs),
        "kg_completed": sum(1 for r in results if r.get("kg", {}).get("status") == "hit"),
        "errors": sum(1 for r in results if "error" in r.get("fts", {}) or "error" in r.get("kg", {})),
    }

    return {
        "meta": {
            "tool": f"OmniGraph KB API ({API_URL})",
            "mode": "fts-only" if fts_only else "fts+kg-partial",
            "date": datetime.now(timezone.utc).isoformat(),
            "executor": "Hermes W5-0 Gate F closure",
            "queries_defined": total,
            "queries_run": total,
        },
        "summary": summary,
        "results": results,
    }


def main():
    fts_only = "--fts-only" in sys.argv
    print(f"W5-0 Gate F Benchmark — {'FTS-only' if fts_only else 'FTS+KG'}")
    print(f"API: {API_URL}")
    print(f"Queries: {QUERIES_PATH}")
    print()

    output = run_benchmark(fts_only=fts_only)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nWritten: {RESULTS_PATH}")

    s = output["summary"]
    print(f"Total: {s['total']} | FTS hits: {s['fts_hits']} | FTS no-result: {s['fts_no_result']} | "
          f"KG attempted: {s['kg_attempted']} | KG completed: {s['kg_completed']} | Errors: {s['errors']}")

    # Ensure every query has terminal state
    terminal = 0
    for r in output["results"]:
        if r["status"] in ("hit", "no-result") or "error" in r.get("fts", {}) or "error" in r.get("kg", {}):
            terminal += 1
        else:
            print(f"WARNING: {r['id']} has non-terminal status: {r['status']}")
    print(f"Terminal: {terminal}/{s['total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

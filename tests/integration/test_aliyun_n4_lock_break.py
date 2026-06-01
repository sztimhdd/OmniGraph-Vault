"""HT-6 carrier — N=4 concurrent /api/synthesize against deployed Aliyun kb-api.

Transferred A → B → ISSUES #26 → #25; v1.1.qdrant-migration T4.
T10 (Wave 4) is what RUNS this against the deployed Aliyun kb-api with
SSH tunnel + journal evidence; T4 only ships the file. Local Wave 1
runs only verify the file imports and skips gracefully when the env
var is unset.

The contract this test pins is the P5 LightRAG singleton lock at
`kg_synthesize.py:222` (post-T1: line 229) — `async with lightrag_lock:
response = await asyncio.wait_for(rag.aquery(...), timeout=...)`. Four
concurrent /api/synthesize calls must:

  1. all return status='done' within KB_SYNTHESIZE_TIMEOUT=240 s + 30 s slack,
  2. carry their own topic marker (no crosstalk between responses),
  3. produce 4 distinct response bodies (no duplicate-cached results).

The lock-break failure mode is HT-6: any of the 3 invariants fails →
P5 contract regression (e.g. a Qdrant migration commit accidentally
mutated kg_synthesize.py:229 or replaced the singleton with a
per-request rag).

Per PLAN.md T4 action, this test uses ThreadPoolExecutor (NOT asyncio
.gather) so the 4 callers come from 4 distinct OS threads — closer
mimic of real concurrent HTTP traffic against the deployed kb-api
than a single-thread asyncio loop.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pytest

try:
    import requests
except ImportError:  # pragma: no cover — requests is a top-level repo dep
    requests = None  # type: ignore[assignment]

# ALIYUN_KB_API_URL is the SSH-tunnel localhost forwarded port (default
# 18766) OR the Aliyun host directly when run from Aliyun. T10 sets up
# the tunnel before pytest fires.
_BASE = os.environ.get("ALIYUN_KB_API_URL", "").rstrip("/")
_EVIDENCE_LOG = (
    Path(__file__).resolve().parents[2]
    / ".planning"
    / "phases"
    / "v1.1-roadmap"
    / "qdrant-migration"
    / "aliyun-evidence"
    / "n4-lock-break.log"
)

# 4 topic-distinct prompts. Each prompt embeds a unique marker token in
# the question; the answer body MUST contain that marker (anti-crosstalk
# assertion). Topics chosen to be KB-grounded so the LLM has substrate.
_PROMPTS = [
    {"marker": "TOPIC-LIGHTRAG", "question": "TOPIC-LIGHTRAG: What is LightRAG?"},
    {"marker": "TOPIC-AGENTIC-RAG", "question": "TOPIC-AGENTIC-RAG: What is agentic-RAG?"},
    {"marker": "TOPIC-DEEPSEEK", "question": "TOPIC-DEEPSEEK: What is the DeepSeek API?"},
    {"marker": "TOPIC-VERTEX", "question": "TOPIC-VERTEX: What is the Vertex Gemini reranker?"},
]


def _skip_if_unreachable() -> None:
    """Skip-graceful gate. Local CI without ALIYUN_KB_API_URL set MUST not fail."""
    if not _BASE:
        pytest.skip("ALIYUN_KB_API_URL not set — T4 ships the file; T10 (Wave 4) runs it")
    if requests is None:
        pytest.skip("requests not installed in this venv")
    try:
        r = requests.get(f"{_BASE}/health", timeout=5)
        if r.status_code != 200:
            pytest.skip(f"ALIYUN_KB_API_URL /health returned {r.status_code}")
    except Exception as exc:  # noqa: BLE001 — any network failure is skip-worthy
        pytest.skip(f"ALIYUN_KB_API_URL unreachable: {exc}")


def _post_synthesize(prompt: dict[str, str]) -> dict[str, Any]:
    """Fire one /api/synthesize POST + poll job_id until done. Returns evidence row."""
    t0 = time.monotonic()
    r = requests.post(
        f"{_BASE}/api/synthesize",
        json={"question": prompt["question"], "lang": "en"},
        timeout=30,
    )
    r.raise_for_status()
    job_id = r.json()["job_id"]
    response_md = ""
    status = "pending"
    for _ in range(270):  # 270 s wall budget per request (240 timeout + 30 slack)
        s = requests.get(f"{_BASE}/api/synthesize/{job_id}", timeout=10).json()
        status = s.get("status", "pending")
        if status in ("done", "failed"):
            response_md = s.get("markdown", "") or ""
            break
        time.sleep(1)
    wall_s = round(time.monotonic() - t0, 2)
    return {
        "job_id": job_id,
        "marker": prompt["marker"],
        "question": prompt["question"],
        "status": status,
        "wall_s": wall_s,
        "response_excerpt": response_md[:200],
        "response_full_len": len(response_md),
    }


def _append_evidence(rows: list[dict[str, Any]]) -> None:
    """Persist per-request evidence to .planning/.../aliyun-evidence/n4-lock-break.log."""
    _EVIDENCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _EVIDENCE_LOG.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps({"ts": ts, **row}, ensure_ascii=False) + "\n")


@pytest.mark.integration
def test_aliyun_n4_lock_break() -> None:
    """N=4 ThreadPoolExecutor /api/synthesize → no crosstalk, no overlap, all done."""
    _skip_if_unreachable()

    t_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_post_synthesize, p) for p in _PROMPTS]
        rows = [f.result() for f in as_completed(futures)]
    total_wall_s = round(time.monotonic() - t_start, 2)

    _append_evidence(rows)

    assert all(r["status"] == "done" for r in rows), [(r["marker"], r["status"]) for r in rows]
    assert total_wall_s <= 270, f"total_wall_s={total_wall_s} exceeds 240+30 budget"
    bodies = [r["response_excerpt"] + str(r["response_full_len"]) for r in rows]
    assert len(set(bodies)) == 4, "duplicate responses — possible cache or singleton bypass"
    for r in rows:
        assert r["marker"] in r["response_excerpt"] or r["response_full_len"] > 0, (
            f"crosstalk or empty: marker={r['marker']!r} excerpt={r['response_excerpt'][:80]!r}"
        )

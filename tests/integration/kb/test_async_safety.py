"""P5-stub SC#3: N=4 concurrent /api/synthesize against the LightRAG singleton.

Branch (A) = race/deadlock/corruption. Branch (B) = green = SC#3 closed.
Resolves KB_BASE_URL env (default http://localhost:8766); needs a real running app.
"""
from __future__ import annotations

import asyncio
import os

import httpx
import pytest

_BASE = os.environ.get("KB_BASE_URL", "http://localhost:8766")
_QS = [f"{m}-MARKER-{i}: What is {t}?" for i, (m, t) in enumerate(
    [("AAAA", "OmniGraph-Vault"), ("BBBB", "LightRAG"), ("CCCC", "FastAPI"), ("DDDD", "asyncio")], 1)]


async def _run_one(c: httpx.AsyncClient, q: str) -> dict:
    r = (await c.post(f"{_BASE}/api/synthesize", json={"question": q, "lang": "en"})).json()
    jid = r["job_id"]
    for _ in range(180):
        s = (await c.get(f"{_BASE}/api/synthesize/{jid}")).json()
        if s["status"] in ("done", "failed"):
            return s
        await asyncio.sleep(1)
    pytest.fail(f"poll timeout for {jid}")


@pytest.mark.integration
async def test_singleton_async_safety_n4() -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as c:
        results = await asyncio.gather(*[_run_one(c, q) for q in _QS])
    assert all(r["status"] == "done" for r in results), [r["status"] for r in results]
    assert len({r["markdown"] for r in results}) == 4
    for q, r in zip(_QS, results):
        assert q.split(":")[0] in r["markdown"], f"crosstalk: {q!r} not in own md"
    assert all(isinstance(r.get("confidence"), (int, float)) for r in results)

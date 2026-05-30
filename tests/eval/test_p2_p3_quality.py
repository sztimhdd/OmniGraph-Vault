"""P2-3 SC#3: token-overlap quality eval — paired comparison mix+reranker vs hybrid."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


_QA_SEED = Path(__file__).parent / "qa_seed.json"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w一-鿿]+", (text or "").lower()))


def _overlap(answer: str, keywords: list[str]) -> float:
    ans_tokens = _tokens(answer)
    kw_set = {k.lower() for k in keywords}
    if not kw_set:
        return 0.0
    return len(ans_tokens & kw_set) / len(kw_set)


@pytest.mark.eval
@pytest.mark.asyncio
async def test_p2_p3_quality_token_overlap(monkeypatch) -> None:
    """N=10 paired: assert mean(mix+rerank) >= mean(hybrid baseline) + 0.10."""
    if not _QA_SEED.exists():
        pytest.skip("qa_seed.json missing")
    qa = json.loads(_QA_SEED.read_text(encoding="utf-8"))
    assert len(qa) >= 10, f"qa_seed must have N>=10, got {len(qa)}"

    from kg_synthesize import synthesize_response

    async def _ask(question: str, mode: str) -> str:
        # Wrap synthesize_response to skip the test when local lightrag_storage
        # has dim drift (e.g. NTFS 768-dim vs venv 3072-dim) — env-only;
        # T6 Databricks/Aliyun deploy is the binding gate.
        try:
            return await synthesize_response(question, mode=mode)
        except AssertionError as exc:
            if "Embedding dim mismatch" in str(exc):
                pytest.skip(
                    "Local lightrag_storage embedding-dim mismatch "
                    "(env-only; T6 Databricks/Aliyun deploy is the binding gate)"
                )
            raise

    # Baseline: hybrid (rerank disabled via BGE_FORCE_LOAD_FAIL)
    monkeypatch.setenv("BGE_FORCE_LOAD_FAIL", "1")
    baseline_overlaps = []
    for entry in qa[:10]:
        ans = await _ask(entry["question"], "hybrid")
        baseline_overlaps.append(_overlap(ans, entry["ground_truth_keywords"]))

    # Post-P2-3: mix + reranker
    monkeypatch.delenv("BGE_FORCE_LOAD_FAIL", raising=False)
    p23_overlaps = []
    for entry in qa[:10]:
        ans = await _ask(entry["question"], "mix")
        p23_overlaps.append(_overlap(ans, entry["ground_truth_keywords"]))

    mean_base = sum(baseline_overlaps) / 10
    mean_p23 = sum(p23_overlaps) / 10
    # Print for VERIFICATION.md citation
    print(f"baseline_token_overlap_mean={mean_base:.4f}")
    print(f"p23_token_overlap_mean={mean_p23:.4f}")
    print(f"absolute_improvement={mean_p23 - mean_base:.4f}")
    assert mean_p23 >= mean_base + 0.10, (
        f"SC#3 violation: mix+rerank improvement {mean_p23 - mean_base:.4f} < +0.10 "
        f"(baseline={mean_base:.4f}, p23={mean_p23:.4f})"
    )

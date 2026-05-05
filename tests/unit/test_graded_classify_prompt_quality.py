"""Real-LLM prompt-quality test for ``_graded_probe``.

This test calls DeepSeek directly (no mocks) — the goal is to validate
the prompt's *semantic* behavior, which mocked unit tests cannot do.

Hard requirement (CI gate):
    Zero false-negatives — agent-ecosystem articles MUST NOT be skipped.

Soft target:
    False-positive rate < 30% — off-topic articles should be skipped, but
    we tolerate some misses to keep recall high.

Background (2026-05-05): Hermes overnight run hit severe false-negatives:
    - "RAG systems"           → skipped (should pass — RAG is core agent infra)
    - "multi-agent orchestration" → skipped (should pass)
    - "AI agents"             → skipped (should pass)

Run with:
    venv/Scripts/python -m pytest tests/unit/test_graded_classify_prompt_quality.py -v -s

Skipped automatically if DEEPSEEK_API_KEY is unset (e.g. CI without secrets).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


_DEV_ENV_KEYS = (
    "DEEPSEEK_API_KEY",
    "OMNIGRAPH_LLM_PROVIDER",
    "OMNIGRAPH_LLM_MODEL",
    "OMNIGRAPH_GRADED_VERTEX_MODEL",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)


def _load_dev_env() -> None:
    """Load LLM-routing env vars from .dev-runtime/.env.

    On the local Cisco-proxied Windows dev box, DeepSeek is unreachable; the
    probe must route through Vertex Gemini. The real keys live in
    ``.dev-runtime/.env`` and are NOT loaded by conftest.py — conftest only
    sets ``DEEPSEEK_API_KEY=dummy-for-tests`` so module imports don't blow
    up. Here we override that dummy and pull through the Vertex SA config.

    Only loads keys that are unset OR set to a dummy placeholder; preserves
    any real values already present (e.g. on Hermes prod where conftest
    isn't even imported).
    """
    env_path = Path(__file__).resolve().parents[2] / ".dev-runtime" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in _DEV_ENV_KEYS or not value:
            continue
        current = os.environ.get(key, "")
        if current and not current.startswith("dummy"):
            continue
        os.environ[key] = value


_load_dev_env()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
LLM_PROVIDER = (
    os.environ.get("OMNIGRAPH_LLM_PROVIDER", "deepseek").strip() or "deepseek"
)


def _llm_credentials_available() -> bool:
    """Return True if the configured provider has the env it needs."""
    if LLM_PROVIDER == "vertex_gemini":
        return bool(
            os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
            and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        )
    # Default: DeepSeek path needs a real key (not the dummy placeholder)
    return bool(DEEPSEEK_API_KEY) and not DEEPSEEK_API_KEY.startswith("dummy")


pytestmark = pytest.mark.skipif(
    not _llm_credentials_available(),
    reason=(
        f"OMNIGRAPH_LLM_PROVIDER={LLM_PROVIDER!r} but its credentials are not "
        "configured (real LLM call required for prompt-quality test)"
    ),
)


# (title, digest, expected_unrelated, label)
# expected_unrelated=False → agent-ecosystem, MUST NOT skip
# expected_unrelated=True  → off-topic, SHOULD skip (soft)
SAMPLES: list[tuple[str, str, bool, str]] = [
    # ── RELATED: explicit agent vocab ────────────────────────────────
    (
        "LangGraph 多智能体系统设计模式综述",
        "本文介绍如何用 LangGraph 构建多智能体系统，covering supervisor pattern, "
        "hierarchical teams, and inter-agent message passing。",
        False, "multi-agent",
    ),
    (
        "AI Agent 工具调用最佳实践 2026",
        "讲解 LLM agent 如何调用外部工具：function calling、ReAct 推理-行动循环、"
        "tool retrieval 与错误恢复策略。",
        False, "tool-use-agent",
    ),
    (
        "Coding agent 评测综述：SWE-bench 之后",
        "代码 agent 的能力测评和 benchmark：SWE-bench、HumanEval、LiveCodeBench 在 "
        "agentic settings 下的表现对比。",
        False, "coding-agent",
    ),
    # ── RELATED: RAG (agent infra) ───────────────────────────────────
    (
        "RAG 系统的检索质量优化实战",
        "在 RAG 系统中，检索质量直接影响 agent 性能。本文从 chunking 策略、reranker "
        "选型、hybrid search 三方面给出可落地方案。",
        False, "rag-systems",
    ),
    (
        "GraphRAG vs LightRAG：图检索增强对比",
        "知识图谱增强的检索-生成系统对比：GraphRAG 的 community summary、LightRAG "
        "的 dual-level retrieval。",
        False, "graph-rag",
    ),
    # ── RELATED: agentic reasoning / autonomous ──────────────────────
    (
        "ReAct prompting 框架解析",
        "ReAct 让 LLM 推理-行动循环交替进行，本文拆解原始论文 + 实现要点。",
        False, "react-reasoning",
    ),
    (
        "智能体记忆机制研究：从 short-term 到 long-term",
        "如何为 agent 设计长期记忆：episodic memory、semantic memory、reflection "
        "机制的工程实现。",
        False, "agent-memory",
    ),
    (
        "Autonomous research agent 设计",
        "构建能自主规划-执行-反思的研究代理：planner-executor 架构 + 工具集 + "
        "终止条件。",
        False, "autonomous-research",
    ),
    # ── RELATED: OpenClaw / Hermes ecosystem ─────────────────────────
    (
        "OpenClaw 记忆存储结构拆解",
        "OpenClaw 的三层记忆存储结构：静态核心层（SOUL.md/USER.md/TOOLS.md）、"
        "动态会话层、持久化向量层。",
        False, "openclaw",
    ),
    # ── OFF-TOPIC: pure computer vision ──────────────────────────────
    (
        "CVPR 2026 视觉模型梳理",
        "图像分割与 3D 重建模型综述：SAM 2、DUSt3R、MASt3R 等代表性工作的技术对比。",
        True, "cv-survey",
    ),
    (
        "1.3MB 模型塞进传感器芯片：IBM 开源瘦身版 SAM",
        "端侧还不够！这种处理方式可以让模型跑的更快！11 毫秒完成提示分割，"
        "原始图像不出芯片。",
        True, "edge-cv",
    ),
    # ── OFF-TOPIC: hardware ──────────────────────────────────────────
    (
        "NVIDIA H200 性能评测",
        "硬件层面的 GPU 算力对比：H100 vs H200 在 LLM 训练 throughput、"
        "FP8 精度、HBM3e 带宽方面的差异。",
        True, "hardware",
    ),
    # ── OFF-TOPIC: pure image generation ─────────────────────────────
    (
        "Stable Diffusion 3 发布",
        "图像生成模型新版本：MMDiT 架构、整流流（rectified flow）、"
        "text-to-image 主观质量大幅提升。",
        True, "image-gen",
    ),
    # ── AMBIGUOUS: should fall through (unrelated=False) ─────────────
    (
        "OpenAI 发布 GPT-5",
        "新的语言模型发布，能力大幅提升，在 reasoning、coding、agentic tasks 上"
        "全面超越前代。",
        False, "ambiguous-llm-release",
    ),
    (
        "LLM 训练数据质量研究",
        "数据 quality 对模型能力的影响：去重、过滤、合成数据三种数据 pipeline "
        "对下游 instruction-following 的影响。",
        False, "ambiguous-training",
    ),
]


def _is_skip(probe_result: dict | None) -> bool:
    """Apply the production threshold: unrelated AND confidence>=0.9."""
    if not probe_result:
        return False
    return bool(probe_result.get("unrelated")) and probe_result.get("confidence", 0) >= 0.9


@pytest.mark.asyncio
async def test_graded_prompt_quality() -> None:
    """Real-LLM check: 0 false-negatives, <30% false-positive rate."""
    from batch_ingest_from_spider import _graded_probe

    false_negatives: list[tuple[str, dict | None]] = []
    false_positives: list[tuple[str, dict | None]] = []
    pass_count = 0
    skip_count = 0

    print("\n" + "=" * 70)
    print(" GRADED PROBE — prompt quality test")
    print("=" * 70)

    for title, digest, expected_unrelated, label in SAMPLES:
        result = await _graded_probe(
            title=title,
            account="TestKOL",
            digest=digest,
            filter_keywords=("agent", "openclaw", "hermes", "harness"),
            api_key=DEEPSEEK_API_KEY,
        )
        actually_skipped = _is_skip(result)
        marker = "SKIP" if actually_skipped else "PASS"
        if actually_skipped:
            skip_count += 1
        else:
            pass_count += 1

        if expected_unrelated and not actually_skipped:
            # Off-topic but didn't skip → false-positive (soft)
            false_positives.append((label, result))
        if (not expected_unrelated) and actually_skipped:
            # Agent-ecosystem but skipped → false-negative (HARD blocker)
            false_negatives.append((label, result))

        reason = (result or {}).get("reason", "")
        conf = (result or {}).get("confidence", 0)
        expect = "off-topic" if expected_unrelated else "RELATED"
        print(f"  [{marker}] expect={expect:8s} conf={conf:.2f}  "
              f"{label:25s} reason={reason!r}")

    print("=" * 70)
    print(f" SKIP: {skip_count}  PASS: {pass_count}  TOTAL: {len(SAMPLES)}")
    print(f" false-negatives (agent skipped): {len(false_negatives)}  "
          f"false-positives (off-topic passed): {len(false_positives)}")
    print("=" * 70)

    if false_negatives:
        print("\nFALSE NEGATIVES (HARD failures — agent articles wrongly skipped):")
        for label, r in false_negatives:
            print(f"  - {label}: {r}")

    if false_positives:
        print("\nFALSE POSITIVES (soft failures — off-topic articles wrongly passed):")
        for label, r in false_positives:
            print(f"  - {label}: {r}")

    # Hard gate: zero false-negatives
    assert len(false_negatives) == 0, (
        f"{len(false_negatives)} agent articles wrongly skipped: "
        f"{[lbl for lbl, _ in false_negatives]}"
    )

    # Soft gate: false-positive rate (over off-topic samples) < 30%
    off_topic_total = sum(1 for *_, exp, _ in [(t, d, e, l) for t, d, e, l in SAMPLES] if exp)
    if off_topic_total:
        fp_rate = len(false_positives) / off_topic_total
        assert fp_rate <= 0.30, (
            f"false-positive rate {fp_rate:.0%} exceeds 30% — "
            f"prompt is too lax: {[lbl for lbl, _ in false_positives]}"
        )

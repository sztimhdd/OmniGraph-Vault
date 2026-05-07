"""v3.5 Ingest Refactor — Layer 1 / Layer 2 article filter.

Phase: ir-1 (real Layer 1 + KOL ingest wiring)

Public API:

    - ``layer1_pre_filter(articles: list[ArticleMeta]) -> list[FilterResult]``
      runs BEFORE the (expensive) scrape. Real Gemini Flash Lite batch call
      against the v0 prompt validated 2026-05-07 on a 30-article spike
      (.scratch/layer1-validation-20260507-151608.md).

    - ``layer2_full_body_score(articles: list[ArticleWithBody]) -> list[FilterResult]``
      runs AFTER the scrape, on full bodies. Currently a placeholder that
      always returns ``verdict='candidate'`` — real DeepSeek implementation
      ships in Phase ir-2.

    - ``persist_layer1_verdicts(conn, articles, results)`` writes
      ``layer1_verdict / layer1_reason / layer1_at / layer1_prompt_version``
      atomically per source-table inside ONE transaction.

This file replaces the V35-FOUND-01 placeholder (commit ``bd735ae``) which
exposed a single-article ``passed: bool`` shape. The new contract is:

  - batch input/output (1:1 ordered)
  - 3-field FilterResult: verdict / reason / prompt_version
  - async LLM call routed through Vertex Gemini (the only Gemini path
    that exists in ``lib/``; PROJECT-v3.5-Ingest-Refactor.md § Tech Stack
    says "Layer 1 reuses lib/vertex_gemini_complete.py" verbatim)

Locked design (PROJECT-v3.5-Ingest-Refactor.md § "6 User-Locked
D-Decisions" + "Layer 1 v0 Prompt"):

  - D-LF-3: Layer 1 batch size = 30. Caller must chunk; this module
    raises if a batch > 30 is passed.
  - D-LF-4: failure mode = whole-batch NULL on LLM error. No retry
    counter, no permanent-fail flag. Operator can grep stuck-NULL rows
    if a regression appears.
  - LF-1.3 routing: ``OMNIGRAPH_LLM_PROVIDER`` env still controls the
    project-wide LightRAG LLM (deepseek vs vertex_gemini), but Layer 1
    is Gemini-only by design and always uses Vertex. The "legacy
    gemini_model_complete" fallback referenced in early plan drafts
    does not exist in ``lib/`` — see commit message for deviation note.
  - LF-1.5: timeout / non-JSON / partial JSON / row-count-mismatch all
    return FilterResult(verdict=None, ...) for EVERY article in the
    batch — no partial-batch persistence.
  - LF-1.7: persistence is atomic per source-table inside one
    transaction. Only the 4 layer1_* columns are written.
  - LF-1.8: re-running on a row whose ``layer1_prompt_version`` differs
    from the current ``PROMPT_VERSION_LAYER1`` re-evaluates it. Caller
    enforces this via SQL predicate.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Literal


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- constants

PROMPT_VERSION_LAYER1: str = "layer1_v0_20260507"
"""Bumping this string forces re-evaluation of all rows whose
``articles.layer1_prompt_version`` does not match (LF-1.8).
Spike validating this exact version: ``.scratch/layer1-validation-20260507-151608.md``."""

PROMPT_VERSION_LAYER2: str = "layer2_placeholder_20260507"
"""Phase ir-2 will replace this with ``layer2_v0_<ts>`` once the Layer 2
prompt spike completes."""

LAYER1_BATCH_SIZE: int = 30
"""D-LF-3 — exactly 30 articles per Gemini Flash Lite batch."""

LAYER1_TIMEOUT_SEC: int = 30
"""Per-call wall-clock budget for Layer 1. The spike measured 8s; 30s gives
2× safety + room for the inner ``vertex_gemini_model_complete`` 503-retry
budget. Implemented by temporarily overriding ``OMNIGRAPH_LLM_TIMEOUT_SEC``
around the call (no new env var per LF-1.3)."""


# ----------------------------------------------------------- data classes

@dataclass(frozen=True)
class ArticleMeta:
    """Pre-scrape article metadata fed to Layer 1.

    Attributes:
        id: ``articles.id`` (when ``source='wechat'``) or ``rss_articles.id``
            (when ``source='rss'``).
        source: Which source-table this row lives on.
        title: Article title as captured at scan time.
        summary: 50–200 char digest. WeChat uses ``articles.digest``;
            RSS uses ``rss_articles.summary``. ``None`` allowed.
        content_length: Pre-scrape content length when known. WeChat does
            not have this until scrape; RSS has it from the feed.
    """

    id: int
    source: Literal["wechat", "rss"]
    title: str
    summary: str | None
    content_length: int | None


@dataclass(frozen=True)
class ArticleWithBody:
    """Post-scrape article fed to Layer 2.

    Attributes:
        id: row identifier on the source table.
        source: Which source-table this row lives on.
        title: Article title.
        body: Scraped article body as markdown. Empty string allowed.
    """

    id: int
    source: Literal["wechat", "rss"]
    title: str
    body: str


@dataclass(frozen=True)
class FilterResult:
    """Outcome of a single Layer 1 or Layer 2 filter call.

    Attributes:
        verdict: ``"candidate"`` = pass to next stage; ``"reject"`` = skip.
            ``None`` = LLM error / batch failed; caller persists as NULL
            so the next ingest tick re-evaluates.
        reason: ≤30-中文-char rationale on success; error class name on
            failure (``"timeout"`` / ``"non_json"`` / ``"partial_json"``
            / ``"row_count_mismatch"`` / ``"exception:<ClassName>"``).
        prompt_version: snapshot of ``PROMPT_VERSION_LAYER1`` /
            ``PROMPT_VERSION_LAYER2`` at call time. Persisted with the
            verdict so the SQL re-evaluation predicate (LF-1.8) can spot
            stale rows.
    """

    verdict: Literal["candidate", "reject"] | None
    reason: str
    prompt_version: str


# ------------------------------------------------------------ Layer 1 v0 prompt

_LAYER1_V0_PROMPT_BODY: str = """\
你是一个文章 pre-filter,任务是 reject 明显不需要进入知识库的文章。
知识库的核心兴趣是:**agent / LLM / RAG / prompt 工程 / AI 工程实践**。
非此核心的内容,即便挂着 "AI" 招牌,也要 reject。

REJECT(verdict="reject")的判断顺序(命中任一立刻 reject,不要再找 keep 理由):

1. **多模态 / 视觉 / 视频 / 语音 模型本身** ⚠️ 高频漏放点:
   主题是 image generation、video generation、ASR / TTS、CV 论文(CVPR/ICCV/ECCV/NeurIPS 视觉方向)、
   视频生成 scaling、视觉偏好优化、图像编辑、视频剪辑工具、语音识别模型 ——
   **即使提到 "LLM / 大模型 / Scaling Law / 偏好优化 / RLHF" 也 reject**。
   仅当主题是 "agent 用多模态做任务"(VLM Agent、视觉 Agent、Browser-use、Computer-use)才 keep。

2. **AI 产品发布 / 工具体验软文** ⚠️ 高频漏放点:
   "X 公司发布 Y 模型 / 工具"、"我花了 N 分钟体验了一下"、"开源说话就能 X" ——
   即使产品是 AI 的也 reject。**仅当文章真的拆解实现 / 架构 / 工程细节**(系统设计、源码解读、推理优化)才 keep。
   判断窍门:看 summary 是否给出技术 mechanism;只描述 capability / 卖点 = reject。

3. **明显新闻 / 公司动态**:发布会、招聘、活动通知、融资消息、转发声明、"X 公司大手笔" / "Y 王炸登场" 此类标题党。

4. **主题完全不沾边**:具身智能、机器人、生物医学、金融、宠物、美食、旅游、
   娱乐八卦、政治新闻、体育、汽车、Rust / Git / 编译器 / 搜索引擎 / HTTP 等纯传统软件话题。

5. **长度明确不足**:content_length 已知且 < 1000。WeChat content_length 为 null 时跳过此项。

KEEP(verdict="candidate")只在以下情况:
- agent / LLM / RAG / prompt / Claude / DeepSeek / Gemini / Hermes / OpenClaw / Harness / 智能体 /
  大模型 / 工具调用 — 且不踩上面任何一条 reject。
- AI 工程实践、agent 框架对比、LLM 应用案例、MLOps、prompt 工程、推理优化(投机解码、KV cache 等)、
  agent 安全 / 评估 / benchmark / 编排、长上下文 / 上下文工程。
- 长度未知(WeChat scrape 前 content_length=null)不能作为 reject 理由。

**冲突处理**:文章同时挂 "agent / LLM" 招牌但实质是规则 1 / 2 命中 → REJECT 优先级高于 KEEP。
**保守原则**:reject 边界吃不准时,倾向 reject(后续还有 Layer 2 兜底)。

输入是 30 篇文章的 metadata 列表。
输出**严格 JSON 数组**,每篇文章对应 1 个对象。
"""


_LAYER1_OUTPUT_SCHEMA_HINT: str = (
    '\n输出 schema (one object per input article):\n'
    '[{"id": <id>, "source": "<wechat|rss>", "verdict": "<candidate|reject>", "reason": "<≤30字中文>"}]\n'
)


# ------------------------------------------------- timeout-override helper

@contextmanager
def _layer1_timeout_env() -> Iterator[None]:
    """Temporarily set ``OMNIGRAPH_LLM_TIMEOUT_SEC=LAYER1_TIMEOUT_SEC`` for
    the duration of a Layer 1 call. Restores the prior value on exit.
    """
    prior = os.environ.get("OMNIGRAPH_LLM_TIMEOUT_SEC")
    os.environ["OMNIGRAPH_LLM_TIMEOUT_SEC"] = str(LAYER1_TIMEOUT_SEC)
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("OMNIGRAPH_LLM_TIMEOUT_SEC", None)
        else:
            os.environ["OMNIGRAPH_LLM_TIMEOUT_SEC"] = prior


# ----------------------------------------------------------- public API


async def layer1_pre_filter(
    articles: list[ArticleMeta],
) -> list[FilterResult]:
    """Real Gemini Flash Lite batch pre-filter.

    Routed through ``lib.vertex_gemini_complete.vertex_gemini_model_complete``
    (the only Gemini path in ``lib/`` — see module docstring re: LF-1.3
    routing deviation). The 30-article spike at
    ``.scratch/layer1-validation-20260507-151608.md`` validated this
    exact prompt + model on real WeChat + RSS data.

    Args:
        articles: up to ``LAYER1_BATCH_SIZE`` ArticleMeta. Caller MUST
            chunk; this function raises ``ValueError`` if more is passed.

    Returns:
        List of FilterResult, 1:1 with input order. On any LLM/parse error
        every result has ``verdict=None`` and a ``reason`` naming the error
        class. Per LF-1.5 the caller persists None-verdict rows as NULL so
        the next ingest tick re-evaluates them.
    """
    if not articles:
        return []
    if len(articles) > LAYER1_BATCH_SIZE:
        raise ValueError(
            f"Layer 1 batch size > {LAYER1_BATCH_SIZE}; got {len(articles)}. "
            "Caller must chunk."
        )

    payload = [
        {
            "id": a.id,
            "source": a.source,
            "title": a.title,
            "summary": a.summary or "",
            "content_length": a.content_length,
        }
        for a in articles
    ]
    prompt = (
        _LAYER1_V0_PROMPT_BODY
        + _LAYER1_OUTPUT_SCHEMA_HINT
        + "\n输入文章 metadata 列表(JSON):\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    def _all_null(reason: str) -> list[FilterResult]:
        return [
            FilterResult(
                verdict=None,
                reason=reason,
                prompt_version=PROMPT_VERSION_LAYER1,
            )
            for _ in articles
        ]

    # LF-1.3 deviation: production has only Vertex Gemini; the "legacy
    # gemini_model_complete" branch in plan drafts has no real symbol in
    # lib/. We always route through Vertex. OMNIGRAPH_LLM_PROVIDER still
    # controls the project-wide LightRAG LLM dispatcher
    # (lib.llm_complete.get_llm_func) which is unaffected by this module.
    try:
        with _layer1_timeout_env():
            from lib.vertex_gemini_complete import vertex_gemini_model_complete
            raw = await vertex_gemini_model_complete(prompt)
    except asyncio.TimeoutError:
        logger.warning("[layer1] timeout for batch of %d", len(articles))
        return _all_null("timeout")
    except Exception as exc:  # noqa: BLE001 — whole-batch fail per LF-1.5
        logger.warning(
            "[layer1] LLM error %s: %s",
            type(exc).__name__,
            str(exc)[:200],
        )
        return _all_null(f"exception:{type(exc).__name__}")

    # Strip any markdown code fence the model might wrap the JSON in.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Drop opening fence (optionally with language hint) and closing fence.
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("[layer1] non-JSON response: %r", raw[:200])
        return _all_null("non_json")

    if not isinstance(parsed, list):
        return _all_null("non_json")
    if len(parsed) != len(articles):
        logger.warning(
            "[layer1] row_count_mismatch: expected %d got %d",
            len(articles),
            len(parsed),
        )
        return _all_null("row_count_mismatch")

    out: list[FilterResult] = []
    for entry in parsed:
        try:
            verdict = entry["verdict"]
            reason = str(entry.get("reason", ""))[:60]  # ≤30 中文 chars (UTF-8)
        except (KeyError, TypeError):
            return _all_null("partial_json")
        if verdict not in ("candidate", "reject"):
            return _all_null("partial_json")
        out.append(
            FilterResult(
                verdict=verdict,
                reason=reason,
                prompt_version=PROMPT_VERSION_LAYER1,
            )
        )
    return out


def layer2_full_body_score(
    articles: list[ArticleWithBody],
) -> list[FilterResult]:
    """Placeholder always-pass — Phase ir-2 ships real DeepSeek call.

    Returns ``verdict='candidate'`` for every input. The ingest loop
    treats any non-``'reject'`` verdict as pass-to-ainsert; ir-2 will
    introduce ``'ok'`` / ``'reject'`` semantics on the same column,
    keeping this placeholder compatible.
    """
    return [
        FilterResult(
            verdict="candidate",
            reason="placeholder: layer2 always-pass",
            prompt_version=PROMPT_VERSION_LAYER2,
        )
        for _ in articles
    ]


def persist_layer1_verdicts(
    conn: sqlite3.Connection,
    articles: list[ArticleMeta],
    results: list[FilterResult],
) -> None:
    """Atomically persist Layer 1 verdicts on each article's source table.

    Groups by source ('wechat' → ``articles``; 'rss' → ``rss_articles``);
    issues one UPDATE per source-table inside ONE transaction; rolls back
    on any error. Only the 4 ``layer1_*`` columns are written; other
    columns untouched (LF-1.7).

    Per LF-1.5: when ALL results have ``verdict=None`` the caller MUST NOT
    call this — leave rows NULL so the next ingest tick re-evaluates. This
    helper persists exactly what is passed; verdict=None will land in the
    DB as NULL on the verdict column (which is the desired effect for a
    mixed-failure batch — currently impossible because LLM errors fail the
    whole batch, but this preserves correctness if ir-2's Layer 2 wants
    per-row error reporting).
    """
    if len(articles) != len(results):
        raise ValueError("articles and results must have equal length")

    now = datetime.now(timezone.utc).isoformat()
    by_source: dict[str, list[tuple[str | None, str, str, str, int]]] = {
        "wechat": [],
        "rss": [],
    }
    for a, r in zip(articles, results):
        by_source[a.source].append(
            (r.verdict, r.reason, now, r.prompt_version, a.id)
        )

    table_for: dict[str, str] = {"wechat": "articles", "rss": "rss_articles"}

    try:
        conn.execute("BEGIN")
        for source, rows in by_source.items():
            if not rows:
                continue
            tbl = table_for[source]
            conn.executemany(
                f"UPDATE {tbl} SET "
                f"layer1_verdict = ?, layer1_reason = ?, layer1_at = ?, "
                f"layer1_prompt_version = ? "
                f"WHERE id = ?",
                rows,
            )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise


__all__ = [
    "ArticleMeta",
    "ArticleWithBody",
    "FilterResult",
    "PROMPT_VERSION_LAYER1",
    "PROMPT_VERSION_LAYER2",
    "LAYER1_BATCH_SIZE",
    "LAYER1_TIMEOUT_SEC",
    "layer1_pre_filter",
    "layer2_full_body_score",
    "persist_layer1_verdicts",
]

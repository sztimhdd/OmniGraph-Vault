"""Batch RSS pre-filter — one DeepSeek call screens N articles.

Returns per-article {keep, confidence, topic_hint, reason}.
Callers INSERT only keep=true rows.

Feature flag: RSS_PREFILTER_ENABLED=0 disables (all articles pass through).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from batch_classify_kol import get_deepseek_api_key

logger = logging.getLogger("rss_prefilter")

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = os.environ.get("PREFILTER_MODEL", "deepseek-chat")
BATCH_SIZE = int(os.environ.get("RSS_PREFILTER_BATCH", "30"))
ENABLED = os.environ.get("RSS_PREFILTER_ENABLED", "1") != "0"
TIMEOUT = 120

ALLOWED_TOPICS = {"Agent", "LLM", "RAG", "NLP", "CV", "Other", None}

PREFILTER_PROMPT = """你是技术文章过滤器。下面是 {n} 篇文章的标题和摘要。
判断每篇是否属于 AI/ML/Agent/LLM/RAG/NLP/CV 领域的技术文章，
值得深入阅读和分析。

**判断标准:**
- keep=true: 技术教程、深度分析、架构拆解、原创研究、工程实践
- keep=false: 纯新闻快讯、个人生活、年度总结、招聘广告、产品发布通稿、非技术内容
- confidence: high(很确定) / medium(比较确定) / low(不确定，先保留)
- topic_hint: Agent / LLM / RAG / NLP / CV / Other (用 Other 表示泛 AI/ML 但不属于前五个)
- reason: 10字以内判断理由(中文)

**特别注意:**
- 关于 AI 产品的新闻通稿(如"OpenAI发布新功能") → keep=false(除非包含技术细节)
- 个人博客年度总结、生活感悟 → keep=false
- 技术教程、代码实战、架构分析 → keep=true
- confidence=low 时，keep 必须为 true(宁滥勿缺)

文章列表:
{articles}

只输出纯 JSON 数组，不要任何其他内容:
[{{"id":1,"keep":true,"confidence":"high","topic_hint":"Agent","reason":"...理由..."}}, ...]"""

CLEAN_JSON = re.compile(r"```(?:json)?\s*|\s*```", re.IGNORECASE)


def _infer_id(article: dict[str, Any], idx: int) -> int:
    return article.get("id", idx + 1)


def _describe(article: dict[str, Any], idx: int) -> str:
    aid = _infer_id(article, idx)
    title = (article.get("title") or "")[:200]
    length = article.get("content_length", 0)
    summary = (article.get("summary") or "")[:500]
    return f"[{aid}] 标题: {title} | 长度: {length} | 摘要: {summary}"


def _call_deepseek(prompt: str, api_key: str) -> str:
    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _parse(raw: str) -> list[dict[str, Any]]:
    cleaned = CLEAN_JSON.sub("", raw).strip()
    results = json.loads(cleaned)
    if not isinstance(results, list):
        raise ValueError(f"expected JSON array, got {type(results)}")
    return results


def _normalize(results: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Map LLM response to position-indexed results (input order).

    The LLM sees sequential [1]..[N] in the prompt. We map those back to
    result slots 0..N-1. Out-of-range / duplicate / missing IDs are handled:
      - out-of-range → dropped (LLM hallucination)
      - duplicate → first wins
      - missing → backfilled as keep (safe default)
    """
    # Initialize all slots as keep-by-default
    slots: list[dict[str, Any]] = [
        {"keep": True, "confidence": "low", "topic_hint": None, "reason": "filter_missed_by_llm"}
        for _ in range(n)
    ]
    seen: set[int] = set()

    for item in results:
        aid = item.get("id")
        if aid is None:
            continue
        aid = int(aid)
        if aid < 1 or aid > n:
            continue
        if aid in seen:
            continue
        seen.add(aid)

        idx = aid - 1  # LLM uses 1-based, we use 0-based
        confidence = str(item.get("confidence", "low")).lower()
        if confidence not in ("high", "medium", "low"):
            confidence = "low"

        keep = bool(item.get("keep", True))
        if confidence == "low" and not keep:
            keep = True

        topic = item.get("topic_hint") or None
        if topic is not None and topic not in ALLOWED_TOPICS:
            topic = "Other"

        reason = str(item.get("reason", ""))[:200]

        slots[idx] = {
            "keep": keep,
            "confidence": confidence,
            "topic_hint": topic,
            "reason": reason,
        }

    return slots


def batch_filter(
    articles: list[dict[str, Any]],
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Filter a batch of articles through DeepSeek pre-filter.

    Returns one dict per input article with {id, keep, confidence, topic_hint, reason}.
    On any error, returns all-keep (safe fallback).
    """
    if not articles:
        return []

    if not ENABLED:
        return [
            {"id": _infer_id(a, i), "keep": True, "confidence": "low",
             "topic_hint": None, "reason": "prefilter_disabled"}
            for i, a in enumerate(articles, 1)
        ]

    if api_key is None:
        api_key = get_deepseek_api_key()
        if not api_key:
            logger.warning("DeepSeek key not found, keeping all articles")
            return [
                {"id": _infer_id(a, i), "keep": True, "confidence": "low",
                 "topic_hint": None, "reason": "no_api_key"}
                for i, a in enumerate(articles, 1)
            ]

    descs = "\n".join(_describe(a, i) for i, a in enumerate(articles, 1))
    prompt = PREFILTER_PROMPT.format(n=len(articles), articles=descs)

    try:
        raw = _call_deepseek(prompt, api_key)
        parsed = _parse(raw)
        return _normalize(parsed, len(articles))
    except Exception as exc:
        logger.warning("pre-filter batch failed: %s — keeping all %d articles", exc, len(articles))
        return [
            {"id": _infer_id(a, i), "keep": True, "confidence": "low",
             "topic_hint": None, "reason": f"error:{exc!r}"[:60]}
            for i, a in enumerate(articles, 1)
        ]

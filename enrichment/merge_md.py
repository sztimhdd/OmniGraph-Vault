"""Merge 好问 summaries inline into the WeChat markdown (D-09).

Pure function — no I/O. Used by merge_and_ingest.py after disk artifacts
are collected.
"""
from __future__ import annotations
from typing import Optional


HEADER = "\n\n## 知识增厚\n"
EMPTY_FOOTER = "\n\n## 知识增厚\n\n(未找到相关的知乎问答)\n"


def merge_wechat_with_haowen(
    wechat_md: str,
    haowen: list[Optional[dict]],
) -> str:
    """Append 好问 summaries to the WeChat MD tail.

    ``haowen`` is a list of {question, summary, best_source_url, ...} dicts
    (from the ``/zhihu-haowen-enrich`` skill's haowen.json). None entries
    (= failed questions) are skipped. If all entries are None (or the list is
    empty), a footer indicating "no Zhihu answers found" is appended instead.

    The question number in the output heading reflects the original list
    position (1-based), so gaps caused by None entries are visible.

    Returns the merged Markdown string. No I/O, no side effects.
    """
    successful = [h for h in haowen if h is not None]
    if not successful:
        return wechat_md.rstrip() + EMPTY_FOOTER

    out = wechat_md.rstrip() + HEADER
    for i, h in enumerate(haowen):
        if h is None:
            continue
        q = h.get("question", "(unknown)")
        summary = h.get("summary", "").strip()
        src = h.get("best_source_url", "").strip()
        out += f"\n### 问题 {i + 1}: {q}\n\n{summary}\n"
        if src:
            out += f"\n来源: {src}\n"
    return out

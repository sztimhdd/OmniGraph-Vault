"""LLM-based article body rewriter for kb-v2.3 readability upgrade.

Single public entry point:

    rewrite_body_with_deepseek(title, body) -> str | None

Cleans a dirty WeChat article body (strips ads/boilerplate/tracking-JS,
reflows paragraphs, fixes headings/lists/code-blocks) WITHIN the source
language. Output is the display-only clean version for ``body_rewritten``.

KEY SAFETY INVARIANT: every ``http://localhost:8765/`` image URL present in
the input MUST appear byte-identical in the output. If the URL sets differ
(any URL added, dropped, or mutated), the rewrite is REJECTED and None is
returned — caller leaves ``body_rewritten`` NULL and falls back to ``body``.

Lazy import discipline: this module MUST NOT import lib.translate or
lib.llm_deepseek at module top — those trigger the DEEPSEEK_API_KEY check.
All lib.* imports live inside ``rewrite_body_with_deepseek`` so callers that
import this module without running a rewrite (e.g. dry-run crons) never need
the key at import time.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

REWRITE_BODY_TIMEOUT_S: float = 300.0
_REWRITE_MODEL: str = "deepseek-v4-pro"
IMAGE_URL_RE = re.compile(r"http://localhost:8765/\S+")

# Trailing markdown punctuation that may follow a bare URL in image lines
_URL_TRAILING = re.compile(r"[)\]>\"']+$")


def _extract_image_urls(text: str) -> set[str]:
    """Return the set of ``http://localhost:8765/...`` URLs found in *text*.

    Strips trailing markdown punctuation (``)`` ``]`` ``>`` ``"`` ``'``) so
    ``![alt](http://localhost:8765/a/0.jpg)`` and the bare reference-line URL
    ``http://localhost:8765/a/0.jpg`` compare equal.
    """
    found = IMAGE_URL_RE.findall(text)
    return {_URL_TRAILING.sub("", url) for url in found}


def _build_rewrite_prompt(title: str, body: str, src_lang: str) -> str:
    """Build the rewrite prompt for a single article body.

    The prompt instructs DeepSeek to clean and reformat the body WITHIN
    *src_lang* (no translation). It includes the full CONTEXT.md gate
    checklist verbatim and a few-shot image-URL verbatim constraint.
    """
    lang_label = "Chinese (zh)" if src_lang == "zh" else "English (en)"
    return (
        f"You are a markdown editor. Clean and reformat the following article "
        f"body, which was scraped from WeChat. The article is in {lang_label}. "
        f"Your task is to emit a clean {lang_label} version — do NOT translate.\n\n"
        f"Apply ALL of the following rules:\n\n"
        f"1. BOILERPLATE STRIP: remove any of these sections if present —\n"
        f"   关注公众号 / 点赞 / 在看 / 分享提示, 扫码 / 二维码段落,\n"
        f"   转载声明, 作者简介尾段 (e.g. \"作者：xxx，现任/曾任...\"),\n"
        f"   subscription CTAs, nav residue, tracking-JS snippets.\n"
        f"   Stop output at the last paragraph of real content.\n\n"
        f"2. LEAD FILLER STRIP: remove pure-filler opening sentences such as\n"
        f"   \"今天我们来聊\", \"大家好\", \"本文将介绍\", or English equivalents.\n"
        f"   The first paragraph MUST open with real content.\n\n"
        f"3. HEADINGS: demote any H1 (`#`) to H2 (`##`). Keep relative depth.\n"
        f"   Headers are chunk boundaries — preserve them.\n\n"
        f"4. STRUCTURE: lists stay as lists; code blocks stay as code blocks;\n"
        f"   fenced code blocks (```...```) are preserved verbatim, content NOT\n"
        f"   modified. For unlabeled fences infer a language tag where obvious.\n\n"
        f"5. PARAGRAPH REFLOW: reflow long paragraphs at logical sentence\n"
        f"   boundaries (~200 chars). Do NOT merge short paragraphs.\n\n"
        f"6. HTML REMOVAL: output MUST be markdown only. NEVER output raw HTML\n"
        f"   tags: <script>, <style>, <div>, <span>, or any other HTML element.\n\n"
        f"7. IMAGE URLs — CRITICAL CONSTRAINT:\n"
        f"   Image URLs of the form `http://localhost:8765/{{hash}}/{{name}}`\n"
        f"   and the `![...](...)` markdown around them MUST be reproduced\n"
        f"   BYTE-FOR-BYTE. NEVER alter, shorten, or invent a URL.\n"
        f"   Treat image lines as opaque tokens — do NOT describe or improve images.\n"
        f"   Also preserve the reference lines `Image N from article '{{title}}':\n"
        f"   http://localhost:8765/{{hash}}/{{name}}` with URLs byte-identical.\n\n"
        f"   CORRECT example — preserve exactly:\n"
        f"   ![图片](http://localhost:8765/abc123/0.jpg)\n\n"
        f"   WRONG example — never shorten or mangle:\n"
        f"   ![图片](http://localhost:8765/0.jpg)   ← WRONG: path truncated\n"
        f"   ![图片](./0.jpg)                        ← WRONG: relative path\n\n"
        f"8. CONTENT GUARD: do NOT over-delete. Keep all substantive content.\n"
        f"   Output length MUST be at least 20% of the input length.\n\n"
        f"9. OUTPUT FORMAT: return ONLY the cleaned markdown — no preamble,\n"
        f"   no explanation, no surrounding fences.\n\n"
        f"Title (context only — do not include in output): {title}\n\n"
        f"Body to clean:\n"
        f"<<<DIRTY_BODY_START>>>\n"
        f"{body}\n"
        f"<<<DIRTY_BODY_END>>>\n"
    )


async def rewrite_body_with_deepseek(
    title: str,
    body: str,
) -> Optional[str]:
    """Rewrite *body* into a clean display version within its source language.

    Returns the cleaned markdown string on success, or ``None`` if:
    - The LLM returns empty output.
    - The URL-set diff safety valve fires (any image URL added/dropped/mutated).
    - An exception is raised (timeout, network error, etc.).

    Never raises — callers leave ``body_rewritten`` NULL on ``None``.
    """
    if not body or not body.strip():
        return None

    # Lazy imports: avoid pulling DeepSeek client at module import time.
    from lib.translate import detect_source_lang  # noqa: PLC0415
    from lib.llm_deepseek import deepseek_model_complete  # noqa: PLC0415

    src_lang = detect_source_lang(body)
    prompt = _build_rewrite_prompt(title or "", body, src_lang)

    try:
        result = await asyncio.wait_for(
            deepseek_model_complete(prompt, model=_REWRITE_MODEL),
            timeout=REWRITE_BODY_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "rewrite_body timeout (>%ss) title=%s",
            REWRITE_BODY_TIMEOUT_S,
            (title or body[:80])[:80],
        )
        return None
    except Exception as exc:
        logger.warning("rewrite_body failed title=%s: %s", (title or body[:80])[:80], exc)
        return None

    cleaned = (result or "").strip()
    if not cleaned:
        logger.warning("rewrite_body returned empty output title=%s", (title or body[:80])[:80])
        return None

    # URL-set diff safety valve (LOCKED decision — see CONTEXT.md)
    input_urls = _extract_image_urls(body)
    output_urls = _extract_image_urls(cleaned)
    if input_urls != output_urls:
        dropped = input_urls - output_urls
        added = output_urls - input_urls
        logger.warning(
            "rewrite_body URL-set mismatch — REJECTING. title=%s dropped=%s added=%s",
            (title or body[:80])[:80],
            dropped,
            added,
        )
        return None

    return cleaned


__all__ = [
    "rewrite_body_with_deepseek",
    "_extract_image_urls",
    "_build_rewrite_prompt",
    "REWRITE_BODY_TIMEOUT_S",
    "_REWRITE_MODEL",
    "IMAGE_URL_RE",
]

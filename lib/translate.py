"""Incremental translation helper for ingest pipeline (260520-trans-inc).

Two public entry points used by the ingest pipeline + nightly cron:

    translate_title_with_deepseek_tavily(title, source_lang) -> dict | None
    translate_body_with_deepseek_tavily(title, body, source_lang) -> dict | None

Both:
  - Detect source lang heuristically (Chinese-character ratio > 30% -> 'zh')
  - Best-effort Tavily web-search for terminology context (fail-soft)
  - DeepSeek async chat completion via existing lib.llm_deepseek wrapper
  - Per-call timeout (15s title / 60s body); on any failure return None,
    never raise. Caller leaves DB column NULL on None per user spec
    "翻译失败 -> NULL,不'best-effort 写半句中文'".

Body prompt applies SSG-bake discipline: boilerplate strip, H1 demotion,
alt-text enrichment, code fence language inference, paragraph splitting.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional, TypedDict

logger = logging.getLogger(__name__)

# TODO(user): DeepSeek V4 Pro model ID — confirmed by user.
# Currently uses DEEPSEEK_MODEL env var (default deepseek-v4-flash via
# lib/llm_deepseek.py). Override per deployment via:
#     export DEEPSEEK_MODEL=<v4-pro-id>
# No wrapper change needed here; deepseek_model_complete reads the env var.

TRANSLATE_TITLE_TIMEOUT_S: float = 15.0
TRANSLATE_BODY_TIMEOUT_S: float = 300.0

# SSG-bake model: body translate path is hardcoded to deepseek-v4-pro,
# independent of DEEPSEEK_MODEL env (which still governs LightRAG callers).
_BAKE_MODEL: str = "deepseek-v4-pro"

# Authoritative-domain restriction for Tavily lookups (per user spec
# "*.org, *.gov, 维基, 大厂官网"). Tavily accepts wildcards.
_TAVILY_DOMAINS = [
    "wikipedia.org",
    "*.gov",
    "*.org",
    "github.com",
    "openai.com",
    "anthropic.com",
    "google.com",
    "microsoft.com",
    "huggingface.co",
]

_CHINESE_CHAR_RE = re.compile(r"[一-鿿]")
_CHINESE_RATIO_THRESHOLD = 0.30


class TranslationResult(TypedDict):
    title_translated: str
    lang: str  # target lang: 'en' or 'zh-CN'


class BodyTranslationResult(TypedDict):
    body_translated: str
    lang: str  # target lang: 'en' or 'zh-CN'


def detect_source_lang(text: str) -> str:
    """Return ``'zh'`` if Chinese-character ratio > 30%, else ``'en'``.

    Whitespace is stripped before counting. Empty / all-whitespace input
    returns ``'en'`` (default).
    """
    if not text:
        return "en"
    stripped = re.sub(r"\s+", "", text)
    if not stripped:
        return "en"
    cn_count = sum(1 for c in stripped if _CHINESE_CHAR_RE.match(c))
    return "zh" if (cn_count / len(stripped)) > _CHINESE_RATIO_THRESHOLD else "en"


def _target_lang(source_lang: str) -> str:
    """Map source -> target. ``'zh'`` -> ``'en'``; anything else -> ``'zh-CN'``."""
    return "en" if source_lang == "zh" else "zh-CN"


async def _tavily_search(title: str, n_results: int = 3) -> list[str]:
    """Best-effort Tavily search for terminology context.

    Returns a list of content snippets (each up to ~500 chars). Fail-soft:
    missing ``TAVILY_API_KEY`` -> empty list; any API/network error -> empty
    list with WARNING log; never raises. Translation proceeds without web
    context if this returns ``[]``.
    """
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        logger.debug("TAVILY_API_KEY not set; skipping terminology lookup")
        return []
    try:
        from tavily import TavilyClient  # lazy import — optional dep
        client = TavilyClient(api_key=api_key)
        result = client.search(
            query=title,
            search_depth="basic",
            max_results=n_results,
            include_domains=_TAVILY_DOMAINS,
        )
        snippets: list[str] = []
        for r in result.get("results", []):
            content = r.get("content") or ""
            if content:
                snippets.append(content[:500])
        return snippets
    except Exception as e:
        logger.warning(
            "Tavily search failed (%s) — proceeding without web context", e
        )
        return []


def _format_context_block(snippets: list[str]) -> str:
    if not snippets:
        return ""
    joined = "\n---\n".join(snippets)
    return f"\n\nReference snippets for terminology consistency:\n{joined}\n"


def _build_title_prompt(
    title: str,
    source_lang: str,
    target_lang: str,
    context_snippets: list[str],
) -> str:
    return (
        f"Translate the following article title from {source_lang} to "
        f"{target_lang}. Preserve technical terms and named entities — use "
        f"widely-accepted English renderings where they exist (or romanized "
        f"forms for proper nouns without established translations). Return "
        f"ONLY the translated title, no preamble, no explanation, no "
        f"surrounding quotes."
        f"{_format_context_block(context_snippets)}"
        f"\n\nTitle: {title}"
    )


def _build_body_prompt(
    title: str,
    body: str,
    source_lang: str,
    target_lang: str,
    context_snippets: list[str],
) -> str:
    """SSG-bake body prompt: translate + restructure for static-site rendering.

    Applies bake discipline (H1 demotion, WeChat boilerplate strip, lead
    filler strip, alt-text enrichment, code-fence language inference,
    paragraph splitting). Image references stay at their source positions —
    they are NOT batched at the end.
    """
    return (
        f"Translate the following article body from {source_lang} to "
        f"{target_lang} and restructure it for clean static-site rendering. "
        f"The body is markdown. Apply ALL of the following rules:\n\n"
        f"1. HEADINGS: NEVER output H1 (`#`). Demote any H1 in the source to "
        f"H2 (`##`). Top-level sections use H2 (`##`); sub-sections use H3 "
        f"(`###`). Preserve relative depth below H2 unchanged.\n\n"
        f"2. WECHAT BOILERPLATE STRIP (body end): remove any of these tail "
        f"sections if present — 关注公众号 / 点赞 / 在看 / 分享提示, "
        f"扫码 / 二维码段落, 转载声明, 作者简介尾段 (e.g. "
        f"\"作者：xxx，现任/曾任...\"). Stop output at the last paragraph of "
        f"real content.\n\n"
        f"3. LEAD FILLER STRIP: remove pure-filler opening sentences such as "
        f"\"今天我们来聊\", \"大家好\", \"本文将介绍\", or their target-language "
        f"equivalents. The first paragraph MUST open with real content.\n\n"
        f"4. IMAGES: image references `![alt](url)` MUST stay at the EXACT "
        f"same line / paragraph position as in the source — do NOT batch them "
        f"at the end of sections or the article. Translate or generate "
        f"descriptive alt text in {target_lang}. Preserve the URL verbatim.\n\n"
        f"5. CODE BLOCKS: fenced code blocks (```...```) are preserved "
        f"verbatim; their content is NOT translated. For unlabeled fences "
        f"(```) infer and add a language tag where obvious "
        f"(python / bash / json / yaml). Leave the tag empty if the language "
        f"is genuinely unclear.\n\n"
        f"6. PARAGRAPH SPLITTING: long paragraphs (natural break beyond "
        f"~200 characters) should be split at logical sentence boundaries "
        f"for web readability. Do NOT merge short paragraphs.\n\n"
        f"7. OUTPUT: return ONLY the baked markdown — no preamble, no "
        f"explanation, no surrounding fences.\n"
        f"{_format_context_block(context_snippets)}"
        f"\n\nTitle (for context only — do not translate or include): {title}"
        f"\n\nBody:\n{body}"
    )


async def translate_title_with_deepseek_tavily(
    title: str,
    source_lang: Optional[str] = None,
) -> Optional[TranslationResult]:
    """Translate one article title via Tavily-augmented DeepSeek.

    Args:
        title: source title to translate (may be empty or whitespace-only).
        source_lang: ``'zh'`` or ``'en'``. If ``None``, auto-detect.

    Returns:
        ``{"title_translated": str, "lang": str}`` on success, or ``None`` on
        any failure (LLM error, timeout, empty output). Never raises — caller
        can swallow ``None`` and leave the DB column NULL.
    """
    if not title or not title.strip():
        return None
    src = source_lang or detect_source_lang(title)
    tgt = _target_lang(src)
    try:
        # Lazy import: avoids pulling deepseek client into modules that import
        # lib.translate but don't actually translate (keeps import side-effects
        # localized to first-call time, matching lib/llm_deepseek.py's pattern).
        from lib.llm_deepseek import deepseek_model_complete

        snippets = await _tavily_search(title, n_results=3)
        prompt = _build_title_prompt(title, src, tgt, snippets)
        translated = await asyncio.wait_for(
            deepseek_model_complete(prompt),
            timeout=TRANSLATE_TITLE_TIMEOUT_S,
        )
        cleaned = (translated or "").strip().strip('"').strip("'").strip()
        if not cleaned:
            logger.warning("Empty title translation for: %s", title[:80])
            return None
        return {"title_translated": cleaned, "lang": tgt}
    except asyncio.TimeoutError:
        logger.warning(
            "Title translation timeout (>%ss): %s",
            TRANSLATE_TITLE_TIMEOUT_S,
            title[:80],
        )
        return None
    except Exception as e:
        logger.warning("Title translation failed: %s", e)
        return None


async def translate_body_with_deepseek_tavily(
    title: str,
    body: str,
    source_lang: Optional[str] = None,
) -> Optional[BodyTranslationResult]:
    """Translate article body via Tavily-augmented DeepSeek with image-position-preserving prompt.

    Args:
        title: source title — used only as Tavily search seed and prompt
            context, NOT translated. Pass empty string if title is unknown.
        body: source body (markdown).
        source_lang: ``'zh'`` or ``'en'``. If ``None``, auto-detect from body.

    Returns:
        ``{"body_translated": str, "lang": str}`` on success, or ``None`` on
        any failure (LLM error, timeout, empty output). Never raises.
    """
    if not body or not body.strip():
        return None
    src = source_lang or detect_source_lang(body)
    tgt = _target_lang(src)
    try:
        from lib.llm_deepseek import deepseek_model_complete

        # Use title as the Tavily seed when present (better terminology hits
        # than body excerpts); fall back to body[:200] if title is empty.
        search_seed = title.strip() if title and title.strip() else body[:200]
        snippets = await _tavily_search(search_seed, n_results=5)
        prompt = _build_body_prompt(title or "", body, src, tgt, snippets)
        translated = await asyncio.wait_for(
            deepseek_model_complete(prompt, model=_BAKE_MODEL),
            timeout=TRANSLATE_BODY_TIMEOUT_S,
        )
        cleaned = (translated or "").strip()
        if not cleaned:
            logger.warning(
                "Empty body translation for title: %s", (title or body[:80])[:80]
            )
            return None
        return {"body_translated": cleaned, "lang": tgt}
    except asyncio.TimeoutError:
        logger.warning(
            "Body translation timeout (>%ss) title=%s",
            TRANSLATE_BODY_TIMEOUT_S,
            (title or body[:80])[:80],
        )
        return None
    except Exception as e:
        logger.warning("Body translation failed: %s", e)
        return None


__all__ = [
    "detect_source_lang",
    "translate_title_with_deepseek_tavily",
    "translate_body_with_deepseek_tavily",
    "TranslationResult",
    "BodyTranslationResult",
    "TRANSLATE_TITLE_TIMEOUT_S",
    "TRANSLATE_BODY_TIMEOUT_S",
]

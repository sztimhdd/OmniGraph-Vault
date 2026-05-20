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

Body prompt mirrors kb-v2.2-7 Wave 2 R7 mitigation: image positioning is
structural data; do NOT relocate to ends; do NOT consolidate consecutive
images; do NOT reorder paragraphs.
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
TRANSLATE_BODY_TIMEOUT_S: float = 60.0

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
    """Body prompt mirrors kb-v2.2-7 Wave 2 R7 mitigation discipline."""
    return (
        f"Translate the following article body from {source_lang} to "
        f"{target_lang}. The body is markdown.\n\n"
        f"Hard rules (each is non-negotiable, treat as structural data):\n"
        f"  - Image references ![alt](url) MUST appear at the EXACT same "
        f"line/paragraph positions as in the source markdown. Do NOT "
        f"relocate images to section ends. Do NOT consolidate consecutive "
        f"images. Do NOT reorder paragraphs.\n"
        f"  - Code blocks ```...``` are preserved verbatim — content "
        f"untranslated.\n"
        f"  - Heading levels (#/##/###) preserved exactly.\n"
        f"  - Translate natural-language text only. Image positioning is "
        f"structural data, NOT stylistic.\n"
        f"  - Return ONLY the translated markdown — no preamble, no "
        f"explanation.\n"
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
            deepseek_model_complete(prompt),
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

"""kb-v2.2-2 F1': Bidirectional article translation service.

Translates article title + body using lib.llm_complete dispatcher.
Stores result in articles.body_translated / title_translated / translated_lang /
translated_at columns (migration 006).

DATA-07 enforcement: only articles where layer1_verdict='candidate' are eligible
for translation — no LLM cost wasted on filtered-out content.

The translation is triggered async via POST /api/translate/{hash} (BackgroundTask)
and stored to DB. Subsequent GET /api/article/{hash}?lang=X returns the stored
translation rather than re-translating.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranslateResult:
    ok: bool
    translated_lang: str
    error: Optional[str] = None


def _get_conn(db_path: Optional[str]) -> sqlite3.Connection:
    if db_path:
        conn = sqlite3.connect(db_path)
    else:
        from kb import config
        conn = sqlite3.connect(config.KB_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_article_for_translation(
    conn: sqlite3.Connection, article_hash: str
) -> Optional[sqlite3.Row]:
    """Resolve article_hash to a row checking both tables. Returns articles row only.

    Translation is only supported for the `articles` table (KOL source) because:
    - RSS articles don't have translation columns (migration 006 adds to articles only)
    - DATA-07 filter applies: layer1_verdict must be 'candidate'

    Returns None if not found or not eligible.
    """
    # Direct KOL match
    row = conn.execute(
        "SELECT id, title, body, lang, content_hash, layer1_verdict, "
        "body_translated, title_translated, translated_lang "
        "FROM articles WHERE content_hash = ?",
        (article_hash,),
    ).fetchone()
    if row:
        return row
    # KOL fallback: NULL content_hash rows (runtime md5 path)
    import hashlib
    for row in conn.execute(
        "SELECT id, title, body, lang, content_hash, layer1_verdict, "
        "body_translated, title_translated, translated_lang "
        "FROM articles WHERE content_hash IS NULL"
    ):
        body = row["body"] or ""
        computed = hashlib.md5(body.encode("utf-8")).hexdigest()[:10]
        if computed == article_hash:
            return row
    return None


async def translate_article(
    article_hash: str,
    target_lang: str,
    db_path: Optional[str] = None,
) -> TranslateResult:
    """Translate article title + body to target_lang and persist to DB.

    Args:
        article_hash: 10-char URL hash (md5[:10]).
        target_lang: 'en' or 'zh-CN'.
        db_path: optional DB path override (for tests).

    Returns:
        TranslateResult(ok=True) on success.
        TranslateResult(ok=False, error=...) on:
          - article not found
          - article not DATA-07 eligible (layer1_verdict != 'candidate')
          - target_lang same as article.lang
          - LLM call failure
    """
    conn = _get_conn(db_path)
    try:
        row = _fetch_article_for_translation(conn, article_hash)
        if row is None:
            return TranslateResult(ok=False, translated_lang=target_lang, error="not_found")

        if row["layer1_verdict"] != "candidate":
            return TranslateResult(
                ok=False,
                translated_lang=target_lang,
                error="not_eligible: layer1_verdict != candidate",
            )

        source_lang = row["lang"] or "unknown"
        if source_lang == target_lang:
            return TranslateResult(ok=False, translated_lang=target_lang, error="same_lang")

        # Already translated to this lang — idempotent
        if row["translated_lang"] == target_lang and row["body_translated"]:
            return TranslateResult(ok=True, translated_lang=target_lang)

        title = row["title"] or ""
        body = row["body"] or ""

        translated_title, translated_body = await _call_llm_translate(
            title, body, source_lang, target_lang
        )

        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "UPDATE articles SET body_translated=?, title_translated=?, "
            "translated_lang=?, translated_at=? WHERE id=?",
            (translated_body, translated_title, target_lang, now, row["id"]),
        )
        conn.commit()
        return TranslateResult(ok=True, translated_lang=target_lang)
    except Exception as exc:
        _log.error("translate_article %s→%s failed: %s", article_hash, target_lang, exc)
        return TranslateResult(ok=False, translated_lang=target_lang, error=str(exc))
    finally:
        conn.close()


async def _call_llm_translate(
    title: str,
    body: str,
    source_lang: str,
    target_lang: str,
) -> tuple[str, str]:
    """Call lib.llm_complete dispatcher to translate title + body.

    Returns (translated_title, translated_body).
    """
    from lib.llm_complete import get_llm_func

    lang_names = {"zh-CN": "Chinese", "en": "English", "unknown": "the source language"}
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)

    title_prompt = (
        f"Translate the following article title from {src_name} to {tgt_name}. "
        f"Return ONLY the translated title, nothing else.\n\nTitle: {title}"
    )
    body_prompt = (
        f"Translate the following article body from {src_name} to {tgt_name}. "
        f"Preserve all markdown formatting, code blocks, and image tags. "
        f"Return ONLY the translated text, nothing else.\n\n{body}"
    )

    llm = get_llm_func()
    translated_title = await llm(title_prompt)
    translated_body = await llm(body_prompt)

    # Strip common LLM wrapping patterns (leading/trailing quotes, "Translation: " prefix)
    translated_title = _strip_llm_wrapper(translated_title)

    return translated_title, translated_body


def _strip_llm_wrapper(text: str) -> str:
    """Remove common LLM response wrappers from short strings (e.g. translated titles)."""
    text = text.strip()
    # Remove "Translation: " or "Translated title: " prefix
    for prefix in ("Translation:", "Translated title:", "Translated:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
            break
    # Remove surrounding quotes
    if len(text) >= 2 and text[0] in ('"', "'", "“") and text[-1] in ('"', "'", "”"):
        text = text[1:-1]
    return text

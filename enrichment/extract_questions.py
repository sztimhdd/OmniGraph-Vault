"""Extract 1-3 under-documented technical questions from a WeChat article.

Uses Gemini 2.5 Flash Lite with google_search grounding (D-12).
Output contract (D-03): single-line JSON on stdout; full questions.json on disk.

CLI:
    python -m enrichment.extract_questions <article_md_path> [--hash <hash>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

from lib import INGESTION_LLM, generate_sync

logger = logging.getLogger(__name__)

# Module-level constants — read from env at import time.
# Tests reload this module after monkeypatching env vars to pick up changes.
DEFAULT_MIN_LENGTH = int(os.environ.get("ENRICHMENT_MIN_LENGTH", "2000"))
DEFAULT_MAX_QUESTIONS = int(os.environ.get("ENRICHMENT_MAX_QUESTIONS", "3"))
# Phase 7: ENRICHMENT_LLM and INGESTION_LLM both resolve to gemini-2.5-flash-lite;
# INGESTION_LLM used here for semantic clarity (enrichment is an ingestion-adjacent step).
DEFAULT_MODEL = os.environ.get("ENRICHMENT_LLM_MODEL", INGESTION_LLM)
DEFAULT_BASE_DIR = Path(
    os.environ.get(
        "ENRICHMENT_DIR",
        str(Path.home() / ".hermes" / "omonigraph-vault" / "enrichment"),
    )
)
GROUNDING_ENABLED = os.environ.get("ENRICHMENT_GROUNDING_ENABLED", "1") != "0"


_PROMPT_TMPL = (
    "You are a technical editor reviewing a Chinese AI/Agent engineering article. "
    "Identify {max_q} questions the article raises but does NOT answer in depth. "
    "Use Google Search to avoid suggesting questions already well-covered on the "
    "public web — focus on genuine under-documented gaps.\n\n"
    "Reply with ONLY a JSON array of objects with fields `question` (Chinese ok) "
    "and `context` (1-sentence why this is a gap). No prose before or after.\n\n"
    "Article:\n{article}"
)


def extract_questions(article_text: str, max_q: int = DEFAULT_MAX_QUESTIONS) -> list[dict]:
    """Call Gemini with grounding; return list of {question, context} dicts.

    Raises on API error or unparseable response.
    Parses best-effort JSON array from response.text.
    Uses lib.generate_sync() for key rotation + rate limit + retry (Phase 7).
    """
    from google.genai import types

    config = None
    if GROUNDING_ENABLED:
        tools = [types.Tool(google_search=types.GoogleSearch())]
        config = types.GenerateContentConfig(tools=tools)

    text = generate_sync(
        DEFAULT_MODEL,
        [_PROMPT_TMPL.format(max_q=max_q, article=article_text)],
        config=config,
    ) or ""
    # Strip code fences / surrounding prose and parse JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(
            f"Gemini response did not contain a JSON array: {text[:200]}"
        )
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError(f"Parsed JSON is not a list: {parsed}")
    return parsed[:max_q]


def _atomic_write_json(path: Path, data: object) -> None:
    """Write data as JSON to path atomically (tmp -> rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _derive_hash(article_path: Path, override: str | None) -> str:
    if override:
        return override
    return hashlib.md5(article_path.read_bytes()).hexdigest()[:10]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code (0 for ok/skipped, 1 for error)."""
    parser = argparse.ArgumentParser(
        description="Extract questions from a WeChat article markdown."
    )
    parser.add_argument("article_path", help="Path to WeChat article markdown file")
    parser.add_argument("--hash", dest="hash", help="Article hash; derived from md5 if omitted")
    parser.add_argument(
        "--base-dir",
        default=str(DEFAULT_BASE_DIR),
        help="Base enrichment directory (default: $ENRICHMENT_DIR or ~/.hermes/omonigraph-vault/enrichment)",
    )
    args = parser.parse_args(argv)

    article_path = Path(args.article_path)
    base_dir = Path(args.base_dir)
    article_hash = _derive_hash(article_path, args.hash)

    if not article_path.is_file():
        print(json.dumps({
            "hash": article_hash,
            "status": "error",
            "error": f"article_path not found: {article_path}",
        }))
        return 1

    article_text = article_path.read_text(encoding="utf-8")

    if len(article_text) < DEFAULT_MIN_LENGTH:
        print(json.dumps({
            "hash": article_hash,
            "status": "skipped",
            "reason": "too_short",
            "char_count": len(article_text),
        }))
        return 0

    try:
        questions = extract_questions(article_text, max_q=DEFAULT_MAX_QUESTIONS)
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({
            "hash": article_hash,
            "status": "error",
            "error": str(exc),
        }))
        return 1

    out_path = base_dir / article_hash / "questions.json"
    _atomic_write_json(out_path, {
        "hash": article_hash,
        "article_path": str(article_path),
        "questions": questions,
    })

    print(json.dumps({
        "hash": article_hash,
        "status": "ok",
        "question_count": len(questions),
        "artifact": str(out_path),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())

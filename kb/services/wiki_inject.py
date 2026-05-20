"""Wiki context resolution for KB synthesize (W4 of llm-wiki-integration).

Decision 4 (CONTEXT.md): synthesize is read-only with respect to wiki — never writes back.
"""
from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from kb import config
from kb.wiki_lint import lint_citation_integrity, lint_staleness


def extract_main_entity(question: str, wiki_root: Path = Path("kb/wiki")) -> str | None:
    entities_dir = Path(wiki_root) / "entities"
    if not entities_dir.exists():
        return None
    q = question.lower()
    for page in sorted(entities_dir.glob("*.md")):
        slug = page.stem
        if slug in q or slug.replace("-", " ") in q:
            return slug
    return None


@lru_cache(maxsize=1)
def _hashes_cached(db_path: str, mtime: float) -> frozenset[str]:
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT content_hash FROM articles WHERE content_hash IS NOT NULL "
                "UNION SELECT substr(content_hash, 1, 10) FROM rss_articles WHERE content_hash IS NOT NULL"
            ).fetchall()
        return frozenset(r[0] for r in rows if r[0])
    except sqlite3.Error:
        return frozenset()


def _known_article_hashes() -> frozenset[str]:
    db_path = config.KB_DB_PATH
    try:
        return _hashes_cached(str(db_path), db_path.stat().st_mtime)
    except OSError:
        return frozenset()


async def resolve_wiki_context(
    question: str,
    wiki_root: Path = Path("kb/wiki"),
    max_age_days: int = 180,
    known_article_hashes: frozenset[str] | None = None,
) -> str:
    try:
        entity = extract_main_entity(question, wiki_root)
        if entity is None:
            return ""
        page = Path(wiki_root) / "entities" / f"{entity}.md"
        if not page.exists() or lint_staleness(page, max_age_days):
            return ""
        hashes = known_article_hashes if known_article_hashes is not None else _known_article_hashes()
        if lint_citation_integrity(page, hashes):
            return ""
        return f"<wiki_context>\n{page.read_text(encoding='utf-8')}\n</wiki_context>\n\n"
    except Exception:
        return ""

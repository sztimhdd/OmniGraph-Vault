"""EXPORT-01..06: Single CLI entry point for KB-v2 SSG build.

Reads SQLite + filesystem -> Jinja2 templates -> kb/output/ static HTML tree.

EXPORT-02 invariant: never writes to SQLite or KB_IMAGES_DIR. Output goes
only to KB_OUTPUT_DIR (default: kb/output/).

EXPORT-01 invariant: re-running on unchanged DB produces byte-identical
output for EVERY file under kb/output/ -- including sitemap.xml. Sitemap
<lastmod> values are derived from input data only; NEVER from wall clock.

Usage:
    python kb/export_knowledge_base.py [--output-dir PATH] [--limit N]

DB path override: env var only -- `KB_DB_PATH=/path python kb/export_knowledge_base.py`.
There is no `--db-path` CLI flag because config.KB_DB_PATH is bound at module
import (before argparse runs) -- a CLI flag would be silently ignored. Use the
env var instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

# When this file is run as a script (`python kb/export_knowledge_base.py`),
# Python prepends the script's directory (kb/) to sys.path, which causes the
# `kb.locale` subpackage to shadow Python's stdlib `locale` module. argparse
# (via gettext) then fails with `module 'locale' has no attribute 'normalize'`.
# Replace the kb/-script-dir entry with the project root so (a) stdlib `locale`
# resolves correctly AND (b) `from kb import config` still works.
# No-op when imported via `python -m kb.export_knowledge_base` (sys.path[0]
# is then '' or the project root, never kb/ itself).
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if sys.path and Path(sys.path[0]).resolve() == _THIS_DIR:
    sys.path[0] = str(_PROJECT_ROOT)

import argparse  # noqa: E402  -- must come after sys.path fix above
import json
import logging
import re
import shutil
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import markdown  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

from kb import config  # noqa: E402
from kb.data.article_query import (  # noqa: E402
    ArticleRecord,
    get_article_body,
    list_articles,
    resolve_url_hash,
)
from kb.i18n import register_jinja2_filter, validate_key_parity  # noqa: E402

logger = logging.getLogger(__name__)

KB_ROOT = Path(__file__).parent
TEMPLATES_DIR = KB_ROOT / "templates"
STATIC_SOURCE_DIR = KB_ROOT / "static"

# Markdown extensions (CONTEXT.md "Markdown rendering")
MD_EXTENSIONS = ["fenced_code", "codehilite", "tables", "toc", "nl2br"]

# EXPORT-01 idempotency: deterministic fallback for missing update_time.
# NEVER use datetime.now() anywhere in this module -- would break byte-equality
# across runs on different days. See REVISION 1 / Issue #1.
_LASTMOD_FALLBACK = "1970-01-01"


def _build_env() -> Environment:
    """Build Jinja2 env with i18n filter registered."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    register_jinja2_filter(env)
    return env


def _render_body_html(body_md: str) -> str:
    """Convert markdown to HTML with Pygments codehilite. Fresh Markdown per call."""
    md = markdown.Markdown(extensions=MD_EXTENSIONS)
    return md.convert(body_md)


def _record_to_dict(rec: ArticleRecord, url_hash: str) -> dict[str, Any]:
    """Shape an ArticleRecord into the dict that templates expect."""
    return {
        "id": rec.id,
        "title": rec.title,
        "url_hash": url_hash,
        "url": rec.url,
        "lang": rec.lang or "unknown",
        "source": rec.source,
        "update_time": rec.update_time,
        "publish_time": rec.publish_time,
    }


def _write_atomic(path: Path, content: str) -> None:
    """Write file atomically: write to .tmp then rename. Idempotency-safe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _build_og(article_dict: dict[str, Any], body_html: str) -> dict[str, str]:
    """og:* meta dict for an article detail page.

    og:description fallback (REVISION 1 / Issue #6): if the body strips down
    to <20 chars (very short article, image-only post), fall back to title.
    """
    # 200-char description from body (strip HTML tags crudely for og:description)
    text_only = re.sub(r"<[^>]+>", "", body_html)
    description = text_only[:200].strip()
    if len(description) < 20:
        description = article_dict["title"]
    return {
        "title": article_dict["title"],
        "description": description,
        "image": "/static/VitaClaw-Logo-v0.png",  # TODO v2.1: use first article image if available
        "type": "article",
        "locale": "zh_CN" if article_dict["lang"] == "zh-CN" else "en_US",
    }


def _build_json_ld(article_dict: dict[str, Any]) -> dict[str, Any]:
    """JSON-LD Article schema (UI-06)."""
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article_dict["title"],
        "datePublished": article_dict["publish_time"] or article_dict["update_time"],
        "inLanguage": article_dict["lang"],
        "author": {"@type": "Organization", "name": "VitaClaw"},
        "image": "/static/VitaClaw-Logo-v0.png",
    }


def render_article_detail(
    env: Environment, rec: ArticleRecord, output_dir: Path
) -> dict[str, Any]:
    """Render one article detail page. Returns the dict added to _url_index.json."""
    url_hash = resolve_url_hash(rec)
    body_md, body_source = get_article_body(rec)
    body_html = _render_body_html(body_md)

    article_dict = _record_to_dict(rec, url_hash)
    article_dict["body_source"] = body_source

    ctx = {
        "lang": rec.lang or "zh-CN",
        "article": article_dict,
        "body_html": body_html,
        "og": _build_og(article_dict, body_html),
        "page_url": f"/articles/{url_hash}.html",
        "json_ld": _build_json_ld(article_dict),
    }
    html = env.get_template("article.html").render(**ctx)
    _write_atomic(output_dir / "articles" / f"{url_hash}.html", html)
    return {"hash": url_hash, "id": rec.id, "source": rec.source, "lang": rec.lang}


def render_index_pages(
    env: Environment, articles: list[ArticleRecord], output_dir: Path
) -> None:
    """Render index.html (homepage), articles/index.html (list), ask/index.html (Q&A entry)."""
    # Build article dicts once, reused across pages
    article_dicts = [
        {**_record_to_dict(rec, resolve_url_hash(rec))}
        for rec in articles
    ]

    # Homepage: 20 most recent
    # TODO v2.1: env-overridable KB_HOME_LATEST_LIMIT
    home_html = env.get_template("index.html").render(
        lang="zh-CN",
        articles=article_dicts[:20],
        page_url="/",
    )
    _write_atomic(output_dir / "index.html", home_html)

    # Article list: all
    list_html = env.get_template("articles_index.html").render(
        lang="zh-CN",
        articles=article_dicts,
        page_url="/articles/",
    )
    _write_atomic(output_dir / "articles" / "index.html", list_html)

    # Q&A entry
    ask_html = env.get_template("ask.html").render(
        lang="zh-CN",
        page_url="/ask/",
    )
    _write_atomic(output_dir / "ask" / "index.html", ask_html)


def _compute_index_lastmod(articles: list[ArticleRecord]) -> str:
    """Deterministic build_date for sitemap index URLs (`/`, `/articles/`, `/ask/`).

    REVISION 1 / Issue #1: NEVER use datetime.now() -- would break EXPORT-01.
    Use the most recent article's update_time (truncated to YYYY-MM-DD).
    Falls back to _LASTMOD_FALLBACK if list is empty or no article has a
    non-empty update_time.
    """
    candidates = [
        (a.update_time or "")[:10]
        for a in articles
        if (a.update_time or "")[:10]
    ]
    return max(candidates) if candidates else _LASTMOD_FALLBACK


def render_sitemap(articles: list[ArticleRecord], output_dir: Path) -> None:
    """EXPORT-06: sitemap.xml with all article URLs + 3 index pages.

    EXPORT-01 idempotency invariant (REVISION 1 / Issue #1):
    every <lastmod> value MUST be derived deterministically from input data;
    NEVER from datetime.now(). Re-running on unchanged DB produces a
    byte-identical sitemap.xml regardless of wall clock.

    - Index URLs (`/`, `/articles/`, `/ask/`): use max(article.update_time[:10])
    - Article URLs: use article.update_time[:10] if non-empty, else _LASTMOD_FALLBACK
    - Empty article list (test-only edge case): use _LASTMOD_FALLBACK everywhere
    """
    index_lastmod = _compute_index_lastmod(articles)
    urls: list[tuple[str, str]] = [
        ("/", index_lastmod),
        ("/articles/", index_lastmod),
        ("/ask/", index_lastmod),
    ]
    for rec in articles:
        url_hash = resolve_url_hash(rec)
        lastmod = (rec.update_time or "")[:10] or _LASTMOD_FALLBACK
        urls.append((f"/articles/{url_hash}.html", lastmod))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url, lastmod in urls:
        lines.append(
            f"  <url><loc>{xml_escape(url)}</loc>"
            f"<lastmod>{xml_escape(lastmod)}</lastmod></url>"
        )
    lines.append("</urlset>")
    _write_atomic(output_dir / "sitemap.xml", "\n".join(lines) + "\n")


def render_robots(output_dir: Path) -> None:
    """EXPORT-06: robots.txt allow all + sitemap reference."""
    content = "User-agent: *\nAllow: /\n\nSitemap: /sitemap.xml\n"
    _write_atomic(output_dir / "robots.txt", content)


def copy_static_assets(output_dir: Path) -> None:
    """UI-04: copy kb/static/ to kb/output/static/."""
    target = output_dir / "static"
    target.mkdir(parents=True, exist_ok=True)
    for item in STATIC_SOURCE_DIR.iterdir():
        if item.name.startswith("."):
            continue
        if item.is_file():
            shutil.copy2(item, target / item.name)


def write_url_index(article_index: list[dict], output_dir: Path) -> None:
    """CONTEXT.md stability concern: record (hash, article_id) for URL drift detection.

    Logs WARN if a hash collides across two different article_ids.
    """
    # Detect collisions
    seen: dict[str, dict] = {}
    for entry in article_index:
        h = entry["hash"]
        if h in seen and seen[h]["id"] != entry["id"]:
            print(
                f"WARN: hash collision {h}: existing id={seen[h]['id']} vs new id={entry['id']}",
                file=sys.stderr,
            )
        else:
            seen[h] = entry
    # Pretty JSON for diff stability (idempotency for EXPORT-01)
    content = json.dumps(article_index, indent=2, sort_keys=True, ensure_ascii=False)
    _write_atomic(output_dir / "_url_index.json", content + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "KB-v2 SSG export. Override DB path with env: "
            "KB_DB_PATH=/path python kb/export_knowledge_base.py"
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override KB_OUTPUT_DIR",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Dev mode: render only first N articles",
    )
    args = parser.parse_args(argv)

    output_dir: Path = args.output_dir or config.KB_OUTPUT_DIR

    # Validate i18n key parity at build time (fail-fast if locales drift)
    validate_key_parity()

    env = _build_env()

    print(f"Querying articles from {config.KB_DB_PATH}...")
    # list_articles: paginated; use a large limit to fetch all
    articles = list_articles(limit=10000, offset=0)
    if args.limit:
        articles = articles[: args.limit]
    print(f"Rendering {len(articles)} article detail pages...")

    article_index: list[dict] = []
    for i, rec in enumerate(articles):
        try:
            idx_entry = render_article_detail(env, rec, output_dir)
            article_index.append(idx_entry)
        except Exception as exc:
            print(
                f"ERROR rendering article id={rec.id} ({rec.source}): {exc}",
                file=sys.stderr,
            )
            continue
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(articles)}")

    print("Rendering index pages (home, articles list, ask)...")
    render_index_pages(env, articles, output_dir)

    print("Rendering sitemap.xml + robots.txt...")
    render_sitemap(articles, output_dir)
    render_robots(output_dir)

    print("Writing _url_index.json...")
    write_url_index(article_index, output_dir)

    print("Copying static assets...")
    copy_static_assets(output_dir)

    print(f"\nDone. Output: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

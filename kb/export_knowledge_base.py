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
import os
import re
import shutil
import sqlite3
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
    # kb-2 additions:
    cooccurring_entities_in_topic,
    entity_articles_query,
    related_entities_for_article,
    related_topics_for_article,
    slugify_entity_name,
    topic_articles_query,
)
from kb.i18n import register_jinja2_filter, t as i18n_t, validate_key_parity  # noqa: E402

logger = logging.getLogger(__name__)

KB_ROOT = Path(__file__).parent
TEMPLATES_DIR = KB_ROOT / "templates"
STATIC_SOURCE_DIR = KB_ROOT / "static"

# Markdown extensions (CONTEXT.md "Markdown rendering")
MD_EXTENSIONS = ["fenced_code", "codehilite", "tables", "toc", "nl2br"]

# Pygments lexer class -> human label for code-block top-right corner
# (mapping is small; keep inline rather than a separate JSON)
_LANG_LABEL = {
    "python": "Python", "py": "Python",
    "bash": "Bash", "sh": "Shell", "shell": "Shell",
    "javascript": "JavaScript", "js": "JavaScript", "ts": "TypeScript", "typescript": "TypeScript",
    "json": "JSON", "yaml": "YAML", "yml": "YAML", "toml": "TOML",
    "go": "Go", "rust": "Rust", "rs": "Rust",
    "java": "Java", "kotlin": "Kotlin", "scala": "Scala",
    "html": "HTML", "css": "CSS", "scss": "SCSS",
    "sql": "SQL", "graphql": "GraphQL",
    "c": "C", "cpp": "C++", "csharp": "C#", "cs": "C#",
    "ruby": "Ruby", "php": "PHP", "perl": "Perl",
    "nix": "Nix", "lua": "Lua", "dart": "Dart", "swift": "Swift",
    "dockerfile": "Dockerfile", "docker": "Dockerfile",
    "markdown": "Markdown", "md": "Markdown",
    "diff": "Diff", "patch": "Patch", "xml": "XML",
}

# Pygments emits `<div class="codehilite"><pre><span class="...">` and inside that
# wraps with `<code class="language-XXX">`. We post-process to add `data-lang-label`
# to the wrapper div so the CSS ::before reads it via attr().
_CODEHILITE_LANG_RE = re.compile(
    r'(<div class="codehilite">)\s*<pre><span></span><code class="language-([a-zA-Z0-9_+-]+)"',
    re.MULTILINE,
)

# Jekyll/Rouge pattern (used by some RSS-scraped articles whose source HTML pre-renders
# code blocks): `<div class="language-X highlighter-rouge"><div class="highlight"><pre>`.
# We add `data-lang-label="X"` to the outer div so the same CSS ::before applies.
_ROUGE_LANG_RE = re.compile(
    r'<div class="language-([a-zA-Z0-9_+-]+) highlighter-rouge">',
)


def _annotate_code_block_lang_label(html: str) -> str:
    """Inject data-lang-label onto Pygments .codehilite divs AND Jekyll/Rouge
    .language-X.highlighter-rouge wrappers, so the CSS ::before reads it via attr().

    Idempotent: re-running on annotated HTML is a no-op (matches the unannotated
    pattern, so already-annotated nodes are skipped).
    """
    def _sub_codehilite(m: re.Match[str]) -> str:
        lang_class = m.group(2).lower()
        label = _LANG_LABEL.get(lang_class, lang_class.upper())
        return f'<div class="codehilite" data-lang-label="{label}"><pre><span></span><code class="language-{m.group(2)}"'

    def _sub_rouge(m: re.Match[str]) -> str:
        lang_class = m.group(1).lower()
        label = _LANG_LABEL.get(lang_class, lang_class.upper())
        return f'<div class="language-{m.group(1)} highlighter-rouge" data-lang-label="{label}">'

    html = _CODEHILITE_LANG_RE.sub(_sub_codehilite, html)
    html = _ROUGE_LANG_RE.sub(_sub_rouge, html)
    return html


def _make_snippet(body_md: str, max_chars: int = 200) -> str:
    """Strip markdown markup crudely + return ~max_chars char snippet for cards."""
    if not body_md:
        return ""
    # Strip code fences first (don't want code in card snippets)
    text = re.sub(r"```[\s\S]*?```", "", body_md)
    # Strip inline code, links, images, headings, html tags, emphasis, list bullets
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^[#>\-\*\+]+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _estimate_reading_time(body_md: str) -> int:
    """Estimate reading time in whole minutes (rounded up).
    Heuristic: 250 wpm for Latin / 500 cpm for CJK (mixed content averages out).
    Returns 1 for any non-empty body so the badge reads naturally.
    """
    if not body_md:
        return 0
    # Crude unit count: count CJK chars + Latin word-tokens
    text = re.sub(r"<[^>]+>", "", body_md)
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    latin_words = len(re.findall(r"[A-Za-z]+", text))
    minutes = max(1, round((cjk / 500) + (latin_words / 250)))
    return minutes


# Topic chips on homepage hero (5 fixed for v2.0; matched against locale keys)
HERO_TOPIC_CHIP_KEYS = [
    "hero.chip_ai_agent",
    "hero.chip_rpa",
    "hero.chip_llm",
    "hero.chip_kg",
    "hero.chip_mcp",
]

# Hot questions on /ask/ (5 fixed for v2.0; locale keys)
ASK_HOT_QUESTION_KEYS = [f"ask.hot_q_{i}" for i in range(1, 6)]

# kb-2 topic enumeration — 5 fixed raw classifications.topic values, alpha-ordered.
# Slug map kept stable for URL idempotency (kb/output/topics/{slug}.html).
KB2_TOPICS: tuple[str, ...] = ("Agent", "CV", "LLM", "NLP", "RAG")
TOPIC_SLUG_MAP: dict[str, str] = {
    "Agent": "agent",
    "CV": "cv",
    "LLM": "llm",
    "NLP": "nlp",
    "RAG": "rag",
}
# Entity surface threshold (ENTITY-01). Env-overridable for fixture/dev DBs.
KB_ENTITY_MIN_FREQ: int = int(os.environ.get("KB_ENTITY_MIN_FREQ", "5"))

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


def _record_to_dict(
    rec: ArticleRecord,
    url_hash: str,
    *,
    body_md: str | None = None,
) -> dict[str, Any]:
    """Shape an ArticleRecord into the dict that templates expect.

    `body_md` (optional): if provided, derive `snippet` (~200-char excerpt) and
    `reading_time` (minutes) for card / detail rendering. Pass None when these
    fields are not needed (sitemap / url-index path).
    """
    out: dict[str, Any] = {
        "id": rec.id,
        "title": rec.title,
        "url_hash": url_hash,
        "url": rec.url,
        "lang": rec.lang or "unknown",
        "source": rec.source,
        "update_time": rec.update_time,
        "publish_time": rec.publish_time,
    }
    if body_md is not None:
        out["snippet"] = _make_snippet(body_md)
        out["reading_time"] = _estimate_reading_time(body_md)
    return out


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
    body_html = _annotate_code_block_lang_label(_render_body_html(body_md))

    article_dict = _record_to_dict(rec, url_hash, body_md=body_md)
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
    """Render index.html (homepage), articles/index.html (list), ask/index.html (Q&A entry).

    Card snippets + reading-time are derived from body_md ONLY for the homepage's
    20 cards (filesystem read per row). The full /articles/ list keeps body_md=None
    to avoid 1800x filesystem reads — those cards show meta + title without snippet.
    """
    # Homepage: 20 most recent — read body_md to enrich cards with snippet + reading_time
    home_dicts: list[dict[str, Any]] = []
    for rec in articles[:20]:
        url_hash = resolve_url_hash(rec)
        body_md, _src = get_article_body(rec)
        home_dicts.append(_record_to_dict(rec, url_hash, body_md=body_md))

    home_html = env.get_template("index.html").render(
        lang="zh-CN",
        articles=home_dicts,
        topic_chip_keys=HERO_TOPIC_CHIP_KEYS,
        page_url="/",
    )
    _write_atomic(output_dir / "index.html", home_html)

    # Article list: all rows, no body_md (would be 1800x FS reads = slow)
    list_dicts = [_record_to_dict(rec, resolve_url_hash(rec)) for rec in articles]
    list_html = env.get_template("articles_index.html").render(
        lang="zh-CN",
        articles=list_dicts,
        page_url="/articles/",
    )
    _write_atomic(output_dir / "articles" / "index.html", list_html)

    # Q&A entry
    ask_html = env.get_template("ask.html").render(
        lang="zh-CN",
        hot_question_keys=ASK_HOT_QUESTION_KEYS,
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


# ---- kb-2 helpers (TOPIC + ENTITY render loops) ----


def _record_to_card_dict(rec: ArticleRecord) -> dict[str, Any]:
    """Build a card-shape dict for topic.html / entity.html article rows.

    Mirrors kb-1's `_record_to_dict(rec, url_hash, body_md=...)` pattern, adding
    a precomputed `update_time_human` (zh-CN by default — matches existing
    article-card meta convention; kb-1 templates also pass `humanize` filter
    inline, so this is just a precomputation for entity.html which uses the
    pre-resolved value).

    Body is read from filesystem to derive snippet + reading_time (mirrors
    homepage card flow). For idempotency, body source is deterministic.
    """
    url_hash = resolve_url_hash(rec)
    body_md, _src = get_article_body(rec)
    out = _record_to_dict(rec, url_hash, body_md=body_md)
    # entity.html consumes a pre-humanized field (rest of templates use the
    # humanize filter inline). Pass zh-CN form — base.html's lang-toggle JS
    # rewrites visible date strings on en-mode if needed, but most cards
    # show zh-CN by default per kb-1 convention.
    from kb.i18n import humanize_date

    out["update_time_human"] = humanize_date(rec.update_time, "zh-CN")
    return out


def _discover_qualifying_entities(
    conn: sqlite3.Connection, min_freq: int
) -> list[dict[str, Any]]:
    """Return list of entity dicts crossing the freq threshold.

    Each dict: {name, slug, article_count, lang_zh, lang_en, lang_unknown}.
    Sorted by name ASC for idempotency (EXPORT-01).

    Single SQL aggregation — no Python-side bucketing. Joins extracted_entities
    against both source tables (articles for source='wechat', rss_articles for
    source='rss') to derive per-language counts. Articles with NULL lang count
    as 'unknown'.
    """
    sql = """
        SELECT
          e.name,
          COUNT(DISTINCT e.article_id || '-' || e.source) AS total_count,
          SUM(CASE WHEN COALESCE(a.lang, r.lang) = 'zh-CN' THEN 1 ELSE 0 END) AS lang_zh,
          SUM(CASE WHEN COALESCE(a.lang, r.lang) = 'en'    THEN 1 ELSE 0 END) AS lang_en,
          SUM(CASE WHEN COALESCE(a.lang, r.lang) NOT IN ('zh-CN','en')
                       OR COALESCE(a.lang, r.lang) IS NULL THEN 1 ELSE 0 END) AS lang_unknown
        FROM extracted_entities e
        LEFT JOIN articles      a ON e.source = 'wechat' AND a.id = e.article_id
        LEFT JOIN rss_articles  r ON e.source = 'rss'    AND r.id = e.article_id
        GROUP BY e.name
        HAVING total_count >= ?
        ORDER BY e.name ASC
    """
    return [
        {
            "name": row["name"],
            "slug": slugify_entity_name(row["name"]),
            "article_count": row["total_count"],
            "lang_zh": row["lang_zh"] or 0,
            "lang_en": row["lang_en"] or 0,
            "lang_unknown": row["lang_unknown"] or 0,
        }
        for row in conn.execute(sql, (min_freq,))
    ]


def _render_topic_pages(
    env: Environment,
    output_dir: Path,
    conn: sqlite3.Connection,
    lang: str = "zh-CN",
) -> int:
    """TOPIC-01 + TOPIC-03: render kb/output/topics/{slug}.html × 5.

    Returns count rendered (always 5; pages with zero qualifying articles emit
    the empty-state version per topic.html template). Idempotent.
    """
    tpl = env.get_template("topic.html")
    topics_dir = output_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for raw_topic in KB2_TOPICS:
        slug = TOPIC_SLUG_MAP[raw_topic]
        articles = topic_articles_query(raw_topic, depth_min=2, conn=conn)
        cooccurring = cooccurring_entities_in_topic(
            raw_topic,
            limit=5,
            min_global_freq=KB_ENTITY_MIN_FREQ,
            conn=conn,
        )
        topic_ctx = {
            "slug": slug,
            "raw_topic": raw_topic,
            "localized_name": i18n_t(f"topic.{slug}.name", lang),
            "localized_desc": i18n_t(f"topic.{slug}.desc", lang),
        }
        prepared = [_record_to_card_dict(rec) for rec in articles]
        page_url = f"/topics/{slug}.html"
        html = tpl.render(
            lang=lang,
            topic=topic_ctx,
            articles=prepared,
            cooccurring_entities=cooccurring,
            page_url=page_url,
            origin="",
        )
        _write_atomic(topics_dir / f"{slug}.html", html)
        count += 1
    return count


def _render_entity_pages(
    env: Environment,
    output_dir: Path,
    conn: sqlite3.Connection,
    qualifying: list[dict[str, Any]],
    lang: str = "zh-CN",
) -> int:
    """ENTITY-01 + ENTITY-03: render kb/output/entities/{slug}.html × N.

    `qualifying` is precomputed by _discover_qualifying_entities (avoid re-scan).
    Sorted by entity name ASC (already from query) for idempotent file order.
    """
    tpl = env.get_template("entity.html")
    entities_dir = output_dir / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for ent in qualifying:
        articles = entity_articles_query(
            ent["name"], min_freq=KB_ENTITY_MIN_FREQ, conn=conn
        )
        prepared = [_record_to_card_dict(rec) for rec in articles]
        page_url = f"/entities/{ent['slug']}.html"
        html = tpl.render(
            lang=lang,
            entity=ent,
            articles=prepared,
            page_url=page_url,
        )
        _write_atomic(entities_dir / f"{ent['slug']}.html", html)
        count += 1
    return count


def _ensure_lang_column(db_path: Path) -> None:
    """Pre-flight check: fail fast if articles.lang or rss_articles.lang are absent.

    The export driver hard-depends on the lang column (DATA-04 list_articles filters
    by it; templates emit `<html lang>` from it). If the migration was never run on
    this DB, list_articles raises an opaque sqlite3.OperationalError mid-loop. Catch
    it here and surface an operator-actionable error pointing at the migration +
    detection scripts.
    """
    import sqlite3

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        for table in ("articles", "rss_articles"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "lang" not in cols:
                raise SystemExit(
                    f"ERROR: '{table}.lang' column missing in {db_path}.\n"
                    f"Run the lang-column migration + detection first:\n"
                    f"  KB_DB_PATH={db_path} venv/Scripts/python.exe -m kb.scripts.migrate_lang_column\n"
                    f"  KB_DB_PATH={db_path} venv/Scripts/python.exe -m kb.scripts.detect_article_lang\n"
                    f"Both scripts are idempotent — safe to re-run."
                )


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

    # Pre-flight: fail fast with operator-actionable error if lang columns absent
    # (DATA-04 list_articles hard-depends on articles.lang + rss_articles.lang)
    _ensure_lang_column(config.KB_DB_PATH)

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

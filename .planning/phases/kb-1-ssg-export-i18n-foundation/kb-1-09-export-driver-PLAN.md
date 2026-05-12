---
phase: kb-1-ssg-export-i18n-foundation
plan: 09
type: execute
wave: 5
depends_on: ["kb-1-01-config-skeleton", "kb-1-03-i18n-locale", "kb-1-04-static-css-js", "kb-1-04b-brand-assets-checkpoint", "kb-1-05-detect-script-driver", "kb-1-06-article-query", "kb-1-07-base-template-pages", "kb-1-08-article-detail-template"]
files_modified:
  - kb/export_knowledge_base.py
  - tests/integration/kb/test_export.py
  - requirements-kb.txt
autonomous: true
requirements:
  - EXPORT-01
  - EXPORT-02
  - EXPORT-03
  - EXPORT-04
  - EXPORT-05
  - EXPORT-06
  - I18N-04
  - UI-04

must_haves:
  truths:
    - "Running `python kb/export_knowledge_base.py` produces a complete kb/output/ tree without writing to SQLite or to KB_IMAGES_DIR (EXPORT-02)"
    - "kb/output/index.html, kb/output/articles/index.html, kb/output/articles/{hash}.html (one per article), kb/output/ask/index.html all generated (EXPORT-03)"
    - "Article detail body is pre-rendered markdown→HTML with Pygments codehilite via markdown library (EXPORT-04)"
    - "All `http://localhost:8765/` URLs in body are rewritten to `/static/img/` BEFORE template render (EXPORT-05)"
    - "kb/output/sitemap.xml lists every article URL + 3 index pages with <lastmod> tags derived deterministically from input data (EXPORT-06)"
    - "kb/output/robots.txt: `User-agent: *` + `Sitemap: /sitemap.xml` (EXPORT-06)"
    - "kb/output/_url_index.json records {hash: article_id} mapping to detect URL drift (CONTEXT.md stability concern)"
    - "Re-running on unchanged DB produces byte-identical HTML AND sitemap.xml AND robots.txt AND _url_index.json (EXPORT-01 idempotency — every file under kb/output/)"
    - "kb/output/static/ contains style.css + lang.js + brand assets (UI-04)"
  artifacts:
    - path: "kb/export_knowledge_base.py"
      provides: "Single CLI entry point for SSG build"
      min_lines: 200
    - path: "kb/output/"
      provides: "Generated SSG tree (gitignored)"
  key_links:
    - from: "kb/export_knowledge_base.py"
      to: "kb.data.article_query (5 functions)"
      via: "from kb.data.article_query import list_articles, get_article_by_hash, resolve_url_hash, get_article_body, ArticleRecord"
      pattern: "from kb\\.data\\.article_query"
    - from: "kb/export_knowledge_base.py"
      to: "kb.i18n.register_jinja2_filter"
      via: "registers t() filter on Jinja2 env"
      pattern: "register_jinja2_filter"
    - from: "kb/export_knowledge_base.py"
      to: "markdown library + Pygments"
      via: "markdown.markdown(body, extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br'])"
      pattern: "markdown\\.markdown|codehilite"
---

<objective>
Build the single CLI entry point that wires every prior plan together: opens DB, lists articles, renders templates, writes HTML files, copies static assets, generates sitemap.xml + robots.txt + _url_index.json.

Purpose: This plan is the spine — without it, all prior plans produce orphaned artifacts. The driver MUST be read-only (EXPORT-02), idempotent (EXPORT-01 — including sitemap.xml and every other file in kb/output/), and complete (EXPORT-03/04/05/06). It also satisfies I18N-04's SSG-side filter (the JS in articles_index.html does the actual filtering — the driver just renders ALL articles into the page).

**Operator note (REVISION 1 — 2026-05-12):** DB path override goes through env var only — set `KB_DB_PATH=/path/to/db.sqlite python kb/export_knowledge_base.py`. The earlier `--db-path` argparse flag was non-functional (config.KB_DB_PATH is computed at module import, before argparse runs) and has been removed for honesty. Issue #3 fix.

Output: 1 Python CLI module + integration test + requirements-kb.txt for new deps.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT-KB-v2.md
@.planning/REQUIREMENTS-KB-v2.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-01-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-02-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-03-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-04-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-04b-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-05-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-06-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-07-SUMMARY.md
@.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-08-SUMMARY.md
@kb/config.py
@kb/data/article_query.py
@kb/i18n.py
@kb/templates/base.html
@kb/templates/article.html
@CLAUDE.md

<interfaces>
Already-built imports this script wires together:

```python
from kb import config
from kb.i18n import register_jinja2_filter
from kb.data.article_query import (
    ArticleRecord, list_articles, get_article_by_hash,
    resolve_url_hash, get_article_body,
)

# Markdown rendering pipeline (per CONTEXT.md "Markdown rendering"):
import markdown
md = markdown.Markdown(extensions=['fenced_code', 'codehilite', 'tables', 'toc', 'nl2br'])
body_html = md.convert(body_md)
md.reset()  # CRITICAL: codehilite holds state per-conversion; reset between articles
```

New deps to add to `requirements-kb.txt` (PROJECT-KB-v2.md "Tech Stack additions only"):

```
jinja2>=3.1
markdown>=3.5
pygments>=2.17
```

DO NOT add fastapi/uvicorn here — those are kb-3 deps.

Output structure (CONTEXT.md "Output verification at end of phase"):

```
kb/output/
├── index.html
├── robots.txt
├── sitemap.xml
├── _url_index.json
├── articles/
│   ├── index.html
│   ├── {hash1}.html
│   └── ...
├── ask/
│   └── index.html
└── static/
    ├── style.css
    ├── lang.js
    ├── VitaClaw-Logo-v0.png
    └── favicon.svg
```

CLI args (REVISION 1 — `--db-path` removed per Issue #3):
- `--output-dir PATH` (override config.KB_OUTPUT_DIR)
- `--limit N` (dev mode: render only first N articles for fast iteration)
- DB path override: env var `KB_DB_PATH=/path` only — NOT a CLI flag (would be a no-op since config.KB_DB_PATH is read at import time)

EXPORT-01 idempotency: same DB content → byte-identical output **for every file under `kb/output/`** including `sitemap.xml`, `robots.txt`, and `_url_index.json`. Achieve by:
- Sorting articles deterministically (already DESC by update_time)
- Using fixed Jinja2 autoescape settings
- NOT including timestamps in HTML output
- **Sitemap `<lastmod>` MUST be computed deterministically from input data, NEVER from `datetime.now()`** (REVISION 1 fix for Issue #1):
  - For the 3 index URLs (`/`, `/articles/`, `/ask/`): use `max(article.update_time[:10])` across all articles (most-recently-updated article's date) — empty/None update_times skipped from the max calculation
  - For article URLs: use `article.update_time[:10]` if non-empty, else the constant string `"1970-01-01"` (NOT `datetime.now()`) so missing-data rows stay stable across runs
  - If the article list is empty (edge case in tests), use `"1970-01-01"` for index URLs as well
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add markdown + jinja2 + pygments to requirements + verify install</name>
  <read_first>
    - .planning/PROJECT-KB-v2.md "Tech Stack (additions only)" section — lists exact deps + versions
    - requirements.txt (root — read existing entries to confirm jinja2 is NOT already pinned)
  </read_first>
  <files>requirements-kb.txt</files>
  <action>
    Create a NEW file `requirements-kb.txt` (do not modify root `requirements.txt` — KB-v2 is a parallel-track milestone with isolated deps to avoid impacting v3.5 / v3.4 work). Content:

    ```
    # KB-v2 milestone runtime deps (kb-1 + kb-3 + kb-4)
    # Add to existing project requirements.txt at deploy time:
    #   pip install -r requirements.txt -r requirements-kb.txt

    # kb-1 (SSG)
    jinja2>=3.1
    markdown>=3.5
    pygments>=2.17

    # kb-3 (FastAPI) — listed here so install order is unified
    fastapi>=0.110
    uvicorn[standard]>=0.27
    python-multipart>=0.0.6
    ```

    Then run `pip install -r requirements-kb.txt` to install all 6 deps. Verify:

    ```bash
    python -c "import jinja2, markdown, pygments; print(jinja2.__version__, markdown.__version__)"
    ```

    Do NOT modify the root `requirements.txt` per Surgical Changes principle.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pip install -r requirements-kb.txt 2>&amp;1 | tail -5 &amp;&amp; python -c "import jinja2, markdown, pygments; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `requirements-kb.txt` exists in repo root
    - Contains exact strings: `jinja2>=3.1`, `markdown>=3.5`, `pygments>=2.17`
    - `pip install -r requirements-kb.txt` exits 0
    - `python -c "import jinja2, markdown, pygments; print('OK')"` outputs `OK`
    - Root `requirements.txt` is UNCHANGED (verify via `git diff --name-only requirements.txt` = empty)
  </acceptance_criteria>
  <done>requirements-kb.txt created, deps installed, root requirements.txt untouched.</done>
</task>

<task type="auto">
  <name>Task 2: Write kb/export_knowledge_base.py — single CLI entry rendering all pages + sitemap + robots + url_index</name>
  <read_first>
    - kb/config.py + kb/i18n.py + kb/data/article_query.py + kb/templates/*.html (all prior outputs in this phase)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Module / file layout" + "Page set (EXPORT-03)" + "Markdown rendering" + "Web courtesy meta tags"
    - .planning/REQUIREMENTS-KB-v2.md EXPORT-01..06 (all 6 export REQs — verbatim wording)
  </read_first>
  <files>kb/export_knowledge_base.py</files>
  <action>
    Create `kb/export_knowledge_base.py` — the single CLI entry point. Use this exact structure:

    ```python
    """EXPORT-01..06: Single CLI entry point for KB-v2 SSG build.

    Reads SQLite + filesystem → Jinja2 templates → kb/output/ static HTML tree.

    EXPORT-02 invariant: never writes to SQLite or KB_IMAGES_DIR. Output goes
    only to KB_OUTPUT_DIR (default: kb/output/).

    EXPORT-01 invariant: re-running on unchanged DB produces byte-identical
    output for EVERY file under kb/output/ — including sitemap.xml. Sitemap
    <lastmod> values are derived from input data only; NEVER from wall clock.

    Usage:
        python kb/export_knowledge_base.py [--output-dir PATH] [--limit N]

    DB path override: env var only — `KB_DB_PATH=/path python kb/export_knowledge_base.py`.
    There is no `--db-path` CLI flag because config.KB_DB_PATH is bound at module
    import (before argparse runs) — a CLI flag would be silently ignored. Use the
    env var instead.
    """
    from __future__ import annotations

    import argparse
    import json
    import re
    import shutil
    import sys
    from pathlib import Path
    from typing import Any
    from xml.sax.saxutils import escape as xml_escape

    import markdown
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from kb import config
    from kb.data.article_query import (
        ArticleRecord,
        get_article_body,
        list_articles,
        resolve_url_hash,
    )
    from kb.i18n import register_jinja2_filter, validate_key_parity

    KB_ROOT = Path(__file__).parent
    TEMPLATES_DIR = KB_ROOT / "templates"
    STATIC_SOURCE_DIR = KB_ROOT / "static"

    # Markdown extensions (CONTEXT.md "Markdown rendering")
    MD_EXTENSIONS = ["fenced_code", "codehilite", "tables", "toc", "nl2br"]

    # EXPORT-01 idempotency: deterministic fallback for missing update_time.
    # NEVER use datetime.now() anywhere in this module — would break byte-equality
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
        """Convert markdown to HTML with Pygments codehilite. Reset state between calls."""
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
            "author": {"@type": "Organization", "name": "VitaClaw 企小勤"},
            "image": "/static/VitaClaw-Logo-v0.png",
        }


    def render_article_detail(env: Environment, rec: ArticleRecord, output_dir: Path) -> dict[str, Any]:
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


    def render_index_pages(env: Environment, articles: list[ArticleRecord], output_dir: Path) -> None:
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

        REVISION 1 / Issue #1: NEVER use datetime.now() — would break EXPORT-01.
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

        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for url, lastmod in urls:
            lines.append(
                f"  <url><loc>{xml_escape(url)}</loc>"
                f"<lastmod>{xml_escape(lastmod)}</lastmod></url>"
            )
        lines.append('</urlset>')
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
                print(f"WARN: hash collision {h}: existing id={seen[h]['id']} vs new id={entry['id']}", file=sys.stderr)
            else:
                seen[h] = entry
        # Pretty JSON for diff stability (idempotency for EXPORT-01)
        content = json.dumps(article_index, indent=2, sort_keys=True, ensure_ascii=False)
        _write_atomic(output_dir / "_url_index.json", content + "\n")


    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(
            description="KB-v2 SSG export. Override DB path with env: KB_DB_PATH=/path"
        )
        parser.add_argument("--output-dir", type=Path, default=None,
                            help="Override KB_OUTPUT_DIR")
        parser.add_argument("--limit", type=int, default=None,
                            help="Dev mode: render only first N articles")
        args = parser.parse_args(argv)

        output_dir: Path = args.output_dir or config.KB_OUTPUT_DIR

        # Validate i18n key parity at build time (fail-fast if locales drift)
        validate_key_parity()

        env = _build_env()

        print(f"Querying articles from {config.KB_DB_PATH}...")
        # list_articles: paginated; use a large limit to fetch all
        articles = list_articles(limit=10000, offset=0)
        if args.limit:
            articles = articles[:args.limit]
        print(f"Rendering {len(articles)} article detail pages...")

        article_index: list[dict] = []
        for i, rec in enumerate(articles):
            try:
                idx_entry = render_article_detail(env, rec, output_dir)
                article_index.append(idx_entry)
            except Exception as exc:
                print(f"ERROR rendering article id={rec.id} ({rec.source}): {exc}", file=sys.stderr)
                continue
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(articles)}")

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
    ```

    Verify EXPORT-02 enforcement at end of file: search the file body for `INSERT`, `UPDATE`, `DELETE`, `os.remove`, `Path(...).unlink`, `shutil.rmtree`. None should appear except inside template strings. (`shutil.copy2` for static asset copy is OK — that writes to OUTPUT, not to source data.)

    Verify EXPORT-01 enforcement (REVISION 1): the file body MUST NOT contain `datetime.now`. Sitemap lastmod values are derived from `articles[*].update_time` or the `_LASTMOD_FALLBACK` constant only.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "import ast; tree = ast.parse(open('kb/export_knowledge_base.py', encoding='utf-8').read()); print('Parse OK,', sum(1 for _ in ast.walk(tree)), 'nodes')"</automated>
  </verify>
  <acceptance_criteria>
    - `kb/export_knowledge_base.py` exists with line count ≥ 200
    - Parses as valid Python (verify command exits 0)
    - Contains all 5 import lines: `from kb import config`, `from kb.data.article_query import`, `from kb.i18n import`, `import markdown`, `from jinja2 import`
    - Contains exact strings: `validate_key_parity()`, `register_jinja2_filter`, `MD_EXTENSIONS`, `codehilite`, `_write_atomic`, `_LASTMOD_FALLBACK`, `_compute_index_lastmod`
    - REVISION 1 / Issue #1 — Idempotency enforcement: `grep -E "datetime\.now|datetime\.utcnow|time\.time\(" kb/export_knowledge_base.py` returns 0 hits (no wall-clock reads anywhere)
    - REVISION 1 / Issue #3 — `--db-path` argparse flag REMOVED: `python kb/export_knowledge_base.py --help` MUST NOT mention `--db-path`. Help text MUST mention `KB_DB_PATH` env var (in the description string).
    - REVISION 1 / Issue #6 — og:description fallback: `_build_og` body contains `len(description) < 20` check that falls back to `article_dict["title"]`
    - REVISION 1 / Issue #8 — `# TODO v2.1: env-overridable KB_HOME_LATEST_LIMIT` comment present near the `articles[:20]` slice in `render_index_pages`
    - Contains EXPORT-02 enforcement: zero `INSERT`/`UPDATE`/`DELETE` SQL strings — `grep -E "(INSERT INTO|UPDATE.*SET|DELETE FROM)" kb/export_knowledge_base.py` returns 0
    - Contains EXPORT-02 enforcement: no `Path(...).unlink` or `shutil.rmtree` — `grep -E "\.unlink\(|rmtree" kb/export_knowledge_base.py` returns 0
    - CLI flags: `python kb/export_knowledge_base.py --help` exits 0 and shows `--limit`, `--output-dir` flags (and ONLY these two; `--db-path` removed)
    - Generates `kb/output/sitemap.xml` containing literal string `<?xml version="1.0"`
    - Generates `kb/output/robots.txt` containing exact lines `User-agent: *`, `Sitemap: /sitemap.xml`
  </acceptance_criteria>
  <done>Export driver complete with all 6 EXPORT REQs implemented + I18N-04 SSG-side filter + idempotent atomic writes + sitemap deterministic build_date.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Integration test — run export against in-memory fixture DB and validate output structure</name>
  <read_first>
    - kb/export_knowledge_base.py (Task 2 output — the module under test)
    - .planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-CONTEXT.md "Output verification at end of phase"
    - .planning/REQUIREMENTS-KB-v2.md (all EXPORT REQs)
  </read_first>
  <files>tests/integration/kb/__init__.py, tests/integration/kb/test_export.py</files>
  <behavior>
    - Test 1: `main(['--output-dir', str(tmp_path)])` against a fixture DB with 3 articles (2 KOL with content_hash, 1 RSS) produces:
      - `tmp_path/index.html` exists and is valid HTML5 (starts with `<!DOCTYPE html>`)
      - `tmp_path/articles/index.html` exists
      - `tmp_path/articles/{hash1}.html`, `tmp_path/articles/{hash2}.html`, `tmp_path/articles/{hash3}.html` all exist
      - `tmp_path/ask/index.html` exists
      - `tmp_path/sitemap.xml` exists with 3 article URLs + 3 index URLs (= 6 `<url>` elements)
      - `tmp_path/robots.txt` exists with `User-agent: *` line
      - `tmp_path/_url_index.json` exists and is valid JSON listing all 3 hashes
      - `tmp_path/static/style.css` exists (copied from kb/static/)
    - Test 2: EXPORT-02 enforcement — after `main()` runs, the source DB is byte-identical to its pre-run state (md5 hash of DB file unchanged). Capture md5 before and after.
    - Test 3: EXPORT-05 — fixture article body containing `http://localhost:8765/path/img.png` produces detail HTML containing `/static/img/path/img.png` and NOT containing `localhost:8765`.
    - Test 4 (REVISION 1 / Issue #2 — recursive sha256 across ALL files): EXPORT-01 idempotency. Run `main()` twice into separate output dirs (`out1/` and `out2/`); walk every file under each dir recursively, assert (a) the relative file set is identical and (b) sha256 of each file matches its counterpart. This catches sitemap.xml / robots.txt / _url_index.json drift in addition to HTML files.
    - Test 5: Detail HTML contains all 5 mandatory I18N/UI elements: `<html lang="zh-CN">` OR `<html lang="en">` matching content lang, `class="lang-badge"` with localized label, `class="breadcrumb"`, `application/ld+json` script tag, `og:type` content `article`.
    - Test 6 (REVISION 1 / Issue #6): every article detail page's `<meta property="og:description" ...>` MUST have a non-empty content attribute. Build a fixture with at least one article whose body strips to <20 chars (e.g., body = `"![](http://localhost:8765/img.png)"` with no other text); the resulting og:description MUST equal the article title (fallback path), not empty.
  </behavior>
  <action>
    Create `tests/integration/kb/__init__.py` (empty) and `tests/integration/kb/test_export.py` exercising the 6 behaviors.

    Strategy:
    - Use `tmp_path` fixture for output dir + KB_IMAGES_DIR
    - Create a temp SQLite file with `articles` + `rss_articles` tables and 3 fixture rows (with at least one short-body row for Test 6)
    - Monkeypatch `kb.config.KB_DB_PATH` and `kb.config.KB_IMAGES_DIR` and `kb.config.KB_OUTPUT_DIR`
    - Use `importlib.reload(kb.config)` if needed to refresh module-level constants
    - Call `kb.export_knowledge_base.main(['--output-dir', str(tmp_path)])` directly (NO `--db-path` arg — it has been removed; DB path comes from monkeypatched config)

    Sample fixture row for EXPORT-05 test:

    ```python
    body_md = "# Test Article\n\nSome text\n\n![](http://localhost:8765/abc/img.png)\n\nMore text"
    # After export, articles/{hash}.html should contain `/static/img/abc/img.png`
    # and should NOT contain `localhost:8765`
    ```

    Test 4 (recursive sha256) reference implementation:

    ```python
    import hashlib

    def _sha256_file(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def test_export_idempotent(tmp_path, dev_db_fixture, monkeypatch):
        # ... monkeypatch KB_DB_PATH/KB_IMAGES_DIR/KB_OUTPUT_DIR to point at fixture ...
        out1 = tmp_path / "out1"
        out2 = tmp_path / "out2"
        from kb.export_knowledge_base import main
        main(["--output-dir", str(out1)])
        main(["--output-dir", str(out2)])
        files1 = sorted(p.relative_to(out1) for p in out1.rglob("*") if p.is_file())
        files2 = sorted(p.relative_to(out2) for p in out2.rglob("*") if p.is_file())
        assert files1 == files2, f"file sets differ: {set(files1) ^ set(files2)}"
        for rel in files1:
            h1 = _sha256_file(out1 / rel)
            h2 = _sha256_file(out2 / rel)
            assert h1 == h2, f"{rel} differs across runs (h1={h1}, h2={h2})"
    ```

    This recursive walk catches sitemap.xml, robots.txt, and _url_index.json drift in addition to HTML files. The original Test 4 only sha256-compared HTML files and would have passed even with Issue #1 (datetime.now() in sitemap) present.

    Use `pytest.mark.integration` marker per `.claude/rules/python/testing.md`.
  </action>
  <verify>
    <automated>cd C:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; pytest tests/integration/kb/test_export.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/integration/kb/test_export.py -v` exits 0 with 6 tests passing (5 originals + 1 new for Issue #6)
    - File contains string `pytest.mark.integration` (test categorization)
    - Test 2 explicitly asserts DB md5 unchanged — proves EXPORT-02
    - Test 3 explicitly greps `/static/img/` IN output AND `localhost:8765` NOT in output — proves EXPORT-05
    - Test 4 (REVISION 1 / Issue #2) uses `Path.rglob("*")` to enumerate ALL files under output dir AND uses `hashlib.sha256` to compare each file's bytes across two runs — proves EXPORT-01 covers EVERY file (sitemap.xml, robots.txt, _url_index.json, every HTML). Specifically: the test fails if you run two exports on different days and `sitemap.xml` byte-differs.
    - Test 6 (REVISION 1 / Issue #6) parses the rendered detail HTML for the short-body article, locates `<meta property="og:description" content="...">`, and asserts the content attribute is BOTH non-empty AND equals the article's title (since the body fallback path triggered).
    - Test invocation: `main(["--output-dir", str(tmp_path)])` only — NO `--db-path` arg appears anywhere in the test file (verifies Issue #3 fix surfaces in tests too).
    - Output of test 1 confirms all 5 mandatory output paths (index, articles/index, articles/{hash} ×3, ask/index, sitemap, robots, _url_index, static/style.css)
  </acceptance_criteria>
  <done>Integration test confirms end-to-end SSG build correctness; 6 tests pass. Test 4 catches sitemap/robots/_url_index drift via recursive sha256.</done>
</task>

</tasks>

<verification>
- `pytest tests/integration/kb/test_export.py -v` exits 0 (6 tests)
- `python kb/export_knowledge_base.py --help` exits 0 (CLI parses) and does NOT mention `--db-path`
- A real export against the dev DB (`KB_DB_PATH=data/kol_scan.db python kb/export_knowledge_base.py --limit 5`) produces a kb/output/ tree with 5 article HTMLs + index pages + sitemap + robots
- `grep "localhost:8765" kb/output/articles/*.html` returns 0 hits (EXPORT-05 verified post-build)
- `grep -E "datetime\.now|datetime\.utcnow|time\.time\(" kb/export_knowledge_base.py` returns 0 hits (EXPORT-01 idempotency invariant — no wall-clock reads)
</verification>

<success_criteria>
- EXPORT-01 satisfied: idempotent across EVERY file in kb/output/ (test 4 recursive sha256 proof; sitemap.xml lastmod values derived deterministically from input data)
- EXPORT-02 satisfied: read-only (test 2 md5 proof)
- EXPORT-03 satisfied: index.html + articles/{hash}.html (one per article) + ask/index.html generated
- EXPORT-04 satisfied: markdown→HTML with codehilite via markdown lib
- EXPORT-05 satisfied: localhost:8765 → /static/img rewrite (test 3 explicit)
- EXPORT-06 satisfied: sitemap.xml (with all URLs + lastmod) + robots.txt
- I18N-04 satisfied (SSG-side): articles_index.html JS-only filter consumes `?lang=` param against pre-rendered cards
- UI-04 satisfied: brand assets copied to output/static/
- All 6 integration tests pass (and earlier unit tests still passing)
- REVISION 1 hygiene: no `--db-path` CLI flag, no `datetime.now()` in source, og:description never empty, KB_HOME_LATEST_LIMIT TODO documented
</success_criteria>

<output>
After completion, create `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-09-SUMMARY.md` documenting:
- Final test counts (target 6 integration + all earlier unit tests still passing)
- A real-DB sanity run output (count of articles rendered, output dir size)
- EXPORT REQ enforcement proofs (md5-equality for EXPORT-02, recursive sha256-equality for EXPORT-01 covering sitemap.xml + robots.txt + _url_index.json + all HTML, grep negative for EXPORT-05, grep negative for `datetime.now` proving Issue #1 fix)
- Phase kb-1 goal-backward verification: all 8 ROADMAP "Phase kb-1 Success Criteria" met
</output>

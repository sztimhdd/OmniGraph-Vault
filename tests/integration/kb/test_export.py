"""Integration tests for kb/export_knowledge_base.py — full SSG pipeline.

Six tests covering EXPORT-01..06 + I18N/UI mandatory elements:

1. Output structure — every expected file under kb/output/ exists
2. EXPORT-02 read-only — DB md5 unchanged after export run
3. EXPORT-05 — `http://localhost:8765/` rewritten to `/static/img/`
4. EXPORT-01 idempotency — recursive sha256 across ALL output files identical
   between two runs (catches sitemap/robots/_url_index drift)
5. I18N/UI mandatory elements — `<html lang>`, lang-badge, breadcrumb,
   JSON-LD, og:type=article all present in detail HTML
6. og:description fallback — short body falls back to title (REVISION 1 / Issue #6)
"""
from __future__ import annotations

import hashlib
import importlib
import re
import sqlite3
from pathlib import Path

import pytest


# Reusable fixture body: Test 3 — explicit localhost:8765 reference for EXPORT-05
_BODY_WITH_LOCALHOST = (
    "# Test Article One\n\n"
    "Some leading paragraph with enough words to be a reasonable description "
    "for OG meta extraction so the fallback path does not trigger.\n\n"
    "![local image](http://localhost:8765/abc/img.png)\n\n"
    "More body text after the image with additional content to ensure the "
    "200-character description has plenty to work with."
)

# Test 6 — short body to exercise og:description fallback
_BODY_SHORT_FOR_OG_FALLBACK = "![](http://localhost:8765/img.png)"

# Plain English body for the third article
_BODY_EN_PLAIN = (
    "# English Article Three\n\n"
    "This is an English-language article about agent technology and tooling. "
    "It contains a meaningful chunk of prose suitable for og:description "
    "extraction in the SSG export pipeline tests."
)


def _md5_file(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def fixture_db(tmp_path: Path) -> Path:
    """Build a SQLite DB with kb_v2 schema (articles + rss_articles, both
    with `lang` column populated) and 3 fixture articles + 1 short-body row."""
    db_path = tmp_path / "fixture.db"
    conn = sqlite3.connect(db_path)
    try:
        # Minimal schema mirroring kb-1-02 post-migration shape (articles +
        # rss_articles both have nullable `lang` column).
        conn.executescript(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                body TEXT,
                content_hash TEXT,
                lang TEXT,
                update_time TEXT
            );
            CREATE TABLE rss_articles (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                body TEXT,
                content_hash TEXT,
                lang TEXT,
                published_at TEXT,
                fetched_at TEXT
            );
            """
        )
        # Article 1 — KOL with content_hash, zh-CN, body has localhost:8765 (Test 3)
        conn.execute(
            "INSERT INTO articles (id, title, url, body, content_hash, lang, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "测试文章一",
                "https://mp.weixin.qq.com/s/test1",
                _BODY_WITH_LOCALHOST,
                "abc1234567",  # 10-char content_hash (KOL form)
                "zh-CN",
                "2026-05-12 10:00:00",
            ),
        )
        # Article 2 — KOL with NULL content_hash, en, short body (Test 6 og fallback)
        conn.execute(
            "INSERT INTO articles (id, title, url, body, content_hash, lang, update_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                2,
                "Image Only Post Title For Fallback",
                "https://mp.weixin.qq.com/s/test2",
                _BODY_SHORT_FOR_OG_FALLBACK,
                None,  # forces md5(body)[:10] runtime fallback
                "en",
                "2026-05-11 09:00:00",
            ),
        )
        # Article 3 — RSS with full md5 content_hash, en, longer body
        conn.execute(
            "INSERT INTO rss_articles (id, title, url, body, content_hash, lang, "
            "published_at, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                10,
                "English Article Three",
                "https://example.com/article-three",
                _BODY_EN_PLAIN,
                # 32-char full md5 (RSS form); will be truncated to 10 chars
                "deadbeefcafebabe1234567890abcdef",
                "en",
                "2026-05-10 08:00:00",
                "2026-05-10 08:01:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.fixture
def export_module(fixture_db: Path, tmp_path: Path, monkeypatch):
    """Reload kb.config + kb modules with KB_DB_PATH pointing at fixture DB.

    Returns the freshly-reloaded `kb.export_knowledge_base` module.
    """
    monkeypatch.setenv("KB_DB_PATH", str(fixture_db))
    # KB_IMAGES_DIR pointed at an empty tmpdir so D-14 fallback skips the
    # filesystem branch and uses rec.body. (No vision-enriched fixtures here.)
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    monkeypatch.setenv("KB_IMAGES_DIR", str(images_dir))

    import kb.config
    import kb.data.article_query
    import kb.export_knowledge_base
    import kb.i18n

    importlib.reload(kb.config)
    importlib.reload(kb.i18n)
    importlib.reload(kb.data.article_query)
    importlib.reload(kb.export_knowledge_base)
    return kb.export_knowledge_base


@pytest.mark.integration
def test_export_produces_expected_output_tree(
    export_module, tmp_path: Path, fixture_db: Path
) -> None:
    """Test 1: every expected file under kb/output/ exists with valid content."""
    out = tmp_path / "out"
    rc = export_module.main(["--output-dir", str(out)])
    assert rc == 0

    # Index pages
    assert (out / "index.html").exists()
    assert (out / "articles" / "index.html").exists()
    assert (out / "ask" / "index.html").exists()

    # Top-of-file is HTML5 doctype on the homepage
    assert (out / "index.html").read_text(encoding="utf-8").lstrip().startswith(
        "<!DOCTYPE html>"
    )

    # 3 article detail pages exist (we don't know hashes upfront, so count files)
    detail_files = sorted(
        p.name for p in (out / "articles").iterdir()
        if p.is_file() and p.name != "index.html" and p.suffix == ".html"
    )
    assert len(detail_files) == 3, f"expected 3 detail HTMLs, got {detail_files}"

    # Sitemap, robots, _url_index
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert sitemap.startswith('<?xml version="1.0"')
    # 6 <url> elements: 3 index URLs + 3 article URLs
    assert sitemap.count("<url>") == 6, f"expected 6 <url> blocks, got {sitemap.count('<url>')}"

    robots = (out / "robots.txt").read_text(encoding="utf-8")
    assert "User-agent: *" in robots
    assert "Sitemap: /sitemap.xml" in robots

    url_index_text = (out / "_url_index.json").read_text(encoding="utf-8")
    import json as _json

    url_index = _json.loads(url_index_text)
    assert len(url_index) == 3
    hashes = sorted(e["hash"] for e in url_index)
    # 'abc1234567' is KOL Article 1's exact content_hash (already 10 chars)
    assert "abc1234567" in hashes
    # 'deadbeefca' is RSS Article 3's truncated md5
    assert "deadbeefca" in hashes

    # Static assets copied
    assert (out / "static" / "style.css").exists()
    assert (out / "static" / "lang.js").exists()


@pytest.mark.integration
def test_export_is_read_only_db(export_module, tmp_path: Path, fixture_db: Path) -> None:
    """Test 2 — EXPORT-02: source DB md5 byte-identical before and after."""
    pre = _md5_file(fixture_db)
    out = tmp_path / "out"
    rc = export_module.main(["--output-dir", str(out)])
    assert rc == 0
    post = _md5_file(fixture_db)
    assert pre == post, f"DB mutated by export run: pre={pre} post={post} (EXPORT-02 violated)"


@pytest.mark.integration
def test_export_rewrites_localhost_image_url(
    export_module, tmp_path: Path, fixture_db: Path
) -> None:
    """Test 3 — EXPORT-05: localhost:8765 -> /static/img/ in detail HTML."""
    out = tmp_path / "out"
    export_module.main(["--output-dir", str(out)])

    # Find Article 1's detail HTML by content_hash 'abc1234567'
    detail = (out / "articles" / "abc1234567.html").read_text(encoding="utf-8")

    # Positive: rewritten path present
    assert "/static/img/abc/img.png" in detail, "rewritten /static/img/ path missing"
    # Negative: original localhost ref must be ABSENT
    assert "localhost:8765" not in detail, "EXPORT-05 violated — localhost:8765 leaked into output"


@pytest.mark.integration
def test_export_idempotent_recursive_sha256(
    export_module, tmp_path: Path, fixture_db: Path
) -> None:
    """Test 4 — EXPORT-01: recursive sha256 across ALL files matches across runs.

    REVISION 1 / Issue #2: walk every file under output dir and compare
    sha256s. Catches sitemap.xml / robots.txt / _url_index.json drift in
    addition to HTML. Specifically: fails if datetime.now() leaks into any
    output (sitemap lastmod was the original Issue #1).
    """
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    rc1 = export_module.main(["--output-dir", str(out1)])
    rc2 = export_module.main(["--output-dir", str(out2)])
    assert rc1 == 0 and rc2 == 0

    files1 = sorted(p.relative_to(out1) for p in out1.rglob("*") if p.is_file())
    files2 = sorted(p.relative_to(out2) for p in out2.rglob("*") if p.is_file())
    assert files1 == files2, (
        f"file sets differ across runs: {set(map(str, files1)) ^ set(map(str, files2))}"
    )

    diffs: list[str] = []
    for rel in files1:
        h1 = _sha256_file(out1 / rel)
        h2 = _sha256_file(out2 / rel)
        if h1 != h2:
            diffs.append(f"{rel}: h1={h1[:8]} h2={h2[:8]}")
    assert not diffs, "EXPORT-01 idempotency violated:\n" + "\n".join(diffs)


@pytest.mark.integration
def test_detail_html_has_mandatory_i18n_ui_elements(
    export_module, tmp_path: Path, fixture_db: Path
) -> None:
    """Test 5: detail HTML carries every mandatory I18N/UI element."""
    out = tmp_path / "out"
    export_module.main(["--output-dir", str(out)])

    # zh-CN article 1
    zh_html = (out / "articles" / "abc1234567.html").read_text(encoding="utf-8")
    assert '<html lang="zh-CN"' in zh_html, "zh-CN article missing <html lang='zh-CN'>"
    assert 'class="lang-badge"' in zh_html, "lang-badge missing"
    assert 'class="breadcrumb"' in zh_html, "breadcrumb missing"
    assert 'application/ld+json' in zh_html, "JSON-LD script tag missing"
    assert '"og:type" content="article"' in zh_html, "og:type=article missing"

    # en article 3 — verify <html lang="en"> for content-lang axis
    en_html = (out / "articles" / "deadbeefca.html").read_text(encoding="utf-8")
    assert '<html lang="en"' in en_html, "en article missing <html lang='en'>"


@pytest.mark.integration
def test_og_description_fallback_to_title_for_short_body(
    export_module, tmp_path: Path, fixture_db: Path
) -> None:
    """Test 6 — REVISION 1 / Issue #6: og:description fallback to title.

    Article 2 body is `![](http://localhost:8765/img.png)` which after HTML
    rendering + tag-strip yields <20 chars. The exporter MUST fall back to
    the article title for og:description.
    """
    out = tmp_path / "out"
    export_module.main(["--output-dir", str(out)])

    # Compute the runtime-fallback hash for Article 2 (body-md5[:10])
    # Use the same body the fixture inserted; the exporter does identical md5.
    expected_hash = hashlib.md5(_BODY_SHORT_FOR_OG_FALLBACK.encode("utf-8")).hexdigest()[:10]
    detail_path = out / "articles" / f"{expected_hash}.html"
    assert detail_path.exists(), f"Article 2 detail HTML not at {detail_path}"
    detail = detail_path.read_text(encoding="utf-8")

    # Find og:description content attribute
    m = re.search(r'<meta property="og:description" content="([^"]*)"', detail)
    assert m, "og:description meta tag not found in detail HTML"
    og_desc = m.group(1)
    assert og_desc, "og:description content is empty"
    # Fallback path must produce article TITLE
    assert og_desc == "Image Only Post Title For Fallback", (
        f"og:description fallback expected article title, got: {og_desc!r}"
    )

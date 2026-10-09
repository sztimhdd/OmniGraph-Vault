"""Local archive reads are independent of processing and public acceptance."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vitax.api import create_app, main
from vitax.knowledge import KnowledgeError, build
from tests.unit.test_vitax_api import _projection


def mirror(root: Path, snapshot_id="one", suffix=""):
    root.mkdir()
    database = root / "articles.sqlite"
    with sqlite3.connect(database) as conn:
        for table, captured in (("articles", "scanned_at"), ("rss_articles", "fetched_at")):
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, title_translated TEXT, body_translated TEXT, body_rewritten TEXT, translated_lang TEXT, lang TEXT, {captured} TEXT, layer2_verdict TEXT)")
        conn.executemany("INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
            (i, f"文章{i}{suffix}", "https://example.test/article", f"LIBRARY_SENTINEL原文{i}{suffix}", None, "已有译文" if i == 1 else None, "整理稿1" if i == 1 else None, "zh", "en", "2026-10-02 01:00:00", "reject")
            for i in range(1, 103)
        ])
        conn.execute("INSERT INTO rss_articles VALUES (1,'RSS','https://example.test/rss','独立RSS原文',NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
        conn.execute("INSERT INTO rss_articles VALUES (2,'缺正文','https://example.test/empty',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
    receipt = root / "receipt.json"
    receipt.write_text(json.dumps({"schema_version": 1, "snapshot_id": snapshot_id, "sqlite_sha256": hashlib.sha256(database.read_bytes()).hexdigest(), "observed_at": "2026-10-02T01:00:00Z"}))
    return database, receipt


def test_archive_covers_unprocessed_rows_and_stable_paging(tmp_path):
    from vitax.local_articles import list_local_articles, read_local_article
    database, _ = mirror(tmp_path / "mirror")
    original = database.read_bytes()
    first = list_local_articles(database, limit=100)
    second = list_local_articles(database, limit=100, offset=first["next_offset"])
    assert len(first["items"]) == 100 and len(second["items"]) == 4
    identities = {(x["source"], x["record_id"]) for x in first["items"] + second["items"]}
    assert len(identities) == 104 and ("wechat", 1) in identities and ("rss", 1) in identities
    assert second["next_offset"] is None
    assert "LIBRARY_SENTINEL" not in json.dumps(first)
    assert read_local_article(database, "wechat", 1)["body_translated"] == "已有译文"
    assert read_local_article(database, "rss", 1)["body"] == "独立RSS原文"
    assert read_local_article(database, "rss", 2)["body_available"] is False
    assert len(list_local_articles(database, q="译文", source="wechat")["items"]) == 1
    assert list_local_articles(database, q="' OR 1=1 --")["items"] == []
    for kwargs in ({"limit": True}, {"offset": -1}, {"source": "../articles"}, {"q": "x" * 513}):
        with pytest.raises(KnowledgeError):
            list_local_articles(database, **kwargs)
    assert database.read_bytes() == original


def test_private_only_http_peer_and_public_boundary(tmp_path):
    database, receipt = mirror(tmp_path / "mirror")
    app = create_app(local_articles_database=database, local_articles_receipt=receipt)
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get("/api/capabilities").json() == {"public_knowledge": False, "local_articles": True}
        assert client.get("/api/library/status").json()["counts"]["wechat"]["total"] == 102
        assert client.get("/api/library").json()["snapshot_id"] == "one"
        assert client.get("/api/library/wechat/1").json()["body"].startswith("LIBRARY_SENTINEL")
        assert client.get("/api/library/wechat/999").status_code == 404
        assert client.get("/api/release").status_code == 404
        assert client.get("/mcp/").status_code == 404
    with TestClient(app, client=("198.51.100.1", 12345)) as remote:
        assert remote.get("/api/library", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403
    public = tmp_path / "public.sqlite"
    build(_projection(), public)
    with TestClient(create_app(public)) as client:
        assert client.get("/api/library").status_code == 404
        assert client.get("/api/capabilities").json()["local_articles"] is False
        assert "LIBRARY_SENTINEL" not in client.get("/api/knowledge").text
    assert "LIBRARY_SENTINEL".encode() not in public.read_bytes()
    with pytest.raises(KnowledgeError):
        create_app(local_articles_database=database)
    assert main(["--host", "0.0.0.0", "--local-articles-db", str(database), "--local-articles-receipt", str(receipt)]) == 2


def test_cloud_reader_opt_in_serves_remote_articles_and_can_disable_mcp(tmp_path):
    database, receipt = mirror(tmp_path / "mirror")
    public = tmp_path / "public.sqlite"
    build(_projection(), public)
    cloud = create_app(public, local_articles_database=database, local_articles_receipt=receipt, allow_remote_articles=True, mount_mcp=False)
    with TestClient(cloud, client=("198.51.100.1", 12345)) as remote:
        assert remote.get("/api/library").json()["snapshot_id"] == "one"
        assert remote.get("/api/library/wechat/1").json()["body"].startswith("LIBRARY_SENTINEL")
        assert remote.get("/api/knowledge").status_code == 200
        assert remote.get("/api/unknown").status_code == 404
        assert remote.get("/mcp/").status_code == 404
    default = create_app(public, local_articles_database=database, local_articles_receipt=receipt)
    with TestClient(default, client=("198.51.100.1", 12345)) as remote:
        assert remote.get("/api/library", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403


def test_snapshot_promotion_and_inplace_change_fail_closed(tmp_path):
    first_db, first_receipt = mirror(tmp_path / "one")
    second_db, second_receipt = mirror(tmp_path / "two", "two", "新版")
    current = tmp_path / "current"
    current.symlink_to(first_db.parent, target_is_directory=True)
    app = create_app(local_articles_database=current / first_db.name, local_articles_receipt=current / first_receipt.name)
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get("/api/library").json()["snapshot_id"] == "one"
        replacement = tmp_path / "replacement"
        replacement.symlink_to(second_db.parent, target_is_directory=True)
        replacement.replace(current)
        assert client.get("/api/library/wechat/1").json()["snapshot_id"] == "two"
        with sqlite3.connect(second_db) as conn:
            conn.execute("UPDATE articles SET body='changed' WHERE id=1")
        response = client.get("/api/library/wechat/1")
        assert response.status_code == 409 and response.json()["error"] == "snapshot_changed"


def test_uncheckpointed_wal_cannot_return_new_data_with_old_snapshot(tmp_path):
    database, receipt = mirror(tmp_path / "wal")
    writer = sqlite3.connect(database)
    writer.execute("PRAGMA journal_mode=WAL")
    metadata = json.loads(receipt.read_text())
    metadata["sqlite_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(metadata))
    app = create_app(local_articles_database=database, local_articles_receipt=receipt)
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get("/api/library/wechat/1").status_code == 200
        writer.execute("UPDATE articles SET body='new WAL value' WHERE id=1")
        writer.commit()
        assert hashlib.sha256(database.read_bytes()).hexdigest() == metadata["sqlite_sha256"]
        assert client.get("/api/library/wechat/1").status_code == 409
    writer.close()


def test_normal_article_filter_excludes_empty_body_and_keeps_full_archive(tmp_path):
    from vitax.local_articles import list_local_articles
    database,receipt=mirror(tmp_path/'mirror')
    all_items=list_local_articles(database,source='rss')['items']
    normal=list_local_articles(database,source='rss',has_body=True)['items']
    assert len(all_items)==2 and len(normal)==1
    assert all(item['body_available'] for item in normal)
    with TestClient(create_app(local_articles_database=database,local_articles_receipt=receipt),client=('127.0.0.1',12345)) as client:
        page=client.get('/api/library?source=rss&has_body=true').json()
        assert len(page['items'])==1


def test_rendered_articles_keep_code_tables_and_links_but_drop_unsafe_html():
    from vitax.local_articles import render_body
    html = render_body(
        '# 标题\n\n<script>alert(1)</script>\n\n'
        '[坏](javascript:alert(1)) [好](https://example.test/a_(b))。\n\n'
        '`<div>`\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\n'
        '```python\nprint("TLA")\n```\n\n裸链接 https://example.test/Foo_(bar)。\n'
    )
    assert render_body('   ') is None
    assert 'alert(1)' not in html and 'javascript:' not in html and '<script' not in html
    assert '&lt;div&gt;' in html
    assert '<table>' in html and '<th>a</th>' in html
    assert 'codehilite' in html
    assert 'href="https://example.test/a_(b)"' in html
    assert 'href="https://example.test/Foo_(bar)"' in html
    assert 'target="_blank"' in html
    assert 'src="/static/img/abc/0.jpg"' in render_body('![x](http://localhost:8765/abc/0.jpg)')


def test_images_mount_is_explicit_and_blocks_traversal(tmp_path):
    database, receipt = mirror(tmp_path / "mirror")
    images = tmp_path / "images"
    (images / "abc").mkdir(parents=True)
    (images / "abc" / "0.jpg").write_bytes(b"JPEGDATA")
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")
    with TestClient(create_app(local_articles_database=database, local_articles_receipt=receipt), client=("127.0.0.1", 12345)) as client:
        assert client.get("/static/img/abc/0.jpg").status_code == 404
    app = create_app(local_articles_database=database, local_articles_receipt=receipt, images_dir=images)
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get("/static/img/abc/0.jpg").content == b"JPEGDATA"
        assert client.get("/static/img/..%2Fsecret.txt").status_code == 404
        assert "SECRET" not in client.get("/static/img/..%2Fsecret.txt").text
    with pytest.raises(KnowledgeError):
        create_app(local_articles_database=database, local_articles_receipt=receipt, images_dir=tmp_path / "missing")


def test_library_detail_exposes_reading_views_and_rewrite_status(tmp_path):
    database, receipt = mirror(tmp_path / "mirror")
    with TestClient(create_app(local_articles_database=database, local_articles_receipt=receipt), client=("127.0.0.1", 12345)) as client:
        item = client.get('/api/library/wechat/1').json()
        assert item['rewrite_available'] is True and item['body_rewritten'] == '整理稿1'
        assert item['body_html'].startswith('<p>LIBRARY_SENTINEL原文1')
        assert item['body_rewritten_html'].startswith('<p>整理稿1')
        listing = client.get('/api/library?source=rss&has_body=true').json()
        assert listing['items'][0]['rewrite_available'] is False
    from vitax.local_articles import local_article_counts
    assert local_article_counts(database)['wechat']['with_rewrite'] == 1


def test_search_ignores_matches_that_only_appear_inside_urls(tmp_path):
    root = tmp_path / "urlonly"
    root.mkdir()
    database = root / "articles.sqlite"
    with sqlite3.connect(database) as conn:
        for table, captured in (("articles", "scanned_at"), ("rss_articles", "fetched_at")):
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, title_translated TEXT, body_translated TEXT, body_rewritten TEXT, translated_lang TEXT, lang TEXT, {captured} TEXT, layer2_verdict TEXT)")
        conn.execute("INSERT INTO rss_articles VALUES (1,'ELF','https://x','see https://gitlab.com/acme/tla-tool for details',NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
        conn.execute("INSERT INTO rss_articles VALUES (2,'TLA 说明','https://y','TLA is explained here',NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
    from vitax.local_articles import list_local_articles
    assert [item['title'] for item in list_local_articles(database, q='tla', source='rss')['items']] == ['TLA 说明']
    assert list_local_articles(database, q='gitlab.com/acme')['items'] == []
    assert len(list_local_articles(database, source='rss')['items']) == 2


def test_legacy_mirror_without_rewrite_column_still_reads(tmp_path):
    """Older exported mirrors predate body_rewritten and must read as 'no 整理稿'."""
    root = tmp_path / "legacy"
    root.mkdir()
    database = root / "articles.sqlite"
    with sqlite3.connect(database) as conn:
        for table, captured in (("articles", "scanned_at"), ("rss_articles", "fetched_at")):
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, title TEXT, url TEXT, body TEXT, title_translated TEXT, body_translated TEXT, translated_lang TEXT, lang TEXT, {captured} TEXT, layer2_verdict TEXT)")
        conn.execute("INSERT INTO articles VALUES (1,'旧库','https://example.test/a','LEGACY原文',NULL,'LEGACY译文','zh','en','2026-10-02 01:00:00','reject')")
        conn.execute("INSERT INTO rss_articles VALUES (1,'RSS','https://example.test/r','LEGACY RSS',NULL,NULL,NULL,NULL,NULL,NULL)")
    receipt = root / "receipt.json"
    receipt.write_text(json.dumps({"schema_version": 1, "snapshot_id": "legacy", "sqlite_sha256": hashlib.sha256(database.read_bytes()).hexdigest(), "observed_at": "2026-10-02T01:00:00Z"}))
    with TestClient(create_app(local_articles_database=database, local_articles_receipt=receipt), client=("127.0.0.1", 12345)) as client:
        assert client.get("/api/library/status").json()["counts"]["wechat"]["with_rewrite"] == 0
        page = client.get("/api/library").json()
        assert page["items"] and all(item["rewrite_available"] is False for item in page["items"])
        detail = client.get("/api/library/wechat/1").json()
        assert detail["body_rewritten"] is None and detail["body_rewritten_html"] is None
        assert detail["body_html"].startswith("<p>LEGACY原文")
        assert client.get("/api/library", params={"q": "LEGACY译文"}).json()["items"]
        assert client.get("/api/library", params={"q": "不存在的词"}).json()["items"] == []


def test_safe_html_closes_only_the_nearest_matching_ancestor():
    from vitax.local_articles import render_body
    # Legal nested tables must stay inside the outer cell; code and trailing
    # content must stay inside their enclosing divs after the inner div closes.
    text = ('<div><div><pre><code>&lt;div&gt; nested code</code></pre></div>'
            '<table><tr><td>outer<table><tr><td>inner</td></tr></table>'
            'after inner</td></tr></table>after table</div>')
    assert render_body(text) == text


def test_display_match_uses_english_boundaries_and_literal_chinese():
    from vitax.local_articles import _display_match, SEARCH_FIELDS

    def matches(text, query):
        row = dict.fromkeys(SEARCH_FIELDS)
        row['body'] = text
        return _display_match(row, query.lower())

    assert not matches('GitLab atlas installation TLAtool', 'TLA')
    assert not matches('[GitLab](https://gitlab.com/tla)', 'TLA')
    assert matches('中文TLA+说明', 'TLA')
    assert matches('TLA+ specification', 'TLA+')
    assert not matches('TLA alone', 'TLA+')
    assert matches('GitLab repository', 'GitLab')
    assert matches('用C++写代码', 'C++')
    assert matches('研究上下文工程', '上下文')
    assert not matches('研究上下游工程', '上下文')


def test_render_relative_urls_against_source_and_keep_local_media_and_anchors():
    from vitax.local_articles import render_body
    body = ('[tools](/2025/7/3/tools/) ![remote](../image.png) '
            '[local](#section) ![media](/static/img/hash/file.jpg) '
            '[bad](javascript:alert(1)) ![bad](file:///tmp/file)')
    html = render_body(body, 'https://example.test/2025/7/4/article/')
    assert 'href="https://example.test/2025/7/3/tools/"' in html
    assert 'src="https://example.test/2025/7/4/image.png"' in html
    assert 'href="#section"' in html
    assert 'src="/static/img/hash/file.jpg"' in html
    assert 'javascript:' not in html and 'file:' not in html
    assert 'href="/2025/7/3/tools/"' not in render_body(body, 'file:///tmp/article')
    assert 'src="../image.png"' not in render_body(body, 'javascript:alert(1)')

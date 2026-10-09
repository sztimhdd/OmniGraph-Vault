"""Inventory must distinguish revisions and never expose source text."""
import json
import sqlite3


def test_inventory_keeps_revisions_and_excludes_unproven_rewrites(tmp_path):
    from scripts.audit_vitax_content import audit_content
    database = tmp_path / 'source.sqlite'
    with sqlite3.connect(database) as conn:
        for table in ('articles', 'rss_articles'):
            conn.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY,url TEXT,body TEXT,body_translated TEXT,translated_lang TEXT,lang TEXT,layer2_verdict TEXT,body_rewritten TEXT)')
        conn.executemany('INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)', [
            (1, 'https://example.test/a#one', 'PRIVATE_SOURCE 42', 'PRIVATE_TRANSLATION 42', 'en', 'zh-CN', 'ok', 'PRIVATE_REWRITE'),
            (2, 'https://example.test/a#two', 'PRIVATE_SOURCE 42', None, None, 'zh-CN', 'ok', None),
            (3, 'https://example.test/a', 'DIFFERENT_REVISION 43', None, None, None, 'ok', None),
            (4, 'https://example.test/missing', None, 'ORPHAN_TRANSLATION', 'en', None, 'ok', None),
        ])
        conn.execute("INSERT INTO rss_articles VALUES (1,'https://example.test/rss','ENGLISH_BODY',NULL,NULL,'en','ok',NULL)")
    before = database.read_bytes()
    report = audit_content(database)
    assert report['counts']['records'] == 5
    assert report['counts']['source_revisions'] == 4
    assert report['counts']['translation_without_original'] == 1
    assert report['counts']['eligible_english_rss_missing_chinese'] == 1
    assert report['rows'][0]['source_revision'] == report['rows'][1]['source_revision']
    assert report['rows'][0]['source_revision'] != report['rows'][2]['source_revision']
    assert report['rows'][0]['rewrite']['reuse'] == 'excluded_missing_revision_and_recipe_receipt'
    assert 'PRIVATE_' not in json.dumps(report) and 'ORPHAN_TRANSLATION' not in json.dumps(report)
    assert database.read_bytes() == before


def test_inventory_reports_missing_columns_and_asset_gaps(tmp_path):
    from scripts.audit_vitax_content import audit_content
    database = tmp_path / 'source.sqlite'
    assets = tmp_path / 'images'
    assets.mkdir()
    (assets / 'exists.jpg').write_bytes(b'image')
    with sqlite3.connect(database) as conn:
        for table in ('articles', 'rss_articles'):
            conn.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY,url TEXT,body TEXT)')
        conn.execute("INSERT INTO articles VALUES (1,'https://example.test/a','![a](http://localhost:8765/exists.jpg) ![b](http://localhost:8765/missing.jpg) ![c](http://localhost:8765/../outside.jpg)')")
    report = audit_content(database, assets)
    row = report['rows'][0]
    assert row['translation']['status'] == 'not_exported'
    assert row['rewrite']['status'] == 'not_exported'
    assert row['assets'] == {'legacy_references': 3, 'present': 1, 'missing': 1, 'outside_root': 1, 'uncheckable': 0}
    assert row['language'] == 'unknown'


def test_markdown_image_url_stops_before_adjacent_prose(tmp_path):
    from scripts.audit_vitax_content import audit_content
    database = tmp_path / 'source.sqlite'
    assets = tmp_path / 'images'
    assets.mkdir()
    (assets / 'one.jpg').write_bytes(b'image')
    with sqlite3.connect(database) as conn:
        for table in ('articles', 'rss_articles'):
            conn.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY,url TEXT,body TEXT)')
        text = '![图](http://localhost:8765/one.jpg)' + '后续正文' * 100
        conn.execute('INSERT INTO articles VALUES (1,?,?)', ('https://example.test/a', text))
    assert audit_content(database, assets)['rows'][0]['assets']['present'] == 1

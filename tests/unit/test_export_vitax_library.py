"""Complete private snapshots promote as one verified directory."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from tests.unit.test_vitax_local_articles import mirror
from vitax.api import create_app


def test_complete_export_promotes_all_history_and_keeps_old_on_invalid_input(tmp_path):
    from scripts.export_vitax_library import export_library, promote_library
    source, _ = mirror(tmp_path / 'source')
    target = tmp_path / 'snapshots' / 'one'
    source_before = source.read_bytes()
    receipt = export_library(source, target)
    assert receipt['counts']['wechat']['total'] == 102
    assert receipt['counts']['rss']['total'] == 2
    assert source.read_bytes() == source_before
    current = tmp_path / 'current'
    promote_library(target, current)
    app = create_app(local_articles_database=current/'articles.sqlite', local_articles_receipt=current/'receipt.json')
    with TestClient(app, client=('127.0.0.1',1)) as client:
        first = client.get('/api/library/wechat/1').json()
        assert first['body'] == 'LIBRARY_SENTINEL原文1'
        with sqlite3.connect(source) as conn:
            conn.execute("UPDATE articles SET body='a later real original' WHERE id=1")
        second = tmp_path / 'snapshots' / 'two'
        export_library(source, second)
        promote_library(second, current)
        newer = client.get('/api/library/wechat/1').json()
        assert newer['body'] == 'a later real original' and newer['snapshot_id'] != first['snapshot_id']
        metadata = json.loads((target/'receipt.json').read_text())
        metadata['sqlite_sha256'] = '0'*64
        (target/'receipt.json').write_text(json.dumps(metadata))
        with pytest.raises(ValueError):
            promote_library(target, current)
        assert client.get('/api/library/wechat/1').json()['snapshot_id'] == newer['snapshot_id']
    with pytest.raises(ValueError):
        export_library(source, second)

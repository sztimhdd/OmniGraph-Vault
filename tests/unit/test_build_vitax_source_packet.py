"""Stored input packets use verified readonly original bodies, never translations."""
import hashlib
import json

import pytest

from tests.unit.test_vitax_local_articles import mirror
from vitax.production import ProductionError, standardize_documents


def test_packet_retains_source_identity_and_original_hash(tmp_path):
    from scripts.build_vitax_source_packet import build_source_packet
    database, receipt = mirror(tmp_path / 'mirror')
    original = database.read_bytes()
    output = tmp_path / 'packet'
    packet = build_source_packet(database, [('wechat', 1), ('rss', 1)], output, source_receipt_path=receipt)
    items = json.loads(packet.read_text())['documents']
    assert [x['source_id'] for x in items] == ['wechat-1', 'rss-1']
    assert items[0]['source_snapshot_id'] == 'one'
    assert items[0]['source_record_ref'] == {'source': 'wechat', 'record_id': 1}
    assert items[0]['fetched_at'] is None
    assert items[0]['representation_saved_at']
    body = (output / 'wechat-1.md').read_bytes()
    assert body == 'LIBRARY_SENTINEL原文1'.encode()
    assert hashlib.sha256(body).hexdigest() == items[0]['raw_markdown_sha256']
    assert '已有译文' not in body.decode()
    assert len(standardize_documents(json.loads(packet.read_text()), capture_root=output)['documents']) == 2
    assert database.read_bytes() == original
    with pytest.raises(ProductionError):
        build_source_packet(database, [('wechat', 1)], output, source_receipt_path=receipt)
    with pytest.raises(ProductionError):
        build_source_packet(database, [('rss', 2)], tmp_path / 'empty', source_receipt_path=receipt)
    metadata = json.loads(receipt.read_text())
    metadata['sqlite_sha256'] = '0' * 64
    receipt.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        build_source_packet(database, [('rss', 1)], tmp_path / 'bad', source_receipt_path=receipt)

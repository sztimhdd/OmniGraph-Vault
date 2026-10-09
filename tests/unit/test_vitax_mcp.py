"""Real JSON-RPC contract checks for the public reader's MCP mount."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from vitax.api import create_app
from vitax.knowledge import build


def _database(tmp_path: Path, extra_rows: int = 0) -> Path:
    projection = {
        'schema_version': 1, 'release_id': 'mcp-test', 'published_at': '2026-10-01T12:00:00Z',
        'documents': [{'doc_id': 'doc', 'revision_id': 'rev', 'title': 'Synthetic source', 'source_url': 'https://example.test/source', 'visibility': 'public'}],
        'evidence': [{'evidence_id': 'ev', 'revision_id': 'rev', 'locator': 'paragraph:1', 'quote': 'Synthetic runtime evidence', 'visibility': 'public'}],
        'knowledge': [
            {'knowledge_id': 'harness', 'kind': 'article', 'title': 'Harness', 'body': 'A synthetic Harness entry.', 'evidence_ids': ['ev'], 'visibility': 'public'},
            {'knowledge_id': 'private-entry', 'kind': 'article', 'title': 'PRIVATE_SENTINEL', 'body': 'PRIVATE_SENTINEL', 'evidence_ids': ['ev'], 'visibility': 'private'},
        ],
        'entities': [{'entity_id': 'harness', 'name': 'Harness', 'visibility': 'public'}, {'entity_id': 'model', 'name': 'Model', 'visibility': 'public'}],
        'relations': [{'relation_id': 'rel', 'source_id': 'harness', 'target_id': 'model', 'relation_type': 'supports', 'evidence_ids': ['ev'], 'visibility': 'public'}],
    }
    for index in range(extra_rows):
        identifier = f'extra-{index:02}'
        projection['knowledge'].append({'knowledge_id': identifier, 'kind': 'article', 'title': f'Harness {index}', 'body': 'Synthetic extra knowledge.', 'evidence_ids': ['ev'], 'visibility': 'public'})
        projection['entities'].append({'entity_id': identifier, 'name': f'Entity {index}', 'visibility': 'public'})
        projection['relations'].append({'relation_id': identifier, 'source_id': 'harness', 'target_id': identifier, 'relation_type': 'supports', 'evidence_ids': ['ev'], 'visibility': 'public'})
    target = tmp_path / 'public.sqlite'
    build(projection, target)
    return target


def _rpc(client: TestClient, method: str, params: dict | None = None) -> dict:
    response = client.post('/mcp/', headers={'Accept': 'application/json, text/event-stream'}, json={
        'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {},
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert 'error' not in result, result
    return result['result']


def _initialize(client: TestClient) -> None:
    result = _rpc(client, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'reader-test', 'version': '1'}})
    assert result['serverInfo']['name'] == 'VitaX public knowledge'
    response = client.post('/mcp/', headers={'Accept': 'application/json, text/event-stream'}, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    assert response.status_code == 202


def _call(client: TestClient, name: str, arguments: dict) -> dict:
    result = _rpc(client, 'tools/call', {'name': name, 'arguments': arguments})
    assert result.get('isError') is not True, result
    return json.loads(result['content'][0]['text'])


def test_mcp_protocol_calls_share_the_http_release(tmp_path: Path) -> None:
    with TestClient(create_app(_database(tmp_path))) as client:
        _initialize(client)
        names = {tool['name'] for tool in _rpc(client, 'tools/list')['tools']}
        assert names == {'release_info', 'search', 'read_knowledge', 'read_evidence', 'list_entities', 'related'}
        checks = [
            ('release_info', {}, '/api/release'),
            ('search', {'query': 'Harness', 'limit': 5}, '/api/knowledge?q=Harness&limit=5'),
            ('read_knowledge', {'knowledge_id': 'harness'}, '/api/knowledge/harness'),
            ('read_evidence', {'evidence_id': 'ev'}, '/api/evidence/ev'),
            ('list_entities', {'limit': 10}, '/api/entities?limit=10'),
            ('related', {'entity_id': 'harness', 'limit': 5}, '/api/entities/harness/related?limit=5'),
        ]
        for name, args, path in checks:
            data = _call(client, name, args)
            assert data == client.get(path).json()
            assert data['release_id'] == 'mcp-test'
            assert 'PRIVATE_SENTINEL' not in json.dumps(data)


def test_mcp_errors_preserve_reader_bounds_and_fail_closed(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with TestClient(create_app(database)) as client:
        _initialize(client)
        for name, args in [
            ('search', {'query': '', 'limit': 1}),
            ('search', {'query': 'Harness', 'limit': 101}),
            ('search', {'query': 'Harness', 'limit': True}),
            ('read_knowledge', {'knowledge_id': 'private-entry'}),
            ('write_knowledge', {}),
        ]:
            assert _rpc(client, 'tools/call', {'name': name, 'arguments': args})['isError'] is True
        database.unlink()
        result = _rpc(client, 'tools/call', {'name': 'search', 'arguments': {'query': 'Harness'}})
        assert result['isError'] is True
        assert str(database) not in json.dumps(result)


def test_mcp_default_limits_match_http_for_larger_releases(tmp_path: Path) -> None:
    with TestClient(create_app(_database(tmp_path, extra_rows=24))) as client:
        _initialize(client)
        for tool, args, path in [
            ('search', {'query': 'Harness'}, '/api/knowledge?q=Harness'),
            ('list_entities', {}, '/api/entities'),
            ('related', {'entity_id': 'harness'}, '/api/entities/harness/related'),
        ]:
            assert _call(client, tool, args) == client.get(path).json()


def test_bare_mcp_path_redirects_before_the_static_site(tmp_path: Path) -> None:
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'index.html').write_text('<h1>Synthetic site</h1>')
    with TestClient(create_app(_database(tmp_path), site_dir=site)) as client:
        response = client.post('/mcp', follow_redirects=False)
        assert response.status_code == 307
        assert response.headers['location'].endswith('/mcp/')
        response = client.post('/mcp', headers={'Accept': 'application/json, text/event-stream'}, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'bare-path', 'version': '1'}},
        })
        assert response.status_code == 200
        assert response.json()['result']['serverInfo']['name'] == 'VitaX public knowledge'
        assert client.get('/').text == '<h1>Synthetic site</h1>'

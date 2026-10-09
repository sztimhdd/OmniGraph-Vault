import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ApiError,
  NetworkError,
  NotFoundError,
  ReleaseMismatchError,
  assertReleaseConsistent,
  createKnowledgeApi,
} from '../src/api.ts';
import type {Release} from '../src/types.ts';

const RELEASE = 'release-2026-09-09';
const PUBLISHED_AT = '2026-09-09T12:00:00Z';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {'content-type': 'application/json'},
  });
}

function releaseResponse(releaseId = RELEASE): Response {
  return jsonResponse({release_id: releaseId, published_at: PUBLISHED_AT});
}

function recorder(...responses: (Response | Error)[]) {
  const calls: string[] = [];
  const fetchImpl = (async (input: string | URL | Request) => {
    calls.push(String(input));
    const next = responses.shift();
    if (next === undefined) throw new Error('unexpected extra request');
    if (next instanceof Error) throw next;
    return next;
  }) as unknown as typeof fetch;
  return {calls, fetchImpl};
}

test('release consistency accepts the first release and rejects a different one', () => {
  const metadata = {release_id: RELEASE, published_at: PUBLISHED_AT};
  assert.equal(assertReleaseConsistent(null, metadata), RELEASE);
  assert.equal(assertReleaseConsistent(RELEASE, metadata), RELEASE);
  assert.throws(
    () => assertReleaseConsistent(RELEASE, {...metadata, release_id: 'release-other'}),
    ReleaseMismatchError,
  );
  assert.throws(() => assertReleaseConsistent(null, {}), ApiError);
  assert.throws(() => assertReleaseConsistent(null, {release_id: 7, published_at: 'x'}), ApiError);
});

test('client reads are refused until /api/release has been confirmed', async () => {
  const {calls, fetchImpl} = recorder(releaseResponse(), jsonResponse({release_id: RELEASE, published_at: PUBLISHED_AT, results: []}));
  const api = createKnowledgeApi(fetchImpl);

  await assert.rejects(() => api.list(), ApiError);
  await assert.rejects(() => api.entities(), ApiError);
  await assert.rejects(() => api.knowledge('k-1'), ApiError);
  assert.deepEqual(calls, [], 'no request may be sent before the release is pinned');

  const release = await api.bootstrap();
  assert.deepEqual(release, {release_id: RELEASE, published_at: PUBLISHED_AT});
  assert.deepEqual(await api.list(), []);
  assert.equal(calls[0], '/api/release');
  assert.equal(calls[1], '/api/knowledge');
});

test('a later response from another release fails the whole session', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse(),
    jsonResponse({
      release_id: RELEASE,
      published_at: PUBLISHED_AT,
      results: [{knowledge_id: 'k-1', kind: 'article', title: 'First'}],
    }),
    jsonResponse({
      release_id: 'release-other',
      published_at: PUBLISHED_AT,
      results: [{knowledge_id: 'k-2', kind: 'wiki', title: 'Second'}],
    }),
    jsonResponse({release_id: 'release-other', published_at: PUBLISHED_AT, results: []}),
  );
  const api = createKnowledgeApi(fetchImpl);
  const seen: Error[] = [];
  const unsubscribe = api.onReleaseMismatch((error) => seen.push(error));

  await api.bootstrap();
  assert.deepEqual(await api.list(), [{knowledge_id: 'k-1', kind: 'article', title: 'First'}]);
  await assert.rejects(() => api.list(), ReleaseMismatchError);
  assert.equal(seen.length, 1);
  assert.ok(seen[0] instanceof ReleaseMismatchError);
  assert.match(seen[0].message, /release/);
  assert.equal(calls.length, 3);

  unsubscribe();
  await assert.rejects(() => api.list(), ReleaseMismatchError);
  assert.equal(seen.length, 1, 'an unsubscribed listener must not be called again');
  assert.equal(calls.length, 4);
});

test('list, search and kind filters build bounded request urls', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse(),
    jsonResponse({release_id: RELEASE, published_at: PUBLISHED_AT, results: []}),
    jsonResponse({release_id: RELEASE, published_at: PUBLISHED_AT, results: []}),
    jsonResponse({release_id: RELEASE, published_at: PUBLISHED_AT, results: []}),
  );
  const api = createKnowledgeApi(fetchImpl);

  await api.bootstrap();
  await api.list();
  await api.list({q: 'Graph RAG', kind: 'wiki', limit: 50});
  await api.list({q: '', kind: 'all'});
  assert.equal(calls[1], '/api/knowledge');
  assert.equal(calls[2], '/api/knowledge?q=Graph%20RAG&kind=wiki&limit=50');
  assert.equal(calls[3], '/api/knowledge');
});

test('out of contract limits fail before any request is sent', async () => {
  const {calls, fetchImpl} = recorder(releaseResponse());
  const api = createKnowledgeApi(fetchImpl);
  await api.bootstrap();
  await assert.rejects(() => api.list({limit: 0}), ApiError);
  await assert.rejects(() => api.list({limit: 101}), ApiError);
  assert.deepEqual(calls, ['/api/release']);
});

test('knowledge, evidence and relations read real identifiers', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse(),
    jsonResponse({
      release_id: RELEASE,
      published_at: PUBLISHED_AT,
      knowledge: {knowledge_id: 'k 1', kind: 'article', title: 'T', body: 'B', evidence_ids: ['ev-1']},
    }),
    jsonResponse({
      release_id: RELEASE,
      published_at: PUBLISHED_AT,
      evidence: {
        evidence_id: 'ev-1',
        revision_id: 'rev-1',
        locator: 'paragraph:2',
        quote: 'Q',
        document: {doc_id: 'd-1', title: 'Doc', source_url: 'https://example.test/a'},
      },
    }),
    jsonResponse({
      release_id: RELEASE,
      published_at: PUBLISHED_AT,
      entity_id: 'e-1',
      relations: [
        {
          relation_id: 'r-1',
          source_id: 'e-1',
          target_id: 'e-2',
          relation_type: 'uses',
          source_name: 'A',
          target_name: 'B',
          evidence_ids: ['ev-1'],
        },
      ],
    }),
  );
  const api = createKnowledgeApi(fetchImpl);
  await api.bootstrap();

  const item = await api.knowledge('k 1');
  assert.equal(item.body, 'B');
  assert.equal(item.kind, 'article');
  const evidence = await api.evidence('ev-1');
  assert.equal(evidence.document.source_url, 'https://example.test/a');
  const relations = await api.relations('e-1');
  assert.equal(relations.length, 1);
  assert.equal(relations[0].target_name, 'B');
  assert.equal(calls[1], '/api/knowledge/k%201');
  assert.equal(calls[2], '/api/evidence/ev-1');
  assert.equal(calls[3], '/api/entities/e-1/related');
});

test('unknown identifiers surface as not found instead of the first record', async () => {
  const {fetchImpl} = recorder(releaseResponse(), jsonResponse({error: 'knowledge item not found: k-9'}, 404));
  const api = createKnowledgeApi(fetchImpl);
  await api.bootstrap();
  await assert.rejects(() => api.knowledge('k-9'), NotFoundError);
});

test('a 404 from another release fails the session instead of showing a local 404', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse('release-a'),
    jsonResponse({error: 'knowledge item not found: k-9'}, 404),
    releaseResponse('release-b'),
  );
  const api = createKnowledgeApi(fetchImpl);
  const seen: Error[] = [];
  api.onReleaseMismatch((error) => seen.push(error));
  await api.bootstrap();

  await assert.rejects(() => api.knowledge('k-9'), ReleaseMismatchError);
  assert.equal(seen.length, 1, 'the global fail-closed signal must fire');
  assert.ok(seen[0] instanceof ReleaseMismatchError);
  assert.deepEqual(calls, ['/api/release', '/api/knowledge/k-9', '/api/release']);
});

test('a 404 that still belongs to the pinned release stays a not-found', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse('release-a'),
    jsonResponse({error: 'knowledge item not found: k-9'}, 404),
    releaseResponse('release-a'),
  );
  const api = createKnowledgeApi(fetchImpl);
  const seen: Error[] = [];
  api.onReleaseMismatch((error) => seen.push(error));
  await api.bootstrap();

  await assert.rejects(() => api.knowledge('k-9'), NotFoundError);
  assert.equal(seen.length, 0);
  assert.deepEqual(calls, ['/api/release', '/api/knowledge/k-9', '/api/release']);
});

test('a domain error that carries another release id is rejected without a second read', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse('release-a'),
    jsonResponse({error: 'not found', release_id: 'release-b', published_at: PUBLISHED_AT}, 404),
  );
  const api = createKnowledgeApi(fetchImpl);
  await api.bootstrap();
  await assert.rejects(() => api.evidence('ev-9'), ReleaseMismatchError);
  assert.deepEqual(calls, ['/api/release', '/api/evidence/ev-9']);
});

test('a failing release re-check never recurses and keeps the bounded domain error', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse('release-a'),
    jsonResponse({error: 'knowledge item not found: k-9'}, 404),
    jsonResponse({error: 'boom'}, 500),
  );
  const api = createKnowledgeApi(fetchImpl);
  await api.bootstrap();
  await assert.rejects(() => api.knowledge('k-9'), NotFoundError);
  assert.deepEqual(calls, ['/api/release', '/api/knowledge/k-9', '/api/release']);

  const {calls: offlineCalls, fetchImpl: offlineFetch} = recorder(
    releaseResponse('release-a'),
    jsonResponse({error: 'knowledge item not found: k-9'}, 404),
    new TypeError('fetch failed'),
  );
  const offline = createKnowledgeApi(offlineFetch);
  await offline.bootstrap();
  await assert.rejects(() => offline.knowledge('k-9'), NotFoundError);
  assert.deepEqual(offlineCalls, ['/api/release', '/api/knowledge/k-9', '/api/release']);
});

test('transport and payload failures stay bounded errors', async () => {
  const offline = createKnowledgeApi(recorder(new TypeError('fetch failed')).fetchImpl);
  await assert.rejects(() => offline.bootstrap(), NetworkError);

  const brokenJson = createKnowledgeApi(recorder(new Response('<html>oops</html>', {status: 200})).fetchImpl);
  await assert.rejects(() => brokenJson.bootstrap(), ApiError);

  const serverError = createKnowledgeApi(
    recorder(releaseResponse(), jsonResponse({error: 'boom'}, 500), releaseResponse()).fetchImpl,
  );
  await serverError.bootstrap();
  const failure = await serverError.list().then(
    () => null,
    (error: unknown) => error,
  );
  assert.ok(failure instanceof ApiError);
  assert.ok(!(failure instanceof NotFoundError));
  assert.match((failure as Error).message, /500/);

  const malformed = createKnowledgeApi(
    recorder(releaseResponse(), jsonResponse({release_id: RELEASE, published_at: 'x', results: 'nope'})).fetchImpl,
  );
  await malformed.bootstrap();
  await assert.rejects(() => malformed.list(), ApiError);

  const badRelease = createKnowledgeApi(recorder(jsonResponse({release_id: RELEASE})).fetchImpl);
  await assert.rejects(() => badRelease.bootstrap(), ApiError);
});

test('entities are listed from the public reader after bootstrap', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse(),
    jsonResponse({
      release_id: RELEASE,
      published_at: PUBLISHED_AT,
      results: [{entity_id: 'e-1', name: 'A'}],
    }),
  );
  const api = createKnowledgeApi(fetchImpl);
  await api.bootstrap();
  assert.deepEqual(await api.entities(5), [{entity_id: 'e-1', name: 'A'}]);
  assert.equal(calls[1], '/api/entities?limit=5');
});

test('bootstrap pins the session and every later bootstrap must match it', async () => {
  const {calls, fetchImpl} = recorder(
    releaseResponse('release-a'),
    releaseResponse('release-a'),
    releaseResponse('release-b'),
  );
  const api = createKnowledgeApi(fetchImpl);
  const seen: Error[] = [];
  api.onReleaseMismatch((error) => seen.push(error));

  assert.equal((await api.bootstrap()).release_id, 'release-a');
  assert.equal((await api.bootstrap()).release_id, 'release-a');
  await assert.rejects(() => api.bootstrap(), ReleaseMismatchError);
  assert.equal(seen.length, 1, 'a cross-release bootstrap also fails the session closed');
  assert.deepEqual(calls, ['/api/release', '/api/release', '/api/release']);
});

test('knowledge client preserves the server-sanitized rendered HTML', async () => {
  const {fetchImpl} = recorder(releaseResponse(), jsonResponse({
    release_id: RELEASE,
    published_at: PUBLISHED_AT,
    knowledge: {knowledge_id: 'wiki-ai', kind: 'wiki', title: 'Wiki', body: '# Heading', rendered_html: '<h1>Heading</h1>', evidence_ids: ['ev-a']},
  }));
  const api = createKnowledgeApi(fetchImpl);
  await api.bootstrap();
  const item = await api.knowledge('wiki-ai');
  assert.equal(item.rendered_html, '<h1>Heading</h1>');
  assert.deepEqual(item.evidence_ids, ['ev-a']);
});

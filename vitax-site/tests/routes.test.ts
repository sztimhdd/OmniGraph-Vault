import assert from 'node:assert/strict';
import test from 'node:test';

import {
  itemPath,
  listPath,
  parseQuery,
  parseRoute,
  routeMatchesKind,
  routeToPath,
  safeReturnTarget,
  setListBase,
  withReturn,
} from '../src/routes.ts';

test('root path is the knowledge list', () => {
  assert.deepEqual(parseRoute('/'), {name: 'list', q: '', kind: 'all'});
  assert.deepEqual(parseRoute(''), {name: 'list', q: '', kind: 'all'});
  assert.deepEqual(parseRoute('/index.html'), {name: 'list', q: '', kind: 'all'});
});

test('list query parameters select deterministic search state', () => {
  assert.deepEqual(parseRoute('/', '?q=GraphRAG&kind=wiki'), {name: 'list', q: 'GraphRAG', kind: 'wiki'});
  assert.deepEqual(parseRoute('/', '?kind=bogus'), {name: 'list', q: '', kind: 'all'});
  assert.deepEqual(parseRoute('/', '?q=%E4%B8%AD%E6%96%87&kind=article'), {
    name: 'list',
    q: '中文',
    kind: 'article',
  });
  assert.deepEqual(parseQuery(''), {q: '', kind: 'all'});
  assert.deepEqual(parseQuery('?q=++trimmed++'), {q: 'trimmed', kind: 'all'});
});

test('article and wiki routes keep the requested identifier', () => {
  assert.deepEqual(parseRoute('/article/k-1'), {name: 'article', id: 'k-1'});
  assert.deepEqual(parseRoute('/wiki/k-2'), {name: 'wiki', id: 'k-2'});
});

test('trailing slash and prerendered index files resolve to the same route', () => {
  assert.deepEqual(parseRoute('/article/k-1/'), {name: 'article', id: 'k-1'});
  assert.deepEqual(parseRoute('/wiki/k-2/index.html'), {name: 'wiki', id: 'k-2'});
  assert.deepEqual(parseRoute('/article/k-1///'), {name: 'article', id: 'k-1'});
});

test('percent encoded identifiers are decoded for the API call', () => {
  assert.deepEqual(parseRoute('/article/k%20one'), {name: 'article', id: 'k one'});
  assert.deepEqual(parseRoute('/wiki/%E4%B8%AD%E6%96%87'), {name: 'wiki', id: '中文'});
});

test('malformed or unsupported paths stay unknown instead of guessing a record', () => {
  assert.deepEqual(parseRoute('/article'), {name: 'unknown', path: '/article'});
  assert.deepEqual(parseRoute('/article/'), {name: 'unknown', path: '/article/'});
  assert.deepEqual(parseRoute('/article/a/b'), {name: 'unknown', path: '/article/a/b'});
  assert.deepEqual(parseRoute('/wiki/'), {name: 'unknown', path: '/wiki/'});
  assert.deepEqual(parseRoute('/topic/t-1'), {name: 'unknown', path: '/topic/t-1'});
  assert.deepEqual(parseRoute('/article/a%2Fb'), {name: 'unknown', path: '/article/a%2Fb'});
  assert.deepEqual(parseRoute('/wiki/%'), {name: 'unknown', path: '/wiki/%'});
});

test('a knowledge id that looks like a generated index file still routes', () => {
  assert.deepEqual(parseRoute('/article/index.html'), {name: 'article', id: 'index.html'});
  assert.deepEqual(parseRoute('/wiki/index.html'), {name: 'wiki', id: 'index.html'});
  assert.deepEqual(parseRoute('/article/index.html/'), {name: 'article', id: 'index.html'});
  assert.equal(routeToPath({name: 'article', id: 'index.html'}), '/article/index.html');
  assert.deepEqual(parseRoute(routeToPath({name: 'wiki', id: 'index.html'})), {
    name: 'wiki',
    id: 'index.html',
  });
});

test('terminal index.html is only a generated suffix of the three segment detail form', () => {
  assert.deepEqual(parseRoute('/article/k-1/index.html'), {name: 'article', id: 'k-1'});
  assert.deepEqual(parseRoute('/wiki/k-2/index.html'), {name: 'wiki', id: 'k-2'});
  assert.deepEqual(parseRoute('/index.html'), {name: 'list', q: '', kind: 'all'});
  assert.deepEqual(parseRoute('/article/k-1/index.html/x'), {
    name: 'unknown',
    path: '/article/k-1/index.html/x',
  });
  assert.deepEqual(parseRoute('/foo/index.html'), {name: 'unknown', path: '/foo/index.html'});
  assert.deepEqual(parseRoute('/article/index.html/index.html'), {
    name: 'article',
    id: 'index.html',
  });
});

test('route paths round trip through the router', () => {
  assert.equal(routeToPath({name: 'list', q: '', kind: 'all'}), '/');
  assert.equal(routeToPath({name: 'article', id: 'k-1'}), '/article/k-1');
  assert.equal(routeToPath({name: 'wiki', id: 'k 2'}), '/wiki/k%202');
  assert.equal(listPath({q: 'a b', kind: 'wiki'}), '/?q=a%20b&kind=wiki');
  assert.equal(listPath({q: '', kind: 'article'}), '/?kind=article');
  assert.equal(listPath({q: '', kind: 'all'}), '/');
  const listUrl = routeToPath({name: 'list', q: 'a b', kind: 'wiki'});
  const [pathname, search] = listUrl.split('?');
  assert.deepEqual(parseRoute(pathname, `?${search}`), {
    name: 'list',
    q: 'a b',
    kind: 'wiki',
  });
  assert.deepEqual(parseRoute(routeToPath({name: 'wiki', id: 'k 2'})), {name: 'wiki', id: 'k 2'});
});

test('list links follow the kind of each knowledge row', () => {
  assert.equal(itemPath({knowledge_id: 'k-1', kind: 'article'}), '/article/k-1');
  assert.equal(itemPath({knowledge_id: 'k-1', kind: 'wiki'}), '/wiki/k-1');
  assert.equal(itemPath({knowledge_id: 'k-1', kind: 'article'}, '/?q=a&kind=wiki'), '/article/k-1?return=%2F%3Fq%3Da%26kind%3Dwiki');
  assert.equal(withReturn('/wiki/k-2', '/?kind=wiki'), '/wiki/k-2?return=%2F%3Fkind%3Dwiki');
});

test('return targets stay internal to the reader', () => {
  assert.equal(safeReturnTarget('/?q=%E4%B8%AD%E6%96%87&kind=article', '/'), '/?q=%E4%B8%AD%E6%96%87&kind=article');
  assert.equal(safeReturnTarget('/library?q=TLA&offset=20', '/'), '/library?q=TLA&offset=20');
  assert.equal(safeReturnTarget('//evil.test/x', '/'), '/');
  assert.equal(safeReturnTarget('https://evil.test/', '/'), '/');
  assert.equal(safeReturnTarget(null, '/'), '/');
  assert.equal(safeReturnTarget('/a b', '/'), '/');
});

test('the knowledge list keeps its own path when the library owns the home route', () => {
  assert.deepEqual(parseRoute('/knowledge'), {name: 'list', q: '', kind: 'all'});
  assert.deepEqual(parseRoute('/knowledge/', '?q=%E4%B8%AD%E6%96%87&kind=wiki'), {
    name: 'list',
    q: '中文',
    kind: 'wiki',
  });
  assert.deepEqual(parseRoute('/knowledge/index.html'), {name: 'list', q: '', kind: 'all'});
  setListBase('/knowledge');
  try {
    assert.equal(listPath({q: '', kind: 'all'}), '/knowledge');
    assert.equal(listPath({q: 'a b', kind: 'wiki'}), '/knowledge?q=a%20b&kind=wiki');
    assert.equal(routeToPath({name: 'list', q: '', kind: 'all'}), '/knowledge');
    assert.equal(itemPath({knowledge_id: 'k-1', kind: 'wiki'}, listPath({q: '', kind: 'all'})), '/wiki/k-1?return=%2Fknowledge');
  } finally {
    setListBase('/');
  }
  assert.equal(listPath({q: '', kind: 'all'}), '/');
});

test('a route only accepts the knowledge kind it names', () => {
  assert.equal(routeMatchesKind({name: 'article', id: 'k-1'}, 'article'), true);
  assert.equal(routeMatchesKind({name: 'article', id: 'k-1'}, 'wiki'), false);
  assert.equal(routeMatchesKind({name: 'wiki', id: 'k-2'}, 'wiki'), true);
  assert.equal(routeMatchesKind({name: 'wiki', id: 'k-2'}, 'article'), false);
  assert.equal(routeMatchesKind({name: 'unknown', path: '/nope'}, 'article'), false);
});

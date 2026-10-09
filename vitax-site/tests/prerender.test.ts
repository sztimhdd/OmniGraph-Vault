import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {cp, mkdtemp, readFile, readdir, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {escapeHtml, prerenderRelease, publicSnapshot, safeUrl} from '../scripts/prerender.mjs';
import {parseRoute, routeToPath} from '../src/routes.ts';

const PRIVATE_SENTINEL = 'PRIVATE_SENTINEL';

const SHELL = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>VitaX 知识阅读</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" crossorigin src="/assets/app.js"></script>
  </body>
</html>
`;

function snapshot(): Record<string, unknown> {
  return {
    schema_version: 1,
    release_id: 'release-test-1',
    published_at: '2026-09-09T12:00:00Z',
    documents: [
      {
        doc_id: 'doc-a',
        revision_id: 'rev-a',
        title: 'Source A & more',
        source_url: 'https://example.test/a?x=1&y=2',
        visibility: 'public',
      },
      {
        doc_id: 'doc-private',
        revision_id: 'rev-private',
        title: `${PRIVATE_SENTINEL} source`,
        source_url: 'https://example.test/private',
        visibility: 'private',
      },
    ],
    evidence: [
      {
        evidence_id: 'ev-a',
        revision_id: 'rev-a',
        locator: 'paragraph:2',
        quote: 'Alpha quote <bold> & "quoted"',
        visibility: 'public',
      },
      {
        evidence_id: 'ev-private',
        revision_id: 'rev-private',
        locator: 'paragraph:1',
        quote: `${PRIVATE_SENTINEL} quote`,
        visibility: 'private',
      },
    ],
    knowledge: [
      {
        knowledge_id: 'k-article',
        kind: 'article',
        title: 'Article <script>alert(1)</script>',
        body: 'First paragraph.\n\nSecond & "quoted" paragraph.',
        evidence_ids: ['ev-a'],
        visibility: 'public',
        internal_note: `${PRIVATE_SENTINEL} note`,
      },
      {
        knowledge_id: 'k-wiki',
        kind: 'wiki',
        title: 'Wiki 词条',
        body: 'Wiki body.',
        evidence_ids: [],
        visibility: 'public',
      },
      {
        knowledge_id: 'k-private',
        kind: 'article',
        title: `${PRIVATE_SENTINEL} article`,
        body: `${PRIVATE_SENTINEL} body`,
        evidence_ids: ['ev-private'],
        visibility: 'private',
      },
    ],
    entities: [
      {entity_id: 'e-1', name: 'Alpha', visibility: 'public'},
      {entity_id: 'e-2', name: 'Beta', visibility: 'public'},
      {entity_id: 'e-private', name: `${PRIVATE_SENTINEL} entity`, visibility: 'private'},
    ],
    relations: [
      {
        relation_id: 'r-1',
        source_id: 'e-1',
        target_id: 'e-2',
        relation_type: 'uses',
        evidence_ids: ['ev-a'],
        visibility: 'public',
      },
      {
        relation_id: 'r-private',
        source_id: 'e-1',
        target_id: 'e-private',
        relation_type: 'leaks',
        evidence_ids: ['ev-private'],
        visibility: 'private',
      },
    ],
  };
}

async function makeDist(): Promise<string> {
  const dist = await mkdtemp(path.join(tmpdir(), 'vitax-dist-'));
  await writeFile(path.join(dist, 'index.html'), SHELL, 'utf8');
  return dist;
}

async function makeDistUnder(root: string): Promise<string> {
  const dist = path.join(root, 'dist');
  await cp(await makeDist(), dist, {recursive: true});
  return dist;
}

/** Extract one entity block from the generated relationship section. */
function entityBlock(html: string, entityId: string): string {
  const start = html.indexOf(`<li id="entity-${entityId}">`);
  assert.notEqual(start, -1, `entity ${entityId} is missing from the generated markup`);
  const next = html.indexOf('<li id="entity-', start + 1);
  return next === -1 ? html.slice(start) : html.slice(start, next);
}

async function readTree(root: string): Promise<Map<string, string>> {
  const files = new Map<string, string>();
  for (const entry of await readdir(root, {withFileTypes: true, recursive: true})) {
    if (!entry.isFile()) continue;
    const absolute = path.join(entry.parentPath ?? root, entry.name);
    files.set(path.relative(root, absolute), await readFile(absolute, 'utf8'));
  }
  return files;
}

test('html escaping neutralises markup and attribute breakouts', () => {
  assert.equal(escapeHtml('<script>alert("x")</script>'), '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;');
  assert.equal(escapeHtml("Tom & Jerry's"), 'Tom &amp; Jerry&#39;s');
  assert.equal(escapeHtml('safe text'), 'safe text');
  assert.equal(escapeHtml('&amp;'), '&amp;amp;');
});

test('only http and https links survive into generated markup', () => {
  assert.equal(safeUrl('https://example.test/a?x=1&y=2'), 'https://example.test/a?x=1&y=2');
  assert.equal(safeUrl('http://example.test/a'), 'http://example.test/a');
  for (const hostile of ['javascript:alert(1)', 'data:text/html,<b>', 'vbscript:x', '/relative', '', null, 7]) {
    assert.equal(safeUrl(hostile as string), null);
  }
});

test('the public snapshot keeps only public records and whitelisted fields', () => {
  const view = publicSnapshot(snapshot());
  assert.equal(view.releaseId, 'release-test-1');
  assert.deepEqual(
    view.items.map((item: {id: string}) => item.id),
    ['k-article', 'k-wiki'],
  );
  const article = view.items[0];
  assert.deepEqual(Object.keys(article).sort(), ['body', 'evidence', 'id', 'kind', 'title']);
  assert.equal(article.evidence.length, 1);
  assert.equal(article.evidence[0].document.title, 'Source A & more');
  assert.deepEqual(
    view.entities.map((entity: {entity_id: string}) => entity.entity_id),
    ['e-1', 'e-2'],
  );
  assert.deepEqual(
    view.relations.map((relation: {relation_id: string}) => relation.relation_id),
    ['r-1'],
  );
  assert.equal(view.relations[0].source_name, 'Alpha');
  assert.equal(view.relations[0].target_name, 'Beta');
});

test('only the accepted knowledge kinds are rendered', () => {
  const invalid = snapshot();
  (invalid.knowledge as Record<string, unknown>[])[1].kind = 'topic';
  assert.throws(() => publicSnapshot(invalid), /kind/);
});

test('prerender writes semantic html for the list, article and wiki routes', async () => {
  const dist = await makeDist();
  const written = await prerenderRelease({snapshot: snapshot(), distDir: dist});
  const files = await readTree(dist);

  assert.deepEqual(
    [...written.written].sort(),
    ['article/k-article/index.html', 'index.html', 'wiki/k-wiki/index.html'],
  );
  assert.deepEqual(written.skipped, []);
  assert.ok(files.has('index.html'));
  assert.ok(files.has('article/k-article/index.html'));
  assert.ok(files.has('wiki/k-wiki/index.html'));

  const index = files.get('index.html')!;
  assert.match(index, /<h1[^>]*>VitaX 知识阅读<\/h1>/);
  assert.match(index, /href="\/article\/k-article"/);
  assert.match(index, /href="\/wiki\/k-wiki"/);
  assert.match(index, /release-test-1/);
  assert.match(index, /Article &lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(index, /<script type="module" crossorigin src="\/assets\/app\.js"><\/script>/);
  assert.doesNotMatch(index, /<div id="root">\s*<\/div>/);

  const article = files.get('article/k-article/index.html')!;
  assert.match(article, /<title>[^<]*Article &lt;script&gt;/);
  assert.match(article, /<h1[^>]*>Article &lt;script&gt;alert\(1\)&lt;\/script&gt;<\/h1>/);
  assert.match(article, /<p>First paragraph\.<\/p>/);
  assert.match(article, /<p>Second &amp; &quot;quoted&quot; paragraph\.<\/p>/);
  assert.match(article, /href="https:\/\/example\.test\/a\?x=1&amp;y=2"/);
  assert.match(article, /Source A &amp; more/);
  assert.match(article, /paragraph:2/);
  assert.match(article, /Alpha quote &lt;bold&gt; &amp; &quot;quoted&quot;/);
  assert.doesNotMatch(article, /<script>alert\(1\)<\/script>/);

  const wiki = files.get('wiki/k-wiki/index.html')!;
  assert.match(wiki, /<h1[^>]*>Wiki 词条<\/h1>/);
  assert.match(wiki, /Wiki body\./);
});

test('no private record, unknown field or review vocabulary reaches the output', async () => {
  const dist = await makeDist();
  await prerenderRelease({snapshot: snapshot(), distDir: dist});
  const files = await readTree(dist);
  for (const [relative, content] of files) {
    assert.doesNotMatch(content, new RegExp(PRIVATE_SENTINEL), `private data leaked into ${relative}`);
    assert.doesNotMatch(content, /internal_note/, `unknown field leaked into ${relative}`);
    assert.doesNotMatch(content, /"visibility"/, `visibility flag leaked into ${relative}`);
  }
  const index = files.get('index.html')!;
  assert.doesNotMatch(index, /r-private|e-private/);
});

test('prerender refuses a shell that cannot host the rendered content', async () => {
  const dist = await mkdtemp(path.join(tmpdir(), 'vitax-dist-'));
  await writeFile(path.join(dist, 'index.html'), '<!doctype html><html><body>no root</body></html>', 'utf8');
  await assert.rejects(() => prerenderRelease({snapshot: snapshot(), distDir: dist}), /root/);
});

test('prerender copies the built shell into a separate output directory', async () => {
  const dist = await makeDist();
  await writeFile(path.join(dist, 'assets.js'), 'console.log(1);', 'utf8');
  const out = await mkdtemp(path.join(tmpdir(), 'vitax-out-'));
  await prerenderRelease({snapshot: snapshot(), distDir: dist, outDir: out});
  const files = await readTree(out);
  assert.ok(files.has('assets.js'));
  assert.match(files.get('index.html')!, /href="\/article\/k-article"/);
});

test('unicode and space identifiers become real prerendered directories', async () => {
  const dist = await makeDist();
  const localised = snapshot();
  localised.knowledge = [
    {
      knowledge_id: '知识-1',
      kind: 'article',
      title: '中文条目',
      body: '中文正文。',
      evidence_ids: ['ev-a'],
      visibility: 'public',
    },
    {
      knowledge_id: 'k 2',
      kind: 'wiki',
      title: '带空格的词条',
      body: '另一段正文。',
      evidence_ids: [],
      visibility: 'public',
    },
  ];
  const result = await prerenderRelease({snapshot: localised, distDir: dist});
  const files = await readTree(dist);

  assert.deepEqual(
    [...result.written].sort(),
    ['article/知识-1/index.html', 'index.html', 'wiki/k 2/index.html'],
  );
  assert.deepEqual(result.skipped, []);
  assert.match(files.get('article/知识-1/index.html')!, /<h1>中文条目<\/h1>/);
  assert.match(files.get('wiki/k 2/index.html')!, /<h1>带空格的词条<\/h1>/);
  const index = files.get('index.html')!;
  assert.match(index, /href="\/article\/%E7%9F%A5%E8%AF%86-1"/);
  assert.match(index, /href="\/wiki\/k%202"/);
});

test('unsafe identifiers are reported and never written outside the output directory', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'vitax-root-'));
  const dist = await makeDistUnder(root);
  const out = path.join(root, 'out');
  const hostile = snapshot();
  const hostileIds = [
    '../escape',
    '../../outside',
    'a/b',
    'a\\b',
    '..',
    '.',
    'nul\u0000byte',
  ];
  const items = hostileIds.map((id) => ({
    knowledge_id: id,
    kind: 'article',
    title: `hostile ${id}`,
    body: 'hostile body',
    evidence_ids: [],
    visibility: 'public',
  }));
  items.push({
    knowledge_id: '知识-1',
    kind: 'article',
    title: '安全条目',
    body: '安全正文。',
    evidence_ids: [],
    visibility: 'public',
  });
  hostile.knowledge = items;

  const result = await prerenderRelease({snapshot: hostile, distDir: dist, outDir: out});

  assert.deepEqual(result.written, ['index.html', 'article/知识-1/index.html']);
  assert.deepEqual(
    [...result.skipped.map((entry: {id: string}) => entry.id)].sort(),
    ['..', '.', '../escape', '../../outside', 'a/b', 'a\\b', 'nul\u0000byte'].sort(),
  );
  for (const entry of result.skipped) assert.match(entry.reason, /segment/);
  assert.deepEqual((await readdir(root)).sort(), ['dist', 'out']);
  assert.equal(existsSync(path.join(root, 'escape')), false);
  assert.equal(existsSync(path.join(path.dirname(root), 'outside')), false);
  assert.equal(existsSync(path.join(out, 'escape')), false);

  const index = (await readTree(out)).get('index.html')!;
  assert.match(index, /知识条目（1）/);
  assert.match(index, /href="\/article\/%E7%9F%A5%E8%AF%86-1"/);
  for (const id of hostileIds) {
    assert.equal(index.includes(`hostile ${id}`), false, `unroutable item ${id} was listed`);
  }
  assert.equal(index.includes('href="/article/.'), false);
  assert.equal(index.includes('href="/article/..'), false);
  assert.equal(index.includes('%2F'), false);
  assert.equal(index.includes('%5C'), false);
});

test('a relation is listed under both its source and target entity', async () => {
  const dist = await makeDist();
  const linked = snapshot();
  linked.entities = [
    {entity_id: 'e-1', name: 'Alpha', visibility: 'public'},
    {entity_id: 'e-2', name: 'Beta', visibility: 'public'},
    {entity_id: 'e-3', name: 'Gamma', visibility: 'public'},
  ];
  linked.relations = [
    {
      relation_id: 'r-1',
      source_id: 'e-1',
      target_id: 'e-2',
      relation_type: 'connects-alpha-beta',
      evidence_ids: ['ev-a'],
      visibility: 'public',
    },
    {
      relation_id: 'r-2',
      source_id: 'e-2',
      target_id: 'e-3',
      relation_type: 'connects-beta-gamma',
      evidence_ids: ['ev-a'],
      visibility: 'public',
    },
  ];
  await prerenderRelease({snapshot: linked, distDir: dist});
  const index = (await readTree(dist)).get('index.html')!;

  const alpha = entityBlock(index, 'e-1');
  const beta = entityBlock(index, 'e-2');
  const gamma = entityBlock(index, 'e-3');
  assert.match(alpha, /connects-alpha-beta/);
  assert.doesNotMatch(alpha, /connects-beta-gamma/);
  assert.match(beta, /connects-alpha-beta/);
  assert.match(beta, /connects-beta-gamma/);
  assert.match(gamma, /connects-beta-gamma/);
  assert.doesNotMatch(gamma, /connects-alpha-beta/);
});

test('every generated index link round-trips through the router to a written page', async () => {
  const dist = await makeDist();
  const tricky = snapshot();
  tricky.knowledge = [
    {knowledge_id: 'index.html', kind: 'article', title: '名为 index.html 的条目', body: '正文。', evidence_ids: [], visibility: 'public'},
    {knowledge_id: '知识-1', kind: 'article', title: '中文条目', body: '正文。', evidence_ids: [], visibility: 'public'},
    {knowledge_id: 'k 2', kind: 'wiki', title: '带空格词条', body: '正文。', evidence_ids: [], visibility: 'public'},
  ];
  tricky.entities = [];
  tricky.relations = [];

  const result = await prerenderRelease({snapshot: tricky, distDir: dist});
  assert.deepEqual(result.skipped, []);
  const files = await readTree(dist);
  const index = files.get('index.html')!;
  const links = [...index.matchAll(/href="(\/(?:article|wiki)\/[^"]*)"/g)].map((match) => match[1]);
  assert.equal(links.length, 3);

  for (const link of links) {
    const route = parseRoute(link);
    assert.notEqual(route.name, 'unknown', `${link} did not resolve to a route`);
    assert.equal(routeToPath(route), link, `${link} did not round trip`);
    assert.ok(
      files.has(`${route.name}/${'id' in route ? route.id : ''}/index.html`),
      `no page was written for ${link}`,
    );
  }
  assert.ok(files.has('article/index.html/index.html'));
});

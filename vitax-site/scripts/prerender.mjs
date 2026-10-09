/**
 * Dependency-free prerender for the VitaX reader.
 *
 * Usage: node scripts/prerender.mjs <snapshot.json> <dist-dir> [out-dir]
 *
 * The snapshot is the accepted public release projection (schema_version 1:
 * release_id, published_at, documents, evidence, knowledge, entities,
 * relations). Records marked `visibility: "private"` are dropped, only
 * whitelisted fields are rendered, and every generated page keeps the built
 * shell so the reader bundle, its styles and its script tags still work.
 *
 * The generated markup is static output only: the reader deliberately replaces
 * `#root` after `/api/release` has been confirmed. Nothing here is hydrated and
 * no framework takeover is implied.
 */
import {cp, mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {pathToFileURL} from 'node:url';

const KINDS = new Set(['article', 'wiki']);
const SITE_TITLE = 'VitaX 知识阅读';
const ROOT_ELEMENT = '<div id="root"></div>';
const FORBIDDEN_SEGMENTS = new Set(['.', '..']);

const ESCAPES = {['&']: '&amp;', ['<']: '&lt;', ['>']: '&gt;', ['"']: '&quot;', ["'"]: '&#39;'};

/** @param {unknown} value @returns {string} */
export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ESCAPES[character]);
}

/**
 * Keep only absolute http(s) links; anything else is not a usable source link.
 * @param {unknown} value
 * @returns {string|null}
 */
export function safeUrl(value) {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return /^https?:\/\/[^\s]+$/i.test(trimmed) ? trimmed : null;
}

function isObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requiredText(value, name) {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`${name} must be a nonempty string`);
  return value;
}

/** Index public records by id; unmarked or private records never leave this step. */
function publicRecords(values, idField, label) {
  const records = new Map();
  const seen = new Set();
  for (const record of Array.isArray(values) ? values : []) {
    if (!isObject(record)) throw new Error(`${label} entries must be objects`);
    const id = requiredText(record[idField], `${label}.${idField}`);
    if (seen.has(id)) throw new Error(`duplicate ${idField}: ${id}`);
    seen.add(id);
    if (record.visibility === 'public') records.set(id, record);
  }
  return records;
}

function evidenceIds(value) {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new Error('evidence_ids must be a list');
  return value.map((id) => requiredText(id, 'evidence_id'));
}

/**
 * Keep the identifier usable as one filesystem directory name. Unicode and
 * spaces are valid segments and are used as-is; NUL, the path separators `/`
 * and `\`, and the relative segments `.` / `..` are rejected so a snapshot can
 * never write outside the output directory.
 * @param {unknown} id
 * @returns {string|null}
 */
function safeSegment(id) {
  if (typeof id !== 'string' || id === '') return null;
  if (FORBIDDEN_SEGMENTS.has(id)) return null;
  if (id.includes('\0') || id.includes('/') || id.includes('\\')) return null;
  return id;
}

function itemPath(item) {
  return `/${item.kind}/${encodeURIComponent(item.id)}`;
}

/**
 * Reduce a release snapshot to the public reading view: no private records,
 * no unknown fields, deterministic order.
 * @param {unknown} snapshot
 */
export function publicSnapshot(snapshot) {
  if (!isObject(snapshot)) throw new Error('release snapshot must be a JSON object');
  const releaseId = requiredText(snapshot.release_id, 'release_id');
  const publishedAt = requiredText(snapshot.published_at, 'published_at');

  const documents = publicRecords(snapshot.documents, 'revision_id', 'documents');
  const evidence = new Map();
  for (const [id, record] of publicRecords(snapshot.evidence, 'evidence_id', 'evidence')) {
    const document = documents.get(requiredText(record.revision_id, 'evidence.revision_id'));
    if (document === undefined) continue; // private or unknown source document
    evidence.set(id, {
      evidence_id: id,
      locator: requiredText(record.locator, 'evidence.locator'),
      quote: requiredText(record.quote, 'evidence.quote'),
      document: {
        title: requiredText(document.title, 'document.title'),
        source_url: safeUrl(document.source_url),
      },
    });
  }

  const entities = [...publicRecords(snapshot.entities, 'entity_id', 'entities')]
    .map(([id, record]) => ({entity_id: id, name: requiredText(record.name, 'entity.name')}))
    .sort((left, right) => left.entity_id.localeCompare(right.entity_id));
  const names = new Map(entities.map((entity) => [entity.entity_id, entity.name]));

  const relations = [];
  for (const [id, record] of publicRecords(snapshot.relations, 'relation_id', 'relations')) {
    const source = names.get(requiredText(record.source_id, 'relation.source_id'));
    const target = names.get(requiredText(record.target_id, 'relation.target_id'));
    if (source === undefined || target === undefined) continue; // private endpoint
    relations.push({
      relation_id: id,
      source_id: record.source_id,
      target_id: record.target_id,
      relation_type: requiredText(record.relation_type, 'relation.relation_type'),
      source_name: source,
      target_name: target,
      evidence_ids: evidenceIds(record.evidence_ids).filter((evidence_id) => evidence.has(evidence_id)),
    });
  }
  relations.sort((left, right) => left.relation_id.localeCompare(right.relation_id));

  const items = [];
  for (const [id, record] of publicRecords(snapshot.knowledge, 'knowledge_id', 'knowledge')) {
    const kind = requiredText(record.kind, 'knowledge.kind');
    if (!KINDS.has(kind)) throw new Error(`knowledge.kind must be article or wiki: ${kind}`);
    items.push({
      id,
      kind,
      title: requiredText(record.title, 'knowledge.title'),
      body: requiredText(record.body, 'knowledge.body'),
      evidence: evidenceIds(record.evidence_ids)
        .map((evidence_id) => evidence.get(evidence_id))
        .filter((entry) => entry !== undefined),
    });
  }
  items.sort((left, right) => left.id.localeCompare(right.id));

  return {releaseId, publishedAt, items, entities, relations};
}

function renderEntitySection(entities, relations) {
  if (entities.length === 0) return '';
  const entries = entities.map((entity) => {
    const related = relations.filter(
      (relation) => relation.source_id === entity.entity_id || relation.target_id === entity.entity_id,
    );
    const body =
      related.length === 0
        ? '<p>暂无已公开关系。</p>'
        : `<ul>${related
            .map(
              (relation) =>
                `<li>${escapeHtml(relation.source_name)} —[${escapeHtml(relation.relation_type)}]→ ` +
                `${escapeHtml(relation.target_name)} <span>证据：${relation.evidence_ids
                  .map((id) => escapeHtml(id))
                  .join('、')}</span></li>`,
            )
            .join('')}</ul>`;
    return `<li id="entity-${escapeHtml(entity.entity_id)}"><h3>${escapeHtml(entity.name)}</h3>${body}</li>`;
  });
  return `<section aria-label="实体与关系"><h2>实体与关系</h2><ul>${entries.join('')}</ul></section>`;
}

function renderEvidenceSection(evidence) {
  if (evidence.length === 0) return '<section aria-label="证据与来源"><h2>证据与来源</h2><p>该条目没有关联证据。</p></section>';
  const entries = evidence.map((entry) => {
    const source =
      entry.document.source_url === null
        ? `<span>${escapeHtml(entry.document.title)}</span>`
        : `<a href="${escapeHtml(entry.document.source_url)}" rel="noreferrer noopener">${escapeHtml(entry.document.title)}</a>`;
    return `<li><blockquote><p>${escapeHtml(entry.quote)}</p></blockquote><p>定位：${escapeHtml(
      entry.locator,
    )}</p><p>来源：${source}</p></li>`;
  });
  return `<section aria-label="证据与来源"><h2>证据与来源</h2><ul>${entries.join('')}</ul></section>`;
}

function renderIndex(view, items) {
  const list =
    items.length === 0
      ? '<p>当前 release 没有可公开的知识条目。</p>'
      : `<ul>${items
          .map(
            (item) =>
              `<li><a href="${escapeHtml(itemPath(item))}">${escapeHtml(item.title)}</a> ` +
              `<span>${item.kind === 'wiki' ? 'Wiki 词条' : '文章解读'}</span></li>`,
          )
          .join('')}</ul>`;
  return [
    '<header><p>VitaX · 公开知识阅读</p></header>',
    '<main id="main">',
    `<h1>${escapeHtml(SITE_TITLE)}</h1>`,
    `<p>当前 release：<code>${escapeHtml(view.releaseId)}</code>（发布于 ${escapeHtml(view.publishedAt)}）。</p>`,
    `<section aria-label="知识列表"><h2>知识条目（${items.length}）</h2>${list}</section>`,
    renderEntitySection(view.entities, view.relations),
    '</main>',
    `<footer><p>release <code>${escapeHtml(view.releaseId)}</code></p></footer>`,
  ].join('\n');
}

function renderDetail(view, item) {
  const paragraphs = item.body
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line !== '')
    .map((line) => `<p>${escapeHtml(line)}</p>`)
    .join('');
  return [
    '<header><p>VitaX · 公开知识阅读</p></header>',
    '<main id="main">',
    '<p><a href="/">← 返回知识列表</a></p>',
    '<article>',
    `<p>${item.kind === 'wiki' ? 'Wiki 词条' : '文章解读'}</p>`,
    `<h1>${escapeHtml(item.title)}</h1>`,
    paragraphs,
    renderEvidenceSection(item.evidence),
    '</article>',
    '</main>',
    `<footer><p>release <code>${escapeHtml(view.releaseId)}</code>（发布于 ${escapeHtml(view.publishedAt)}）</p></footer>`,
  ].join('\n');
}

function renderDocument(shell, title, body) {
  if (!shell.includes(ROOT_ELEMENT)) {
    throw new Error('built shell must contain an empty <div id="root"></div> to host prerendered content');
  }
  if (!/<title>[\s\S]*?<\/title>/.test(shell)) throw new Error('built shell must contain a <title> element');
  return shell
    .replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(title)}</title>`)
    .replace(ROOT_ELEMENT, `<div id="root">\n${body}\n</div>`);
}

/**
 * Write prerendered index, article and wiki documents into the built site.
 * @param {{snapshot: unknown, distDir: string, outDir?: string|null}} options
 * @returns {Promise<{written: string[], skipped: {id: string, kind: string, reason: string}[]}>}
 *   written paths relative to the output directory, plus reported skips
 */
export async function prerenderRelease({snapshot, distDir, outDir = undefined}) {
  const view = publicSnapshot(snapshot);
  const source = path.resolve(distDir);
  const target = path.resolve(outDir ?? distDir);
  if (target !== source) await cp(source, target, {recursive: true});
  const shell = await readFile(path.join(target, 'index.html'), 'utf8');

  const written = [];
  const skipped = [];
  const write = async (relative, html) => {
    const file = path.join(target, relative);
    await mkdir(path.dirname(file), {recursive: true});
    await writeFile(file, html, 'utf8');
    written.push(relative);
  };

  const routeable = [];
  for (const item of view.items) {
    const segment = safeSegment(item.id);
    if (segment === null) {
      // Reported, never written: the identifier cannot be one directory name.
      // The API-driven client route decides its fate after bootstrap.
      skipped.push({id: item.id, kind: item.kind, reason: 'identifier is not a usable path segment'});
      continue;
    }
    routeable.push({item, segment});
  }

  // Every link in the generated index must resolve, so only items that get a
  // written page are listed there.
  await write('index.html', renderDocument(shell, SITE_TITLE, renderIndex(view, routeable.map((entry) => entry.item))));
  for (const {item, segment} of routeable) {
    await write(
      path.join(item.kind, segment, 'index.html'),
      renderDocument(shell, `${item.title} · ${SITE_TITLE}`, renderDetail(view, item)),
    );
  }
  return {written, skipped};
}

/** @param {string[]} [argv] @returns {Promise<number>} process exit code */
export async function main(argv = process.argv.slice(2)) {
  const [snapshotPath, distDir, outDir] = argv;
  if (snapshotPath === undefined || distDir === undefined) {
    process.stderr.write('usage: node scripts/prerender.mjs <snapshot.json> <dist-dir> [out-dir]\n');
    return 2;
  }
  const snapshot = JSON.parse(await readFile(snapshotPath, 'utf8'));
  const {written, skipped} = await prerenderRelease({snapshot, distDir, outDir});
  process.stdout.write(`prerendered ${written.length} document(s): ${written.join(', ')}\n`);
  if (skipped.length > 0) {
    process.stderr.write(`skipped ${skipped.length} unusable identifier(s): ${skipped.map((entry) => `${entry.id} (${entry.reason})`).join(', ')}\n`);
  }
  return 0;
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().then(
    (code) => {
      process.exitCode = code;
    },
    (error) => {
      process.stderr.write(`error: ${error instanceof Error ? error.message : String(error)}\n`);
      process.exitCode = 1;
    },
  );
}

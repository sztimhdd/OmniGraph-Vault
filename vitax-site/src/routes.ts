/** Pure path/query routing for the reader. No DOM access, no data access. */
import type {KindFilter, KnowledgeKind, KnowledgeSummary, Route} from './types.ts';

const KINDS: readonly KnowledgeKind[] = ['article', 'wiki'];

/**
 * Where the knowledge list lives. Public-only keeps `/`; an instance that also
 * serves the article library makes the library the home and moves this list to
 * `/knowledge`. Set once at boot by `main.tsx`.
 */
let listBase = '/';

export function setListBase(base: string): void {
  listBase = base === '/knowledge' ? '/knowledge' : '/';
}

function isKind(value: string): value is KnowledgeKind {
  return (KINDS as readonly string[]).includes(value);
}

/** Read the search state from a location search string. */
export function parseQuery(search: string): {q: string; kind: KindFilter} {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const q = (params.get('q') ?? '').trim();
  const kind = params.get('kind') ?? '';
  return {q, kind: isKind(kind) ? kind : 'all'};
}

function encodeSearch(parts: string[]): string {
  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

function listSearch({q, kind}: {q: string; kind: KindFilter}): string {
  const parts: string[] = [];
  const query = q.trim();
  if (query !== '') parts.push(`q=${encodeURIComponent(query)}`);
  if (kind !== 'all') parts.push(`kind=${kind}`);
  return encodeSearch(parts);
}

export function listPath(state: {q: string; kind: KindFilter}): string {
  const search = listSearch(state);
  return listBase === '/' ? `/${search}` : `${listBase}${search}`;
}

function decodeIdentifier(segment: string): string | null {
  let value: string;
  try {
    value = decodeURIComponent(segment);
  } catch {
    return null;
  }
  if (value === '' || value.includes('/') || value.includes('\\')) return null;
  return value;
}

/**
 * Resolve a request path to a route. Anything that is not one of the supported
 * routes stays `unknown` so the UI can show a not-found state instead of
 * falling back to an arbitrary record.
 */
export function parseRoute(pathname: string, search = ''): Route {
  const {q, kind} = parseQuery(search);
  const path = pathname.replace(/\/+$/, '');
  if (path === '' || path === '/index.html') return {name: 'list', q, kind};
  if (path === '/knowledge' || path === '/knowledge/index.html') return {name: 'list', q, kind};

  const segments = path.startsWith('/') ? path.slice(1).split('/') : path.split('/');
  // A terminal `index.html` is only the generated file suffix of the three
  // segment detail form (`/article/<id>/index.html`). In the two segment form it
  // is a knowledge id of its own: `/article/index.html` means id `index.html`.
  const suffix = segments.length === 3 && segments[2] === 'index.html' ? 1 : 0;
  if (segments.length - suffix !== 2) return {name: 'unknown', path: pathname};
  const collection = segments[0];
  const raw = segments[1];
  if (collection !== 'article' && collection !== 'wiki') return {name: 'unknown', path: pathname};
  const id = decodeIdentifier(raw);
  if (id === null) return {name: 'unknown', path: pathname};
  return {name: collection, id};
}

export function routeToPath(route: Route): string {
  switch (route.name) {
    case 'list':
      return listPath({q: route.q, kind: route.kind});
    case 'article':
    case 'wiki':
      return `/${route.name}/${encodeURIComponent(route.id)}`;
    default:
      return route.path;
  }
}

export function itemPath(item: Pick<KnowledgeSummary, 'knowledge_id' | 'kind'>, returnTo?: string): string {
  const path = routeToPath(item.kind === 'wiki' ? {name: 'wiki', id: item.knowledge_id} : {name: 'article', id: item.knowledge_id});
  return returnTo === undefined ? path : withReturn(path, returnTo);
}

/** Accept only an internal reader path so a "return" link cannot leave the site. */
export function safeReturnTarget(value: string | null | undefined, fallback: string): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\s\\]/.test(value)) return fallback;
  return value;
}

/** Carry the list state through a detail link without a global store. */
export function withReturn(path: string, returnTo: string): string {
  return `${path}${path.includes('?') ? '&' : '?'}return=${encodeURIComponent(returnTo)}`;
}

/** A named route only accepts knowledge of the kind it names. */
export function routeMatchesKind(route: Route, kind: KnowledgeKind): boolean {
  return route.name === kind;
}

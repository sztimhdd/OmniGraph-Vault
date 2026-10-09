/** Browser client for the same-origin read API from `vitax.api`. */
import type {
  Entity,
  Evidence,
  KnowledgeItem,
  KnowledgeKind,
  KnowledgeSummary,
  KindFilter,
  Relation,
  Release,
} from './types.ts';

const MAX_LIMIT = 100;
const MAX_QUERY_LENGTH = 512;
const RELEASE_PATH = '/api/release';

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

/** The reader could not reach the knowledge service at all. */
export class NetworkError extends ApiError {
  constructor(message: string) {
    super(message);
    this.name = 'NetworkError';
  }
}

/** The release does not contain the requested identifier. */
export class NotFoundError extends ApiError {
  constructor(message: string) {
    super(message);
    this.name = 'NotFoundError';
  }
}

/** A response came from a different release than the pinned one. */
export class ReleaseMismatchError extends ApiError {
  constructor(message: string) {
    super(message);
    this.name = 'ReleaseMismatchError';
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function text(value: unknown): string {
  if (typeof value !== 'string' || value === '') throw new ApiError('知识服务返回了不符合约定的字段');
  return value;
}

/** Optional contract fields stay null when the release does not carry them. */
function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null;
}

function textList(value: unknown): string[] {
  if (!Array.isArray(value)) throw new ApiError('知识服务返回了不符合约定的字段');
  return value.map(text);
}

export function readReleaseMetadata(payload: unknown): Release {
  if (!isObject(payload)) throw new ApiError('知识服务未返回 release 元数据');
  return {release_id: text(payload.release_id), published_at: text(payload.published_at)};
}

/** Pin the release of every response to the first release seen in the session. */
export function assertReleaseConsistent(pinned: string | null, payload: unknown): string {
  const release = readReleaseMetadata(payload);
  if (pinned !== null && release.release_id !== pinned) {
    throw mismatchError(pinned, release.release_id);
  }
  return release.release_id;
}

function mismatchError(pinnedRelease: string, actualRelease: string): ReleaseMismatchError {
  return new ReleaseMismatchError(
    `知识服务在前端会话中切换了 release（${pinnedRelease} → ${actualRelease}），请刷新页面。`,
  );
}

/** Tolerant identity read: a domain error may carry `release_id` without the rest. */
function readReleaseIdentity(payload: unknown): string | null {
  if (!isObject(payload)) return null;
  const value = payload.release_id;
  return typeof value === 'string' && value !== '' ? value : null;
}

function readKind(value: unknown): KnowledgeKind {
  if (value !== 'article' && value !== 'wiki') throw new ApiError('知识服务返回了未知的知识类型');
  return value;
}

function readSummary(value: unknown): KnowledgeSummary {
  if (!isObject(value)) throw new ApiError('知识服务返回了不符合约定的字段');
  return {
    knowledge_id: text(value.knowledge_id),
    kind: readKind(value.kind),
    title: text(value.title),
  };
}

function readKnowledgeItem(payload: Record<string, unknown>): KnowledgeItem {
  if (!isObject(payload.knowledge)) throw new ApiError('知识服务未返回知识条目');
  const item = payload.knowledge;
  return {
    knowledge_id: text(item.knowledge_id),
    kind: readKind(item.kind),
    title: text(item.title),
    body: text(item.body),
    rendered_html: optionalText(item.rendered_html),
    evidence_ids: textList(item.evidence_ids ?? []),
    image_url: optionalText(item.image_url),
    image_caption: optionalText(item.image_caption),
  };
}

function readEvidence(payload: Record<string, unknown>): Evidence {
  if (!isObject(payload.evidence)) throw new ApiError('知识服务未返回证据');
  const item = payload.evidence;
  if (!isObject(item.document)) throw new ApiError('知识服务未返回证据来源');
  return {
    evidence_id: text(item.evidence_id),
    revision_id: text(item.revision_id),
    locator: text(item.locator),
    quote: text(item.quote),
    document: {
      doc_id: text(item.document.doc_id),
      title: text(item.document.title),
      source_url: text(item.document.source_url),
    },
  };
}

function readEntity(value: unknown): Entity {
  if (!isObject(value)) throw new ApiError('知识服务返回了不符合约定的字段');
  return {entity_id: text(value.entity_id), name: text(value.name)};
}

function readRelation(value: unknown): Relation {
  if (!isObject(value)) throw new ApiError('知识服务返回了不符合约定的字段');
  return {
    relation_id: text(value.relation_id),
    source_id: text(value.source_id),
    target_id: text(value.target_id),
    relation_type: text(value.relation_type),
    source_name: text(value.source_name),
    target_name: text(value.target_name),
    evidence_ids: textList(value.evidence_ids ?? []),
  };
}

function readList<T>(payload: Record<string, unknown>, key: string, read: (value: unknown) => T): T[] {
  const values = payload[key];
  if (!Array.isArray(values)) throw new ApiError('知识服务返回了不符合约定的列表');
  return values.map(read);
}

function boundedLimit(limit: number): number {
  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
    throw new ApiError(`limit 必须在 1 到 ${MAX_LIMIT} 之间`);
  }
  return limit;
}

export interface KnowledgeApi {
  /**
   * Read `/api/release` first. This pins the session release; every other read
   * is refused until it resolves, so panels can never race against it.
   */
  bootstrap(): Promise<Release>;
  /** Subscribe to the fail-closed signal raised by any cross-release response. */
  onReleaseMismatch(listener: (error: ReleaseMismatchError) => void): () => void;
  list(params?: {q?: string; kind?: KindFilter; limit?: number}): Promise<KnowledgeSummary[]>;
  knowledge(id: string): Promise<KnowledgeItem>;
  evidence(id: string): Promise<Evidence>;
  entities(limit?: number): Promise<Entity[]>;
  relations(entityId: string, limit?: number): Promise<Relation[]>;
}

export function createKnowledgeApi(fetchImpl: typeof fetch): KnowledgeApi {
  let pinned: string | null = null;
  const mismatchListeners = new Set<(error: ReleaseMismatchError) => void>();

  function reportMismatch(error: ReleaseMismatchError): void {
    for (const listener of mismatchListeners) listener(error);
  }

  async function send(path: string): Promise<Response> {
    try {
      return await fetchImpl(path, {headers: {accept: 'application/json'}});
    } catch {
      throw new NetworkError('无法连接知识服务，请确认本地读取服务正在运行。');
    }
  }

  async function readJson(response: Response): Promise<Record<string, unknown> | null> {
    try {
      const payload: unknown = await response.json();
      return isObject(payload) ? payload : null;
    } catch {
      return null;
    }
  }

  /**
   * Dedicated release re-read for a domain error that carries no release
   * metadata. It never re-enters the domain error handling and never re-pins,
   * so a failing check cannot recurse.
   */
  async function probeReleaseIdentity(): Promise<string | null> {
    try {
      const response = await send(RELEASE_PATH);
      return response.ok ? readReleaseIdentity(await readJson(response)) : null;
    } catch {
      return null;
    }
  }

  function assertReleaseUnchanged(actualRelease: string): void {
    if (pinned === null || actualRelease === pinned) return;
    const error = mismatchError(pinned, actualRelease);
    reportMismatch(error);
    throw error;
  }

  /**
   * A failed read may still belong to a release that is no longer the pinned
   * one. Validate that before any status code is mapped to a local error, so a
   * cross-release 404 fails the session closed instead of rendering not-found.
   */
  async function confirmFailedRead(path: string, payload: Record<string, unknown> | null): Promise<void> {
    if (pinned === null || path === RELEASE_PATH) return;
    const inline = readReleaseIdentity(payload);
    if (inline !== null) {
      assertReleaseUnchanged(inline);
      return;
    }
    const probed = await probeReleaseIdentity();
    if (probed !== null) assertReleaseUnchanged(probed);
  }

  async function request(path: string, {requirePinned}: {requirePinned: boolean}): Promise<Record<string, unknown>> {
    if (requirePinned && pinned === null) {
      throw new ApiError('尚未确认 release，读取已被拒绝。');
    }
    const response = await send(path);
    const payload = await readJson(response);
    if (!response.ok) {
      await confirmFailedRead(path, payload);
      if (response.status === 404) throw new NotFoundError('该标识不存在于当前 release。');
      throw new ApiError(`知识服务请求失败（HTTP ${response.status}）。`);
    }
    if (payload === null) throw new ApiError('知识服务返回了无法解析的响应。');
    try {
      pinned = assertReleaseConsistent(pinned, payload);
    } catch (error) {
      if (error instanceof ReleaseMismatchError) reportMismatch(error);
      throw error;
    }
    return payload;
  }

  async function read<T>(path: string, readValue: (payload: Record<string, unknown>) => T): Promise<T> {
    return readValue(await request(path, {requirePinned: true}));
  }

  return {
    async bootstrap() {
      return readReleaseMetadata(await request(RELEASE_PATH, {requirePinned: false}));
    },
    onReleaseMismatch(listener) {
      mismatchListeners.add(listener);
      return () => {
        mismatchListeners.delete(listener);
      };
    },
    async list(params = {}) {
      const parts: string[] = [];
      const q = (params.q ?? '').trim();
      if (q !== '') {
        if (q.length > MAX_QUERY_LENGTH) throw new ApiError(`检索词不能超过 ${MAX_QUERY_LENGTH} 个字符`);
        parts.push(`q=${encodeURIComponent(q)}`);
      }
      if (params.kind !== undefined && params.kind !== 'all') parts.push(`kind=${params.kind}`);
      if (params.limit !== undefined) parts.push(`limit=${boundedLimit(params.limit)}`);
      const query = parts.length === 0 ? '' : `?${parts.join('&')}`;
      return read(`/api/knowledge${query}`, (payload) => readList(payload, 'results', readSummary));
    },
    async knowledge(id) {
      return read(`/api/knowledge/${encodeURIComponent(id)}`, readKnowledgeItem);
    },
    async evidence(id) {
      return read(`/api/evidence/${encodeURIComponent(id)}`, readEvidence);
    },
    async entities(limit) {
      const query = limit === undefined ? '' : `?limit=${boundedLimit(limit)}`;
      return read(`/api/entities${query}`, (payload) => readList(payload, 'results', readEntity));
    },
    async relations(entityId, limit) {
      const query = limit === undefined ? '' : `?limit=${boundedLimit(limit)}`;
      return read(`/api/entities/${encodeURIComponent(entityId)}/related${query}`, (payload) =>
        readList(payload, 'relations', readRelation),
      );
    },
  };
}

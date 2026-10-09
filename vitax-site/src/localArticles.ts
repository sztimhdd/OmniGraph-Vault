/** The private archive uses snapshot identity, independently of public releases. */
export type ArticleView = 'original' | 'translated' | 'rewrite';

export interface ArticleSummary {
  source: 'wechat' | 'rss';
  record_id: number;
  title: string | null;
  title_translated: string | null;
  source_url: string | null;
  lang: string | null;
  captured_at: string | null;
  body_available: boolean;
  translation_available: boolean;
  rewrite_available: boolean;
}
export interface ArticleDetail extends ArticleSummary {
  snapshot_id: string;
  body: string | null;
  body_translated: string | null;
  body_rewritten: string | null;
  translated_lang: string | null;
  body_html: string | null;
  body_translated_html: string | null;
  body_rewritten_html: string | null;
}
export interface ArticlePage {snapshot_id: string; items: ArticleSummary[]; next_offset: number | null}
export interface LibraryStatus {
  snapshot_id: string;
  observed_at: string;
  counts: Record<'wechat' | 'rss', {total: number; with_body: number; with_translation: number; with_rewrite: number}>;
}
export interface LibraryQuery {q: string; source: string; offset: number; hasBody: boolean}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('文章库返回了无效数据');
  return value as Record<string, unknown>;
}
function snapshot(value: Record<string, unknown>): string {
  if (typeof value.snapshot_id !== 'string' || !value.snapshot_id.trim()) throw new Error('无法确认文章数据快照');
  return value.snapshot_id;
}
function summary(value: unknown): ArticleSummary {
  const item = object(value);
  if ((item.source !== 'wechat' && item.source !== 'rss') || !Number.isSafeInteger(item.record_id) || Number(item.record_id) < 1) throw new Error('文章来源标识无效');
  for (const key of ['title', 'title_translated', 'source_url', 'lang', 'captured_at']) {
    if (item[key] !== null && typeof item[key] !== 'string') throw new Error('文章元数据无效');
  }
  for (const key of ['body_available', 'translation_available', 'rewrite_available']) {
    if (typeof item[key] !== 'boolean') throw new Error('文章内容状态无效');
  }
  return item as unknown as ArticleSummary;
}
export function parseLibraryPage(value: unknown): ArticlePage {
  const page = object(value);
  if (!Array.isArray(page.items) || (page.next_offset !== null && (!Number.isSafeInteger(page.next_offset) || Number(page.next_offset) < 0))) throw new Error('文章分页无效');
  return {snapshot_id: snapshot(page), items: page.items.map(summary), next_offset: page.next_offset as number | null};
}
export function parseLibraryDetail(value: unknown): ArticleDetail {
  const item = object(value);
  for (const key of ['body', 'body_translated', 'body_rewritten', 'translated_lang', 'body_html', 'body_translated_html', 'body_rewritten_html']) {
    if (item[key] !== null && typeof item[key] !== 'string') throw new Error('文章正文无效');
  }
  return {
    ...summary(item),
    snapshot_id: snapshot(item),
    body: item.body as string | null,
    body_translated: item.body_translated as string | null,
    body_rewritten: item.body_rewritten as string | null,
    translated_lang: item.translated_lang as string | null,
    body_html: item.body_html as string | null,
    body_translated_html: item.body_translated_html as string | null,
    body_rewritten_html: item.body_rewritten_html as string | null,
  };
}
export function parseLibraryStatus(value: unknown): LibraryStatus {
  const status = object(value); snapshot(status);
  if (typeof status.observed_at !== 'string') throw new Error('快照时间无效');
  const counts = object(status.counts);
  for (const source of ['wechat', 'rss']) {
    const entry = object(counts[source]);
    for (const key of ['total', 'with_body', 'with_translation', 'with_rewrite']) {
      if (!Number.isSafeInteger(entry[key]) || Number(entry[key]) < 0) throw new Error('文章计数无效');
    }
  }
  return status as unknown as LibraryStatus;
}
export async function fetchLibrary<T>(url: string, parse: (value: unknown) => T, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {signal});
  if (!response.ok) {
    if (response.status === 409) throw new Error('文章镜像正在更新，请重新读取。');
    if (response.status === 404) throw new Error('文章不存在，或本地文章库未启用。');
    throw new Error(`文章库读取失败（${response.status}）`);
  }
  return parse(await response.json());
}
export function sourceLink(value: string | null): string | null {
  if (!value) return null;
  try {const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null;} catch {return null;}
}

export function articleTitle(item: Pick<ArticleSummary, 'title' | 'title_translated'>): string {
  const chinese = /\p{Script=Han}/u;
  if (item.title && chinese.test(item.title)) return item.title;
  if (item.title_translated && chinese.test(item.title_translated)) return item.title_translated;
  return item.title || item.title_translated || '无标题';
}

export function sourceLabel(source: ArticleSummary['source']): string {
  return source === 'wechat' ? '微信公众号' : 'RSS';
}

export function sourceHost(value: string | null): string | null {
  const link = sourceLink(value);
  if (link === null) return null;
  try {
    return new URL(link).hostname;
  } catch {
    return null;
  }
}

export function articleStatus(item: Pick<ArticleSummary, 'body_available' | 'translation_available' | 'rewrite_available'>): string {
  const parts: string[] = [];
  if (item.body_available) parts.push('原文可读');
  if (item.translation_available) parts.push('已有译文');
  if (item.rewrite_available) parts.push('已有整理稿');
  return parts.length > 0 ? parts.join(' · ') : '暂无正文';
}

export function displayDate(value: string | null): string {
  if (!value) return '采集时间未记录';
  const date = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return value.slice(0, 10) || '采集时间未记录';
  return new Intl.DateTimeFormat('zh-CN', {dateStyle: 'medium', timeZone: 'America/Halifax'}).format(date);
}

export function availableViews(item: ArticleSummary): ArticleView[] {
  const views: ArticleView[] = [];
  if (item.body_available) views.push('original');
  if (item.translation_available) views.push('translated');
  if (item.rewrite_available) views.push('rewrite');
  return views;
}

export function defaultView(item: ArticleSummary): ArticleView {
  if (item.rewrite_available) return 'rewrite';
  if (item.body_available) return 'original';
  return 'translated';
}

export const VIEW_LABELS: Record<ArticleView, string> = {original: '原文', translated: '已有译文', rewrite: '整理稿'};

export function viewHtml(item: ArticleDetail, view: ArticleView): string | null {
  if (view === 'rewrite') return item.body_rewritten_html;
  if (view === 'translated') return item.body_translated_html;
  return item.body_html;
}

export function libraryListPath(state: LibraryQuery): string {
  const params = new URLSearchParams({q: state.q, limit: '20', offset: String(state.offset), has_body: String(state.hasBody)});
  if (state.source) params.set('source', state.source);
  return `/library?${params}`;
}

export function libraryItemPath(item: Pick<ArticleSummary, 'source' | 'record_id'>, state: LibraryQuery): string {
  return `/library/${item.source}/${item.record_id}?return=${encodeURIComponent(libraryListPath(state))}`;
}

/** Accept only an internal library return target so "back" can never leave the site. */
export function safeLibraryReturn(value: string | null): string {
  if (!value || !value.startsWith('/library')) return '/library';
  if (value.startsWith('//') || /[\s\\]/.test(value)) return '/library';
  return value;
}

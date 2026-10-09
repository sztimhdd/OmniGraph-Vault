import {useEffect, useRef, useState} from 'react';

import {
  articleStatus,
  articleTitle,
  availableViews,
  defaultView,
  displayDate,
  fetchLibrary,
  libraryItemPath,
  libraryListPath,
  parseLibraryDetail,
  parseLibraryPage,
  parseLibraryStatus,
  safeLibraryReturn,
  sourceHost,
  sourceLabel,
  VIEW_LABELS,
  viewHtml,
  type ArticleDetail,
  type ArticlePage,
  type ArticleView,
  type LibraryQuery,
  type LibraryStatus,
} from '../localArticles.ts';
import {listPath} from '../routes.ts';
import {ArticleBody} from './ArticleBody.tsx';

export function LocalArticlesPage({publicKnowledge}: {publicKnowledge: boolean}) {
  const params = new URLSearchParams(window.location.search);
  const segments = window.location.pathname.split('/').filter(Boolean);
  const detail = segments[0] === 'library' && segments.length === 3;
  const invalid = segments[0] === 'library' && segments.length !== 1 && !detail;
  const initialSource = params.get('source') ?? '';
  const [query, setQuery] = useState(params.get('q') ?? '');
  const [source, setSource] = useState(['wechat', 'rss'].includes(initialSource) ? initialSource : '');
  const parsedOffset = Number(params.get('offset') ?? '0');
  const [offset, setOffset] = useState(Number.isSafeInteger(parsedOffset) && parsedOffset >= 0 ? parsedOffset : 0);
  const [search, setSearch] = useState(query);
  const [hasBody, setHasBody] = useState(params.get('has_body') !== 'false');
  const [view, setView] = useState<ArticleView>('original');
  const [retry, setRetry] = useState(0);
  const [value, setValue] = useState<{status: LibraryStatus; page: ArticlePage | null; item: ArticleDetail | null} | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastSnapshot = useRef<string | null>(null);
  const promotionRetried = useRef(false);
  const listState: LibraryQuery = {q: search, source, offset, hasBody};

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      void fetchLibrary('/api/library/status', parseLibraryStatus, controller.signal)
        .then(status => {if (lastSnapshot.current && status.snapshot_id !== lastSnapshot.current) setRetry(n => n + 1);})
        .catch(() => {});
    }, 60_000);
    return () => {window.clearInterval(timer); controller.abort();};
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setValue(null); setError(null);
    if (invalid) {setError('该文章地址不存在。'); return () => controller.abort();}
    const result = detail
      ? fetchLibrary(`/api/library/${encodeURIComponent(segments[1])}/${encodeURIComponent(segments[2])}`, parseLibraryDetail, controller.signal)
      : fetchLibrary(`/api${libraryListPath(listState)}`, parseLibraryPage, controller.signal);
    void Promise.all([fetchLibrary('/api/library/status', parseLibraryStatus, controller.signal), result])
      .then(([status, data]) => {
        if (controller.signal.aborted) return;
        if (status.snapshot_id !== data.snapshot_id) {
          if (!promotionRetried.current) {
            promotionRetried.current = true;
            setOffset(0); setRetry(n => n + 1); return;
          }
          setError('文章库正在更新，请重新读取。'); return;
        }
        promotionRetried.current = false;
        const changed = lastSnapshot.current !== null && lastSnapshot.current !== data.snapshot_id;
        lastSnapshot.current = data.snapshot_id;
        if (changed && !detail && offset !== 0) {setOffset(0); return;}
        if (detail) setView(defaultView(data as ArticleDetail));
        setValue({status, page: detail ? null : data as ArticlePage, item: detail ? data as ArticleDetail : null});
      }).catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '读取失败');
      });
    if (!detail) window.history.replaceState(null, '', libraryListPath(listState));
    return () => controller.abort();
  }, [search, source, offset, retry, detail, invalid, hasBody]);

  const item = value?.item;
  const status = value?.status;
  const total = status ? status.counts.wechat.total + status.counts.rss.total : null;
  const originalCount = status ? status.counts.wechat.with_body + status.counts.rss.with_body : null;
  const translationCount = status ? status.counts.wechat.with_translation + status.counts.rss.with_translation : null;
  const rewriteCount = status ? status.counts.wechat.with_rewrite + status.counts.rss.with_rewrite : null;
  const host = item ? sourceHost(item.source_url) : null;
  const knowledgeHref = listPath({q: search, kind: 'all'});
  const button = 'rounded-md border border-stone-300 bg-white px-3 py-2 text-sm disabled:opacity-40';
  const views = item ? availableViews(item) : [];
  const activeView = item ? (views.includes(view) ? view : defaultView(item)) : 'original';
  const html = item ? viewHtml(item, activeView) : null;

  return <div className="min-h-screen bg-[#FBFBFA] text-stone-900">
    <header className="border-b border-stone-200 bg-white px-4 py-4"><nav className="mx-auto flex max-w-5xl items-center gap-5">
      <a href="/library" className="text-xl font-bold">VitaX · 文章库</a>
      <span className="text-xs text-stone-500">原文 · 译文 · 整理稿</span>
      {publicKnowledge ? <a href={knowledgeHref} className="ml-auto text-sm text-blue-700">文章解读与 Wiki</a> : null}
    </nav></header>
    <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      {detail ? <a href={safeLibraryReturn(params.get('return'))} className="mb-4 inline-block text-sm text-blue-700">返回文章库</a> : <>
        <h1 className="text-2xl font-bold">文章库</h1>
        <p className="mt-2 text-sm text-stone-600">{total !== null ? `${total.toLocaleString()} 条来源记录 · ${originalCount?.toLocaleString()} 份原文 · ${translationCount?.toLocaleString()} 份译文 · ${rewriteCount?.toLocaleString()} 份整理稿` : '正在读取文章数据…'}</p>
        <form className="my-5 flex flex-wrap items-center gap-3" role="search" onSubmit={event => {event.preventDefault(); setOffset(0); setSearch(query.trim()); setRetry(n => n + 1);}}>
          <label className="sr-only" htmlFor="article-search">搜索原文、译文或整理稿</label>
          <input id="article-search" type="search" maxLength={512} value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索标题、原文、译文或整理稿" className="min-w-0 flex-1 rounded-md border border-stone-300 bg-white px-3 py-2 text-sm" />
          <label className="sr-only" htmlFor="article-source">来源</label>
          <select id="article-source" value={source} onChange={event => {setOffset(0); setSource(event.target.value);}} className={button}>
            <option value="">全部来源</option><option value="wechat">微信公众号</option><option value="rss">RSS</option>
          </select><button className={button} type="submit">检索</button>
        </form>
        <label className="mb-4 inline-flex items-center gap-2 text-sm text-stone-600"><input type="checkbox" checked={hasBody} onChange={event => {setOffset(0);setHasBody(event.target.checked);}} />仅有正文</label>
      </>}
      {error ? <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-5"><p>{error}</p><button className={`${button} mt-3`} onClick={() => {setOffset(0); setRetry(n => n + 1);}}>重新读取</button></div> : value === null ? <p role="status">正在读取…</p> : item ? <article className="rounded-xl border border-stone-200 bg-white p-5 sm:p-8">
        <h1 className="text-xl font-bold sm:text-2xl">{articleTitle(item)}</h1>
        <p className="mt-3 text-sm text-stone-500">{sourceLabel(item.source)}{host ? ` · ${host}` : ''} · 采集 {displayDate(item.captured_at)} · {articleStatus(item)}</p>
        {item.source_url ? <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-sm text-blue-700">原文章来源</a> : null}
        <div className="my-5 flex flex-wrap gap-3" role="group" aria-label="稿件版本">{views.map(option => <button key={option} type="button" className={button} aria-pressed={activeView === option} onClick={() => setView(option)}>{VIEW_LABELS[option]}</button>)}</div>
        {html === null ? <p className="text-sm text-stone-500">该记录没有可显示的正文。</p> : <ArticleBody html={html} />}
      </article> : <>
        {value.page?.items.length === 0 ? <p>没有符合查询的记录。</p> : <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 bg-white">{value.page?.items.map(record => <li key={`${record.source}:${record.record_id}`} className="px-5 py-4">
          <a href={libraryItemPath(record, listState)} className="font-semibold hover:text-blue-700">{articleTitle(record)}</a>
          <p className="mt-1 text-xs text-stone-500">{sourceLabel(record.source)}{sourceHost(record.source_url) ? ` · ${sourceHost(record.source_url)}` : ''} · 采集 {displayDate(record.captured_at)} · {articleStatus(record)}</p>
        </li>)}</ul>}
        <div className="mt-5 flex items-center gap-4"><button className={button} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</button><span className="text-sm">第 {Math.floor(offset / 20) + 1} 页</span><button className={button} disabled={value.page?.next_offset == null} onClick={() => setOffset(value.page?.next_offset ?? offset)}>下一页</button></div>
      </>}
      {value ? <p className="mt-6 text-xs text-stone-500">数据镜像：{new Date(value.status.observed_at).toLocaleString('zh-CN', {timeZone: 'America/Halifax'})}（Halifax）</p> : null}
    </main>
  </div>;
}

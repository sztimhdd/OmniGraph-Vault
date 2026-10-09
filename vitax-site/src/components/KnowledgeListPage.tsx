import {SearchX} from 'lucide-react';

import type {KnowledgeApi} from '../api.ts';
import {NavLink} from '../links.tsx';
import {itemPath, listPath} from '../routes.ts';
import type {KindFilter, KnowledgeSummary} from '../types.ts';
import {useAsyncData} from '../useAsyncData.ts';
import {EntityPanel} from './EntityPanel.tsx';
import {EmptyState, ErrorState, LoadingState} from './StateViews.tsx';

const LIST_LIMIT = 100;
const FILTERS: {kind: KindFilter; label: string}[] = [
  {kind: 'all', label: '全部'},
  {kind: 'article', label: '文章'},
  {kind: 'wiki', label: 'Wiki'},
];

interface KnowledgeListPageProps {
  api: KnowledgeApi;
  route: {q: string; kind: KindFilter};
}

function kindLabel(kind: KnowledgeSummary['kind']): string {
  return kind === 'wiki' ? 'Wiki 词条' : '文章解读';
}

export function KnowledgeListPage({api, route}: KnowledgeListPageProps) {
  const {state, retry} = useAsyncData(() => api.list({q: route.q, kind: route.kind, limit: LIST_LIMIT}), [
    api,
    route.q,
    route.kind,
  ]);
  const returnTo = listPath({q: route.q, kind: route.kind});

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-6 sm:px-6 lg:flex-row lg:items-start lg:px-8">
      <section aria-labelledby="knowledge-heading" className="min-w-0 flex-1">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3 border-b border-stone-200 pb-3">
          <div>
            <h1 id="knowledge-heading" className="text-lg font-bold tracking-tight text-stone-900">
              知识条目
            </h1>
            <p className="mt-1 text-xs text-stone-500">
              {route.q === '' ? '按 release 中稳定的知识标识排序。' : `检索：“${route.q}”`}
            </p>
          </div>
          <nav aria-label="知识类型筛选" className="flex items-center gap-1.5">
            {FILTERS.map((filter) => (
              <NavLink
                key={filter.kind}
                to={listPath({q: route.q, kind: filter.kind})}
                className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium ${
                  route.kind === filter.kind
                    ? 'bg-stone-900 text-stone-50'
                    : 'border border-stone-200 bg-white text-stone-700 hover:bg-stone-100'
                }`}
              >
                {filter.label}
              </NavLink>
            ))}
          </nav>
        </div>

        {state.status === 'loading' && <LoadingState label="正在读取公开知识列表…" />}
        {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
        {state.status === 'ready' && state.value.length === 0 && (
          <EmptyState
            title="没有匹配的公开知识"
            detail={
              route.q === ''
                ? '当前 release 的该类型下没有可公开条目。'
                : '当前 release 中没有与该检索词匹配的公开条目。'
            }
            action={
              <NavLink
                to={listPath({q: '', kind: route.kind})}
                className="inline-flex items-center gap-1.5 rounded-md border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 hover:bg-stone-100"
              >
                <SearchX aria-hidden="true" className="h-3.5 w-3.5" />
                <span>清空检索词</span>
              </NavLink>
            }
          />
        )}
        {state.status === 'ready' && state.value.length > 0 && (
          <>
            <p className="mb-2 text-xs text-stone-500">共 {state.value.length} 条</p>
            <ul className="divide-y divide-stone-100 overflow-hidden rounded-lg border border-stone-200/90 bg-white">
              {state.value.map((item) => (
                <li key={item.knowledge_id}>
                  <NavLink
                    to={itemPath(item, returnTo)}
                    className="group block px-4 py-4 hover:bg-stone-50/70 sm:px-5"
                  >
                    <span className="mb-2 flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${
                          item.kind === 'wiki'
                            ? 'border-emerald-200/80 bg-emerald-50 text-emerald-800'
                            : 'border-blue-200/70 bg-blue-50 text-blue-800'
                        }`}
                      >
                        {kindLabel(item.kind)}
                      </span>
                    </span>
                    <span className="block text-base font-bold leading-snug tracking-tight text-stone-900 group-hover:text-blue-700">
                      {item.title}
                    </span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <EntityPanel api={api} />
    </div>
  );
}

import {ArrowLeft} from 'lucide-react';

import {NotFoundError, type KnowledgeApi} from '../api.ts';
import {NavLink} from '../links.tsx';
import {itemPath, listPath, routeMatchesKind, safeReturnTarget} from '../routes.ts';
import type {Route} from '../types.ts';
import {useAsyncData} from '../useAsyncData.ts';
import {EvidencePanel} from './EvidencePanel.tsx';
import {ArticleBody} from './ArticleBody.tsx';
import {ReleaseImage} from './ReleaseImage.tsx';
import {ErrorState, LoadingState, NotFoundState, Notice} from './StateViews.tsx';

interface KnowledgeDetailPageProps {
  api: KnowledgeApi;
  route: Extract<Route, {name: 'article'} | {name: 'wiki'}>;
}

export function KnowledgeDetailPage({api, route}: KnowledgeDetailPageProps) {
  const {state, retry} = useAsyncData(() => api.knowledge(route.id), [api, route.id]);
  const returnTo = safeReturnTarget(new URLSearchParams(window.location.search).get('return'), listPath({q: '', kind: 'all'}));

  if (state.status === 'loading') return <LoadingState label="正在读取知识条目…" />;
  if (state.status === 'error') {
    if (state.error instanceof NotFoundError) {
      return (
        <NotFoundState
          title="该知识条目不存在"
          detail={`当前 release 中找不到标识 ${route.id}，没有回退到其他条目。`}
        />
      );
    }
    return (
      <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
        <ErrorState error={state.error} onRetry={retry} />
      </div>
    );
  }

  const item = state.value;
  if (!routeMatchesKind(route, item.kind)) {
    const correct = itemPath(item);
    return (
      <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
        <Notice title="路由与该条目的类型不一致">
          <p>
            标识 <code className="font-mono">{item.knowledge_id}</code> 是
            {item.kind === 'wiki' ? '一个 Wiki 词条' : '一篇文章'}，不在
            <code className="font-mono"> /{route.name}/ </code>路由下展示。
          </p>
          <p className="mt-2">
            <NavLink to={correct} className="font-semibold text-blue-700 underline decoration-blue-300 underline-offset-2">
              打开正确地址 {correct}
            </NavLink>
          </p>
        </Notice>
      </div>
    );
  }

  const paragraphs = item.body
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line !== '');

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <NavLink
        to={returnTo}
        className="mb-4 inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold text-stone-600 hover:bg-stone-100 hover:text-stone-900"
      >
        <ArrowLeft aria-hidden="true" className="h-3.5 w-3.5" />
        <span>返回知识列表</span>
      </NavLink>

      <article className="rounded-xl border border-stone-200/90 bg-white p-6 shadow-[0_1px_2px_rgba(0,0,0,0.02)] sm:p-10">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span
            className={`rounded border px-2.5 py-0.5 text-xs font-bold ${
              item.kind === 'wiki'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                : 'border-blue-200/70 bg-blue-50 text-blue-800'
            }`}
          >
            {item.kind === 'wiki' ? 'Wiki 词条' : '文章解读'}
          </span>
          <details className="text-[11px] text-stone-400">
            <summary className="cursor-pointer select-none">技术信息</summary>
            <code className="font-mono">{item.knowledge_id}</code>
          </details>
        </div>

        <h1 className="text-xl font-bold leading-snug tracking-tight text-stone-900 sm:text-2xl">{item.title}</h1>

        <ReleaseImage src={item.image_url ?? null} alt={item.title} caption={item.image_caption ?? null} />

        <div className="mt-5 space-y-4 font-editorial text-[15px] leading-relaxed text-stone-800">
          {item.rendered_html ? <ArticleBody html={item.rendered_html} /> : paragraphs.map((paragraph, index) => (
            <p key={`${index}-${paragraph.slice(0, 12)}`}>{paragraph}</p>
          ))}
        </div>

        <div className="mt-8">
          <EvidencePanel api={api} evidenceIds={item.evidence_ids} headingId={`evidence-${item.knowledge_id}`} />
        </div>
      </article>
    </div>
  );
}

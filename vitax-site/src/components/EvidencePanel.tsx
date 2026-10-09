import {ExternalLink} from 'lucide-react';

import {NotFoundError, type KnowledgeApi} from '../api.ts';
import type {Evidence} from '../types.ts';
import {useAsyncData} from '../useAsyncData.ts';
import {ErrorState, LoadingState} from './StateViews.tsx';

type EvidenceEntry = {ok: true; evidence: Evidence} | {ok: false; id: string; error: Error};

interface EvidencePanelProps {
  api: KnowledgeApi;
  evidenceIds: string[];
  headingId: string;
  compact?: boolean;
}

async function loadEvidence(api: KnowledgeApi, ids: string[]): Promise<EvidenceEntry[]> {
  const results = await Promise.allSettled(ids.map((id) => api.evidence(id)));
  return results.map((result, index) =>
    result.status === 'fulfilled'
      ? {ok: true, evidence: result.value}
      : {ok: false, id: ids[index], error: result.reason as Error},
  );
}

function entryError(error: Error, id: string): string {
  return error instanceof NotFoundError ? `该 release 中没有证据 ${id}。` : error.message;
}

export function EvidencePanel({api, evidenceIds, headingId, compact = false}: EvidencePanelProps) {
  const {state, retry} = useAsyncData(() => loadEvidence(api, evidenceIds), [api, evidenceIds.join('|')]);

  return (
    <section
      aria-labelledby={headingId}
      className={compact ? 'mt-3 border-t border-stone-100 pt-3' : 'border-t border-stone-100 pt-6'}
    >
      <h2 id={headingId} className={compact ? 'text-xs font-bold text-stone-800' : 'text-base font-bold text-stone-900'}>
        证据与来源
      </h2>
      <div className="mt-3">
        {evidenceIds.length === 0 && <p className="text-xs text-stone-500">该条目没有关联证据。</p>}
        {evidenceIds.length > 0 && state.status === 'loading' && <LoadingState label="正在读取证据…" />}
        {evidenceIds.length > 0 && state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
        {evidenceIds.length > 0 && state.status === 'ready' && (
          <ul className="space-y-3">
            {state.value.map((entry, index) =>
              entry.ok ? (
                <li key={entry.evidence.evidence_id} className="rounded-md border border-stone-200 bg-stone-50/50 p-3.5">
                  <blockquote className="border-l-2 border-blue-300 pl-3 text-sm leading-relaxed text-stone-700">
                    {entry.evidence.quote}
                  </blockquote>
                  <p className="mt-2 text-xs text-stone-500">来源 {index + 1}</p>
                  <details className="mt-2 font-mono text-[11px] text-stone-500">
                    <summary>技术信息</summary>
                    {entry.evidence.evidence_id} · {entry.evidence.locator}
                  </details>
                  <p className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                    <ExternalLink aria-hidden="true" className="h-3.5 w-3.5 text-stone-400" />
                    <a
                      href={entry.evidence.document.source_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="font-medium text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-900"
                    >
                      {entry.evidence.document.title}
                    </a>
                  </p>
                </li>
              ) : (
                <li key={entry.id} className="rounded-md border border-amber-200 bg-amber-50/60 p-3.5 text-xs text-amber-900">
                  证据读取失败：{entryError(entry.error, entry.id)}
                  <button type="button" onClick={retry} className="ml-2 font-semibold underline">
                    重试
                  </button>
                </li>
              ),
            )}
          </ul>
        )}
      </div>
    </section>
  );
}

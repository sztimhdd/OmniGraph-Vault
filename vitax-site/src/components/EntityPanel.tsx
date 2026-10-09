import {Layers, Network} from 'lucide-react';
import {useState} from 'react';

import type {KnowledgeApi} from '../api.ts';
import type {Relation} from '../types.ts';
import {useAsyncData} from '../useAsyncData.ts';
import {EvidencePanel} from './EvidencePanel.tsx';
import {ErrorState, LoadingState} from './StateViews.tsx';

const ENTITY_LIMIT = 20;
const RELATION_LIMIT = 10;

/** Compact entity/relationship panel: bounded list, bounded relations, real reads. */
export function EntityPanel({api}: {api: KnowledgeApi}) {
  const entities = useAsyncData(() => api.entities(ENTITY_LIMIT), [api]);
  const [selected, setSelected] = useState<string | null>(null);
  const [expandedRelation, setExpandedRelation] = useState<string | null>(null);
  const relations = useAsyncData(
    async () => (selected === null ? [] : await api.relations(selected, RELATION_LIMIT)),
    [api, selected],
  );

  const select = (entityId: string) => {
    setExpandedRelation(null);
    setSelected((current) => (current === entityId ? null : entityId));
  };

  return (
    <aside aria-label="实体与关系" className="w-full shrink-0 lg:w-80">
      <div className="rounded-lg border border-stone-200/90 bg-white p-4">
        <h2 className="flex items-center gap-1.5 border-b border-stone-200 pb-2 text-sm font-bold text-stone-900">
          <Network aria-hidden="true" className="h-3.5 w-3.5 text-stone-500" />
          <span>实体与关系</span>
        </h2>

        {entities.state.status === 'loading' && <LoadingState label="正在读取实体…" />}
        {entities.state.status === 'error' && <ErrorState error={entities.state.error} onRetry={entities.retry} />}
        {entities.state.status === 'ready' && entities.state.value.length === 0 && (
          <p className="mt-3 text-xs text-stone-500">当前 release 没有可公开的实体。</p>
        )}
        {entities.state.status === 'ready' && entities.state.value.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {entities.state.value.map((entity) => (
              <li key={entity.entity_id}>
                <button
                  type="button"
                  aria-expanded={selected === entity.entity_id}
                  onClick={() => select(entity.entity_id)}
                  className={`w-full rounded-md border px-2.5 py-1.5 text-left text-xs ${
                    selected === entity.entity_id
                      ? 'border-blue-300 bg-blue-50 font-semibold text-blue-900'
                      : 'border-stone-200 bg-white text-stone-700 hover:bg-stone-50'
                  }`}
                >
                  {entity.name}
                </button>
              </li>
            ))}
          </ul>
        )}

        {selected !== null && (
          <div className="mt-3 border-t border-stone-200 pt-3">
            <h3 className="flex items-center gap-1.5 text-xs font-bold text-stone-800">
              <Layers aria-hidden="true" className="h-3.5 w-3.5 text-stone-500" />
              <span>关联关系</span>
            </h3>
            {relations.state.status === 'loading' && <LoadingState label="正在读取关系…" />}
            {relations.state.status === 'error' && <ErrorState error={relations.state.error} onRetry={relations.retry} />}
            {relations.state.status === 'ready' && relations.state.value.length === 0 && (
              <p className="mt-2 text-xs text-stone-500">该实体没有已公开的关系。</p>
            )}
            {relations.state.status === 'ready' && relations.state.value.length > 0 && (
              <ul className="mt-2 space-y-2">
                {relations.state.value.map((relation) => (
                  <RelationRow
                    key={relation.relation_id}
                    api={api}
                    relation={relation}
                    expanded={expandedRelation === relation.relation_id}
                    onToggle={() =>
                      setExpandedRelation((current) =>
                        current === relation.relation_id ? null : relation.relation_id,
                      )
                    }
                  />
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

interface RelationRowProps {
  api: KnowledgeApi;
  relation: Relation;
  expanded: boolean;
  onToggle: () => void;
}

function RelationRow({api, relation, expanded, onToggle}: RelationRowProps) {
  return (
    <li className="rounded-md border border-stone-200 bg-stone-50/60 p-2.5 text-xs">
      <p className="text-stone-700">
        <span className="font-semibold text-stone-900">{relation.source_name}</span>
        <span className="mx-1 font-mono text-[11px] text-stone-500">—[{relation.relation_type}]→</span>
        <span className="font-semibold text-stone-900">{relation.target_name}</span>
      </p>
      {relation.evidence_ids.length === 0 ? (
        <p className="mt-1 text-[11px] text-stone-500">该关系没有关联证据。</p>
      ) : (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={onToggle}
          className="mt-1 text-[11px] font-semibold text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-900"
        >
          {expanded ? '收起证据' : `查看证据（${relation.evidence_ids.length}）`}
        </button>
      )}
      {expanded && relation.evidence_ids.length > 0 && (
        <EvidencePanel
          api={api}
          evidenceIds={relation.evidence_ids}
          headingId={`relation-evidence-${relation.relation_id}`}
          compact
        />
      )}
    </li>
  );
}

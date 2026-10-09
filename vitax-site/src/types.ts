/** Shapes shared by the reader, taken from the Task-2a read API contract. */

export type KnowledgeKind = 'article' | 'wiki';

export type KindFilter = 'all' | KnowledgeKind;

export interface Release {
  release_id: string;
  published_at: string;
}

export interface KnowledgeSummary {
  knowledge_id: string;
  kind: KnowledgeKind;
  title: string;
}

export interface KnowledgeItem extends KnowledgeSummary {
  body: string;
  rendered_html?: string | null;
  evidence_ids: string[];
  /** Optional in the read contract; absent in the current release. */
  image_url?: string | null;
  image_caption?: string | null;
}

export interface EvidenceDocument {
  doc_id: string;
  title: string;
  source_url: string;
}

export interface Evidence {
  evidence_id: string;
  revision_id: string;
  locator: string;
  quote: string;
  document: EvidenceDocument;
}

export interface Entity {
  entity_id: string;
  name: string;
}

export interface Relation {
  relation_id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  source_name: string;
  target_name: string;
  evidence_ids: string[];
}

export type Route =
  | {name: 'list'; q: string; kind: KindFilter}
  | {name: 'article'; id: string}
  | {name: 'wiki'; id: string}
  | {name: 'unknown'; path: string};

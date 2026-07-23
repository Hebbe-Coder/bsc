import type { GrowthRecord, GrowthStage } from '../../api/growthApi';

export type GrowthGraphNodeType = 'source' | 'page' | 'method' | 'output' | 'feedback' | 'other';

export const GROWTH_STAGES: Array<{ id: GrowthStage; index: string; label: string; detail: string }> = [
  { id: 'A', index: 'A', label: 'Evidence', detail: 'Immutable captured material' },
  { id: 'B', index: 'B', label: 'Knowledge', detail: 'Compiled Wiki state' },
  { id: 'C', index: 'C', label: 'Methods', detail: 'Tested reusable playbooks' },
  { id: 'D', index: 'D', label: 'Outputs', detail: 'Grounded project work' },
  { id: 'review', index: 'R', label: 'Review', detail: 'Feedback and proposals' },
];

export const GROWTH_RELATIONS = [
  'wiki_cites_source', 'wiki_links_to', 'proposal_changes_page',
  'source_supports_page', 'source_contradicts_source', 'page_informs_method', 'output_used_source',
  'output_used_page', 'output_used_method_revision', 'output_produced_by_run', 'feedback_evaluates_output',
  'output_proposes_page', 'output_proposes_method', 'method_supersedes_method',
];

export function growthRecordLabel(record: GrowthRecord): string {
  if (typeof record.feedback_type === 'string') {
    const summary = String(record.correction || record.comment || '').trim();
    return `${record.feedback_type} feedback${summary ? `: ${summary.slice(0, 48)}` : ''}`;
  }
  if (record.asset_type === 'wiki_proposal' || record.asset_type === 'proposal') {
    const rationale = String(record.rationale || '').trim();
    return rationale || `Wiki proposal ${record.id}`;
  }
  if (record.asset_type === 'method_proposal') {
    return String(record.rationale || record.task_family || `Method candidate ${record.id}`);
  }
  return String(record.title || record.name || record.origin || record.path || record.slug || record.id);
}

export function growthRecordTimestamp(record: GrowthRecord): string {
  const value = typeof record.updated_at === 'string' ? record.updated_at : typeof record.created_at === 'string' ? record.created_at : '';
  if (!value) return 'Time not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function normalizeGrowthNodeType(value: string | undefined): GrowthGraphNodeType {
  if (value === 'source') return 'source';
  if (value === 'page' || value === 'wiki_page') return 'page';
  if (value === 'method' || value === 'method_revision' || value === 'method_proposal') return 'method';
  if (value === 'output') return 'output';
  if (value === 'feedback') return 'feedback';
  if (value === 'proposal' || value === 'wiki_proposal') return 'feedback';
  return 'other';
}

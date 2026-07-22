import { ArrowLeft, ArrowRight, FileSearch, Search } from 'lucide-react';

import type { GrowthRecord, GrowthRequestState, GrowthStage } from '../../api/growthApi';
import { growthRecordLabel, growthRecordTimestamp } from './growthModel';

type Props = {
  stage: GrowthStage;
  records: GrowthRecord[];
  selectedId: string;
  query: string;
  statusFilter: string;
  page: number;
  pageSize: number;
  totalHint?: number;
  truncated: boolean;
  serverCapped: boolean;
  state: GrowthRequestState;
  error?: string;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onPageChange: (value: number) => void;
  onSelect: (record: GrowthRecord) => void;
  onRetry: () => void;
};

function ListState({ state, error, onRetry }: { state: GrowthRequestState; error?: string; onRetry: () => void }) {
  const labels: Partial<Record<GrowthRequestState, string>> = {
    loading: 'Loading persisted stage records...',
    permission: 'Your project key cannot read this stage.',
    offline: 'The stage list is offline. No cached records are being shown.',
    unavailable: 'This stage endpoint is unavailable.',
    error: error || 'The stage list could not be loaded.',
  };
  if (!labels[state]) return null;
  return <div className={`growth-inline-state growth-inline-state--${state}`} role={state === 'loading' ? 'status' : 'alert'}>
    <FileSearch size={17} />
    <span>{labels[state]}{error && state !== 'error' ? ` ${error}` : ''}</span>
    {state !== 'loading' && <button type="button" onClick={onRetry}>Retry</button>}
  </div>;
}

export function GrowthAssetList(props: Props) {
  const {
    stage, records, selectedId, query, statusFilter, page, pageSize, totalHint, truncated, serverCapped, state, error,
    onQueryChange, onStatusChange, onPageChange, onSelect, onRetry,
  } = props;
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const statuses = [...new Set(records.map((record) => String(record.status || 'recorded')))];
  const filtered = records.filter((record) => {
    const matchesStatus = !statusFilter || String(record.status || 'recorded') === statusFilter;
    if (!matchesStatus || !normalizedQuery) return matchesStatus;
    return [growthRecordLabel(record), record.id, record.status, record.path, record.origin, record.slug]
      .some((value) => String(value || '').toLocaleLowerCase().includes(normalizedQuery));
  });
  const start = (page - 1) * pageSize;
  const visible = filtered.slice(start, start + pageSize);
  const hasNext = filtered.length > start + pageSize || (!serverCapped && (truncated || (!normalizedQuery && !statusFilter && totalHint !== undefined && totalHint > start + pageSize)));

  return <section className="growth-asset-list" aria-label={`Stage ${stage} assets`}>
    <div className="growth-list-toolbar">
      <label className="growth-search"><Search size={14} /><span className="growth-visually-hidden">Search this stage</span><input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Search ID, title, path" /></label>
      <label><span className="growth-visually-hidden">Filter by status</span><select value={statusFilter} onChange={(event) => onStatusChange(event.target.value)}><option value="">All statuses</option>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
    </div>
    <ListState state={state} error={error} onRetry={onRetry} />
    {state !== 'loading' && state !== 'permission' && state !== 'offline' && state !== 'unavailable' && state !== 'error' && (
      visible.length ? <div className="growth-record-list" role="listbox" aria-label={`Stage ${stage} records`}>
        {visible.map((record) => <button
          type="button"
          role="option"
          aria-selected={selectedId === record.id}
          key={record.id}
          className={selectedId === record.id ? 'is-selected' : ''}
          onClick={() => onSelect(record)}
        >
          <span className="growth-record-list__status">{String(record.status || 'recorded')}</span>
          <span className="growth-record-list__copy"><strong>{growthRecordLabel(record)}</strong><small>{record.id}</small><time>{growthRecordTimestamp(record)}</time></span>
          <ArrowRight size={14} aria-hidden="true" />
        </button>)}
      </div> : <div className="growth-empty"><FileSearch size={18} /><span>{records.length ? 'No loaded records match these filters.' : 'No persisted assets exist in this stage.'}</span></div>
    )}
    <footer className="growth-pagination" aria-label="Asset list pagination">
      <span>{visible.length ? `${start + 1}-${start + visible.length}` : '0'}{totalHint !== undefined ? ` of ${totalHint}` : truncated ? ' of a bounded result' : ` of ${filtered.length}`}</span>
      <div>
        <button type="button" aria-label="Previous asset page" disabled={page <= 1 || state === 'loading'} onClick={() => onPageChange(page - 1)}><ArrowLeft size={14} /></button>
        <strong>Page {page}</strong>
        <button type="button" aria-label="Next asset page" disabled={!hasNext || state === 'loading'} onClick={() => onPageChange(page + 1)}><ArrowRight size={14} /></button>
      </div>
    </footer>
    {serverCapped && truncated && <div className="growth-boundary-note" role="status"><span>This list reached the API maximum of {records.length} returned records. Narrow the search or status filter.</span></div>}
  </section>;
}

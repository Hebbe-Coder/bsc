import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Inbox, Radio, RefreshCw, Send, ShieldAlert } from 'lucide-react';

import {
  createKnowledgeInformationSource,
  fetchKnowledgeInformationOverview,
  type InformationRegistrySource,
  type KnowledgeInformationOverview,
} from '../../api/knowledgeWorkspaceApi';

type Props = { projectId: string; canWrite: boolean; refreshToken: number };

const connectorLabels: Record<InformationRegistrySource['connector_type'], string> = {
  rss: 'RSS',
  youtube_channel_rss: 'YouTube channel RSS',
  x: 'X',
  reddit: 'Reddit',
  youtube_data: 'YouTube Data',
  tiktok: 'TikTok',
};

export function InformationOperationsPanel({ projectId, canWrite, refreshToken }: Props) {
  const [overview, setOverview] = useState<KnowledgeInformationOverview | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [connectorType, setConnectorType] = useState<InformationRegistrySource['connector_type']>('rss');
  const [feedReference, setFeedReference] = useState('');
  const [authority, setAuthority] = useState<InformationRegistrySource['authority_tier']>('untrusted');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setOverview(await fetchKnowledgeInformationOverview(projectId));
    } catch (reason) {
      setOverview(null);
      setError(reason instanceof Error ? reason.message : 'Information operations could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { void load(); }, [load, refreshToken]);

  const register = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim() || !feedReference.trim()) return;
    const normalizedReference = feedReference.trim();
    const isYoutubeChannel = connectorType === 'youtube_channel_rss';
    const channelId = isYoutubeChannel ? resolveYouTubeChannelId(normalizedReference) : '';
    const feedUrl = isYoutubeChannel
      ? normalizedReference.startsWith('http')
        ? normalizedReference
        : `https://www.youtube.com/feeds/videos.xml?channel_id=${encodeURIComponent(channelId)}`
      : normalizedReference;
    if (isYoutubeChannel && !channelId) {
      setError('A YouTube Channel ID or YouTube Channel RSS URL is required.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await createKnowledgeInformationSource(projectId, {
        project_id: projectId,
        name: name.trim(),
        connector_type: connectorType,
        feed_url: feedUrl,
        channel_id: channelId,
        topics: [],
        languages: [],
        freshness_hours: 168,
        retention_days: 90,
        authority_tier: authority,
        enabled: true,
      });
      setName('');
      setFeedReference('');
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'RSS source could not be registered.');
    } finally {
      setSaving(false);
    }
  };

  const isYoutubeChannel = connectorType === 'youtube_channel_rss';

  if (loading && !overview) return <section className="information-operations information-operations--loading">Loading governed information operations...</section>;
  if (error && !overview) return <section className="information-operations information-operations--error" role="alert"><AlertTriangle size={18} /><div><strong>Information operations unavailable</strong><p>{error}</p><button type="button" onClick={() => void load()}><RefreshCw size={14} /> Retry</button></div></section>;
  if (!overview) return null;

  return <section className="information-operations" aria-label="Governed information operations">
    <header className="knowledge-content-header">
      <div><span className="eyebrow"><Radio size={14} /> GOVERNED INFORMATION</span><h3>Discovery is not knowledge.</h3><p>n8n may discover and rank signals. BSC verifies the receipt, preserves original evidence, and routes every item through project review.</p></div>
      <button type="button" className="icon-button" onClick={() => void load()} aria-label="Refresh information operations" title="Refresh source status and BSC receipts"><RefreshCw size={16} /></button>
    </header>
    <div className="information-metrics" aria-label="Information intake metrics">
      <Metric icon={<Radio size={16} />} label="Enabled feeds" value={overview.counts.available_sources} detail={`${overview.counts.unavailable_sources} unavailable adapters`} />
      <Metric icon={<CheckCircle2 size={16} />} label="Evidence captured" value={overview.counts.captured} detail="BSC receipt and immutable source present" />
      <Metric icon={<Inbox size={16} />} label="Needs original source" value={overview.counts.lead_only} detail="Discovery lead only, not evidence" />
      <Metric icon={<ShieldAlert size={16} />} label="Rejected items" value={overview.counts.rejected} detail="Policy, registry, or payload failure" />
    </div>
    <div className="information-operations__grid">
      <section className="information-panel">
        <header><div><span>PROJECT SOURCE REGISTRY</span><small>{overview.source_registry.length} declared</small></div></header>
        <div className="information-source-list">
          {overview.source_registry.length ? overview.source_registry.map((source) => <article key={source.id} className="information-source-row">
            <div><strong>{source.name}</strong><small>{connectorLabels[source.connector_type]} / {source.authority_tier} / {source.channel_id || source.feed_url}</small></div>
            <span className={`information-state information-state--${source.availability}`}>{source.availability === 'available' && source.enabled ? 'ready' : source.unavailable_reason || 'disabled'}</span>
          </article>) : <p className="information-empty">No source is registered. Add an RSS or YouTube Channel RSS source before importing the disabled workflow.</p>}
        </div>
        <form className="information-source-form" onSubmit={register}>
          <label>Connector<select value={connectorType} onChange={(event) => setConnectorType(event.target.value as InformationRegistrySource['connector_type'])} disabled={!canWrite || saving}><option value="rss">RSS</option><option value="youtube_channel_rss">YouTube channel RSS</option></select></label>
          <label>Source name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Engineering publications" disabled={!canWrite || saving} /></label>
          <label>{isYoutubeChannel ? 'YouTube Channel ID or feed URL' : 'RSS feed URL'}<input value={feedReference} onChange={(event) => setFeedReference(event.target.value)} placeholder={isYoutubeChannel ? 'UC... or https://www.youtube.com/feeds/videos.xml?...' : 'https://example.com/feed.xml'} type={isYoutubeChannel ? 'text' : 'url'} disabled={!canWrite || saving} /></label>
          <label>Authority<select value={authority} onChange={(event) => setAuthority(event.target.value as InformationRegistrySource['authority_tier'])} disabled={!canWrite || saving}><option value="untrusted">Untrusted, review required</option><option value="community">Community, review required</option><option value="trusted">Trusted, still review-gated</option><option value="primary">Primary publisher, still review-gated</option></select></label>
          <button type="submit" disabled={!canWrite || saving || !name.trim() || !feedReference.trim()} title="Register a project-scoped source"><Send size={14} /> Register source</button>
        </form>
      </section>
      <section className="information-panel">
        <header><div><span>BSC RECEIPT LEDGER</span><small>{overview.receipts.length} recent records</small></div></header>
        <ol className="information-receipts">
          {overview.receipts.length ? overview.receipts.map((receipt) => <li key={receipt.id}>
            <span className={`information-receipt-kind information-receipt-kind--${receipt.disposition}`}>{receipt.disposition}</span>
            <div><strong>{receipt.canonical_url || receipt.external_id || 'Unresolved signal'}</strong><small>{receipt.reason || (receipt.disposition === 'lead_only' ? 'Awaiting original source capture' : `Immutable source ${receipt.source_id}`)}</small></div>
          </li>) : <li className="information-empty">No BSC receipt exists yet. Starting a container, importing a workflow, or ranking an item does not create one.</li>}
        </ol>
      </section>
      <section className="information-panel information-panel--runs">
        <header><div><span>INGRESS RUN HISTORY</span><small>{overview.runs.length} durable run(s)</small></div></header>
        <ol className="information-runs">
          {overview.runs.length ? overview.runs.map((run) => <li key={run.id}>
            <span className={`information-state information-state--${run.status}`}>{run.status}</span>
            <div><strong>{String(run.input_refs.batch_id || run.id)}</strong><small>{describeRun(run)}</small></div>
          </li>) : <li className="information-empty">No persisted ingress run exists. A source stays configuration only until n8n submits a signed BSC receipt.</li>}
        </ol>
      </section>
    </div>
    <footer className="information-operations__footer">
      <span>n8n reads only this project's enabled RSS and YouTube Channel RSS registry entries at each run.</span>
      <span>DeepSeek summaries and classifications remain derivatives. They never replace the original RSS body.</span>
    </footer>
  </section>;
}

function Metric({ icon, label, value, detail }: { icon: ReactNode; label: string; value: number; detail: string }) {
  return <div><span>{icon}</span><strong>{value}</strong><small>{label}</small><p>{detail}</p></div>;
}

function resolveYouTubeChannelId(value: string): string {
  if (!value.startsWith('http')) return value.trim();
  try {
    return new URL(value).searchParams.get('channel_id')?.trim() || '';
  } catch {
    return '';
  }
}

function describeRun(run: KnowledgeInformationOverview['runs'][number]): string {
  const items = Number(run.input_refs.item_count || 0);
  const receipts = Number(run.output_refs.receipt_count || 0);
  const failures = Number(run.output_refs.failure_count || 0);
  if (run.error) return run.error;
  return `${items} signal${items === 1 ? '' : 's'} / ${receipts} receipt${receipts === 1 ? '' : 's'}${failures ? ` / ${failures} rejected` : ''}`;
}

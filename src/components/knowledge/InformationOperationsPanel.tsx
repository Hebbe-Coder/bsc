import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, Inbox, Play, Radio, RefreshCw, Send, ShieldAlert } from 'lucide-react';

import {
  captureKnowledgePrimaryWebSource,
  createKnowledgeInformationSource,
  fetchKnowledgeInformationOverview,
  runKnowledgeInformationManualIngress,
  type InformationBriefItem,
  type InformationRegistrySource,
  type HorizonReviewItem,
  type KnowledgeInformationOverview,
} from '../../api/knowledgeWorkspaceApi';

type Props = { projectId: string; canWrite: boolean; refreshToken: number; onInspectSource?: (sourceId: string) => void };

const connectorLabels: Record<InformationRegistrySource['connector_type'], string> = {
  rss: 'RSS',
  youtube_channel_rss: 'YouTube channel RSS',
  x: 'X',
  reddit: 'Reddit',
  youtube_data: 'YouTube Data',
  tiktok: 'TikTok',
};

export function InformationOperationsPanel({ projectId, canWrite, refreshToken, onInspectSource }: Props) {
  const [overview, setOverview] = useState<KnowledgeInformationOverview | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [runningManualCheck, setRunningManualCheck] = useState(false);
  const [manualRunMessage, setManualRunMessage] = useState('');
  const [capturingSourceId, setCapturingSourceId] = useState('');
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

  const capturePrimarySource = async (item: HorizonReviewItem) => {
    if (!item.origin) {
      setError('This Horizon signal has no source URL to capture.');
      return;
    }
    setCapturingSourceId(item.source_id);
    setError('');
    try {
      const result = await captureKnowledgePrimaryWebSource(projectId, item.origin, item.source_id);
      onInspectSource?.(result.source.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The primary source could not be captured.');
    } finally {
      setCapturingSourceId('');
    }
  };

  const runManualSourceCheck = async () => {
    setRunningManualCheck(true);
    setError('');
    setManualRunMessage('');
    try {
      const result = await runKnowledgeInformationManualIngress(projectId);
      const detail = result.state === 'receipt_verification_pending'
        ? 'Source check is awaiting BSC receipt verification. No new receipt is counted yet.'
        : result.state === 'completed_no_fresh_items'
          ? 'Source check completed. No fresh feed entries required a BSC receipt.'
          : result.state === 'completed_with_rejections'
            ? `Source check persisted ${result.receipt_count} BSC receipt${result.receipt_count === 1 ? '' : 's'} with rejected input(s). Review the receipt ledger before using the result.`
            : `Source check completed with ${result.receipt_count} BSC receipt${result.receipt_count === 1 ? '' : 's'} across ${result.batch_count} batch${result.batch_count === 1 ? '' : 'es'}.`;
      setManualRunMessage(detail);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The governed source check could not be completed.');
    } finally {
      setRunningManualCheck(false);
    }
  };

  const isYoutubeChannel = connectorType === 'youtube_channel_rss';

  if (loading && !overview) return <section className="information-operations information-operations--loading">Loading governed information operations...</section>;
  if (error && !overview) return <section className="information-operations information-operations--error" role="alert"><AlertTriangle size={18} /><div><strong>Information operations unavailable</strong><p>{error}</p><button type="button" onClick={() => void load()}><RefreshCw size={14} /> Retry</button></div></section>;
  if (!overview) return null;

  return <section className="information-operations" aria-label="Governed information operations">
    <header className="knowledge-content-header">
      <div><span className="eyebrow"><Radio size={14} /> GOVERNED INFORMATION</span><h3>Discovery is not knowledge.</h3><p>n8n may discover and rank signals. BSC verifies the receipt, preserves original evidence, and routes every item through project review.</p></div>
      <div className="information-header-actions"><button type="button" className="information-run-check" onClick={() => void runManualSourceCheck()} disabled={!canWrite || runningManualCheck} title="Run the configured project feeds through the signed n8n and BSC receipt path"><Play size={14} />{runningManualCheck ? 'Running source check...' : 'Run source check'}</button><button type="button" className="icon-button" onClick={() => void load()} aria-label="Refresh information operations" title="Refresh source status and BSC receipts"><RefreshCw size={16} /></button></div>
    </header>
    {manualRunMessage ? <p className="information-run-message" role="status">{manualRunMessage}</p> : null}
    <div className="information-metrics" aria-label="Information intake metrics">
      <Metric icon={<Radio size={16} />} label="Enabled feeds" value={overview.counts.available_sources} detail={`${overview.counts.unavailable_sources} unavailable adapters`} />
      <Metric icon={<CheckCircle2 size={16} />} label="Evidence receipts" value={overview.counts.captured} detail="All BSC receipts, including repeat discoveries" />
      <Metric icon={<CheckCircle2 size={16} />} label="New sources" value={overview.counts.new_sources} detail={`${overview.counts.new_sources} new evidence asset(s)`} />
      <Metric icon={<RefreshCw size={16} />} label="Repeat discoveries" value={overview.counts.duplicate_sources} detail={`${overview.counts.duplicate_sources} repeat receipt(s), no source growth`} />
      <Metric icon={<Inbox size={16} />} label="Needs original source" value={overview.counts.lead_only} detail="Discovery lead only, not evidence" />
      <Metric icon={<ShieldAlert size={16} />} label="Rejected items" value={overview.counts.rejected} detail="Policy, registry, or payload failure" />
    </div>
    {overview.daily_brief && <DailyBrief brief={overview.daily_brief} onInspectSource={onInspectSource} />}
    {overview.horizon_review_queue?.count ? <HorizonPrimaryReview queue={overview.horizon_review_queue} canWrite={canWrite} capturingSourceId={capturingSourceId} onCapturePrimary={capturePrimarySource} onInspectSource={onInspectSource} /> : null}
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

function HorizonPrimaryReview({
  queue,
  canWrite,
  capturingSourceId,
  onCapturePrimary,
  onInspectSource,
}: {
  queue: NonNullable<KnowledgeInformationOverview['horizon_review_queue']>;
  canWrite: boolean;
  capturingSourceId: string;
  onCapturePrimary: (item: HorizonReviewItem) => Promise<void>;
  onInspectSource?: (sourceId: string) => void;
}) {
  return <section className="information-panel information-panel--brief" aria-label="Horizon primary-source review">
    <header><div><span>HORIZON PRIMARY-SOURCE REVIEW</span><small>{queue.count} un-cited signal{queue.count === 1 ? '' : 's'}</small></div></header>
    <p className="information-empty">Discovery leads only. Capture an authoritative primary source before a signal can support project knowledge.</p>
    <ol className="information-brief-list">{queue.items.map((item: HorizonReviewItem) => <li key={item.source_id}>
      <div><strong title={item.title}>{item.title}</strong><small title={item.origin}>{item.origin || 'No origin recorded'}</small><small>{item.trust_level} / score {item.ai_score ?? 'unavailable'}{item.task_families.length ? ` / ${item.task_families.join(', ')}` : ''}</small></div>
      <div className="information-horizon-actions"><code>{item.next_action}</code>{item.primary_capture ? <button type="button" className="information-capture-primary" title="Inspect the captured primary evidence before triage" onClick={() => onInspectSource?.(item.primary_capture?.source_id || '')}><Inbox size={14} />Review primary evidence</button> : <button type="button" className="information-capture-primary" disabled={!canWrite || !item.origin || Boolean(capturingSourceId)} title="Capture the linked public page as reviewable primary evidence" onClick={() => void onCapturePrimary(item)}><Download size={14} />{capturingSourceId === item.source_id ? 'Capturing...' : 'Capture primary source'}</button>}{onInspectSource ? <button type="button" className="icon-button" aria-label={`Inspect source ${item.source_id}`} title="Inspect authorized source" onClick={() => onInspectSource(item.source_id)}><Inbox size={14} /></button> : null}</div>
    </li>)}</ol>
  </section>;
}

function DailyBrief({ brief, onInspectSource }: { brief: NonNullable<KnowledgeInformationOverview['daily_brief']>; onInspectSource?: (sourceId: string) => void }) {
  const captured = brief.sections.captured;
  const repeats = brief.sections.repeat_discoveries;
  const confirmations = brief.sections.confirmation_required;
  const failures = brief.sections.failures;
  return <section className="information-panel information-panel--brief" aria-label="Daily intelligence brief">
    <header><div><span>DAILY INTELLIGENCE BRIEF</span><small>{brief.window.date} / {brief.state} / {brief.coverage}</small></div></header>
    <div className="information-brief-meta"><span>{brief.denominator} completed receipt{brief.denominator === 1 ? '' : 's'}</span><span>Lineage {brief.lineage.receipt_ids.length} receipt refs</span><span>Revision {brief.lineage.revision.slice(0, 12)}</span><span>Feishu {brief.delivery.state}</span></div>
    {brief.state === 'no_sample' ? <p className="information-empty">No completed BSC batch is in this window. The brief remains no_sample.</p> : <div className="information-brief-grid">
      <BriefSection label="New evidence" section={captured} onInspectSource={onInspectSource} />
      <BriefSection label="Repeat discovery" section={repeats} onInspectSource={onInspectSource} />
      <BriefSection label="Needs original source" section={confirmations} onInspectSource={onInspectSource} />
      <BriefSection label="Batch failures" section={failures} onInspectSource={onInspectSource} />
    </div>}
  </section>;
}

function BriefSection({ label, section, onInspectSource }: { label: string; section?: { count: number; items: Array<InformationBriefItem | Record<string, unknown>> }; onInspectSource?: (sourceId: string) => void }) {
  const items = (section?.items || []).slice(0, 8);
  return <section className="information-brief-section">
    <header><span>{label}</span><small>{section?.count || 0}</small></header>
    {items.length ? <ol>{items.map((raw, index) => {
      const entry = raw as Partial<InformationBriefItem> & Record<string, unknown>;
      const title = String(entry.title || entry.canonical_url || entry.batch_id || entry.reason || 'Unresolved item');
      const sourceId = String(entry.source_id || '');
      return <li key={String(entry.receipt_id || entry.batch_id || index)}>
        <div><strong>{title}</strong><small>{String(entry.reason || entry.disposition || entry['status'] || '')}</small></div>
        {sourceId && onInspectSource ? <button type="button" className="icon-button" aria-label={`Inspect source ${sourceId}`} title="Inspect authorized source" onClick={() => onInspectSource(sourceId)}><Inbox size={14} /></button> : null}
      </li>;
    })}</ol> : <p className="information-empty">No records</p>}
    {section && section.count > items.length ? <small className="information-brief-more">+{section.count - items.length} more in receipt ledger</small> : null}
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

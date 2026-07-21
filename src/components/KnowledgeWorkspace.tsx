import { useEffect, useState } from 'react';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import { BookOpen, RefreshCw, X, Database, Radar, Clock3, Network, FileText, GitPullRequest, ShieldCheck, KeyRound, Download, WandSparkles } from 'lucide-react';
import {
  fetchKnowledgeGraph, fetchKnowledgeHealth, fetchKnowledgePage, fetchKnowledgePages, fetchKnowledgeProposals, fetchKnowledgeRunEvents, fetchKnowledgeRuns,
  fetchKnowledgeSchedules, fetchKnowledgeSources, fetchKnowledgeWorkspace, fetchWeeklyDistillations,
  lintKnowledgeProposal, publishKnowledgeProposal, runKnowledgeJob, setKnowledgeWorkspaceAccessKey, transitionKnowledgeSource,
  type KnowledgeHealth, type KnowledgePage, type KnowledgePageDetail, type KnowledgeProposal, type KnowledgeRunEvent, type KnowledgeSource,
  type KnowledgeWorkspaceData, type WeeklyDistillation,
} from '../api/knowledgeWorkspaceApi';

type Props = { onClose: () => void };

export function KnowledgeWorkspace({ onClose }: Props) {
  const [projectId, setProjectId] = useState('default');
  const [accessKey, setAccessKey] = useState('');
  const [workspace, setWorkspace] = useState<KnowledgeWorkspaceData | null>(null);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [runs, setRuns] = useState<Array<Record<string, unknown>>>([]);
  const [schedules, setSchedules] = useState<Array<Record<string, unknown>>>([]);
  const [graph, setGraph] = useState<Array<{ from_id: string; to_id: string; edge_type: string }>>([]);
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [pages, setPages] = useState<KnowledgePage[]>([]);
  const [distillations, setDistillations] = useState<WeeklyDistillation[]>([]);
  const [health, setHealth] = useState<KnowledgeHealth | null>(null);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [runEvents, setRunEvents] = useState<KnowledgeRunEvent[]>([]);
  const [selectedPage, setSelectedPage] = useState<KnowledgePageDetail | null>(null);
  const [selectedProposal, setSelectedProposal] = useState<KnowledgeProposal | null>(null);
  const [error, setError] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [nextWorkspace, nextSources, nextRuns, nextGraph, nextSchedules, nextProposals, nextPages, nextDistillations, nextHealth] = await Promise.all([
        fetchKnowledgeWorkspace(projectId), fetchKnowledgeSources(projectId), fetchKnowledgeRuns(projectId), fetchKnowledgeGraph(projectId),
        fetchKnowledgeSchedules(projectId), fetchKnowledgeProposals(projectId), fetchKnowledgePages(projectId), fetchWeeklyDistillations(projectId), fetchKnowledgeHealth(projectId),
      ]);
      setWorkspace(nextWorkspace);
      setSources(nextSources.sources);
      setRuns(nextRuns.runs);
      setGraph(nextGraph.edges);
      setSchedules(nextSchedules.schedules);
      setProposals(nextProposals.proposals);
      setPages(nextPages.pages);
      setDistillations(nextDistillations.distillations);
      setHealth(nextHealth);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Knowledge workspace failed to load');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [projectId]);

  const inspectPage = async (page: KnowledgePage) => {
    setActionMessage('');
    try {
      setSelectedPage(await fetchKnowledgePage(projectId, page.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Page failed to load');
    }
  };

  const inspectRun = async (runId: string) => {
    setSelectedRunId(runId);
    try {
      const result = await fetchKnowledgeRunEvents(projectId, runId);
      setRunEvents(result.events);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Run event history failed to load');
    }
  };

  const lintProposal = async (proposal: KnowledgeProposal) => {
    setActionBusy(true);
    setActionMessage('');
    try {
      const result = await lintKnowledgeProposal(projectId, proposal.id);
      setActionMessage(result.valid ? 'Lint passed. The proposal can proceed to the evaluation gate.' : result.findings.map((finding) => `${finding.path}: ${finding.code}`).join('; '));
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : 'Lint failed');
    } finally {
      setActionBusy(false);
    }
  };

  const publishProposal = async (proposal: KnowledgeProposal) => {
    setActionBusy(true);
    setActionMessage('');
    try {
      const result = await publishKnowledgeProposal(projectId, proposal.id);
      setActionMessage(`Published ${result.paths.length} Wiki paths at evaluation score ${result.evaluation_score}.`);
      await load();
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : 'Publication was blocked');
    } finally {
      setActionBusy(false);
    }
  };

  const syncNow = async () => {
    setActionBusy(true);
    setActionMessage('');
    try {
      const result = await runKnowledgeJob(projectId, 'source_sync');
      setActionMessage(`Source sync ${result.status}: ${result.run_id}.`);
      await load();
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : 'Source sync failed');
    } finally {
      setActionBusy(false);
    }
  };

  const maintainNow = async () => {
    setActionBusy(true);
    setActionMessage('');
    try {
      const result = await runKnowledgeJob(projectId, 'wiki_maintenance');
      setActionMessage(`Wiki maintenance ${result.status}: ${result.run_id}. Review any resulting proposal before publication.`);
      await load();
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : 'Wiki maintenance failed');
    } finally {
      setActionBusy(false);
    }
  };

  const promoteSource = async (source: KnowledgeSource) => {
    setActionBusy(true);
    setActionMessage('');
    try {
      await transitionKnowledgeSource(projectId, source.id, 'eligible');
      setActionMessage(`Evidence approved for governed synthesis: ${source.origin || source.id}.`);
      await load();
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : 'Source approval failed');
    } finally {
      setActionBusy(false);
    }
  };

  const nodes: Node[] = Array.from(new Set(graph.flatMap((edge) => [edge.from_id, edge.to_id]))).map((id, index) => ({
    id, data: { label: id }, position: { x: 80 + (index % 3) * 190, y: 75 + Math.floor(index / 3) * 110 },
  }));
  const edges: Edge[] = graph.map((edge, index) => ({ id: `${edge.from_id}-${edge.to_id}-${index}`, source: edge.from_id, target: edge.to_id, label: edge.edge_type, animated: true }));

  return <section className="knowledge-workspace" aria-label="Knowledge workspace">
    <header className="knowledge-workspace__header">
      <div><span className="eyebrow"><BookOpen size={14} /> KNOWLEDGE WORKSPACE</span><h2>Evidence, proposals, and growth loops.</h2></div>
      <div className="knowledge-workspace__actions">
        <input value={projectId} onChange={(event) => setProjectId(event.target.value)} aria-label="Project ID" />
        <input type="password" value={accessKey} onChange={(event) => setAccessKey(event.target.value)} placeholder="Access key" aria-label="Knowledge access key" />
        <button onClick={() => { setKnowledgeWorkspaceAccessKey(accessKey); void load(); }} title="Use this key only for the current browser session"><KeyRound size={15} /> Connect</button>
        <button onClick={() => void syncNow()} disabled={actionBusy} title="Capture user-authored Obsidian notes as immutable evidence"><Download size={15} /> Sync</button>
        <button onClick={() => void maintainNow()} disabled={actionBusy} title="Compile approved evidence into a reviewable Wiki proposal"><WandSparkles size={15} /> Maintain</button>
        <button onClick={() => void load()} disabled={loading} title="Refresh project records"><RefreshCw size={15} className={loading ? 'spin' : ''} /> Refresh</button>
        <button className="icon-button" onClick={onClose} aria-label="Close knowledge workspace"><X size={18} /></button>
      </div>
    </header>
    {error && <div className="knowledge-workspace__error">{error}</div>}
    {loading && !workspace ? <div className="knowledge-workspace__loading">Loading the project knowledge state...</div> : <>
      <div className="knowledge-metrics">
        <Metric icon={<Database />} label="Evidence" value={workspace?.sources ?? 0} detail={workspace?.vault.configured ? 'Vault connected' : 'Vault unconfigured'} />
        <Metric icon={<Radar />} label="Runs" value={workspace?.runs ?? 0} detail="Auditable execution" />
        <Metric icon={<Clock3 />} label="Schedules" value={workspace?.schedules ?? 0} detail="Persistent intent" />
        <Metric icon={<Network />} label="Relations" value={graph.length} detail="Derived graph edges" />
        <Metric icon={<ShieldCheck />} label="Citation coverage" value={health?.citation_coverage === null || health?.citation_coverage === undefined ? 0 : Math.round(health.citation_coverage * 100)} detail={health?.citation_coverage === null ? 'No published pages yet' : `${health?.orphan_page_ids.length ?? 0} orphan pages`} />
      </div>
      <div className="knowledge-grid">
        <article><header><span>Evidence Inbox</span><small>{sources.length} records</small></header><div className="knowledge-list">{sources.length ? sources.map((source) => <div className="knowledge-source" key={source.id}><span className={`source-status source-status--${source.status}`}>{source.status}</span><div><strong>{source.origin || source.id}</strong><p>{source.source_type} / {source.trust_level}</p></div>{source.status === 'validated' && <button className="knowledge-source__approve" disabled={actionBusy} onClick={() => void promoteSource(source)} title="Approve this evidence for proposal-only synthesis">Approve</button>}</div>) : <Empty text="No evidence has been captured for this project." />}</div></article>
        <article><header><span>Knowledge Graph</span><small>{graph.length} edges</small></header><div className="knowledge-graph">{nodes.length ? <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}><Background /><Controls showInteractive={false} /></ReactFlow> : <Empty text="Published citations and links will appear here after a proposal passes the gate." />}</div></article>
        <article><header><span>Run Ledger</span><small>{runs.length} runs</small></header><div className="knowledge-list">{runs.length ? runs.slice(0, 8).map((run) => <button className={`knowledge-run knowledge-run--select ${selectedRunId === String(run.id) ? 'is-selected' : ''}`} key={String(run.id)} onClick={() => void inspectRun(String(run.id))}><span>{String(run.status)}</span><strong>{String(run.run_type)}</strong><small>{String(run.trigger)}</small></button>) : <Empty text="No governed knowledge run has been recorded yet." />}</div>{selectedRunId && <div className="run-event-list">{runEvents.length ? runEvents.map((event) => <p key={event.id}><span>{event.sequence}</span>{event.event_type}</p>) : <Empty text="This run has no persisted events yet." />}</div>}</article>
        <article><header><span>Automation</span><small>{schedules.length} schedules</small></header><div className="knowledge-list">{schedules.length ? schedules.map((schedule) => <div className="knowledge-run" key={String(schedule.id)}><span>{schedule.enabled ? 'enabled' : 'paused'}</span><strong>{String(schedule.job_type)}</strong><small>{String(schedule.cron)}</small></div>) : <Empty text="Schedules remain intentionally inactive until durable Celery execution is available." />}</div></article>
      </div>
      <div className="knowledge-review-grid">
        <article><header><span><GitPullRequest size={15} /> Proposal Review</span><small>{proposals.length} records</small></header><div className="knowledge-list">{proposals.length ? proposals.map((proposal) => <button className={`knowledge-proposal ${selectedProposal?.id === proposal.id ? 'is-selected' : ''}`} key={proposal.id} onClick={() => setSelectedProposal(proposal)}><span>{proposal.status}</span><strong>{proposal.rationale || proposal.id}</strong><small>{proposal.operations.length} operations</small></button>) : <Empty text="No reviewable proposal has been recorded." />}</div>{selectedProposal && <div className="proposal-detail"><div className="proposal-detail__actions"><strong>{selectedProposal.status}</strong><button disabled={actionBusy || selectedProposal.status !== 'draft'} onClick={() => void lintProposal(selectedProposal)}>Lint</button><button disabled={actionBusy || selectedProposal.status !== 'draft'} onClick={() => void publishProposal(selectedProposal)}><ShieldCheck size={14} /> Publish</button></div>{selectedProposal.operations.map((operation) => <pre key={operation.id}><small>{operation.operation} {operation.path}</small>{operation.content || 'No content body'}</pre>)}</div>}</article>
        <article><header><span><FileText size={15} /> Published Wiki</span><small>{pages.length} pages</small></header><div className="knowledge-reader"><nav>{pages.length ? pages.map((page) => <button key={page.id} onClick={() => void inspectPage(page)} className={selectedPage?.page.id === page.id ? 'is-selected' : ''}><span>{page.page_kind}</span>{page.title}</button>) : <Empty text="Published pages appear after a proposal passes every gate." />}</nav><div>{selectedPage ? <><h3>{selectedPage.page.title}</h3><p className="knowledge-page-meta">{selectedPage.page.path} / revision {selectedPage.page.version}</p><pre>{selectedPage.content}</pre><div className="citation-list">{selectedPage.citations.map((citation) => <p key={`${citation.source_id}-${citation.claim_text}`}><span>[source:{citation.source_id}]</span>{citation.claim_text}</p>)}</div></> : <Empty text="Choose a published page to inspect its stored revision and citations." />}</div></div></article>
        <article><header><span>Weekly Distillation</span><small>{distillations.length} weeks</small></header><div className="knowledge-list">{distillations.length ? distillations.map((item) => <div className="knowledge-run" key={item.id}><span>{item.status}</span><strong>{item.week}</strong><small>{item.knowledge_path}</small></div>) : <Empty text="No source-backed weekly distillation has been generated." />}</div></article>
        <article><header><span>Knowledge Health</span><small>{health?.status ?? 'unavailable'}</small></header><div className="knowledge-list"><HealthRow label="Dangling citations" value={health?.dangling_citation_count ?? 0} /><HealthRow label="Stale pages" value={health?.stale_page_ids.length ?? 0} /><HealthRow label="Uncited eligible evidence" value={health?.uncited_eligible_source_ids.length ?? 0} /><HealthRow label="Pending proposals" value={health?.pending_proposal_ids.length ?? 0} /></div></article>
      </div>
      {actionMessage && <div className="knowledge-action-message" role="status">{actionMessage}</div>}
    </>}
  </section>;
}

function Metric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: number; detail: string }) {
  return <article className="knowledge-metric"><span>{icon}</span><div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div></article>;
}

function Empty({ text }: { text: string }) { return <p className="knowledge-empty">{text}</p>; }
function HealthRow({ label, value }: { label: string; value: number }) { return <div className="knowledge-run"><span>{value}</span><strong>{label}</strong></div>; }

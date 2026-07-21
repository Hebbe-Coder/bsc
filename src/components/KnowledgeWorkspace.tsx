import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import {
  AlertTriangle, BookOpen, CheckCircle2, ChevronRight, Clock3, Database, Download, FileClock,
  FileText, GitPullRequest, KeyRound, Link2, Network, Pause, Play, RefreshCw, RotateCcw,
  Search, ShieldCheck, Sparkles, WandSparkles, X,
} from 'lucide-react';
import {
  configureKnowledgeSchedule, fetchKnowledgeGraph, fetchKnowledgeHealth, fetchKnowledgeHealthTrend,
  fetchKnowledgePage, fetchKnowledgePages, fetchKnowledgeProposals, fetchKnowledgeRunEvents,
  fetchKnowledgeRuns, fetchKnowledgeSchedules, fetchKnowledgeSources, fetchKnowledgeWorkspace,
  fetchWeeklyDistillation, fetchWeeklyDistillations, lintKnowledgeProposal, publishKnowledgeProposal,
  rejectKnowledgeProposal, retryKnowledgeRun, runKnowledgeJob, setKnowledgeScheduleState,
  setKnowledgeWorkspaceAccessKey, streamKnowledgeRunEvents, transitionKnowledgeSource,
  type KnowledgeGraph, type KnowledgeGraphNode, type KnowledgeHealth, type KnowledgeHealthTrend,
  type KnowledgePage, type KnowledgePageDetail, type KnowledgeProposal, type KnowledgeRun,
  type KnowledgeRunEvent, type KnowledgeSchedule, type KnowledgeSource, type KnowledgeWorkspaceData,
  type WeeklyDistillation, type WeeklyDistillationDetail,
} from '../api/knowledgeWorkspaceApi';

type Props = { onClose: () => void };
type CenterView = 'page' | 'proposal' | 'run' | 'graph' | 'distillation';
type MobilePane = 'tree' | 'main' | 'inspector';
type GraphNodeData = { record: KnowledgeGraphNode; label: string };
type ProposalBaseline = Record<string, string>;

const JOB_TYPES = ['source_sync', 'horizon_capture', 'wiki_maintenance', 'knowledge_lint_eval', 'weekly_distillation'];
const TERMINAL_RUNS = new Set(['completed', 'failed', 'cancelled', 'unavailable']);
const TrendChart = lazy(() => import('echarts-for-react'));

export function KnowledgeWorkspace({ onClose }: Props) {
  const [projectId, setProjectId] = useState('default');
  const [accessKey, setAccessKey] = useState('');
  const [workspace, setWorkspace] = useState<KnowledgeWorkspaceData | null>(null);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [runs, setRuns] = useState<KnowledgeRun[]>([]);
  const [schedules, setSchedules] = useState<KnowledgeSchedule[]>([]);
  const [graph, setGraph] = useState<KnowledgeGraph>({ nodes: [], edges: [], count: 0 });
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [pages, setPages] = useState<KnowledgePage[]>([]);
  const [distillations, setDistillations] = useState<WeeklyDistillation[]>([]);
  const [health, setHealth] = useState<KnowledgeHealth | null>(null);
  const [trend, setTrend] = useState<KnowledgeHealthTrend | null>(null);
  const [selectedPage, setSelectedPage] = useState<KnowledgePageDetail | null>(null);
  const [selectedSource, setSelectedSource] = useState<KnowledgeSource | null>(null);
  const [selectedProposal, setSelectedProposal] = useState<KnowledgeProposal | null>(null);
  const [selectedRun, setSelectedRun] = useState<KnowledgeRun | null>(null);
  const [selectedDistillation, setSelectedDistillation] = useState<WeeklyDistillationDetail | null>(null);
  const [proposalBaselines, setProposalBaselines] = useState<ProposalBaseline>({});
  const [runEvents, setRunEvents] = useState<KnowledgeRunEvent[]>([]);
  const [centerView, setCenterView] = useState<CenterView>('page');
  const [mobilePane, setMobilePane] = useState<MobilePane>('main');
  const [isCompactViewport, setIsCompactViewport] = useState(() => window.matchMedia('(max-width: 780px)').matches);
  const [graphEdgeType, setGraphEdgeType] = useState('');
  const [graphNodeType, setGraphNodeType] = useState('');
  const [graphNodeStatus, setGraphNodeStatus] = useState('');
  const [scheduleJobType, setScheduleJobType] = useState('source_sync');
  const [scheduleCron, setScheduleCron] = useState('0 8 * * 1');
  const [error, setError] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const requestVersion = useRef(0);

  const load = async (graphFilter = graphEdgeType) => {
    const version = ++requestVersion.current;
    setLoading(true);
    setError('');
    try {
      const [nextWorkspace, nextSources, nextRuns, nextGraph, nextSchedules, nextProposals, nextPages, nextDistillations, nextHealth, nextTrend] = await Promise.all([
        fetchKnowledgeWorkspace(projectId), fetchKnowledgeSources(projectId), fetchKnowledgeRuns(projectId), fetchKnowledgeGraph(projectId, graphFilter),
        fetchKnowledgeSchedules(projectId), fetchKnowledgeProposals(projectId), fetchKnowledgePages(projectId), fetchWeeklyDistillations(projectId),
        fetchKnowledgeHealth(projectId), fetchKnowledgeHealthTrend(projectId),
      ]);
      if (version !== requestVersion.current) return;
      setWorkspace(nextWorkspace);
      setSources(nextSources.sources);
      setRuns(nextRuns.runs);
      setGraph(nextGraph);
      setSchedules(nextSchedules.schedules);
      setProposals(nextProposals.proposals);
      setPages(nextPages.pages);
      setDistillations(nextDistillations.distillations);
      setHealth(nextHealth);
      setTrend(nextTrend);
    } catch (reason) {
      if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : 'Knowledge workspace failed to load');
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [projectId]);
  useEffect(() => { void load(graphEdgeType); }, [graphEdgeType]);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 780px)');
    const sync = () => setIsCompactViewport(query.matches);
    sync();
    query.addEventListener('change', sync);
    return () => query.removeEventListener('change', sync);
  }, []);

  useEffect(() => {
    if (!selectedRun) return undefined;
    const controller = new AbortController();
    let lastSequence = 0;
    let active = true;
    const appendEvents = (incoming: KnowledgeRunEvent[]) => {
      setRunEvents((previous) => {
        const current = new Map(previous.map((event) => [event.sequence, event]));
        for (const event of incoming) current.set(event.sequence, event);
        const next = [...current.values()].sort((left, right) => left.sequence - right.sequence);
        lastSequence = next.at(-1)?.sequence ?? lastSequence;
        return next;
      });
    };
    const connect = async () => {
      try {
        const initial = await fetchKnowledgeRunEvents(projectId, selectedRun.id);
        if (!active) return;
        appendEvents(initial.events);
        if (TERMINAL_RUNS.has(selectedRun.status)) return;
        await streamKnowledgeRunEvents(projectId, selectedRun.id, lastSequence, controller.signal, (event) => {
          if (event.run_id === selectedRun.id) appendEvents([event]);
        });
      } catch (reason) {
        if (active && !controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Run event stream failed');
      }
    };
    setRunEvents([]);
    void connect();
    return () => { active = false; controller.abort(); };
  }, [projectId, selectedRun?.id]);

  useEffect(() => {
    if (!selectedProposal) return undefined;
    let active = true;
    const loadBaselines = async () => {
      const uniquePaths = [...new Set(selectedProposal.operations.map((operation) => operation.path))];
      const records = await Promise.all(uniquePaths.map(async (path) => {
        const page = pages.find((candidate) => candidate.path === path);
        if (!page) return [path, ''] as const;
        const detail = await fetchKnowledgePage(projectId, page.id);
        return [path, detail.content] as const;
      }));
      if (active) setProposalBaselines(Object.fromEntries(records));
    };
    setProposalBaselines({});
    void loadBaselines().catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : 'Proposal baseline failed to load');
    });
    return () => { active = false; };
  }, [projectId, selectedProposal?.id, pages]);

  const showMessage = (message: string) => { setError(''); setActionMessage(message); };
  const withAction = async (action: () => Promise<void>) => {
    setActionBusy(true);
    setActionMessage('');
    try { await action(); } catch (reason) { setActionMessage(reason instanceof Error ? reason.message : 'Knowledge operation failed'); } finally { setActionBusy(false); }
  };

  const inspectPage = async (page: KnowledgePage) => {
    try {
      setSelectedPage(await fetchKnowledgePage(projectId, page.id));
      setCenterView('page');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Page failed to load'); }
  };
  const inspectProposal = (proposal: KnowledgeProposal) => { setSelectedProposal(proposal); setCenterView('proposal'); };
  const inspectRun = (run: KnowledgeRun) => { setSelectedRun(run); setCenterView('run'); };
  const inspectDistillation = async (item: WeeklyDistillation) => {
    try { setSelectedDistillation(await fetchWeeklyDistillation(projectId, item.id)); setCenterView('distillation'); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Weekly distillation failed to load'); }
  };
  const inspectSource = (sourceId: string) => {
    const source = sources.find((item) => item.id === sourceId);
    if (source) setSelectedSource(source);
  };
  const followWikiLink = (path: string) => {
    const normalized = path.endsWith('.md') ? path : `${path}.md`;
    const page = pages.find((item) => item.path === normalized || item.path.endsWith(`/${normalized}`));
    if (page) void inspectPage(page);
    else showMessage(`Linked page ${normalized} is not published in this project.`);
  };

  const runJob = (jobType: string) => withAction(async () => {
    const result = await runKnowledgeJob(projectId, jobType);
    showMessage(`${jobType} ${result.status}: ${result.run_id}`);
    await load();
    const persisted = (await fetchKnowledgeRuns(projectId)).runs.find((item) => item.id === result.run_id);
    if (persisted) inspectRun(persisted);
  });
  const promoteSource = (source: KnowledgeSource) => withAction(async () => {
    await transitionKnowledgeSource(projectId, source.id, 'eligible');
    showMessage(`Evidence approved for governed synthesis: ${source.origin || source.id}.`);
    await load();
  });
  const lintProposal = (proposal: KnowledgeProposal) => withAction(async () => {
    const result = await lintKnowledgeProposal(projectId, proposal.id);
    showMessage(result.valid ? 'Lint passed. Evaluation will still decide publication.' : result.findings.map((finding) => `${finding.path}: ${finding.code}`).join('; '));
  });
  const publishProposal = (proposal: KnowledgeProposal) => withAction(async () => {
    const result = await publishKnowledgeProposal(projectId, proposal.id);
    showMessage(`Published ${result.paths.length} Wiki files at evaluation score ${result.evaluation_score}.`);
    await load();
  });
  const rejectProposal = (proposal: KnowledgeProposal) => withAction(async () => {
    await rejectKnowledgeProposal(projectId, proposal.id);
    showMessage('Proposal rejected without changing published Wiki content.');
    await load();
  });
  const retryRun = (run: KnowledgeRun) => withAction(async () => {
    const result = await retryKnowledgeRun(projectId, run.id);
    showMessage(`Retry ${result.status}: ${result.run_id}`);
    await load();
  });
  const toggleSchedule = (schedule: KnowledgeSchedule) => withAction(async () => {
    const enabled = Boolean(schedule.enabled);
    await setKnowledgeScheduleState(projectId, schedule.id, !enabled);
    showMessage(enabled ? 'Schedule paused.' : 'Schedule enabled.');
    await load();
  });
  const createSchedule = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void withAction(async () => {
      const result = await configureKnowledgeSchedule(projectId, scheduleJobType, scheduleCron);
      showMessage(result.schedule.enabled ? 'Schedule saved and enabled.' : 'Schedule saved. Durable worker availability is required before it can run.');
      await load();
    });
  };

  const maxNodes = 160;
  const filteredGraphNodes = graph.nodes.filter((record) => (
    (!graphNodeType || record.node_type === graphNodeType)
    && (!graphNodeStatus || record.status === graphNodeStatus)
  ));
  const renderedRecords = filteredGraphNodes.slice(0, maxNodes);
  const visibleNodeIds = new Set(renderedRecords.map((record) => record.id));
  const flowNodes: Node<GraphNodeData>[] = renderedRecords.map((record, index) => ({
    id: record.id,
    data: { record, label: record.label },
    type: 'default',
    position: { x: 40 + (index % 4) * 220, y: 36 + Math.floor(index / 4) * 118 },
    className: `knowledge-flow-node knowledge-flow-node--${record.node_type}`,
  }));
  const flowEdges: Edge[] = graph.edges
    .filter((edge) => visibleNodeIds.has(edge.from_id) && visibleNodeIds.has(edge.to_id))
    .map((edge) => ({ id: edge.id, source: edge.from_id, target: edge.to_id, label: edge.edge_type, type: 'smoothstep', animated: false }));
  const graphTypes = [...new Set(graph.edges.map((edge) => edge.edge_type))];
  const graphNodeTypes = [...new Set(graph.nodes.map((node) => node.node_type))].sort();
  const graphNodeStatuses = [...new Set(graph.nodes.map((node) => node.status).filter(Boolean))].sort();
  const sourceLabels = trend?.source_throughput.map((item) => item.date) ?? [];
  const sourceValues = trend?.source_throughput.map((item) => item.count) ?? [];
  const evalLabels = trend?.evaluations.map((item) => item.at.slice(0, 10)) ?? [];
  const evalValues = trend?.evaluations.map((item) => item.score) ?? [];
  const proposalLabels = trend?.proposal_outcomes.map((item) => item.date) ?? [];
  const proposalStatuses = [...new Set((trend?.proposal_outcomes ?? []).flatMap((item) => Object.keys(item.statuses)))].sort();
  const proposalValues = Object.fromEntries(proposalStatuses.map((status) => [
    status,
    (trend?.proposal_outcomes ?? []).map((item) => item.statuses[status] ?? 0),
  ]));
  const showTrendCharts = !isCompactViewport || mobilePane === 'inspector';

  return <section className="knowledge-workspace" aria-label="Knowledge workspace">
    <header className="knowledge-workspace__header">
      <div className="knowledge-workspace__title"><span className="eyebrow"><BookOpen size={14} /> KNOWLEDGE WORKSPACE</span><h2>Evidence, proposals, and growth loops.</h2><p>Project-scoped Wiki maintenance with evidence, gates, and replayable execution.</p></div>
      <div className="knowledge-workspace__actions">
        <label><span>Project</span><input value={projectId} onChange={(event) => setProjectId(event.target.value)} aria-label="Project ID" /></label>
        <label><span>Access key</span><input type="password" value={accessKey} onChange={(event) => setAccessKey(event.target.value)} placeholder="Access key" aria-label="Knowledge access key" /></label>
        <button onClick={() => { setKnowledgeWorkspaceAccessKey(accessKey); void load(); }} title="Use this key only for the current browser session"><KeyRound size={15} /> Connect</button>
        <button onClick={() => void runJob('source_sync')} disabled={actionBusy} title="Capture user-authored Obsidian material as immutable evidence"><Download size={15} /> Sync</button>
        <button onClick={() => void runJob('wiki_maintenance')} disabled={actionBusy} title="Compile eligible evidence into a reviewable proposal"><WandSparkles size={15} /> Maintain</button>
        <button onClick={() => void load()} disabled={loading} title="Refresh current project state"><RefreshCw size={15} className={loading ? 'spin' : ''} /> Refresh</button>
        <button className="icon-button" onClick={onClose} aria-label="Close knowledge workspace"><X size={18} /></button>
      </div>
    </header>
    {error && <div className="knowledge-workspace__error" role="alert">{error}</div>}
    {actionMessage && <div className="knowledge-action-message" role="status">{actionMessage}</div>}
    {loading && !workspace ? <div className="knowledge-workspace__loading">Loading the project knowledge state...</div> : <>
      <div className="knowledge-status-strip">
        <StatusMetric icon={<Database size={16} />} label="Evidence" value={workspace?.sources ?? 0} detail={workspace?.vault.configured ? 'Vault connected' : 'Vault unconfigured'} />
        <StatusMetric icon={<GitPullRequest size={16} />} label="Proposals" value={proposals.length} detail={`${health?.pending_proposal_ids.length ?? 0} awaiting review`} />
        <StatusMetric icon={<Network size={16} />} label="Relations" value={graph.count} detail={graphEdgeType || 'all edge types'} />
        <StatusMetric icon={<ShieldCheck size={16} />} label="Citation coverage" value={health?.citation_coverage == null ? 'N/A' : `${Math.round(health.citation_coverage * 100)}%`} detail={health?.evaluation.status === 'unavailable' ? 'Evaluation baseline missing' : `Evaluation ${health?.evaluation.status}`} />
      </div>
      <nav className="knowledge-mobile-tabs" aria-label="Knowledge mobile panes">
        <button className={mobilePane === 'tree' ? 'is-active' : ''} onClick={() => setMobilePane('tree')}>Navigate</button>
        <button className={mobilePane === 'main' ? 'is-active' : ''} onClick={() => setMobilePane('main')}>Workspace</button>
        <button className={mobilePane === 'inspector' ? 'is-active' : ''} onClick={() => setMobilePane('inspector')}>Inspect</button>
      </nav>
      <div className="knowledge-layout" data-mobile-pane={mobilePane}>
        <aside className="knowledge-pane knowledge-pane--tree" aria-label="Vault tree">
          <PaneHeader title="Vault" detail={workspace?.vault.configured ? 'configured' : 'unconfigured'} />
          <div className="knowledge-vault-state"><span className={workspace?.vault.configured ? 'is-ready' : 'is-warning'}>{workspace?.vault.configured ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}</span><span>{workspace?.vault.configured ? 'Managed project root' : 'Map a project Vault before publication'}</span></div>
          <VaultTree pages={pages} selectedPageId={selectedPage?.page.id ?? ''} onSelect={inspectPage} />
          <PaneHeader title="Evidence" detail={`${sources.length} records`} />
          <div className="knowledge-list knowledge-list--tree">{sources.length ? sources.map((source) => <button className={`knowledge-record ${selectedSource?.id === source.id ? 'is-selected' : ''}`} key={source.id} onClick={() => setSelectedSource(source)}><span className={`source-status source-status--${source.status}`}>{source.status}</span><strong>{source.origin || source.id}</strong><small>{source.source_type}</small></button>) : <Empty text="No evidence has been captured for this project." />}</div>
          <PaneHeader title="Review queue" detail={`${proposals.length}`} />
          <div className="knowledge-list knowledge-list--tree">{proposals.length ? proposals.map((proposal) => <button className={`knowledge-record ${selectedProposal?.id === proposal.id ? 'is-selected' : ''}`} key={proposal.id} onClick={() => inspectProposal(proposal)}><span className="record-kind">{proposal.status}</span><strong>{proposal.rationale || proposal.id}</strong><small>{proposal.operations.length} operations</small></button>) : <Empty text="No reviewable proposal has been recorded." />}</div>
        </aside>

        <main className="knowledge-pane knowledge-pane--main" aria-label="Knowledge work surface">
          <nav className="knowledge-view-tabs" aria-label="Knowledge views">
            <ViewTab active={centerView === 'page'} onClick={() => setCenterView('page')} icon={<FileText size={14} />} label="Wiki" />
            <ViewTab active={centerView === 'proposal'} onClick={() => setCenterView('proposal')} icon={<GitPullRequest size={14} />} label="Diff" />
            <ViewTab active={centerView === 'run'} onClick={() => setCenterView('run')} icon={<Clock3 size={14} />} label="Runs" />
            <ViewTab active={centerView === 'graph'} onClick={() => setCenterView('graph')} icon={<Network size={14} />} label="Graph" />
            <ViewTab active={centerView === 'distillation'} onClick={() => setCenterView('distillation')} icon={<Sparkles size={14} />} label="Weekly" />
          </nav>
          {centerView === 'page' && <WikiReader page={selectedPage} pages={pages} onCitation={inspectSource} onWikiLink={followWikiLink} />}
          {centerView === 'proposal' && <ProposalReview proposal={selectedProposal} baselines={proposalBaselines} busy={actionBusy} onLint={lintProposal} onPublish={publishProposal} onReject={rejectProposal} />}
          {centerView === 'run' && <RunTimeline runs={runs} selectedRun={selectedRun} events={runEvents} busy={actionBusy} onSelect={inspectRun} onRetry={retryRun} />}
          {centerView === 'graph' && <section className="knowledge-graph-view"><header className="knowledge-content-header"><div><span className="eyebrow">RELATIONSHIP GRAPH</span><h3>Traceable knowledge relations</h3></div><div className="knowledge-graph-filters"><label className="knowledge-select-label">Edge filter<select value={graphEdgeType} onChange={(event) => setGraphEdgeType(event.target.value)}><option value="">All edges</option>{graphTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label className="knowledge-select-label">Node type<select value={graphNodeType} onChange={(event) => setGraphNodeType(event.target.value)}><option value="">All types</option>{graphNodeTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label className="knowledge-select-label">Node status<select value={graphNodeStatus} onChange={(event) => setGraphNodeStatus(event.target.value)}><option value="">All states</option>{graphNodeStatuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label></div></header><div className="knowledge-graph-canvas">{flowNodes.length ? <ReactFlow nodes={flowNodes} edges={flowEdges} fitView nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => { const record = node.data.record; if (record.node_type === 'source') inspectSource(record.id); if (record.node_type === 'page') { const page = pages.find((item) => item.id === record.id); if (page) void inspectPage(page); } if (record.node_type === 'proposal') { const proposal = proposals.find((item) => item.id === record.id); if (proposal) inspectProposal(proposal); } }}><Background gap={22} size={1} /><Controls showInteractive={false} /></ReactFlow> : <Empty text="No persisted relationships match the selected graph filters." />}</div>{filteredGraphNodes.length > maxNodes && <p className="knowledge-limit-note">Showing {maxNodes} of {filteredGraphNodes.length} persisted nodes. Narrow the graph filters to inspect a smaller relationship slice.</p>}</section>}
          {centerView === 'distillation' && <DistillationReader records={distillations} selected={selectedDistillation} onSelect={inspectDistillation} />}
        </main>

        <aside className="knowledge-pane knowledge-pane--inspector" aria-label="Evidence and health inspector">
          <PaneHeader title="Source inspector" detail={selectedSource?.status || 'select evidence'} />
          {selectedSource ? <SourceInspector source={selectedSource} busy={actionBusy} onApprove={promoteSource} /> : <Empty text="Select evidence to inspect immutable provenance, policy state, and capture metadata." />}
          <PaneHeader title="Automation" detail={`${schedules.length} schedules`} />
          <div className="knowledge-list">{schedules.length ? schedules.map((schedule) => <div className="knowledge-schedule" key={schedule.id}><div><strong>{schedule.job_type}</strong><small>{schedule.cron} / {schedule.timezone}</small><small>{schedule.enabled ? `Next ${formatTimestamp(schedule.next_run_at)}` : 'Manual-only or paused'}</small></div><button className="icon-button" disabled={actionBusy} title={schedule.enabled ? 'Pause schedule' : 'Enable schedule'} onClick={() => void toggleSchedule(schedule)}>{schedule.enabled ? <Pause size={14} /> : <Play size={14} />}</button></div>) : <Empty text="Schedules remain unavailable until durable Celery execution is configured." />}</div>
          <form className="knowledge-schedule-form" onSubmit={createSchedule}><label>Job<select value={scheduleJobType} onChange={(event) => setScheduleJobType(event.target.value)}>{JOB_TYPES.map((jobType) => <option key={jobType} value={jobType}>{jobType}</option>)}</select></label><label>Cron<input value={scheduleCron} onChange={(event) => setScheduleCron(event.target.value)} aria-label="Schedule cron" /></label><button disabled={actionBusy} type="submit"><Clock3 size={14} /> Save cadence</button></form>
          <PaneHeader title="Knowledge health" detail={health?.status || 'unavailable'} />
          <HealthInspector health={health} />
          <PaneHeader title="Observed trends" detail="persisted records only" />
          {showTrendCharts && <><section className="knowledge-chart"><Suspense fallback={<Empty text="Loading source trend..." />}><TrendChart option={trendOption('Sources captured', sourceLabels, sourceValues, '#64d5a9')} style={{ height: 180 }} notMerge lazyUpdate /></Suspense></section><section className="knowledge-chart"><Suspense fallback={<Empty text="Loading proposal trend..." />}><TrendChart option={proposalTrendOption(proposalLabels, proposalValues)} style={{ height: 180 }} notMerge lazyUpdate /></Suspense></section><section className="knowledge-chart"><Suspense fallback={<Empty text="Loading evaluation trend..." />}><TrendChart option={trendOption('Evaluation score', evalLabels, evalValues, '#88b9ff', true)} style={{ height: 180 }} notMerge lazyUpdate /></Suspense></section></>}
        </aside>
      </div>
    </>}
  </section>;
}

function PaneHeader({ title, detail }: { title: string; detail: string }) { return <header className="knowledge-pane-header"><span>{title}</span><small>{detail}</small></header>; }
function Empty({ text }: { text: string }) { return <p className="knowledge-empty">{text}</p>; }
function ViewTab({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) { return <button className={active ? 'is-active' : ''} onClick={onClick}>{icon}{label}</button>; }
function StatusMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: number | string; detail: string }) { return <div className="knowledge-status-metric"><span>{icon}</span><div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div></div>; }

function VaultTree({ pages, selectedPageId, onSelect }: { pages: KnowledgePage[]; selectedPageId: string; onSelect: (page: KnowledgePage) => void }) {
  const grouped = new Map<string, KnowledgePage[]>();
  for (const page of pages) { const folder = page.path.split('/').slice(0, -1).join('/') || 'wiki'; grouped.set(folder, [...(grouped.get(folder) || []), page]); }
  if (!pages.length) return <Empty text="Published Wiki pages will appear here after a gated proposal is accepted." />;
  return <nav className="knowledge-vault-tree">{[...grouped.entries()].map(([folder, children]) => <section key={folder}><p><ChevronRight size={12} />{folder}</p>{children.map((page) => <button key={page.id} className={selectedPageId === page.id ? 'is-selected' : ''} onClick={() => onSelect(page)}><FileText size={13} />{page.title}</button>)}</section>)}</nav>;
}

function WikiReader({ page, pages, onCitation, onWikiLink }: { page: KnowledgePageDetail | null; pages: KnowledgePage[]; onCitation: (id: string) => void; onWikiLink: (path: string) => void }) {
  if (!page) return <section className="knowledge-reader-empty"><BookOpen size={26} /><h3>Choose a published page</h3><p>The reader displays stored Markdown, revision metadata, citations, and safe internal page links.</p></section>;
  return <section className="knowledge-reader-view"><header className="knowledge-content-header"><div><span className="eyebrow">PUBLISHED WIKI</span><h3>{page.page.title}</h3><p>{page.page.path} / revision {page.page.version}</p></div><span className="record-kind">{page.page.page_kind}</span></header><SafeMarkdown content={page.content} pages={pages} onCitation={onCitation} onWikiLink={onWikiLink} /><section className="knowledge-citations"><h4><Link2 size={14} /> Citations</h4>{page.citations.length ? page.citations.map((citation) => <button key={`${citation.source_id}-${citation.claim_text}`} onClick={() => onCitation(citation.source_id)}><span>[source:{citation.source_id}]</span>{citation.claim_text || citation.anchor || 'Open source provenance'}</button>) : <Empty text="This page has no active source citations." />}</section></section>;
}

function SafeMarkdown({ content, pages, onCitation, onWikiLink }: { content: string; pages: KnowledgePage[]; onCitation: (id: string) => void; onWikiLink: (path: string) => void }) {
  const lines = content.replace(/^---[\s\S]*?---\s*/u, '').split('\n');
  const inline = (value: string) => {
    const segments = value.split(/(\[source:[^\]\s]+\]|\[\[[^\]]+\]\])/g);
    return segments.map((segment, index) => {
      const source = /^\[source:([^\]\s]+)\]$/.exec(segment);
      if (source) return <button className="knowledge-inline-link" key={`${segment}-${index}`} onClick={() => onCitation(source[1])}>{segment}</button>;
      const wiki = /^\[\[([^\]]+)\]\]$/.exec(segment);
      if (wiki) { const target = wiki[1]; const exists = pages.some((page) => page.path === target || page.path === `${target}.md` || page.path.endsWith(`/${target}.md`)); return <button className="knowledge-inline-link" key={`${segment}-${index}`} disabled={!exists} onClick={() => onWikiLink(target)}>{target}</button>; }
      return <span key={`${segment}-${index}`}>{segment}</span>;
    });
  };
  return <article className="safe-markdown">{lines.map((line, index) => {
    if (!line.trim()) return null;
    if (line.startsWith('### ')) return <h5 key={index}>{inline(line.slice(4))}</h5>;
    if (line.startsWith('## ')) return <h4 key={index}>{inline(line.slice(3))}</h4>;
    if (line.startsWith('# ')) return <h3 key={index}>{inline(line.slice(2))}</h3>;
    if (line.startsWith('- ')) return <p className="safe-markdown__item" key={index}>{inline(line.slice(2))}</p>;
    return <p key={index}>{inline(line)}</p>;
  })}</article>;
}

function ProposalReview({ proposal, baselines, busy, onLint, onPublish, onReject }: { proposal: KnowledgeProposal | null; baselines: ProposalBaseline; busy: boolean; onLint: (proposal: KnowledgeProposal) => void; onPublish: (proposal: KnowledgeProposal) => void; onReject: (proposal: KnowledgeProposal) => void }) {
  if (!proposal) return <section className="knowledge-reader-empty"><GitPullRequest size={26} /><h3>Select a proposal</h3><p>Review each persisted operation against its current page body before asking the governed publication gate to apply it.</p></section>;
  const canAct = proposal.status === 'draft';
  return <section className="proposal-review"><header className="knowledge-content-header"><div><span className="eyebrow">GOVERNED PATCH</span><h3>{proposal.rationale || proposal.id}</h3><p>{proposal.source_ids.length} evidence references / {proposal.operations.length} operations</p></div><span className="record-kind">{proposal.status}</span></header><div className="proposal-actions"><button disabled={busy || !canAct} onClick={() => onLint(proposal)}><Search size={14} /> Lint</button><button disabled={busy || !canAct} onClick={() => onPublish(proposal)}><ShieldCheck size={14} /> Publish</button><button className="is-danger" disabled={busy || !canAct} onClick={() => onReject(proposal)}><X size={14} /> Reject</button></div><div className="proposal-operations">{proposal.operations.map((operation) => { const before = baselines[operation.path] ?? ''; const after = operation.operation === 'append' ? `${before}${operation.content}` : operation.operation === 'archive' ? '' : operation.content; return <article key={operation.id}><header><span>{operation.operation}</span><strong>{operation.path}</strong>{operation.destination_path && <small>to {operation.destination_path}</small>}</header><div className="proposal-diff"><pre><small>Before</small>{before || '(new page or no stored revision)'}</pre><pre><small>After</small>{after || '(archived)'}</pre></div><p>Evidence: {operation.source_ids.length ? operation.source_ids.join(', ') : 'manual operation; no immutable source claim'}</p></article>; })}</div></section>;
}

function RunTimeline({ runs, selectedRun, events, busy, onSelect, onRetry }: { runs: KnowledgeRun[]; selectedRun: KnowledgeRun | null; events: KnowledgeRunEvent[]; busy: boolean; onSelect: (run: KnowledgeRun) => void; onRetry: (run: KnowledgeRun) => void }) {
  return <section className="run-timeline"><header className="knowledge-content-header"><div><span className="eyebrow">RUN LEDGER</span><h3>{selectedRun ? selectedRun.run_type : 'Select a governed run'}</h3><p>{selectedRun ? `${selectedRun.status} / ${selectedRun.trigger}` : 'Runs remain durable even after an SSE reconnect.'}</p></div>{selectedRun && <span className={`run-status run-status--${selectedRun.status}`}>{selectedRun.status}</span>}</header><div className="run-timeline__body"><nav>{runs.length ? runs.map((run) => <button key={run.id} className={selectedRun?.id === run.id ? 'is-selected' : ''} onClick={() => onSelect(run)}><span>{run.status}</span><strong>{run.run_type}</strong><small>{formatTimestamp(run.created_at)}</small></button>) : <Empty text="No governed knowledge run has been recorded yet." />}</nav><section>{selectedRun ? <><div className="run-summary"><p><strong>Trigger:</strong> {selectedRun.trigger}</p>{selectedRun.retry_of && <p><strong>Retry of:</strong> {selectedRun.retry_of}</p>}{selectedRun.error && <p className="run-error"><strong>Error:</strong> {selectedRun.error}</p>}{['failed', 'unavailable', 'cancelled'].includes(selectedRun.status) && <button disabled={busy} onClick={() => onRetry(selectedRun)}><RotateCcw size={14} /> Retry through the normal pipeline</button>}</div><ol className="run-events">{events.length ? events.map((event) => <li key={event.id}><span>{event.sequence}</span><div><strong>{event.event_type}</strong><small>{formatTimestamp(event.created_at)}</small><code>{Object.keys(event.payload).length ? JSON.stringify(event.payload) : 'No event payload'}</code></div></li>) : <Empty text="This run has no persisted events yet." />}</ol></> : <Empty text="Select a run to inspect its durable ordered events." />}</section></div></section>;
}

function DistillationReader({ records, selected, onSelect }: { records: WeeklyDistillation[]; selected: WeeklyDistillationDetail | null; onSelect: (item: WeeklyDistillation) => void }) {
  const documentEntries = selected ? Object.entries(selected.documents) : [];
  return <section className="distillation-reader"><header className="knowledge-content-header"><div><span className="eyebrow">WEEKLY DISTILLATION</span><h3>{selected?.distillation.week || 'Choose a weekly bundle'}</h3><p>{selected ? `Source cutoff ${selected.distillation.source_cutoff}` : 'Three deterministic documents are generated from eligible evidence.'}</p></div><FileClock size={20} /></header><div className="distillation-reader__body"><nav>{records.length ? records.map((item) => <button key={item.id} className={selected?.distillation.id === item.id ? 'is-selected' : ''} onClick={() => onSelect(item)}><span>{item.status}</span><strong>{item.week}</strong><small>{formatTimestamp(item.created_at)}</small></button>) : <Empty text="No source-backed weekly distillation has been generated." />}</nav><section>{documentEntries.length ? documentEntries.map(([path, content]) => <article key={path}><h4>{path.split('/').at(-1)}</h4><pre>{content}</pre></article>) : <Empty text="Select a bundle to read its stored evidence-backed documents." />}</section></div></section>;
}

function SourceInspector({ source, busy, onApprove }: { source: KnowledgeSource; busy: boolean; onApprove: (source: KnowledgeSource) => void }) {
  const curated = Boolean(source.metadata.curated || source.metadata.user_annotation || source.metadata.annotation);
  return <section className="source-inspector"><span className={`source-status source-status--${source.status}`}>{source.status}</span><h3>{source.origin || source.id}</h3><dl><div><dt>Type</dt><dd>{source.source_type}</dd></div><div><dt>Trust</dt><dd>{source.trust_level}</dd></div><div><dt>Captured</dt><dd>{formatTimestamp(source.captured_at)}</dd></div><div><dt>SHA-256</dt><dd>{source.content_hash}</dd></div><div><dt>Vault path</dt><dd>{source.vault_path || 'external or API import'}</dd></div><div><dt>Interpretation</dt><dd>{curated ? 'Curated opinion or user annotation' : 'Immutable evidence record'}</dd></div></dl>{source.supersedes_id && <p className="source-supersedes">Supersedes source {source.supersedes_id}</p>}{source.status === 'validated' && <button disabled={busy} onClick={() => onApprove(source)}><CheckCircle2 size={14} /> Approve for synthesis</button>}</section>;
}

function HealthInspector({ health }: { health: KnowledgeHealth | null }) { if (!health) return <Empty text="Health records are unavailable until the workspace loads." />; return <div className="health-inspector"><HealthRow label="Dangling citations" value={health.dangling_citation_count} /><HealthRow label="Stale citations" value={health.stale_citation_count} /><HealthRow label="Stale pages" value={health.stale_page_ids.length} /><HealthRow label="Orphan pages" value={health.orphan_page_ids.length} /><HealthRow label="Uncited eligible evidence" value={health.uncited_eligible_source_ids.length} /><HealthRow label="Pending proposals" value={health.pending_proposal_ids.length} /><HealthRow label="Contradictions" value={health.contradiction_count} /></div>; }
function HealthRow({ label, value }: { label: string; value: number }) { return <div><strong>{value}</strong><span>{label}</span></div>; }

function trendOption(title: string, labels: string[], values: Array<number | null>, color: string, percentage = false) {
  return { animation: false, title: { text: title, textStyle: { color: '#b9c9d9', fontSize: 11, fontWeight: 500 } }, tooltip: { trigger: 'axis' }, grid: { top: 34, right: 12, bottom: 28, left: 32 }, xAxis: { type: 'category', data: labels, axisLabel: { color: '#8093a5', fontSize: 10 }, axisLine: { lineStyle: { color: '#2e4051' } } }, yAxis: { type: 'value', min: percentage ? 0 : undefined, max: percentage ? 1 : undefined, axisLabel: { color: '#8093a5', fontSize: 10, formatter: percentage ? '{value}' : undefined }, splitLine: { lineStyle: { color: '#1b2935' } } }, series: [{ type: 'line', data: values, smooth: true, showSymbol: labels.length < 16, lineStyle: { color, width: 2 }, itemStyle: { color }, areaStyle: { color: `${color}24` } }], graphic: labels.length ? undefined : [{ type: 'text', left: 'center', top: 'middle', style: { text: 'No persisted observations', fill: '#8093a5', fontSize: 11 } }] };
}

function proposalTrendOption(labels: string[], values: Record<string, number[]>) {
  const statuses = Object.keys(values);
  const palette: Record<string, string> = { approved: '#64d5a9', published: '#78d4df', rejected: '#e78787', failed: '#e8ba62', draft: '#88b9ff', validating: '#c7a7e8', superseded: '#8195a4' };
  return { animation: false, color: statuses.map((status) => palette[status] ?? '#9eb5c5'), title: { text: 'Proposal outcomes', textStyle: { color: '#b9c9d9', fontSize: 11, fontWeight: 500 } }, legend: { data: statuses, top: 19, textStyle: { color: '#91a5b5', fontSize: 9 }, itemWidth: 8, itemHeight: 8 }, tooltip: { trigger: 'axis' }, grid: { top: 52, right: 12, bottom: 28, left: 32 }, xAxis: { type: 'category', data: labels, axisLabel: { color: '#8093a5', fontSize: 10 }, axisLine: { lineStyle: { color: '#2e4051' } } }, yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#8093a5', fontSize: 10 }, splitLine: { lineStyle: { color: '#1b2935' } } }, series: statuses.map((status) => ({ name: status, type: 'bar', stack: 'proposals', data: values[status], barMaxWidth: 26 })), graphic: labels.length ? undefined : [{ type: 'text', left: 'center', top: 'middle', style: { text: 'No persisted proposal outcomes', fill: '#8093a5', fontSize: 11 } }] };
}

function formatTimestamp(value: string | undefined) { if (!value) return 'Not recorded'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }

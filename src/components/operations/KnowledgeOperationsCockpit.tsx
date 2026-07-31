import type { ECharts, EChartsOption } from 'echarts';
import { AlertTriangle, ArrowUpRight, BarChart3, BookOpenCheck, ChevronLeft, ChevronRight, Database, ListFilter, Network, RefreshCw, ShieldAlert, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, { Background, Controls, Handle, Position, type Edge, type Node, type NodeProps } from 'reactflow';
import 'reactflow/dist/style.css';

import {
  fetchOperationsGraph,
  fetchOperationsPortfolio,
  fetchOperationsProject,
  OperationsRequestError,
  type OperationsAction,
  type OperationsGraph,
  type OperationsGraphNode,
  type OperationsMetric,
  type OperationsOverview,
  type OperationsProjectSummary,
} from '../../api/knowledgeOperationsApi';

type View = 'portfolio' | 'project';
type RequestState = 'idle' | 'loading' | 'success' | 'empty' | 'permission' | 'unavailable' | 'offline' | 'error';

type Props = {
  onClose: () => void;
  initialProjectId?: string;
  onOpenKnowledge?: (projectId: string, entityId: string) => void;
  onOpenGrowth?: (projectId: string, entityId: string) => void;
  onOpenDbos?: (projectId: string, missionId: string, artifactId: string) => void;
};

type LifecycleLaneData = {
  lane: string;
  label: string;
  count: number;
  compact: boolean;
  onSelect: (lane: string) => void;
};

type GraphFilters = {
  missionId: string;
  nodeTypes: string[];
  statuses: string[];
  relations: string[];
};

const EMPTY_GRAPH_FILTERS: GraphFilters = { missionId: '', nodeTypes: [], statuses: [], relations: [] };

const LANE_COLORS: Record<string, string> = {
  evidence_source: '#6bb9d1',
  mission: '#d7aa63',
  assumption: '#b1c978',
  risk_constraint: '#e1848d',
  method_sop: '#80b5e5',
  validation: '#72c5a7',
  memory_feedback: '#bb9ad5',
};

function classifyError(error: unknown): { state: RequestState; message: string } {
  if (error instanceof OperationsRequestError) {
    if (error.status === 401 || error.status === 403) return { state: 'permission', message: error.message };
    if (error.status === 503) return { state: 'unavailable', message: error.message };
    return { state: 'error', message: error.message };
  }
  const message = error instanceof Error ? error.message : 'Unable to load knowledge operations.';
  return /failed to fetch|network|abort/i.test(message)
    ? { state: 'offline', message }
    : { state: 'error', message };
}

function metricValue(metric: OperationsMetric | undefined): string {
  if (!metric) return '--';
  if (metric.state !== 'available' || metric.value === null) return 'No sample';
  return metric.unit === 'percent' ? `${metric.value}%` : String(metric.value);
}

function compactLabel(value: string): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized.length > 48 ? `${normalized.slice(0, 47).trimEnd()}...` : normalized;
}

function nodeDisplayLabel(node: OperationsGraphNode): string {
  const genericLabels = new Set(['Assumption', 'Capability selection', 'Constraint', 'Diagnosis', 'Evidence', 'Evidence gap', 'Execution result', 'Memory', 'Risk', 'Runtime context', 'Task verification']);
  if (!genericLabels.has(node.label)) return node.label;
  const reference = node.id.length > 12 ? `${node.id.slice(0, 8)}...` : node.id;
  return `${node.label} #${reference}`;
}

function LifecycleLaneNode({ data }: NodeProps<LifecycleLaneData>) {
  const inspectLane = () => data.onSelect(data.lane);
  return <>
    <Handle type="target" position={data.compact ? Position.Top : Position.Left} isConnectable={false} />
    <button type="button" className={`operations-flow-lane__card operations-flow-lane__card--${data.lane}`} onClick={inspectLane} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); inspectLane(); } }} aria-label={`Inspect ${data.label} records`}>
      <span>{data.label}</span>
      <strong>{data.count}</strong>
      <small>authorized records</small>
    </button>
    <Handle type="source" position={data.compact ? Position.Bottom : Position.Right} isConnectable={false} />
  </>;
}

const lifecycleNodeTypes = { lifecycleLane: LifecycleLaneNode };

function readableFilterValue(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function readableLane(value: string): string {
  const labels: Record<string, string> = {
    mission: 'business problem',
    evidence_source: 'evidence',
    method_sop: 'method or SOP',
    validation: 'validation',
    memory_feedback: 'memory or feedback',
  };
  return labels[value] ?? readableFilterValue(value);
}

function useCompactOperationsLayout(): boolean {
  const [compact, setCompact] = useState(() => typeof window !== 'undefined' && window.innerWidth <= 720);
  useEffect(() => {
    const update = () => setCompact(window.innerWidth <= 720);
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);
  return compact;
}

function graphMissions(catalog: OperationsGraph | null): Array<{ id: string; label: string }> {
  return (catalog?.nodes ?? [])
    .filter((node) => node.type === 'mission')
    .map((node) => ({ id: node.drilldown.mission_id || node.id, label: node.label }))
    .filter((mission, index, all) => all.findIndex((item) => item.id === mission.id) === index)
    .sort((left, right) => left.label.localeCompare(right.label));
}

function GraphFilterFields({
  catalog,
  filters,
  onChange,
  includeMission = false,
  missionLabel = 'Filter lifecycle mission',
  className = '',
}: {
  catalog: OperationsGraph | null;
  filters: GraphFilters;
  onChange: (filters: GraphFilters) => void;
  includeMission?: boolean;
  missionLabel?: string;
  className?: string;
}) {
  const nodes = catalog?.nodes ?? [];
  const missions = graphMissions(catalog);
  const nodeTypes = [...new Set(nodes.map((node) => node.type))].sort();
  const statuses = [...new Set(nodes.map((node) => node.status))].sort();
  const relations = [...new Set(catalog?.edges.map((edge) => edge.relation) ?? [])].sort();
  const setSingle = (key: 'nodeTypes' | 'statuses' | 'relations', value: string) => onChange({ ...filters, [key]: value ? [value] : [] });
  const hasCatalog = Boolean(catalog);

  return <div className={`operations-graph-filters ${className}`.trim()}>
    {includeMission && <label><span>Mission</span><select value={filters.missionId} onChange={(event) => onChange({ ...filters, missionId: event.target.value })} aria-label={missionLabel} disabled={!hasCatalog}><option value="">All persisted missions</option>{missions.map((mission) => <option key={mission.id} value={mission.id}>{compactLabel(mission.label)}</option>)}</select></label>}
    <label><span>Type</span><select value={filters.nodeTypes[0] ?? ''} onChange={(event) => setSingle('nodeTypes', event.target.value)} aria-label="Filter lifecycle node type" disabled={!hasCatalog}><option value="">All types</option>{nodeTypes.map((value) => <option key={value} value={value}>{readableFilterValue(value)}</option>)}</select></label>
    <label><span>Status</span><select value={filters.statuses[0] ?? ''} onChange={(event) => setSingle('statuses', event.target.value)} aria-label="Filter lifecycle status" disabled={!hasCatalog}><option value="">All statuses</option>{statuses.map((value) => <option key={value} value={value}>{readableFilterValue(value)}</option>)}</select></label>
    <label><span>Relationship</span><select value={filters.relations[0] ?? ''} onChange={(event) => setSingle('relations', event.target.value)} aria-label="Filter lifecycle relationship" disabled={!hasCatalog}><option value="">All persisted relations</option>{relations.map((value) => <option key={value} value={value}>{readableFilterValue(value)}</option>)}</select></label>
  </div>;
}

function OperationsChart({ option, label, emptyText }: { option: EChartsOption; label: string; emptyText: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const hasSeries = Array.isArray(option.series) && option.series.length > 0;
  useEffect(() => {
    if (!ref.current || !hasSeries || (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent))) return undefined;
    const element = ref.current;
    let active = true;
    let chart: ECharts | undefined;
    void import('../charts/echartsRuntime').then(({ echarts }) => {
      if (!active) return;
      chart = echarts.init(element);
      chart.setOption(option, true);
    }).catch(() => { chart = undefined; });
    const resize = () => chart?.resize();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
    observer?.observe(element);
    return () => { active = false; observer?.disconnect(); chart?.dispose(); };
  }, [hasSeries, option]);
  if (!hasSeries) return <div className="operations-chart-empty"><BarChart3 size={18} /><span>{emptyText}</span></div>;
  return <div ref={ref} className="operations-chart" role="img" aria-label={label} data-chart={label} />;
}

function OverviewMetric({ label, metric, tone = '', detail = 'persisted records' }: { label: string; metric: OperationsMetric | undefined; tone?: string; detail?: string }) {
  return <article className={`operations-metric ${tone}`}>
    <span>{label}</span>
    <strong>{metricValue(metric)}</strong>
    <small>{metric?.state === 'available' ? `${metric.record_count} ${detail}` : (metric?.reason || 'No qualified record')}</small>
  </article>;
}

function ActionCountMetric({ count, coverage }: { count: number; coverage: OperationsOverview['coverage'] | undefined }) {
  return <article className="operations-metric is-action">
    <span>Open actions</span>
    <strong>{count}</strong>
    <small>{coverage?.state === 'available' ? `${coverage.record_count} authorized audit records considered` : (coverage?.reason || 'No qualified record')}</small>
  </article>;
}

function ActionQueue({
  actions,
  scope,
  onSelect,
}: {
  actions: OperationsAction[];
  scope: OperationsOverview['scope'] | undefined;
  onSelect: (action: OperationsAction) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  if (!actions.length) return <div className="operations-empty"><BookOpenCheck size={20} /><p>No action is derived from the currently authorized records.</p></div>;
  const visibleActions = showAll ? actions : actions.slice(0, 5);
  const hiddenCount = Math.max(0, actions.length - visibleActions.length);
  return <ol className="operations-actions" aria-label="Prioritized action queue">
    {visibleActions.map((action) => <li key={action.id} data-severity={action.severity}>
      <button type="button" onClick={() => onSelect(action)}>
        <span className="operations-action__severity">{action.severity}</span>
        <span className="operations-action__copy">
          <strong>{action.kind.replace(/_/g, ' ')}</strong>
          <small>{action.recommendation}</small>
          <small className="operations-action__scope">Scope: {action.project_id} / {scope?.role || 'authorized reader'}</small>
          <small className="operations-action__sources">Sources: {action.source_refs.join(', ')}</small>
          <small className="operations-action__read-only">Read-only here. The governed target confirms whether your role can change it.</small>
        </span>
        <ArrowUpRight size={15} aria-hidden="true" />
      </button>
    </li>)}
    {actions.length > 5 && <li className="operations-actions__more"><button type="button" onClick={() => setShowAll((value) => !value)} aria-expanded={showAll}>{showAll ? 'Show top 5 only' : `View ${hiddenCount} more actions`}<ArrowUpRight size={14} aria-hidden="true" /></button></li>}
  </ol>;
}

function freshnessLabel(freshness: OperationsProjectSummary['freshness']): string {
  if (freshness.state !== 'available' || !freshness.latest_activity_at) return freshness.reason || 'No activity sample';
  return `Updated ${new Date(freshness.latest_activity_at).toLocaleDateString()}`;
}

function PortfolioProjects({ summaries, onOpenProject }: { summaries: OperationsProjectSummary[]; onOpenProject: (projectId: string) => void }) {
  if (!summaries.length) return null;
  return <section className="operations-panel operations-panel--portfolio" aria-label="Authorized project health">
    <header><div><p>PROJECT HEALTH</p><h3>Compare authorized knowledge operations</h3></div><span>Server-authorized summaries only</span></header>
    <ol className="operations-projects">
      {summaries.map((summary) => <li key={summary.project_id}>
        <div className="operations-projects__identity"><strong>{summary.project_name}</strong><small>{summary.project_id}</small><span data-state={summary.coverage.state}>{summary.coverage.state === 'available' ? `${summary.coverage.record_count} projected records` : 'Lifecycle unavailable'}</span></div>
        <dl>
          <div><dt>Governed assets</dt><dd>{metricValue(summary.metrics.asset_count)}</dd></div>
          <div><dt>Qualified states</dt><dd>{metricValue(summary.metrics.verified)}</dd></div>
          <div><dt>Risk debt</dt><dd>{metricValue(summary.metrics.risk_debt)}</dd></div>
          <div><dt>Reuse</dt><dd>{metricValue(summary.metrics.durable_references)}</dd></div>
        </dl>
        <div className="operations-projects__action"><small>{freshnessLabel(summary.freshness)}</small><strong>{summary.highest_priority_action ? summary.highest_priority_action.kind.replace(/_/g, ' ') : 'No derived action'}</strong><button type="button" onClick={() => onOpenProject(summary.project_id)} aria-label={`Open ${summary.project_name} cockpit`}>Open <ArrowUpRight size={14} /></button></div>
      </li>)}
    </ol>
  </section>;
}

function LifecycleGraph({
  graph,
  catalog,
  filters,
  onFiltersChange,
  selectedNode,
  onSelect,
}: {
  graph: OperationsGraph | null;
  catalog: OperationsGraph | null;
  filters: GraphFilters;
  onFiltersChange: (filters: GraphFilters) => void;
  selectedNode: OperationsGraphNode | null;
  onSelect: (node: OperationsGraphNode) => void;
}) {
  const [selectedLane, setSelectedLane] = useState('');
  const [recordPage, setRecordPage] = useState(0);
  const compactLayout = useCompactOperationsLayout();
  const lanes = useMemo(() => graph?.lanes ?? [], [graph]);
  const graphProjection = useMemo(() => {
    const relevantEdges = graph?.edges ?? [];
    const nodesByLane = new Map(lanes.map((lane) => [lane.id, [] as OperationsGraphNode[]]));
    for (const node of graph?.nodes ?? []) {
      nodesByLane.get(node.lane)?.push(node);
    }
    const laneNodes = lanes.filter((lane) => (nodesByLane.get(lane.id) ?? []).length > 0);
    const nodes: Node<LifecycleLaneData>[] = laneNodes.map((lane, index) => ({
      id: `lane:${lane.id}`,
      type: 'lifecycleLane',
      data: { lane: lane.id, label: lane.label, count: (nodesByLane.get(lane.id) ?? []).length, compact: compactLayout, onSelect: (value) => { setSelectedLane(value); setRecordPage(0); } },
      position: compactLayout ? { x: 28, y: 28 + index * 118 } : { x: 28 + (index % 4) * 208, y: 28 + Math.floor(index / 4) * 138 },
      className: 'operations-flow-lane',
      ariaLabel: `${lane.label}: ${(nodesByLane.get(lane.id) ?? []).length} authorized records`,
    }));
    const laneByNode = new Map((graph?.nodes ?? []).map((node) => [node.id, node.lane]));
    const edgeGroups = new Map<string, { count: number; domain: OperationsGraph['edges'][number]['domain']; relation: string; source: string; target: string }>();
    for (const edge of relevantEdges) {
      const sourceLane = laneByNode.get(edge.source);
      const targetLane = laneByNode.get(edge.target);
      if (!sourceLane || !targetLane || sourceLane === targetLane) continue;
      const key = `${sourceLane}:${targetLane}:${edge.relation}`;
      const grouped = edgeGroups.get(key);
      if (grouped) grouped.count += 1;
      else edgeGroups.set(key, { count: 1, domain: edge.domain, relation: edge.relation, source: sourceLane, target: targetLane });
    }
    const edges: Edge[] = [...edgeGroups.entries()].map(([id, edge]) => ({
      id,
      source: `lane:${edge.source}`,
      target: `lane:${edge.target}`,
      type: 'smoothstep',
      className: `operations-flow-edge operations-flow-edge--${edge.domain}`,
    }));
    const relations = [...new Map(relevantEdges.map((edge) => [edge.relation, 0])).entries()]
      .map(([relationName]) => ({ relation: relationName, count: relevantEdges.filter((edge) => edge.relation === relationName).length }))
      .sort((left, right) => right.count - left.count || left.relation.localeCompare(right.relation));
    return { nodes, edges, nodesByLane, relations };
  }, [compactLayout, graph, lanes]);

  const activeLane = graphProjection.nodesByLane.has(selectedLane)
    ? selectedLane
    : graphProjection.nodes[0]?.data.lane ?? '';
  const laneRecords = (graphProjection.nodesByLane.get(activeLane) ?? []).slice().sort((left, right) => left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id));
  const recordPageSize = 12;
  const pageCount = Math.max(1, Math.ceil(laneRecords.length / recordPageSize));
  const safeRecordPage = Math.min(recordPage, pageCount - 1);
  const pageRecords = laneRecords.slice(safeRecordPage * recordPageSize, (safeRecordPage + 1) * recordPageSize);
  const adjacentRecords = useMemo(() => {
    if (!graph || !selectedNode) return [];
    const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
    return graph.edges.flatMap((edge) => {
      const linkedId = edge.source === selectedNode.id ? edge.target : edge.target === selectedNode.id ? edge.source : '';
      const node = nodeById.get(linkedId);
      return node ? [{ edge, node, direction: edge.source === selectedNode.id ? 'leads to' : 'supported by' }] : [];
    }).sort((left, right) => left.edge.relation.localeCompare(right.edge.relation) || left.node.label.localeCompare(right.node.label));
  }, [graph, selectedNode]);

  if (!graph) return <div className="operations-chart-empty"><Network size={18} /><span>Select a project to inspect its persisted lifecycle.</span></div>;
  return <section className="operations-lifecycle" aria-label="Knowledge lifecycle projection">
    <header><GraphFilterFields catalog={catalog} filters={filters} onChange={onFiltersChange} /><span>{graph.nodes.length} nodes / {graph.edges.length} edges</span></header>
    <div className={`operations-lifecycle-audit ${graph.lifecycle_audit.complete_risk_lineage_count ? 'is-complete' : 'is-incomplete'}`} role="status" aria-label="Lifecycle closure audit">
      <Network size={15} />
      <div><strong>{graph.lifecycle_audit.complete_risk_lineage_count}/{graph.lifecycle_audit.risk_node_count} risks have a complete durable lifecycle</strong><span>{graph.lifecycle_audit.reason}</span></div>
      {graph.lifecycle_audit.missing_lanes.length > 0 && <small>Missing: {graph.lifecycle_audit.missing_lanes.map(readableLane).join(', ')}</small>}
      {graph.lifecycle_audit.scope === 'visible_page' && <small>Audit covers this visible graph page only.</small>}
    </div>
    {graph.pagination.truncated && <p className="operations-boundary"><AlertTriangle size={13} />Showing a bounded graph slice. {graph.pagination.omitted_node_count} nodes and {graph.pagination.omitted_endpoint_count} endpoints are outside this page.</p>}
    {!graphProjection.nodes.length ? <div className="operations-chart-empty"><Network size={18} /><span>No persisted lifecycle relationships match this filter.</span></div> : <>
      <div className={`operations-flow ${compactLayout ? 'is-compact' : ''}`} style={compactLayout ? { height: Math.max(420, graphProjection.nodes.length * 118 + 30) } : undefined} data-graph-nodes={graph.nodes.length} data-flow-lanes={graphProjection.nodes.length}>
        <ReactFlow nodes={graphProjection.nodes} edges={graphProjection.edges} nodeTypes={lifecycleNodeTypes} fitView fitViewOptions={{ padding: 0.16 }} minZoom={0.25} maxZoom={1.6} nodesDraggable={false}><Background gap={22} size={1} /><Controls showInteractive={false} /></ReactFlow>
      </div>
      <p className="operations-relation-summary" aria-label="Lifecycle relationship counts">{graphProjection.relations.map((item) => <span key={item.relation}>{item.relation} x{item.count}</span>)}</p>
      <section className="operations-lane-records" aria-label="Lifecycle record inspector">
        <header><div><span>{lanes.find((lane) => lane.id === activeLane)?.label || 'Lifecycle records'}</span><small>{laneRecords.length} authorized records</small></div><div><button type="button" className="operations-icon-button" title="Previous lifecycle records" aria-label="Previous lifecycle records" onClick={() => setRecordPage((page) => Math.max(0, page - 1))} disabled={safeRecordPage === 0}><ChevronLeft size={15} /></button><span>{safeRecordPage + 1}/{pageCount}</span><button type="button" className="operations-icon-button" title="Next lifecycle records" aria-label="Next lifecycle records" onClick={() => setRecordPage((page) => Math.min(pageCount - 1, page + 1))} disabled={safeRecordPage >= pageCount - 1}><ChevronRight size={15} /></button></div></header>
        <ol>{pageRecords.map((node) => <li key={node.id}><button type="button" onClick={() => onSelect(node)}><span>{node.status}</span><strong>{compactLabel(nodeDisplayLabel(node))}</strong><small>{node.domain} / {node.type.replace(/_/g, ' ')}</small></button></li>)}</ol>
      </section>
    </>}
    {selectedNode && <aside className="operations-node-inspector" aria-label="Selected lifecycle node">
      <span style={{ color: LANE_COLORS[selectedNode.lane] || '#9eb3bd' }}>{selectedNode.lane.replace(/_/g, ' ')}</span>
      <strong>{nodeDisplayLabel(selectedNode)}</strong>
      <dl><div><dt>Status</dt><dd>{selectedNode.status}</dd></div><div><dt>Domain</dt><dd>{selectedNode.domain}</dd></div><div><dt>Confidence</dt><dd>{selectedNode.confidence ?? 'Not recorded'}</dd></div><div><dt>Connections</dt><dd>{adjacentRecords.length}</dd></div></dl>
      <section className="operations-node-connections" aria-label="Persisted connections"><h4>Persisted connections</h4>{adjacentRecords.length ? <ol>{adjacentRecords.map(({ edge, node, direction }) => <li key={edge.id}><button type="button" onClick={() => onSelect(node)} aria-label={`${readableFilterValue(edge.relation)} ${nodeDisplayLabel(node)}`}><span>{readableFilterValue(edge.relation)} / {direction}</span><strong>{compactLabel(nodeDisplayLabel(node))}</strong><small>{node.lane.replace(/_/g, ' ')} / {node.status}</small></button></li>)}</ol> : <p>No persisted adjacent record is available in this bounded slice.</p>}</section>
    </aside>}
  </section>;
}

export function KnowledgeOperationsCockpit({ onClose, initialProjectId = '', onOpenKnowledge, onOpenGrowth, onOpenDbos }: Props) {
  const [view, setView] = useState<View>('portfolio');
  const [projectId, setProjectId] = useState(initialProjectId);
  const [activeProjectId, setActiveProjectId] = useState(initialProjectId);
  const [range, setRange] = useState<'all' | '30d' | '90d'>('all');
  const [overview, setOverview] = useState<OperationsOverview | null>(null);
  const [graph, setGraph] = useState<OperationsGraph | null>(null);
  const [graphCatalog, setGraphCatalog] = useState<OperationsGraph | null>(null);
  const [graphFilters, setGraphFilters] = useState<GraphFilters>(EMPTY_GRAPH_FILTERS);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<OperationsGraphNode | null>(null);
  const [state, setState] = useState<RequestState>('idle');
  const [message, setMessage] = useState('');
  const requestId = useRef(0);
  const pendingGraphNodeIdRef = useRef('');
  const layoutRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const targetProject = activeProjectId.trim();
    if (view === 'project' && !targetProject) {
      setState('empty'); setOverview(null); setGraph(null); setGraphCatalog(null); setMessage('Enter an authorized project ID to open its cockpit.'); return;
    }
    const id = ++requestId.current;
    setState('loading'); setOverview(null); setGraph(null); setGraphCatalog(null); setSelectedNode(null); setMessage('');
    const until = new Date();
    const since = range === 'all' ? undefined : new Date(until.getTime() - (range === '30d' ? 30 : 90) * 86_400_000);
    const query = since ? { from: since.toISOString(), to: until.toISOString() } : {};
    try {
      const data = view === 'portfolio' ? await fetchOperationsPortfolio(query) : await fetchOperationsProject(targetProject, query);
      if (id !== requestId.current) return;
      setOverview(data);
      if (data.scope.mode === 'project') {
        const catalogRequest = fetchOperationsGraph(targetProject, { ...query, limit: 200 });
        const hasGraphFilter = Boolean(graphFilters.missionId || graphFilters.nodeTypes.length || graphFilters.statuses.length || graphFilters.relations.length);
        const filteredRequest = hasGraphFilter
          ? fetchOperationsGraph(targetProject, { ...query, ...graphFilters, limit: 200 })
          : catalogRequest;
        const [catalog, lifecycle] = await Promise.all([catalogRequest, filteredRequest]);
        if (id !== requestId.current) return;
        setGraphCatalog(catalog);
        setGraph(lifecycle);
        if (pendingGraphNodeIdRef.current) {
          const targetId = pendingGraphNodeIdRef.current;
          const target = lifecycle.nodes.find((node) => node.id === targetId) ?? null;
          setSelectedNode(target);
          if (!target) setMessage(`The requested DBOS record (${targetId}) is not present in this bounded project graph.`);
          pendingGraphNodeIdRef.current = '';
        }
      }
      setState(data.coverage.state === 'unavailable' ? 'unavailable' : (data.project_count || data.actions.length ? 'success' : 'empty'));
      setMessage(data.coverage.reason);
    } catch (error) {
      if (id !== requestId.current) return;
      if (view === 'portfolio' && initialProjectId && error instanceof OperationsRequestError && error.code === 'operations_portfolio_admin_required') {
        setView('project');
        return;
      }
      const failure = classifyError(error);
      setState(failure.state); setMessage(failure.message); setOverview(null); setGraph(null); setGraphCatalog(null);
    }
  }, [activeProjectId, graphFilters, initialProjectId, range, view]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!selectedNode || view !== 'project') return;
    const layout = layoutRef.current;
    const inspector = layout?.querySelector<HTMLElement>('[aria-label="Selected lifecycle node"]');
    if (!layout || !inspector) return;
    const targetTop = Math.max(0, inspector.offsetTop - 18);
    layout.scrollTop = targetTop;
  }, [selectedNode, view]);

  const selectAction = (action: OperationsAction) => {
    setProjectId(action.project_id);
    setActiveProjectId(action.project_id);
    setGraphFilters(EMPTY_GRAPH_FILTERS);
    if (action.drilldown.surface === 'dbos' && !action.drilldown.mission_id) {
      const currentProjectIsOpen = view === 'project' && activeProjectId.trim() === action.project_id;
      pendingGraphNodeIdRef.current = action.drilldown.entity_id;
      setView('project');
      // An action chosen within the same open project must still fetch its
      // bounded graph again so the exact durable node can be selected.
      if (currentProjectIsOpen) void load();
    } else if (action.drilldown.surface === 'dbos') onOpenDbos?.(action.project_id, action.drilldown.mission_id, action.drilldown.entity_id);
    else if (action.drilldown.surface === 'growth') onOpenGrowth?.(action.project_id, action.drilldown.entity_id);
    else onOpenKnowledge?.(action.project_id, action.drilldown.entity_id);
  };

  const openProjectCockpit = (nextProjectId: string) => {
    setProjectId(nextProjectId);
    setActiveProjectId(nextProjectId);
    setGraphFilters(EMPTY_GRAPH_FILTERS);
    pendingGraphNodeIdRef.current = '';
    setView('project');
  };

  const updateGraphFilters = (filters: GraphFilters) => {
    setSelectedNode(null);
    setGraphFilters(filters);
  };

  const missions = graphMissions(graphCatalog);

  const assets = overview?.metrics.assets;
  const quality = overview?.metrics.quality;
  const growth = overview?.trends.asset_growth ?? [];
  const agentEvolution = overview?.trends.agent_evolution ?? [];
  const hasAgentRateTrend = agentEvolution.some((item) => item.verification_pass_rate !== null || item.routing_holdout_pass_rate !== null);
  const growthOption: EChartsOption = {
    animationDuration: 420, animationEasing: 'cubicOut', color: ['#2c796a', '#bd7a32', '#3f788f'], tooltip: { trigger: 'axis', backgroundColor: '#193033', borderWidth: 0, textStyle: { color: '#f3faf6', fontSize: 11 } }, legend: { top: 8, left: 'center', itemWidth: 12, itemHeight: 8, data: ['Sources', 'Methods', 'Outputs'], textStyle: { color: '#536b6e', fontSize: 10 } }, grid: { top: 48, right: 18, bottom: 34, left: 42 },
    xAxis: { type: 'category', data: growth.map((item) => item.date), axisLabel: { color: '#66797b', fontSize: 10 }, axisLine: { lineStyle: { color: '#cbd9d3' } } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#66797b', fontSize: 10 }, splitLine: { lineStyle: { color: '#e1e9e4' } } },
    series: growth.length ? [
      { name: 'Sources', type: 'line', data: growth.map((item) => item.sources), showSymbol: growth.length < 18, lineStyle: { width: 2 } },
      { name: 'Methods', type: 'line', data: growth.map((item) => item.methods), showSymbol: growth.length < 18, lineStyle: { width: 2 } },
      { name: 'Outputs', type: 'line', data: growth.map((item) => item.outputs), showSymbol: growth.length < 18, lineStyle: { width: 2 } },
    ] : [],
  };
  const qualityOption: EChartsOption = {
    animationDuration: 420, animationEasing: 'cubicOut', grid: { top: 18, right: 18, bottom: 28, left: 84 }, xAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#66797b', fontSize: 10 }, splitLine: { lineStyle: { color: '#e1e9e4' } } }, yAxis: { type: 'category', data: ['Qualified', 'Pending', 'Attention'], axisLabel: { color: '#536b6e', fontSize: 11 }, axisLine: { lineStyle: { color: '#cbd9d3' } } },
    series: quality ? [{ type: 'bar', barMaxWidth: 22, data: [quality.verified?.value ?? 0, quality.pending_validation?.value ?? 0, quality.requires_attention?.value ?? 0], itemStyle: { color: (params: { dataIndex: number }) => ['#72c5a7', '#d7aa63', '#e1848d'][params.dataIndex] } }] : [],
  };
  const agentOption: EChartsOption = {
    animationDuration: 420, animationEasing: 'cubicOut', color: ['#2c796a', '#3f788f'], tooltip: { trigger: 'axis', backgroundColor: '#193033', borderWidth: 0, textStyle: { color: '#f3faf6', fontSize: 11 } }, legend: { top: 8, left: 'center', itemWidth: 12, itemHeight: 8, data: ['Verification pass rate', 'Routing holdout pass rate'], textStyle: { color: '#536b6e', fontSize: 10 } }, grid: { top: 52, right: 18, bottom: 34, left: 44 },
    xAxis: { type: 'category', data: agentEvolution.map((item) => item.date), axisLabel: { color: '#66797b', fontSize: 10 }, axisLine: { lineStyle: { color: '#cbd9d3' } } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: '#66797b', fontSize: 10, formatter: '{value}%' }, splitLine: { lineStyle: { color: '#e1e9e4' } } },
    series: hasAgentRateTrend ? [
      { name: 'Verification pass rate', type: 'line', data: agentEvolution.map((item) => item.verification_pass_rate), connectNulls: false, showSymbol: agentEvolution.length < 18, lineStyle: { width: 2 } },
      { name: 'Routing holdout pass rate', type: 'line', data: agentEvolution.map((item) => item.routing_holdout_pass_rate), connectNulls: false, showSymbol: agentEvolution.length < 18, lineStyle: { width: 2 } },
    ] : [],
  };

  const isFailure = ['permission', 'offline', 'error'].includes(state);
  return <section className="operations-cockpit" aria-label="Knowledge operations cockpit">
    <header className="operations-cockpit__header">
      <div className="operations-cockpit__brand"><span><Database size={18} /></span><div><p>KNOWLEDGE OPERATIONS</p><h2>Decision cockpit</h2></div></div>
      <div className="operations-cockpit__controls">
        <div className="operations-scope" role="tablist" aria-label="Operations scope"><button type="button" role="tab" aria-selected={view === 'portfolio'} onClick={() => setView('portfolio')}>Portfolio</button><button type="button" role="tab" aria-selected={view === 'project'} onClick={() => setView('project')}>Project</button></div>
        <label className="operations-range-field"><span>Range</span><select value={range} onChange={(event) => setRange(event.target.value as 'all' | '30d' | '90d')} aria-label="Operations time range"><option value="all">All records</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option></select></label>
        {view === 'project' && <label className="operations-project-field"><span>Project</span><input value={projectId} onChange={(event) => setProjectId(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { setGraphFilters(EMPTY_GRAPH_FILTERS); setActiveProjectId(projectId.trim()); } }} placeholder="Authorized project ID" aria-label="Operations project ID" /></label>}
        {view === 'project' && <label className="operations-mission-field"><span>Mission</span><select value={graphFilters.missionId} onChange={(event) => updateGraphFilters({ ...graphFilters, missionId: event.target.value })} aria-label="Operations mission" disabled={!graphCatalog}><option value="">All persisted missions</option>{missions.map((mission) => <option key={mission.id} value={mission.id}>{compactLabel(mission.label)}</option>)}</select></label>}
        {view === 'project' && <button type="button" className="operations-filter-trigger" aria-label="Open lifecycle filters" aria-haspopup="dialog" aria-expanded={filtersOpen} onClick={() => setFiltersOpen(true)}><ListFilter size={16} /><span>Filters</span></button>}
        <button type="button" className="operations-icon-button" title="Refresh operations data" aria-label="Refresh operations data" onClick={() => void load()} disabled={state === 'loading'}><RefreshCw size={16} className={state === 'loading' ? 'spin' : ''} /></button>
        <button type="button" className="operations-icon-button" title="Close knowledge operations" aria-label="Close knowledge operations" onClick={onClose}><X size={17} /></button>
      </div>
    </header>

    {view === 'project' && filtersOpen && <div className="operations-filter-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setFiltersOpen(false); }}>
      <section className="operations-filter-drawer" role="dialog" aria-modal="true" aria-labelledby="operations-filter-drawer-title">
        <header><div><p>SEMANTIC LIFECYCLE</p><h3 id="operations-filter-drawer-title">Filter persisted records</h3></div><button type="button" className="operations-icon-button" aria-label="Close lifecycle filters" title="Close lifecycle filters" onClick={() => setFiltersOpen(false)}><X size={16} /></button></header>
        <GraphFilterFields catalog={graphCatalog} filters={graphFilters} onChange={updateGraphFilters} includeMission missionLabel="Filter lifecycle mission" className="operations-graph-filters--drawer" />
        <button type="button" className="operations-filter-drawer__done" onClick={() => setFiltersOpen(false)}>Apply filters</button>
      </section>
    </div>}

    {isFailure ? <div className="operations-state" role="alert"><AlertTriangle size={20} /><div><strong>{state} operations data</strong><p>{message || 'No previous cockpit data is shown after a failed request.'}</p></div><button type="button" onClick={() => void load()}><RefreshCw size={14} />Retry</button></div> : <>
      <div className="operations-disclosure"><span className={`operations-state-dot is-${state}`} />{state === 'loading' ? 'Reading authorized operational records...' : `${overview?.scope.mode || view} view`}<span>{overview ? `${overview.project_count} authorized project${overview.project_count === 1 ? '' : 's'}` : 'No record shown'}</span><span>{overview?.coverage ? `Coverage ${overview.coverage.record_count} authorized audit records` : ''}</span><span>{overview?.generated_at ? `Projection generated ${new Date(overview.generated_at).toLocaleString()}` : ''}</span>{message && <span className="is-warning">{message}</span>}</div>
      {state === 'loading' ? <div className="operations-loading" role="status"><RefreshCw size={20} className="spin" />Loading real operational records...</div> : <>
        <section className="operations-decision-strip" aria-label="Decision summary">
          <OverviewMetric label="Governed assets" metric={assets?.qualified_total} tone="is-good" detail="status-qualified assets" />
          <OverviewMetric label="Pending validation" metric={quality?.pending_validation} tone="is-pending" detail="records waiting for a gate" />
          <OverviewMetric label="Needs attention" metric={quality?.requires_attention} tone="is-risk" detail="rejected, retired, or risk records" />
          <OverviewMetric label="Reusable references" metric={overview?.metrics.reuse.durable_references} tone="is-info" detail="durable reuse references" />
          <ActionCountMetric count={overview?.actions.length ?? 0} coverage={overview?.coverage} />
        </section>
        <div className="operations-layout" ref={layoutRef}>
          <main className="operations-main">
            {view === 'portfolio' && <PortfolioProjects summaries={overview?.project_summaries ?? []} onOpenProject={openProjectCockpit} />}
            <section className="operations-panel operations-panel--charts"><header><div><p>ASSET MOVEMENT</p><h3>Evidence becoming reusable work</h3></div><span>{metricValue(assets?.sources)} eligible evidence / {metricValue(assets?.methods)} published methods / {metricValue(assets?.outputs)} accepted outputs</span></header><OperationsChart option={growthOption} label="Knowledge asset growth" emptyText="No status-qualified source, method, or output timestamps exist for this scope." /></section>
            <section className="operations-panel operations-panel--charts"><header><div><p>QUALITY AND DEBT</p><h3>Approval state is not inferred from generation</h3></div><span>{overview?.coverage.record_count ?? 0} authorized audit records</span></header><OperationsChart option={qualityOption} label="Knowledge qualification and risk composition" emptyText="No quality records are available for this scope." /></section>
            <section className="operations-panel operations-panel--agent-chart"><header><div><p>AGENT EVOLUTION</p><h3>Observed validation evidence over time</h3></div><span>3+ persisted observations per rate</span></header><OperationsChart option={agentOption} label="Agent verification and holdout trends" emptyText="No sufficiently sampled verification or holdout results exist for this scope." /></section>
            {view === 'project' && <section className="operations-panel operations-panel--graph"><header><div><p>SEMANTIC LIFECYCLE</p><h3>Business problem to reusable experience</h3></div><span>Read-only projection</span></header><LifecycleGraph graph={graph} catalog={graphCatalog} filters={graphFilters} onFiltersChange={updateGraphFilters} selectedNode={selectedNode} onSelect={setSelectedNode} /></section>}
          </main>
          <aside className="operations-sidebar">
            <section className="operations-panel operations-panel--actions"><header><div><p>NEXT ACTIONS</p><h3>Prioritized from durable evidence</h3></div><span>{overview?.actions.length ?? 0}</span></header><ActionQueue actions={overview?.actions ?? []} scope={overview?.scope} onSelect={selectAction} /></section>
            <section className="operations-panel operations-panel--agent"><header><div><p>AGENT EVIDENCE</p><h3>Measured, not claimed</h3></div></header><dl>{Object.values(overview?.metrics.agent_evolution ?? {}).map((metric) => <div key={metric.key}><dt>{metric.key.replace(/_/g, ' ')}</dt><dd>{metricValue(metric)}<small>{metric.reason}</small></dd></div>)}</dl></section>
            {view === 'portfolio' && <section className="operations-project-handoff"><ShieldAlert size={17} /><p>Select a project view to inspect its lifecycle graph. Portfolio metrics never assemble graphs in the browser.</p></section>}
          </aside>
        </div>
      </>}
    </>}
    <button type="button" className="operations-back" onClick={onClose}><ChevronLeft size={15} />Return to workspace</button>
  </section>;
}

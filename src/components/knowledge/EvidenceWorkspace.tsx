import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import { AlertTriangle, Box, ChevronLeft, ChevronRight, FileBarChart2, Image, Network, Table2, X } from 'lucide-react';

import { fetchKnowledgeEvidence, fetchKnowledgeEvidenceRecord, fetchKnowledgeImageThumbnail, fetchKnowledgeTablePreview, type KnowledgeEvidenceData, type KnowledgeEvidenceRecord, type KnowledgeTablePreview } from '../../api/knowledgeWorkspaceApi';

type Props = { projectId: string; refreshVersion?: number };
type EvidenceGraphNodeData = { label: string; recordType?: KnowledgeEvidenceRecord['record_type']; recordId?: string; targetType?: string; targetId?: string; status?: string };
type ExternalEvidenceTarget = { id: string; record_type: 'external_target'; target_type: string; target_id: string; status: string };
type EvidenceSelection = KnowledgeEvidenceRecord | ExternalEvidenceTarget;

const RECORD_LABELS: Record<string, string> = { source: 'Source', asset: 'Asset', extraction: 'Extraction', table: 'Table', reference: 'Reference', target: 'External target' };
const DRILLABLE_RECORD_TYPES = new Set<KnowledgeEvidenceRecord['record_type']>(['source', 'asset', 'extraction', 'table', 'reference']);
const GRAPH_STAGE_ORDER = ['source', 'asset', 'extraction', 'table', 'target'];
const GRAPH_STAGE_WIDTH = 270;
const GRAPH_STAGE_COLUMN_CAPACITY = 3;
const TABLE_PAGE_SIZE = 5;
const RECORD_TYPES = ['all', 'source', 'asset', 'extraction', 'table', 'reference'] as const;

type EvidenceRecordTypeFilter = typeof RECORD_TYPES[number];
export type EvidenceFilters = { recordType: EvidenceRecordTypeFilter; status: string; query: string };
type FilteredEvidence = Pick<KnowledgeEvidenceData, 'sources' | 'assets' | 'extractions' | 'tables' | 'references' | 'timeline' | 'graph'> & { records: KnowledgeEvidenceRecord[]; active: boolean };

function recordStatus(record: KnowledgeEvidenceRecord): string {
  return String(record.status || record.access_state || 'recorded');
}

function recordSearchText(record: KnowledgeEvidenceRecord): string {
  const fields = [
    record.record_type,
    record.origin,
    record.source_type,
    record.mime_type,
    record.extractor,
    record.anchor,
    record.relation,
    ...(Array.isArray(record.schema) ? record.schema : []),
    record.metadata,
  ];
  return fields.map((value) => typeof value === 'string' ? value : JSON.stringify(value || '')).join(' ').toLocaleLowerCase();
}

function filterEvidenceGraph(
  graph: KnowledgeEvidenceData['graph'],
  selectedRecords: KnowledgeEvidenceRecord[],
  active: boolean,
): KnowledgeEvidenceData['graph'] {
  if (!active) return graph;
  const selectedIds = new Set(selectedRecords.map((record) => record.id));
  const matchingEdges = graph.edges.filter((edge) => (
    selectedIds.has(edge.source) || selectedIds.has(edge.target) || selectedIds.has(edge.id)
  ));
  const includedIds = new Set(matchingEdges.flatMap((edge) => [edge.source, edge.target]));
  return {
    nodes: graph.nodes.filter((node) => includedIds.has(node.id)),
    edges: matchingEdges,
    node_total: includedIds.size,
    edge_total: matchingEdges.length,
    omitted_edge_count: 0,
    truncated: graph.truncated,
  };
}

export function filterEvidence(data: KnowledgeEvidenceData, filters: EvidenceFilters): FilteredEvidence {
  const query = filters.query.trim().toLocaleLowerCase();
  const active = filters.recordType !== 'all' || Boolean(filters.status) || Boolean(query);
  const accepts = (record: KnowledgeEvidenceRecord) => (
    (filters.recordType === 'all' || record.record_type === filters.recordType)
    && (!filters.status || recordStatus(record) === filters.status)
    && (!query || recordSearchText(record).includes(query))
  );
  const sources = data.sources.filter(accepts);
  const assets = data.assets.filter(accepts);
  const extractions = data.extractions.filter(accepts);
  const tables = data.tables.filter(accepts);
  const references = data.references.filter(accepts);
  const records = [...sources, ...assets, ...extractions, ...tables, ...references];
  const visibleRecords = new Set(records.map((record) => `${record.record_type}:${record.id}`));
  return {
    sources,
    assets,
    extractions,
    tables,
    references,
    records,
    active,
    timeline: data.timeline.filter((item) => visibleRecords.has(`${item.record_type}:${item.id}`)),
    graph: filterEvidenceGraph(data.graph, records, active),
  };
}

export function visualEvidence(extractions: KnowledgeEvidenceRecord[], assets: KnowledgeEvidenceRecord[]) {
  const assetById = new Map(assets.map((asset) => [String(asset.id), asset]));
  return extractions
    .filter((extraction) => {
      const asset = assetById.get(String(extraction.asset_id || ''));
      return String(asset?.mime_type || '').startsWith('image/')
        || ['canvas-elements', 'excalidraw-elements', 'excalidraw-scene', 'image-metadata'].includes(String(extraction.extractor || ''));
    })
    .map((extraction) => ({ extraction, asset: assetById.get(String(extraction.asset_id || '')) || null }));
}

export function buildEvidenceGraph(graph: KnowledgeEvidenceData['graph']): { nodes: Array<Node<EvidenceGraphNodeData>>; edges: Edge[]; hiddenEdgeCount: number; hiddenUnconnectedNodeCount: number } {
  const sourceNodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const candidateEdges = graph.edges.filter((edge) => sourceNodes.has(edge.source) && sourceNodes.has(edge.target));
  const connectedNodeIds = new Set(candidateEdges.flatMap((edge) => [edge.source, edge.target]));
  const stageRowCounts = new Map<string, number>();
  const connectedNodes = graph.nodes
    .filter((node) => connectedNodeIds.has(node.id))
    .sort((left, right) => {
      const leftStage = graphStageIndex(left.type);
      const rightStage = graphStageIndex(right.type);
      if (leftStage !== rightStage) return leftStage - rightStage;
      return left.id.localeCompare(right.id);
    });
  const nodes = connectedNodes.map((node) => {
    const recordType = DRILLABLE_RECORD_TYPES.has(node.type as KnowledgeEvidenceRecord['record_type'])
      ? node.type as KnowledgeEvidenceRecord['record_type']
      : undefined;
    const label = node.label || (recordType
      ? `${RECORD_LABELS[recordType]}: ${node.status || 'recorded'}`
      : `${RECORD_LABELS[node.type] || node.type}: ${node.target_type || 'related'} / ${node.status || 'unavailable'}`);
    const stage = graphStageIndex(node.type);
    const stageRow = stageRowCounts.get(node.type) || 0;
    stageRowCounts.set(node.type, stageRow + 1);
    return {
      id: node.id,
      position: {
        x: 34 + stage * GRAPH_STAGE_WIDTH + Math.floor(stageRow / GRAPH_STAGE_COLUMN_CAPACITY) * 122,
        y: 28 + (stageRow % GRAPH_STAGE_COLUMN_CAPACITY) * 86,
      },
      data: { label, recordType, recordId: recordType ? node.id : undefined, targetType: node.target_type, targetId: node.target_id, status: node.status },
      className: `evidence-flow-node evidence-flow-node--${node.type}`,
    };
  });
  const visible = new Set(nodes.map((node) => node.id));
  const renderedEdges = candidateEdges.filter((edge) => visible.has(edge.source) && visible.has(edge.target));
  return {
    nodes,
    edges: renderedEdges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, label: edge.relation, type: 'smoothstep' })),
    hiddenEdgeCount: graph.edges.length - renderedEdges.length + graph.omitted_edge_count,
    hiddenUnconnectedNodeCount: graph.nodes.length - nodes.length,
  };
}

function graphStageIndex(type: string): number {
  const index = GRAPH_STAGE_ORDER.indexOf(type);
  return index >= 0 ? index : GRAPH_STAGE_ORDER.length;
}

export function EvidenceWorkspace({ projectId, refreshVersion = 0 }: Props) {
  const [data, setData] = useState<KnowledgeEvidenceData | null>(null);
  const [selected, setSelected] = useState<EvidenceSelection | null>(null);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState<EvidenceFilters>({ recordType: 'all', status: '', query: '' });
  const [tablePage, setTablePage] = useState(0);
  const [tablePreview, setTablePreview] = useState<KnowledgeTablePreview | null>(null);
  const [tablePreviewError, setTablePreviewError] = useState('');
  const [visualPreview, setVisualPreview] = useState<{ assetId: string; url: string } | null>(null);
  const [visualPreviewError, setVisualPreviewError] = useState('');
  const chartRef = useRef<HTMLDivElement>(null);
  const deferredQuery = useDeferredValue(filters.query);

  const openTable = useCallback((id: string, page = 1) => {
    setTablePreviewError('');
    void Promise.all([
      fetchKnowledgeEvidenceRecord(projectId, 'table', id),
      fetchKnowledgeTablePreview(projectId, id, page),
    ])
      .then(([{ record }, preview]) => {
        setSelected(record);
        setTablePreview(preview);
      })
      .catch((reason: unknown) => setTablePreviewError(reason instanceof Error ? reason.message : 'Table preview is unavailable.'));
  }, [projectId]);

  const open = useCallback((recordType: string, id: string) => {
    if (recordType === 'table') {
      openTable(id);
      return;
    }
    setTablePreview(null);
    setTablePreviewError('');
    void fetchKnowledgeEvidenceRecord(projectId, recordType, id)
      .then(({ record }) => setSelected(record))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Evidence record is unavailable.'));
  }, [openTable, projectId]);

  const openVisual = useCallback((extraction: KnowledgeEvidenceRecord, asset: KnowledgeEvidenceRecord | null) => {
    open('extraction', extraction.id);
    setVisualPreviewError('');
    setVisualPreview(null);
    if (!asset || !String(asset.mime_type || '').startsWith('image/')) return;
    void fetchKnowledgeImageThumbnail(projectId, asset.id)
      .then((url) => setVisualPreview({ assetId: asset.id, url }))
      .catch((reason: unknown) => setVisualPreviewError(reason instanceof Error ? reason.message : 'Image preview is unavailable.'));
  }, [open, projectId]);

  useEffect(() => {
    let active = true;
    setError('');
    setSelected(null);
    setTablePreview(null);
    setTablePreviewError('');
    setVisualPreview(null);
    setVisualPreviewError('');
    void fetchKnowledgeEvidence(projectId).then((next) => {
      if (active) setData(next);
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : 'Evidence read model is unavailable.');
    });
    return () => { active = false; };
  }, [projectId, refreshVersion]);

  useEffect(() => () => {
    if (visualPreview?.url) URL.revokeObjectURL?.(visualPreview.url);
  }, [visualPreview?.url]);

  const effectiveFilters = { ...filters, query: deferredQuery };
  const scoped = useMemo(() => data ? filterEvidence(data, effectiveFilters) : null, [data, effectiveFilters.query, effectiveFilters.recordType, effectiveFilters.status]);
  const allRecords = data ? [...data.sources, ...data.assets, ...data.extractions, ...data.tables, ...data.references] : [];
  const statuses = useMemo(() => [...new Set(allRecords.map(recordStatus))].sort(), [allRecords]);
  const records = scoped?.records || [];
  const graph = scoped ? buildEvidenceGraph(scoped.graph) : { nodes: [], edges: [], hiddenEdgeCount: 0, hiddenUnconnectedNodeCount: 0 };
  const visibleTables = scoped?.tables || [];
  const pagedTables = visibleTables.slice(tablePage * TABLE_PAGE_SIZE, tablePage * TABLE_PAGE_SIZE + TABLE_PAGE_SIZE);
  const tablePageCount = Math.max(1, Math.ceil(visibleTables.length / TABLE_PAGE_SIZE));
  const visualItems = scoped ? visualEvidence(scoped.extractions, scoped.assets) : [];
  const updateFilters = (next: Partial<EvidenceFilters>) => {
    setTablePage(0);
    setFilters((current) => ({ ...current, ...next }));
  };
  const clearFilters = () => {
    setTablePage(0);
    setFilters({ recordType: 'all', status: '', query: '' });
  };
  useEffect(() => {
    const element = chartRef.current;
    if (!element || !scoped) return undefined;
    let chart: import('echarts').ECharts | undefined;
    let resize: ResizeObserver | undefined;
    void import('../charts/echartsRuntime').then(({ echarts }) => {
      if (!element.isConnected) return;
      chart = echarts.init(element, undefined, { renderer: 'canvas' });
      const entries = Object.entries(countStatuses(scoped.extractions));
      chart.setOption({
        animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        grid: { top: 18, right: 16, bottom: 24, left: 36 },
        xAxis: { type: 'category', data: entries.map(([status]) => status), axisLabel: { color: '#a7b8c5', fontSize: 10 }, axisLine: { lineStyle: { color: '#3d515f' } } },
        yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#a7b8c5', fontSize: 10 }, splitLine: { lineStyle: { color: '#263a48' } } },
        series: [{ type: 'bar', data: entries.map(([, count]) => count), barMaxWidth: 28, itemStyle: { color: '#43b79e' }, emphasis: { focus: 'series' } }],
        tooltip: { trigger: 'axis' },
      });
      chart.on('click', (event: { name?: string }) => {
        const extraction = scoped.extractions.find((item) => recordStatus(item) === event.name);
        if (extraction) open('extraction', extraction.id);
      });
      resize = new ResizeObserver(() => chart?.resize());
      resize.observe(element);
    });
    return () => { resize?.disconnect(); chart?.dispose(); };
  }, [open, scoped]);
  const selectNode = (_: unknown, node: Node<EvidenceGraphNodeData>) => {
    if (node.data.recordType && node.data.recordId) {
      open(node.data.recordType, node.data.recordId);
      return;
    }
    setSelected({
      id: node.id,
      record_type: 'external_target',
      target_type: node.data.targetType || 'related_record',
      target_id: node.data.targetId || node.id,
      status: node.data.status || 'unavailable',
    });
  };

  return <section className="evidence-workspace" aria-label="Evidence Atlas">
    <header><div><span className="eyebrow"><Network size={14} /> EVIDENCE ATLAS</span><h3>Evidence health and extraction lineage</h3><p>Operational inventory from persisted project records. Source and derivative bodies remain protected.</p></div><span className={`evidence-state evidence-state--${data?.state || 'unavailable'}`}>{data?.state === 'available' ? 'Live records' : data ? 'No samples' : 'Loading'}</span></header>
    {data && <form className="evidence-filters" aria-label="Evidence filters" onSubmit={(event) => event.preventDefault()}>
      <label>Type<select aria-label="Evidence record type" value={filters.recordType} onChange={(event) => updateFilters({ recordType: event.target.value as EvidenceRecordTypeFilter })}>{RECORD_TYPES.map((type) => <option key={type} value={type}>{type === 'all' ? 'All records' : RECORD_LABELS[type]}</option>)}</select></label>
      <label>Status<select aria-label="Evidence status" value={filters.status} onChange={(event) => updateFilters({ status: event.target.value })}><option value="">All states</option>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
      <label className="evidence-filters__query">Find metadata<input aria-label="Find evidence metadata" value={filters.query} onChange={(event) => updateFilters({ query: event.target.value })} placeholder="URL, MIME type, extractor, field..." /></label>
      <button type="button" className="icon-button" onClick={clearFilters} disabled={!scoped?.active} title="Clear evidence filters" aria-label="Clear evidence filters"><X size={14} /></button>
      <p>{records.length} of {allRecords.length} persisted metadata records in view.</p>
    </form>}
    {error && <p className="evidence-error" role="alert">{error}</p>}
    {!data ? <p className="evidence-empty">Loading project evidence...</p> : <>
      <div className="evidence-summary">
        <Metric icon={<Box size={17} />} label="Assets" value={scoped?.assets.length || 0} detail={scopeDetail(scoped?.assets.length || 0, data.summary.assets, `${data.summary.sources} source records`)} />
        <Metric icon={<FileBarChart2 size={17} />} label="Extractions" value={scoped?.extractions.length || 0} detail={scopeDetail(scoped?.extractions.length || 0, Object.values(data.summary.extractions).reduce((total, value) => total + value, 0), statusDetail(countStatuses(scoped?.extractions || [])))} />
        <Metric icon={<Table2 size={17} />} label="Tables" value={visibleTables.length} detail={scopeDetail(visibleTables.length, data.summary.tables, `${data.summary.references} typed references`)} />
        <Metric icon={<AlertTriangle size={17} />} label="Unavailable tools" value={Object.values(data.capabilities).filter((item) => item.state === 'unavailable').length} detail={Object.entries(data.capabilities).filter(([, item]) => item.state === 'unavailable').map(([name]) => name).join(', ') || 'None'} />
      </div>
      <div className="evidence-layout">
        <article className="evidence-card evidence-card--chart"><header><strong>Extraction states</strong><small>Persisted derivatives</small></header><div ref={chartRef} className="evidence-chart" aria-label="Extraction status chart" /></article>
        <article className="evidence-card evidence-card--timeline"><header><strong>Research timeline</strong><small>{scoped?.timeline.length || 0} visible events</small></header><ol>{(scoped?.timeline || []).slice(0, 8).map((item) => <li key={`${item.record_type}:${item.id}`}><button type="button" onClick={() => open(item.record_type, item.id)}><span>{RECORD_LABELS[item.record_type]}</span><strong>{item.status || 'recorded'}</strong><small>{formatTime(item.occurred_at)}</small></button></li>)}</ol>{!scoped?.timeline.length && <p className="evidence-empty">No persisted events match this evidence view.</p>}</article>
        <article className="evidence-card evidence-card--catalog"><header><strong>Reference browser</strong><small>{records.length} metadata records</small></header><ol>{records.slice(0, 12).map((record) => <li key={`${record.record_type}:${record.id}`}><button type="button" onClick={() => open(record.record_type, record.id)}><span>{RECORD_LABELS[record.record_type]}</span><strong>{recordLabel(record)}</strong><small>{recordStatus(record)}</small></button></li>)}</ol>{!records.length && <p className="evidence-empty">No persisted records match this evidence view.</p>}</article>
        <article className="evidence-card evidence-card--inspector"><header><strong>Evidence inspector</strong><small>Metadata only</small></header>{selected ? <dl>{Object.entries(selected).filter(([key]) => !['metadata', 'record_type'].includes(key)).map(([key, value]) => <div key={key}><dt>{key.replace(/_/g, ' ')}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>)}{'metadata' in selected && <div><dt>metadata</dt><dd>{JSON.stringify(selected.metadata || {})}</dd></div>}</dl> : <p className="evidence-empty">Select a timeline item, catalog row, chart bar, or graph node to inspect persisted metadata.</p>}</article>
        <article className="evidence-card evidence-card--tables"><header><strong>Table explorer</strong><small>{visibleTables.length} captured table{visibleTables.length === 1 ? '' : 's'}</small></header>{pagedTables.length ? <><div className="evidence-table-wrap"><table><thead><tr><th>Schema</th><th>Rows</th><th>State</th></tr></thead><tbody>{pagedTables.map((table) => <tr key={table.id}><td><button type="button" onClick={() => openTable(table.id)}>{Array.isArray(table.schema) && table.schema.length ? table.schema.join(', ') : 'Schema unavailable'}</button></td><td>{String(table.row_count || 0)}</td><td>{recordStatus(table)}</td></tr>)}</tbody></table></div>{tablePageCount > 1 && <nav className="evidence-pagination" aria-label="Table pages"><button type="button" className="icon-button" onClick={() => setTablePage((page) => Math.max(0, page - 1))} disabled={tablePage === 0} title="Previous table page" aria-label="Previous table page"><ChevronLeft size={14} /></button><span>Page {tablePage + 1} of {tablePageCount}</span><button type="button" className="icon-button" onClick={() => setTablePage((page) => Math.min(tablePageCount - 1, page + 1))} disabled={tablePage >= tablePageCount - 1} title="Next table page" aria-label="Next table page"><ChevronRight size={14} /></button></nav>}</> : <p className="evidence-empty">No captured table artifacts match this evidence view.</p>}{tablePreview ? <section className="evidence-table-preview" aria-label="Authorized table preview"><header><span><strong>Derived table rows</strong><small>{tablePreview.available_rows} available / {tablePreview.total_rows} declared rows{tablePreview.truncated ? ' / truncated derivative' : ''}</small></span><button type="button" className="icon-button" title="Close table preview" aria-label="Close table preview" onClick={() => setTablePreview(null)}><X size={14} /></button></header>{tablePreview.rows.length ? <div className="evidence-table-wrap"><table><thead><tr>{tablePreview.schema.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{tablePreview.rows.map((row, index) => <tr key={`${tablePreview.page}:${index}`}>{row.map((value, column) => <td key={`${column}:${value}`}>{value || <span className="evidence-cell-empty">Missing</span>}</td>)}</tr>)}</tbody></table></div> : <p className="evidence-empty">{tablePreview.reason || 'No preview rows are available for this table.'}</p>}<footer><small>Derived data via {tablePreview.provenance.extractor || 'unknown extractor'}{tablePreview.provenance.sheet ? ` / ${tablePreview.provenance.sheet}` : ''}. Review before treating any value as a conclusion.</small>{tablePreview.total_pages > 1 && <nav className="evidence-pagination" aria-label="Table row pages"><button type="button" className="icon-button" onClick={() => openTable(tablePreview.table_id, Math.max(1, tablePreview.page - 1))} disabled={tablePreview.page === 1} title="Previous row page" aria-label="Previous row page"><ChevronLeft size={14} /></button><span>Rows page {tablePreview.page} of {tablePreview.total_pages}</span><button type="button" className="icon-button" onClick={() => openTable(tablePreview.table_id, Math.min(tablePreview.total_pages, tablePreview.page + 1))} disabled={tablePreview.page >= tablePreview.total_pages} title="Next row page" aria-label="Next row page"><ChevronRight size={14} /></button></nav>}</footer></section> : <p className="evidence-preview-hint">Select a captured table to inspect authorized, bounded rows and provenance.</p>}{tablePreviewError && <p className="evidence-error">{tablePreviewError}</p>}</article>
        <article className="evidence-card evidence-card--visual"><header><strong>Image and figure inspector</strong><small>{visualItems.length} visual derivative{visualItems.length === 1 ? '' : 's'}</small></header>{visualItems.length ? <ol className="evidence-visual-list">{visualItems.slice(0, 8).map(({ extraction, asset }) => <li key={extraction.id}><button type="button" onClick={() => openVisual(extraction, asset)}><Image size={15} /><span><strong>{String(extraction.extractor || 'visual extraction')}</strong><small>{String(asset?.mime_type || 'visual asset')} / {recordStatus(extraction)}</small></span><em>{visualDetail(extraction)}</em></button></li>)}</ol> : <p className="evidence-empty">No persisted image, Canvas, or Excalidraw derivatives match this evidence view.</p>}{visualPreview ? <section className="evidence-image-preview" aria-label="Authorized image preview"><header><strong>Authorized image preview</strong><button type="button" className="icon-button" title="Close image preview" aria-label="Close image preview" onClick={() => setVisualPreview(null)}><X size={14} /></button></header><img src={visualPreview.url} alt="Authorized evidence preview" /><p>Preview pixels are limited to this authorized asset. OCR, labels, and visual elements remain evidence candidates until reviewed.</p></section> : <p className="evidence-preview-hint">Select an image to load a stripped, bounded preview. Canvas and Excalidraw remain metadata-led until a reviewed visual export exists.</p>}{visualPreviewError && <p className="evidence-error">{visualPreviewError}</p>}</article>
        <article className="evidence-card evidence-card--graph"><header><strong>Reference network</strong><small>{graph.nodes.length} connected / {scoped?.graph.node_total || 0} focused nodes / {scoped?.graph.edge_total || 0} focused edges</small></header>{graph.nodes.length ? <><div className="evidence-flow"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView nodesDraggable={false} onNodeClick={selectNode}><Background gap={20} size={1} /><Controls showInteractive={false} /></ReactFlow></div><details className="evidence-graph-list"><summary>{graph.edges.length} persisted relationship{graph.edges.length === 1 ? '' : 's'} in an accessible list</summary><ul>{graph.edges.map((edge) => { const source = graph.nodes.find((node) => node.id === edge.source); const target = graph.nodes.find((node) => node.id === edge.target); return <li key={edge.id}><button type="button" onClick={() => target && selectNode(null, target)}>{source?.data.label || edge.source} <span>{edge.label}</span> {target?.data.label || edge.target}</button></li>; })}</ul></details></> : <p className="evidence-empty">No persisted evidence relationships match this evidence view.</p>}{graph.hiddenUnconnectedNodeCount > 0 && <p className="evidence-graph-focus">{graph.hiddenUnconnectedNodeCount} unconnected record{graph.hiddenUnconnectedNodeCount === 1 ? '' : 's'} remain in Reference browser and are intentionally omitted from this relationship canvas.</p>}{(scoped?.graph.truncated || graph.hiddenEdgeCount > 0) && <p className="evidence-truncated">{graph.hiddenEdgeCount} relation{graph.hiddenEdgeCount === 1 ? '' : 's'} outside the visible evidence window. Refine the project evidence before relying on this projection.</p>}</article>
      </div>
    </>}
  </section>;
}

function Metric({ icon, label, value, detail }: { icon: ReactNode; label: string; value: number; detail: string }) {
  return <div><span>{icon}</span><strong>{value}</strong><small>{label}</small><p>{detail}</p></div>;
}

function recordLabel(record: KnowledgeEvidenceRecord) {
  return String(record.origin || record.mime_type || record.extractor || record.target_type || record.id);
}

function statusDetail(values: Record<string, number>) {
  const entries = Object.entries(values);
  return entries.length ? entries.map(([status, count]) => `${count} ${status}`).join(' / ') : 'No derivatives yet';
}

function countStatuses(records: KnowledgeEvidenceRecord[]): Record<string, number> {
  return records.reduce<Record<string, number>>((counts, record) => {
    const status = recordStatus(record);
    counts[status] = (counts[status] || 0) + 1;
    return counts;
  }, {});
}

function scopeDetail(visible: number, total: number, defaultDetail: string): string {
  return visible === total ? defaultDetail : `${visible} matching / ${total} total`;
}

function visualDetail(extraction: KnowledgeEvidenceRecord): string {
  const metadata = extraction.metadata && typeof extraction.metadata === 'object'
    ? extraction.metadata as Record<string, unknown>
    : {};
  const elements = metadata.element_count ?? metadata.node_count;
  if (typeof elements === 'number') return `${elements} element${elements === 1 ? '' : 's'}`;
  const width = metadata.width;
  const height = metadata.height;
  if (typeof width === 'number' && typeof height === 'number') return `${width} x ${height}`;
  return recordStatus(extraction);
}

function formatTime(value: string) {
  return value ? value.replace('T', ' ').slice(0, 16) : 'No timestamp';
}

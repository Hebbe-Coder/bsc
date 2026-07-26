import { AlertTriangle, Filter, LoaderCircle, Network } from 'lucide-react';
import { useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';

import type { GrowthLineage, GrowthLineageEdge, GrowthRequestState } from '../../api/growthApi';
import { GROWTH_RELATIONS, normalizeGrowthNodeType, type GrowthGraphNodeType } from './growthModel';
type NodeData = { label: string; kind: GrowthGraphNodeType; endpointType: string };

const FILTER_TYPES: Array<Exclude<GrowthGraphNodeType, 'other'>> = ['source', 'page', 'method', 'candidate', 'output', 'feedback'];
const LANE_ORDER: GrowthGraphNodeType[] = ['source', 'page', 'method', 'candidate', 'output', 'feedback', 'other'];

function compactId(id: string): string {
  return id.length > 18 ? `${id.slice(0, 10)}...${id.slice(-4)}` : id;
}

function compactLabel(value: string): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized.length > 54 ? `${normalized.slice(0, 53).trimEnd()}...` : normalized;
}

function inferEndpointType(edge: GrowthLineageEdge, endpoint: 'from' | 'to'): string {
  const explicit = endpoint === 'from' ? edge.from_type : edge.to_type;
  if (explicit) return explicit;
  const relation = edge.edge_type;
  if (relation === 'wiki_cites_source') return endpoint === 'from' ? 'page' : 'source';
  if (relation === 'wiki_links_to') return 'page';
  if (relation === 'proposal_changes_page') return endpoint === 'from' ? 'proposal' : 'page';
  if (relation.startsWith('source_')) return endpoint === 'from' ? 'source' : relation.endsWith('_source') ? 'source' : 'page';
  if (relation.startsWith('feedback_')) return endpoint === 'from' ? 'feedback' : 'output';
  if (relation.startsWith('page_')) return endpoint === 'from' ? 'page' : 'method';
  if (relation.startsWith('method_')) return 'method';
  if (relation.startsWith('output_')) {
    if (endpoint === 'from') return 'output';
    if (relation.includes('source')) return 'source';
    if (relation.includes('page')) return 'page';
    if (relation.includes('method')) return 'method_revision';
  }
  return '';
}

type Props = {
  lineage: GrowthLineage | null;
  state: GrowthRequestState;
  error?: string;
  relation: string;
  onRelationChange: (relation: string) => void;
  onSelect: (id: string, endpointType: string) => void;
  onRetry: () => void;
};

export function GrowthLineageGraph({ lineage, state, error, relation, onRelationChange, onSelect, onRetry }: Props) {
  const [enabledTypes, setEnabledTypes] = useState<Set<GrowthGraphNodeType>>(() => new Set(FILTER_TYPES));
  const graph = useMemo(() => {
    const descriptors = new Map((lineage?.nodes ?? []).map((node) => [node.id, node]));
    const endpoints = new Map<string, { type: string; kind: GrowthGraphNodeType; label: string }>();
    for (const edge of lineage?.edges ?? []) {
      const fromType = inferEndpointType(edge, 'from');
      const toType = inferEndpointType(edge, 'to');
      const fromDescriptor = descriptors.get(edge.from_id);
      const toDescriptor = descriptors.get(edge.to_id);
      endpoints.set(edge.from_id, {
        type: fromDescriptor?.type || fromType,
        kind: normalizeGrowthNodeType(fromDescriptor?.type || fromType),
        label: compactLabel(fromDescriptor?.label || compactId(edge.from_id)),
      });
      endpoints.set(edge.to_id, {
        type: toDescriptor?.type || toType,
        kind: normalizeGrowthNodeType(toDescriptor?.type || toType),
        label: compactLabel(toDescriptor?.label || compactId(edge.to_id)),
      });
    }
    const visibleIds = new Set([...endpoints.entries()].filter(([, endpoint]) => endpoint.kind === 'other' || enabledTypes.has(endpoint.kind)).map(([id]) => id));
    const records = [...endpoints.entries()].filter(([id]) => visibleIds.has(id));
    const lanes = new Map(LANE_ORDER.map((kind) => [kind, records.filter(([, endpoint]) => endpoint.kind === kind).sort(([left], [right]) => left.localeCompare(right))]));
    const tallestLane = Math.max(1, ...[...lanes.values()].map((lane) => lane.length));
    const nodes: Node<NodeData>[] = LANE_ORDER.flatMap((kind, laneIndex) => {
      const lane = lanes.get(kind) ?? [];
      const offset = ((tallestLane - lane.length) * 106) / 2;
      return lane.map(([id, endpoint], index) => ({
        id,
        data: { label: endpoint.label, kind: endpoint.kind, endpointType: endpoint.type },
        position: { x: 30 + laneIndex * 220, y: 28 + offset + index * 106 },
        className: `growth-flow-node growth-flow-node--${endpoint.kind}`,
        ariaLabel: `${endpoint.kind} ${endpoint.label} (${id})`,
      }));
    });
    const visibleEdges = (lineage?.edges ?? []).filter((edge) => visibleIds.has(edge.from_id) && visibleIds.has(edge.to_id));
    const showEdgeLabels = visibleEdges.length <= 6;
    const edges: Edge[] = visibleEdges.map((edge) => ({
      id: edge.id,
      source: edge.from_id,
      target: edge.to_id,
      label: showEdgeLabels ? edge.edge_type : undefined,
      ariaLabel: `${edge.from_id} ${edge.edge_type} ${edge.to_id}`,
      type: 'smoothstep',
    }));
    return { nodes, edges, endpoints };
  }, [enabledTypes, lineage]);

  const toggleType = (kind: GrowthGraphNodeType) => setEnabledTypes((current) => {
    const next = new Set(current);
    if (next.has(kind)) next.delete(kind); else next.add(kind);
    return next;
  });

  if (state === 'loading') return <div className="growth-empty growth-empty--graph" role="status"><LoaderCircle className="spin" size={18} /><span>Loading a server-bounded lineage slice...</span></div>;
  if (state === 'permission' || state === 'offline' || state === 'unavailable' || state === 'error') return <div className="growth-state growth-state--panel" role="alert"><AlertTriangle size={18} /><div><strong>Lineage {state}</strong><span>{error || 'No cached graph is displayed.'}</span></div><button type="button" onClick={onRetry}>Retry</button></div>;

  return <section className="growth-lineage" aria-label="Knowledge lineage explorer">
    <div className="growth-lineage__toolbar">
      <label><Filter size={13} /><span>Relation</span><select aria-label="Filter lineage relation" value={relation} onChange={(event) => onRelationChange(event.target.value)}><option value="">All relations</option>{GROWTH_RELATIONS.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <fieldset><legend>Node types</legend>{FILTER_TYPES.map((kind) => <label key={kind}><input type="checkbox" checked={enabledTypes.has(kind)} onChange={() => toggleType(kind)} />{kind}</label>)}</fieldset>
    </div>
    {lineage?.truncated && <div className="growth-boundary-note" role="status"><AlertTriangle size={13} /><span>Showing the first {lineage.limit} server-returned edges. Narrow the relation filter before drawing conclusions.</span></div>}
    {!graph.nodes.length ? <div className="growth-empty growth-empty--graph"><Network size={18} /><span>{lineage?.edges.length ? 'No nodes match the active type filters.' : 'No persisted relationships exist for this project and relation.'}</span></div> : <>
      <div className="growth-graph" role="img" aria-label={`${graph.nodes.length} lineage nodes and ${graph.edges.length} edges`} data-graph-nodes={graph.nodes.length}>
        <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView fitViewOptions={{ padding: 0.16 }} minZoom={0.25} maxZoom={1.6} onNodeClick={(_, node) => onSelect(node.id, node.data.endpointType)} nodesDraggable={false}><Background gap={22} size={1} /><Controls showInteractive={false} /></ReactFlow>
      </div>
      <ul className="growth-visually-hidden" aria-label="Lineage relationships">{(lineage?.edges ?? []).map((edge) => <li key={edge.id}>{edge.from_id} {edge.edge_type} {edge.to_id}</li>)}</ul>
    </>}
    <footer className="growth-lineage__footer"><span>{lineage?.edges.length ?? 0} persisted edges</span><span>{graph.nodes.length} visible nodes</span><span>Server limit {lineage?.limit ?? 0}</span></footer>
  </section>;
}

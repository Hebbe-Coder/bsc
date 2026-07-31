// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import { fetchKnowledgeEvidence, fetchKnowledgeEvidenceRecord, fetchKnowledgeImageThumbnail, fetchKnowledgeTablePreview, type KnowledgeEvidenceData } from '../../api/knowledgeWorkspaceApi';
import { EvidenceWorkspace, buildEvidenceGraph, evidenceComposition, filterEvidence, visualEvidence } from './EvidenceWorkspace';

vi.mock('../../api/knowledgeWorkspaceApi', () => ({
  fetchKnowledgeEvidence: vi.fn(),
  fetchKnowledgeEvidenceRecord: vi.fn(),
  fetchKnowledgeImageThumbnail: vi.fn(),
  fetchKnowledgeTablePreview: vi.fn(),
}));

vi.mock('../charts/echartsRuntime', () => ({
  echarts: { init: () => ({ setOption: vi.fn(), on: vi.fn(), resize: vi.fn(), dispose: vi.fn() }) },
}));

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', TestResizeObserver);
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

function evidenceSnapshot(origin: string): KnowledgeEvidenceData {
  return {
    project_id: 'default', state: 'available',
    summary: { sources: 1, assets: 0, extractions: {}, tables: 0, references: 0, source_statuses: { validated: 1 }, denominator: 1 },
    capabilities: {},
    sources: [{ id: origin, record_type: 'source', source_type: 'article', origin, origin_kind: 'url', content_hash: 'hash', trust_level: 'trusted', status: 'validated', captured_at: '2026-07-27T00:00:00Z', updated_at: '2026-07-27T00:00:00Z', metadata: {} }],
    assets: [], extractions: [], tables: [], references: [],
    timeline: [{ id: origin, record_type: 'source', status: 'validated', occurred_at: '2026-07-27T00:00:00Z' }],
    graph: { nodes: [], edges: [], node_total: 0, edge_total: 0, omitted_edge_count: 0, truncated: false },
    truncated: false,
  };
}

function richEvidenceSnapshot(): KnowledgeEvidenceData {
  const tables = Array.from({ length: 6 }, (_, index) => ({
    id: `table-${index + 1}`,
    record_type: 'table' as const,
    source_id: 'source-a',
    extraction_id: 'extract-visual',
    schema: [`metric_${index + 1}`, 'value'],
    row_count: index + 2,
    units: { value: 'count' },
    content_hash: 'a'.repeat(64),
    status: 'detected',
    created_at: '2026-07-29T00:00:00Z',
  }));
  return {
    project_id: 'default', state: 'available',
    summary: { sources: 1, assets: 1, extractions: { partial: 1 }, tables: tables.length, references: 1, source_statuses: { validated: 1 }, denominator: 10 },
    capabilities: {},
    sources: [{ id: 'source-a', record_type: 'source', source_type: 'article', origin: 'https://example.test/canvas', origin_kind: 'url', content_hash: 'hash', trust_level: 'trusted', status: 'validated', captured_at: '2026-07-29T00:00:00Z', updated_at: '2026-07-29T00:00:00Z', metadata: {} }],
    assets: [{ id: 'asset-image', record_type: 'asset', source_id: 'source-a', mime_type: 'image/png', byte_hash: 'b'.repeat(64), byte_size: 42, rights: 'user_owned', access_state: 'available', created_at: '2026-07-29T00:00:00Z', updated_at: '2026-07-29T00:00:00Z', metadata: {} }],
    extractions: [{ id: 'extract-visual', record_type: 'extraction', source_id: 'source-a', asset_id: 'asset-image', extractor: 'canvas-elements', extractor_revision: 'local-v2', input_hash: 'b'.repeat(64), content_hash: 'c'.repeat(64), status: 'partial', error: '', created_at: '2026-07-29T00:00:00Z', metadata: { element_count: 3, drawing_json_detected: true } }],
    tables,
    references: [{ id: 'reference-a', record_type: 'reference', source_id: 'source-a', target_type: 'wiki_page', target_id: 'page-a', anchor_type: 'heading', anchor: 'Evidence', relation: 'supports', resolution_state: 'resolved', created_at: '2026-07-29T00:00:00Z' }],
    timeline: [
      { id: 'source-a', record_type: 'source', status: 'validated', occurred_at: '2026-07-29T00:00:00Z' },
      { id: 'extract-visual', record_type: 'extraction', status: 'partial', occurred_at: '2026-07-29T00:00:00Z' },
      ...tables.map((table) => ({ id: table.id, record_type: 'table' as const, status: 'detected', occurred_at: table.created_at })),
    ],
    graph: {
      nodes: [
        { id: 'source-a', type: 'source', status: 'validated' },
        { id: 'asset-image', type: 'asset', status: 'available' },
        { id: 'extract-visual', type: 'extraction', status: 'partial' },
        ...tables.map((table) => ({ id: table.id, type: 'table', status: 'detected' })),
        { id: 'target:wiki_page:page-a', type: 'target', status: 'resolved', target_type: 'wiki_page', target_id: 'page-a' },
      ],
      edges: [
        { id: 'source-asset', source: 'source-a', target: 'asset-image', relation: 'has_asset' },
        { id: 'asset-extraction', source: 'asset-image', target: 'extract-visual', relation: 'extracted_by' },
        ...tables.map((table) => ({ id: `extract-${table.id}`, source: 'extract-visual', target: table.id, relation: 'contains_table' })),
        { id: 'reference-a', source: 'source-a', target: 'target:wiki_page:page-a', relation: 'supports', resolution_state: 'resolved' },
      ],
      node_total: 10, edge_total: 9, omitted_edge_count: 0, truncated: false,
    },
    truncated: false,
  };
}

describe('EvidenceWorkspace graph projection', () => {
  it('keeps captured sources and references visible in the composition when derivative layers are empty', () => {
    const data = evidenceSnapshot('https://example.test/research');
    data.references = [{
      id: 'reference-a', record_type: 'reference', source_id: 'https://example.test/research',
      target_type: 'wiki_page', target_id: 'overview', anchor_type: 'heading', anchor: 'Overview',
      relation: 'supports', resolution_state: 'resolved', created_at: '2026-07-27T00:00:00Z',
    }];

    expect(evidenceComposition(data)).toEqual([
      { recordType: 'source', label: 'Sources', count: 1, color: '#63b7d2' },
      { recordType: 'asset', label: 'Assets', count: 0, color: '#d6a85c' },
      { recordType: 'extraction', label: 'Extractions', count: 0, color: '#56bd9c' },
      { recordType: 'table', label: 'Tables', count: 0, color: '#8999e7' },
      { recordType: 'reference', label: 'References', count: 1, color: '#ca91d7' },
    ]);
  });

  it('uses the composition controls to filter the persisted evidence inventory', async () => {
    const data = evidenceSnapshot('https://example.test/research');
    data.references = [{
      id: 'reference-a', record_type: 'reference', source_id: 'https://example.test/research',
      target_type: 'wiki_page', target_id: 'overview', anchor_type: 'heading', anchor: 'Overview',
      relation: 'supports', resolution_state: 'resolved', created_at: '2026-07-27T00:00:00Z',
    }];
    vi.mocked(fetchKnowledgeEvidence).mockResolvedValue(data);

    render(<EvidenceWorkspace projectId="default" />);
    const sourceFilter = await screen.findByRole('button', { name: 'Filter evidence to Sources: 1 records' });
    fireEvent.click(sourceFilter);

    await waitFor(() => expect((screen.getByLabelText('Evidence record type') as HTMLSelectElement).value).toBe('source'));
    expect(screen.getByText('1 of 2 persisted metadata records in view.')).toBeTruthy();
  });

  it('keeps source nodes drillable and renders non-local reference targets explicitly', () => {
    const graph = buildEvidenceGraph({
      nodes: [
        { id: 'source-a', type: 'source', status: 'captured' },
        { id: 'asset-a', type: 'asset', status: 'available' },
        { id: 'target:wiki_page:overview-a', type: 'target', status: 'resolved', target_type: 'wiki_page', target_id: 'overview-a', anchor: 'Knowledge overview' },
      ],
      edges: [
        { id: 'source-asset', source: 'source-a', target: 'asset-a', relation: 'has_asset' },
        { id: 'source-wiki', source: 'source-a', target: 'target:wiki_page:overview-a', relation: 'explains', resolution_state: 'resolved' },
      ],
      node_total: 3,
      edge_total: 2,
      omitted_edge_count: 0,
      truncated: false,
    });

    expect(graph.nodes.find((node) => node.id === 'source-a')?.data.recordType).toBe('source');
    expect(graph.nodes.find((node) => node.id === 'target:wiki_page:overview-a')?.data.recordType).toBeUndefined();
    expect(graph.nodes.find((node) => node.id === 'target:wiki_page:overview-a')?.data.targetAnchor).toBe('Knowledge overview');
    expect(graph.edges.map((edge) => edge.id)).toEqual(['source-asset', 'source-wiki']);
  });

  it('prioritizes persisted lineage over unrelated inventory and lays it out by evidence stage', () => {
    const graph = buildEvidenceGraph({
      nodes: [
        { id: 'source-a', type: 'source', status: 'captured' },
        { id: 'asset-a', type: 'asset', status: 'available' },
        { id: 'extract-a', type: 'extraction', status: 'complete' },
        { id: 'source-unrelated', type: 'source', status: 'validated' },
      ],
      edges: [
        { id: 'source-asset', source: 'source-a', target: 'asset-a', relation: 'has_asset' },
        { id: 'asset-extract', source: 'asset-a', target: 'extract-a', relation: 'extracted_by' },
      ],
      node_total: 4,
      edge_total: 2,
      omitted_edge_count: 0,
      truncated: false,
    });

    expect(graph.nodes.map((node) => node.id)).toEqual(['source-a', 'asset-a', 'extract-a']);
    expect(graph.hiddenUnconnectedNodeCount).toBe(1);
    expect(graph.nodes[0].position.x).toBeLessThan(graph.nodes[1].position.x);
    expect(graph.nodes[1].position.x).toBeLessThan(graph.nodes[2].position.x);
  });

  it('uses a bounded readable mobile focus without presenting omitted records as absent', () => {
    const graph = buildEvidenceGraph({
      nodes: [
        { id: 'source-a', type: 'source', status: 'captured' },
        { id: 'asset-a', type: 'asset', status: 'available' },
        { id: 'extract-a', type: 'extraction', status: 'complete' },
      ],
      edges: [
        { id: 'source-asset', source: 'source-a', target: 'asset-a', relation: 'has_asset' },
        { id: 'asset-extract', source: 'asset-a', target: 'extract-a', relation: 'extracted_by' },
      ],
      node_total: 3,
      edge_total: 2,
      omitted_edge_count: 0,
      truncated: false,
    }, { focusLimit: 2, compact: true });

    expect(graph.focusApplied).toBe(true);
    expect(graph.connectedNodeCount).toBe(3);
    expect(graph.hiddenFocusedNodeCount).toBe(1);
    expect(graph.nodes.map((node) => node.id)).toEqual(['source-a', 'asset-a']);
    expect(graph.edges.map((edge) => edge.id)).toEqual(['source-asset']);
    expect(graph.nodes[0].position).toEqual({ x: 18, y: 24 });
  });

  it('collapses asset-only hops into a traceable focus path without hiding persisted relations', () => {
    const graph = buildEvidenceGraph({
      nodes: [
        { id: 'source-a', type: 'source', status: 'captured', label: 'Source: research.example/brief' },
        { id: 'asset-a', type: 'asset', status: 'available', label: 'Asset: Binary file' },
        { id: 'extract-a', type: 'extraction', status: 'complete', label: 'Extraction: OCR (complete)' },
        { id: 'target:wiki_page:overview-a', type: 'target', status: 'resolved', target_type: 'wiki_page', target_id: 'overview-a', label: 'Wiki page: overview-a' },
      ],
      edges: [
        { id: 'source-asset', source: 'source-a', target: 'asset-a', relation: 'has_asset' },
        { id: 'asset-extract', source: 'asset-a', target: 'extract-a', relation: 'extracted_by' },
        { id: 'source-wiki', source: 'source-a', target: 'target:wiki_page:overview-a', relation: 'cites' },
      ],
      node_total: 4,
      edge_total: 3,
      omitted_edge_count: 0,
      truncated: false,
    }, { focusLimit: 3, collapseAssetBridges: true });

    expect(graph.nodes.map((node) => node.id)).toEqual(['source-a', 'extract-a', 'target:wiki_page:overview-a']);
    expect(graph.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: 'source-a', target: 'extract-a', label: 'via 1 recorded asset' }),
    ]));
    expect(graph.collapsedAssetNodeCount).toBe(1);
    expect(graph.persistedEdges.map((edge) => edge.id)).toEqual(['source-asset', 'asset-extract', 'source-wiki']);
  });

  it('reloads persisted evidence when the parent workspace refreshes the same project', async () => {
    vi.mocked(fetchKnowledgeEvidence).mockResolvedValueOnce(evidenceSnapshot('https://example.test/first'));
    vi.mocked(fetchKnowledgeEvidence).mockResolvedValueOnce(evidenceSnapshot('https://example.test/refreshed'));
    vi.mocked(fetchKnowledgeEvidenceRecord).mockResolvedValue({ record: evidenceSnapshot('unused').sources[0] });

    const view = render(<EvidenceWorkspace projectId="default" refreshVersion={0} />);
    expect(await screen.findByText('https://example.test/first')).toBeTruthy();

    view.rerender(<EvidenceWorkspace projectId="default" refreshVersion={1} />);
    expect(await screen.findByText('https://example.test/refreshed')).toBeTruthy();
    await waitFor(() => expect(fetchKnowledgeEvidence).toHaveBeenCalledTimes(2));
  });

  it('filters by persisted metadata while retaining the focused lineage context', () => {
    const data = richEvidenceSnapshot();
    const filtered = filterEvidence(data, { recordType: 'extraction', status: 'partial', query: 'canvas' });

    expect(filtered.records.map((record) => record.id)).toEqual(['extract-visual']);
    expect(filtered.graph.edges.map((edge) => edge.id)).toContain('asset-extraction');
    expect(filtered.graph.edges.filter((edge) => edge.relation === 'contains_table')).toHaveLength(6);
    expect(filtered.graph.nodes.map((node) => node.id)).toContain('extract-visual');
    expect(visualEvidence(filtered.extractions, data.assets)).toHaveLength(1);
  });

  it('treats an Obsidian Excalidraw Markdown derivative as visual evidence', () => {
    const data = richEvidenceSnapshot();
    const extraction = { ...data.extractions[0], extractor: 'excalidraw-elements' };
    const markdownAsset = { ...data.assets[0], mime_type: 'text/markdown' };

    expect(visualEvidence([extraction], [markdownAsset])).toHaveLength(1);
  });

  it('renders filterable table pagination and a visual metadata inspector without source bodies', async () => {
    vi.mocked(fetchKnowledgeEvidence).mockResolvedValue(richEvidenceSnapshot());
    vi.mocked(fetchKnowledgeEvidenceRecord).mockResolvedValue({ record: richEvidenceSnapshot().extractions[0] });

    render(<EvidenceWorkspace projectId="default" />);
    expect(await screen.findByText('Table explorer')).toBeTruthy();
    expect(screen.getByText('Image and figure inspector')).toBeTruthy();
    expect(screen.getByText('3 elements')).toBeTruthy();
    expect(screen.getByText('Page 1 of 2')).toBeTruthy();

    const next = screen.getByLabelText('Next table page');
    fireEvent.click(next);
    expect(await screen.findByText('Page 2 of 2')).toBeTruthy();
    expect(screen.getByText('metric_6, value')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('Evidence record type'), { target: { value: 'table' } });
    await waitFor(() => expect(screen.getByText('6 of 10 persisted metadata records in view.')).toBeTruthy());
    expect(screen.getByText('No persisted image, Canvas, or Excalidraw derivatives match this evidence view.')).toBeTruthy();
  });

  it('opens an authorized, bounded table-row preview with its derivative provenance', async () => {
    vi.mocked(fetchKnowledgeEvidence).mockResolvedValue(richEvidenceSnapshot());
    vi.mocked(fetchKnowledgeEvidenceRecord).mockResolvedValue({ record: richEvidenceSnapshot().tables[0] });
    vi.mocked(fetchKnowledgeTablePreview).mockResolvedValue({
      table_id: 'table-1', source_id: 'source-a', extraction_id: 'extract-visual',
      schema: ['metric_1', 'value'], units: { value: 'count' }, rows: [['qualified evidence', '3']],
      page: 1, page_size: 25, total_rows: 2, available_rows: 2, total_pages: 1,
      truncated: false, derived: true, state: 'available', reason: '',
      provenance: { extractor: 'csv-table', extractor_revision: 'local-v2', sheet: 'Signals', content_hash: 'c'.repeat(64) },
    });

    render(<EvidenceWorkspace projectId="default" />);
    const tableButton = await screen.findByRole('button', { name: 'metric_1, value' });
    fireEvent.click(tableButton);

    expect(await screen.findByText('Derived table rows')).toBeTruthy();
    expect(screen.getByText('qualified evidence')).toBeTruthy();
    expect(screen.getByText('Derived data via csv-table / Signals. Review before treating any value as a conclusion.')).toBeTruthy();
    expect(fetchKnowledgeTablePreview).toHaveBeenCalledWith('default', 'table-1', 1);
  });

  it('loads a bounded image thumbnail only after the user selects its visual derivative', async () => {
    vi.mocked(fetchKnowledgeEvidence).mockResolvedValue(richEvidenceSnapshot());
    vi.mocked(fetchKnowledgeEvidenceRecord).mockResolvedValue({ record: richEvidenceSnapshot().extractions[0] });
    vi.mocked(fetchKnowledgeImageThumbnail).mockResolvedValue('blob:authorized-image-preview');

    render(<EvidenceWorkspace projectId="default" />);
    const visualCard = (await screen.findByText('Image and figure inspector')).closest('article');
    expect(visualCard).toBeTruthy();
    const extractorLabels = await within(visualCard as HTMLElement).findAllByText('canvas-elements', { exact: true });
    expect(extractorLabels).toHaveLength(1);
    fireEvent.click(extractorLabels[0]);

    const preview = await screen.findByRole('img', { name: 'Authorized evidence preview' });
    expect(preview.getAttribute('src')).toBe('blob:authorized-image-preview');
    expect(fetchKnowledgeImageThumbnail).toHaveBeenCalledWith('default', 'asset-image');
  });
});

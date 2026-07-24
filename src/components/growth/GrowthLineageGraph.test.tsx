// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('reactflow', () => ({
  default: ({ nodes, edges, onNodeClick }: { nodes: Array<{ id: string; data: { label: string; endpointType: string } }>; edges: Array<{ id: string; label?: string }>; onNodeClick: (event: unknown, node: unknown) => void }) => <div data-testid="flow" data-edge-count={edges.length} data-edge-label-count={edges.filter((edge) => edge.label).length}>{nodes.map((node) => <button type="button" key={node.id} aria-label={`Graph node ${node.id}`} onClick={() => onNodeClick({}, node)}>{node.data.label}</button>)}</div>,
  Background: () => null,
  Controls: () => null,
}));

import { GrowthLineageGraph } from './GrowthLineageGraph';

const lineage = {
  project_id: 'project-a', limit: 200, truncated: true,
  nodes: [
    { id: 'source-a', type: 'source', label: 'Robotics research signal', status: 'processed' },
    { id: 'page-a', type: 'page', label: 'Embodied AI overview', status: 'published' },
    { id: 'method-a', type: 'method', label: 'Research synthesis', status: 'published' },
    { id: 'feedback-a', type: 'feedback', label: 'accepted', status: 'processed' },
    { id: 'output-a', type: 'output', label: 'Client research brief', status: 'accepted' },
  ],
  edges: [
    { id: 'edge-a', from_id: 'source-a', to_id: 'page-a', from_type: 'source', to_type: 'page', edge_type: 'source_supports_page' },
    { id: 'edge-b', from_id: 'page-a', to_id: 'method-a', from_type: 'page', to_type: 'method', edge_type: 'page_informs_method' },
    { id: 'edge-c', from_id: 'feedback-a', to_id: 'output-a', from_type: 'feedback', to_type: 'output', edge_type: 'feedback_evaluates_output' },
  ],
};

afterEach(() => cleanup());

describe('GrowthLineageGraph', () => {
  it('renders a bounded real slice and selects a typed node', () => {
    const select = vi.fn();
    render(<GrowthLineageGraph lineage={lineage} state="success" relation="" onRelationChange={vi.fn()} onSelect={select} onRetry={vi.fn()} />);

    expect(screen.getByText(/first 200 server-returned edges/)).toBeVisible();
    expect(screen.getByTestId('flow')).toHaveAttribute('data-edge-count', '3');
    expect(screen.getByTestId('flow')).toHaveAttribute('data-edge-label-count', '3');
    expect(screen.getByRole('button', { name: 'Graph node source-a' })).toHaveTextContent('Robotics research signal');
    fireEvent.click(screen.getByRole('button', { name: 'Graph node source-a' }));
    expect(select).toHaveBeenCalledWith('source-a', 'source');
  });

  it('suppresses overlapping edge labels in a dense graph while preserving every edge', () => {
    const denseLineage = {
      ...lineage,
      truncated: false,
      edges: Array.from({ length: 7 }, (_, index) => ({
        id: `dense-${index}`,
        from_id: `source-${index}`,
        to_id: `page-${index}`,
        from_type: 'source',
        to_type: 'page',
        edge_type: 'source_supports_page',
      })),
    };
    render(<GrowthLineageGraph lineage={denseLineage} state="success" relation="" onRelationChange={vi.fn()} onSelect={vi.fn()} onRetry={vi.fn()} />);

    expect(screen.getByTestId('flow')).toHaveAttribute('data-edge-count', '7');
    expect(screen.getByTestId('flow')).toHaveAttribute('data-edge-label-count', '0');
    expect(screen.getByRole('list', { name: 'Lineage relationships' })).toHaveTextContent('source-0 source_supports_page page-0');
  });

  it('filters nodes and edges by the requested domain type', () => {
    render(<GrowthLineageGraph lineage={lineage} state="success" relation="" onRelationChange={vi.fn()} onSelect={vi.fn()} onRetry={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'source' }));

    expect(screen.queryByRole('button', { name: 'Graph node source-a' })).not.toBeInTheDocument();
    expect(screen.getByTestId('flow')).toHaveAttribute('data-edge-count', '2');
  });

  it('requests a server relation filter', () => {
    const change = vi.fn();
    render(<GrowthLineageGraph lineage={lineage} state="success" relation="" onRelationChange={change} onSelect={vi.fn()} onRetry={vi.fn()} />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter lineage relation' }), { target: { value: 'page_informs_method' } });
    expect(change).toHaveBeenCalledWith('page_informs_method');
  });

  it('shows empty and endpoint error states truthfully', () => {
    const { rerender } = render(<GrowthLineageGraph lineage={{ ...lineage, edges: [], truncated: false }} state="empty" relation="" onRelationChange={vi.fn()} onSelect={vi.fn()} onRetry={vi.fn()} />);
    expect(screen.getByText(/No persisted relationships/)).toBeVisible();
    rerender(<GrowthLineageGraph lineage={null} state="error" error="Server error (500)" relation="" onRelationChange={vi.fn()} onSelect={vi.fn()} onRetry={vi.fn()} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Server error (500)');
  });
});

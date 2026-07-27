import { describe, expect, it, vi } from 'vitest';

import { fetchOperationsGraph, fetchOperationsPortfolio, OperationsRequestError } from './knowledgeOperationsApi';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('knowledge operations API client', () => {
  it('uses the bounded graph query and unwraps the standard response envelope', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(jsonResponse({
      success: true,
      data: { project_id: 'project-a', nodes: [], edges: [], lanes: [], pagination: {}, lifecycle_audit: { scope: 'filtered_graph', risk_node_count: 0, complete_risk_lineage_count: 0, missing_lanes: [], reason: 'No persisted risk or constraint nodes are present in this graph.' }, coverage: { state: 'available', record_count: 0, reason: '' }, state: 'available', scope: {} },
    }));

    const graph = await fetchOperationsGraph('project/a', { missionId: 'mission-a', nodeTypes: ['risk'], relations: ['artifact_parent'], limit: 100 });

    expect(graph.project_id).toBe('project-a');
    expect(String(fetchMock.mock.calls[0][0])).toContain('/knowledge/operations/projects/project%2Fa/graph?');
    expect(String(fetchMock.mock.calls[0][0])).toContain('mission_id=mission-a');
    expect(String(fetchMock.mock.calls[0][0])).toContain('node_type=risk');
    expect(String(fetchMock.mock.calls[0][0])).toContain('relation=artifact_parent');
    fetchMock.mockRestore();
  });

  it('turns a policy response into a typed error rather than retaining a previous value', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(jsonResponse({
      code: 403,
      message: { code: 'operations_portfolio_admin_required', message: 'Portfolio operations require a tenant administrator.' },
      data: null,
    }, 403));

    await expect(fetchOperationsPortfolio()).rejects.toEqual(expect.objectContaining<Partial<OperationsRequestError>>({
      name: 'OperationsRequestError', code: 'operations_portfolio_admin_required', status: 403,
    }));
    fetchMock.mockRestore();
  });
});

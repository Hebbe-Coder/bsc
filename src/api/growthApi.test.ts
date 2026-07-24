import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  addGrowthOutputFeedback,
  GrowthRequestError,
  classifyGrowthError,
  fetchGrowthAssetDetail,
  fetchGrowthLineage,
  fetchGrowthOverview,
  fetchGrowthStage,
  evaluateGrowthOutput,
  fileGrowthOutput,
  growthRecordKind,
  linkGrowthOutputEvidence,
  updateGrowthProfile,
} from './growthApi';

const ok = (data: unknown) => new Response(JSON.stringify({ success: true, data }), { status: 200, headers: { 'Content-Type': 'application/json' } });
const failed = (status: number, code: string, message: string) => new Response(JSON.stringify({ success: false, detail: { code, message } }), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => vi.unstubAllGlobals());

describe('growthApi', () => {
  it('loads only project-scoped persisted overview data', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/profile')) return Promise.resolve(ok({ profile: { project_id: 'project-a', revision: 2 } }));
      return Promise.resolve(ok({ project_id: 'project-a', counts: { sources: 2, pages: 1 } }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const overview = await fetchGrowthOverview('project-a');

    expect(overview.profile.project_id).toBe('project-a');
    expect(overview.summary.counts.sources).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.every(([url]) => String(url).includes('project-a'))).toBe(true);
  });

  it('updates the project profile through the revisioned PATCH contract', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), init });
      return Promise.resolve(ok({ profile: { project_id: 'project-a', revision: 8, user_role: 'research lead' } }));
    }));

    const saved = await updateGrowthProfile('project-a', {
      expected_revision: 7,
      user_role: 'research lead',
      research_domains: ['agent systems'],
      primary_output_types: ['research brief'],
      target_audiences: ['product team'],
      preferred_channels: ['Obsidian'],
      language: 'zh-CN',
      content_voice: 'evidence-backed',
      evidence_threshold: 85,
      automatic_publication_policy: 'review',
      method_promotion_policy: 'gated',
    });

    expect(saved.revision).toBe(8);
    expect(requests).toHaveLength(1);
    expect(requests[0].url).toContain('/knowledge/growth/project-a/profile');
    expect(requests[0].init?.method).toBe('PATCH');
    expect(JSON.parse(String(requests[0].init?.body))).toMatchObject({ expected_revision: 7, research_domains: ['agent systems'] });
  });

  it('uses stage and bounded limit parameters for incremental pagination', async () => {
    const requestedUrls: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      requestedUrls.push(String(input));
      return Promise.resolve(ok({
        project_id: 'project-a',
        stage: 'D',
        items: Array.from({ length: 40 }, (_, index) => ({ id: `output-${index}`, asset_type: 'output' })),
        pagination: { limit: 40, cursor: null, next_cursor: '40', count: 40 },
      }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchGrowthStage('project-a', 'D', 40);

    expect(result.records).toHaveLength(40);
    expect(result.truncated).toBe(true);
    expect(requestedUrls[0]).toContain('stage=D&limit=40');
  });

  it('keeps legacy grouped assets compatible while preferring canonical item types', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(ok({
      project_id: 'project-a',
      stage: 'A',
      sources: [{ id: 'source-a' }],
    }))));

    const result = await fetchGrowthStage('project-a', 'A', 40);

    expect(result.records).toEqual([{ id: 'source-a' }]);
    expect(result.truncated).toBe(false);
    expect(growthRecordKind({ id: 'proposal-a', asset_type: 'wiki_proposal' }, 'review')).toBe('proposal');
  });

  it('includes bounded distillations in Review and reads their managed documents', async () => {
    const requests: string[] = [];
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.includes('/assets?')) return Promise.resolve(ok({ project_id: 'project-a', stage: 'review', items: [{ id: 'proposal-a', asset_type: 'wiki_proposal' }], pagination: { next_cursor: null } }));
      if (url.includes('/growth/project-a/distillations?')) return Promise.resolve(ok({ distillations: [{ id: 'weekly-a', project_id: 'project-a', kind: 'weekly', period: '2026-W30', status: 'generated', paths: ['distillations/weekly/2026-W30/summary.md'] }], pagination: { next_cursor: null } }));
      return Promise.resolve(ok({ distillation: { id: 'weekly-a', project_id: 'project-a', kind: 'weekly', period: '2026-W30', status: 'generated' }, documents: { 'distillations/weekly/2026-W30/summary.md': '# Evidence-backed weekly summary' } }));
    }));

    const stage = await fetchGrowthStage('project-a', 'review', 40);
    const detail = await fetchGrowthAssetDetail('project-a', 'review', 'weekly-a');

    expect(stage.records).toEqual(expect.arrayContaining([expect.objectContaining({ id: 'weekly-a', asset_type: 'distillation', title: 'Weekly distillation 2026-W30' })]));
    expect(detail.kind).toBe('distillation');
    expect(detail.content).toContain('Evidence-backed weekly summary');
    expect(requests.some((url) => url.includes('/knowledge/distillations/weekly-a?project_id=project-a'))).toBe(true);
  });

  it('loads a page detail and content from the real Wiki detail endpoint', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/assets?')) return Promise.resolve(ok({ project_id: 'project-a', stage: 'B', pages: [{ id: 'page-a', path: 'wiki/page-a.md' }] }));
      return Promise.resolve(ok({ page: { id: 'page-a', path: 'wiki/page-a.md' }, content: '# Persisted page', revisions: [{ id: 'revision-a' }], citations: [{ source_id: 'source-a' }], backlinks: [] }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const detail = await fetchGrowthAssetDetail('project-a', 'B', 'page-a');

    expect(detail.content).toBe('# Persisted page');
    expect(detail.citations).toEqual([{ source_id: 'source-a' }]);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/knowledge/wiki/pages/page-a?project_id=project-a'))).toBe(true);
  });

  it('resolves a published method body and accepts an active revision graph id', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/assets?')) return Promise.resolve(ok({ project_id: 'project-a', stage: 'C', items: [{ id: 'method-a', active_revision_id: 'revision-a', asset_type: 'method' }], pagination: { next_cursor: null } }));
      return Promise.resolve(ok({ method: { id: 'method-a', status: 'published', active_revision_id: 'revision-a' }, revision: { id: 'revision-a', body: '# Exact method revision', version: 1 }, resolution_status: 'available' }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const detail = await fetchGrowthAssetDetail('project-a', 'C', 'revision-a');

    expect(detail.record.id).toBe('method-a');
    expect(detail.content).toBe('# Exact method revision');
    expect(detail.revisions?.[0].id).toBe('revision-a');
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/methods/method-a/resolve'))).toBe(true);
  });

  it('loads verified output content, evaluations and feedback from real endpoints', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/assets?')) return Promise.resolve(ok({ project_id: 'project-a', stage: 'D', items: [{ id: 'output-a', asset_type: 'output' }], pagination: { next_cursor: null } }));
      if (url.endsWith('/content')) return Promise.resolve(ok({ content: { output_id: 'output-a', mime_type: 'text/markdown', content_hash: 'a'.repeat(64), byte_size: 18, vault_path: 'outputs/2026/output-a/report.md', render_mode: 'text', content: '# Verified output' } }));
      return Promise.resolve(ok({ output: { id: 'output-a', status: 'accepted' }, evaluations: [{ id: 'eval-a', quality: 96 }], feedback: [{ id: 'feedback-a', feedback_type: 'rated', rating: 95 }] }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const detail = await fetchGrowthAssetDetail('project-a', 'D', 'output-a');

    expect(detail.content).toBe('# Verified output');
    expect(detail.evaluations?.[0].quality).toBe(96);
    expect(detail.feedback?.[0].rating).toBe(95);
    expect(detail.contentDescriptor?.render_mode).toBe('text');
  });

  it('hydrates a canonical review proposal before loading its baselines', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/assets?')) return Promise.resolve(ok({ project_id: 'project-a', stage: 'review', items: [{ id: 'proposal-a', asset_type: 'wiki_proposal', operation_count: 1 }], pagination: { next_cursor: null } }));
      if (url.includes('/knowledge/proposals?')) return Promise.resolve(ok({ proposals: [{ id: 'proposal-a', operations: [{ path: 'wiki/page.md', operation: 'update', content: '# Proposed' }] }] }));
      if (url.includes('/knowledge/wiki/pages?')) return Promise.resolve(ok({ pages: [{ id: 'page-a', path: 'wiki/page.md' }] }));
      return Promise.resolve(ok({ page: { id: 'page-a', path: 'wiki/page.md' }, content: '# Current', revisions: [], citations: [], backlinks: [] }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const detail = await fetchGrowthAssetDetail('project-a', 'review', 'proposal-a');

    expect(detail.record.operations).toEqual([{ path: 'wiki/page.md', operation: 'update', content: '# Proposed' }]);
    expect(detail.baselines).toEqual({ 'wiki/page.md': '# Current' });
  });

  it('persists output feedback and filing through project-scoped mutation endpoints', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), init });
      return Promise.resolve(ok(String(input).endsWith('/file') ? { output: { id: 'output-a', status: 'filed' } } : { feedback: { id: 'feedback-a', status: 'pending' } }));
    }));

    const feedback = await addGrowthOutputFeedback('project-a', 'output-a', { feedback_type: 'rated', rating: 96 });
    const filed = await fileGrowthOutput('project-a', 'output-a');

    expect(feedback.id).toBe('feedback-a');
    expect(filed.status).toBe('filed');
    expect(requests.map((item) => item.url)).toEqual([
      expect.stringContaining('/project-a/outputs/output-a/feedback'),
      expect.stringContaining('/project-a/outputs/output-a/file'),
    ]);
    expect(requests.every((item) => item.init?.method === 'POST')).toBe(true);
  });

  it('links captured evidence before persisting an output quality review', async () => {
    const requests: Array<{ url: string; body?: string }> = [];
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), body: String(init?.body || '') });
      return Promise.resolve(ok(String(input).endsWith('/evidence')
        ? { output: { id: 'output-a', source_refs: [], status: 'registered' }, evidence: { source_ids: ['source-a'], page_ids: [] } }
        : { evaluation: { id: 'evaluation-a', quality: 90, status: 'completed' } }));
    }));

    const linked = await linkGrowthOutputEvidence('project-a', 'output-a', { source_ids: ['source-a'], page_ids: [] });
    const evaluated = await evaluateGrowthOutput('project-a', 'output-a', {
      groundedness: 0.9, task_fit: 0.9, usefulness: 0.9, coherence: 0.9, format_quality: 0.9, findings: ['Evidence linked'],
    });

    expect(linked.output.source_refs).toEqual([]);
    expect(linked.evidence.source_ids).toEqual(['source-a']);
    expect(evaluated.quality).toBe(90);
    expect(requests.map((item) => item.url)).toEqual([
      expect.stringContaining('/project-a/outputs/output-a/evidence'),
      expect.stringContaining('/project-a/outputs/output-a/evaluate'),
    ]);
    expect(JSON.parse(requests[0].body || '{}')).toEqual({ source_ids: ['source-a'], page_ids: [] });
    expect(JSON.parse(requests[1].body || '{}')).toMatchObject({ groundedness: 0.9, findings: ['Evidence linked'] });
  });

  it('retains server graph bounds without inventing a total', async () => {
    const edges = Array.from({ length: 200 }, (_, index) => ({ id: `edge-${index}`, from_id: `source-${index}`, to_id: `page-${index}`, edge_type: 'source_supports_page' }));
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(ok({ project_id: 'project-a', edges }))));

    const lineage = await fetchGrowthLineage('project-a', 'source_supports_page', 200);

    expect(lineage).toMatchObject({ limit: 200, truncated: true });
  });

  it('rejects immediately when the caller aborts a stale request', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => setTimeout(() => resolve(ok({ project_id: 'project-a', stage: 'A', sources: [] })), 40))));
    const controller = new AbortController();
    const pending = fetchGrowthStage('project-a', 'A', 20, controller.signal);
    controller.abort();

    await expect(pending).rejects.toMatchObject({ code: 'request_aborted' });
  });

  it('surfaces proposal baseline server failures instead of claiming a partial success', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/assets?')) return Promise.resolve(ok({ project_id: 'project-a', stage: 'review', feedback: [], proposals: [{ id: 'proposal-a', operations: [{ path: 'wiki/page.md', content: 'next' }] }] }));
      if (url.includes('/growth/project-a/distillations?')) return Promise.resolve(ok({ distillations: [], pagination: { next_cursor: null } }));
      return Promise.resolve(failed(500, 'baseline_failed', 'baseline service failed'));
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchGrowthAssetDetail('project-a', 'review', 'proposal-a')).rejects.toMatchObject({ status: 500, code: 'baseline_failed' });
  });

  it.each([
    [403, 'permission'],
    [503, 'unavailable'],
    [500, 'error'],
  ] as const)('classifies HTTP %s without a mock fallback', async (status, state) => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(failed(status, 'growth_failure', 'not available'))));

    await expect(fetchGrowthStage('project-a', 'A')).rejects.toMatchObject({ status, state, code: 'growth_failure' });
  });

  it('classifies a network failure as offline', () => {
    const result = classifyGrowthError(new TypeError('fetch failed'));
    expect(result).toBeInstanceOf(GrowthRequestError);
    expect(result.state).toBe('offline');
  });
});

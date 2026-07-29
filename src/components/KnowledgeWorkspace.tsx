import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import ReactFlow, { Background, Controls, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import {
  AlertTriangle, BookOpen, CheckCircle2, ChevronRight, Clock3, Database, Download, FileClock,
  FileText, GitPullRequest, Link2, Network, Pause, Play, RefreshCw, RotateCcw,
  Pencil, Radio, Search, ShieldCheck, Sparkles, Sprout, Trash2, Upload, WandSparkles, X,
} from 'lucide-react';
import {
  configureKnowledgePlugins, configureKnowledgeSchedule, configureKnowledgeVault, fetchKnowledgeGraph, fetchKnowledgeHealth, fetchKnowledgeHealthTrend,
  fetchKnowledgePage, fetchKnowledgePages, fetchKnowledgeProposals, fetchKnowledgeRunEvents, fetchKnowledgeSourceTriage,
  fetchKnowledgeRuns, fetchKnowledgeSchedules, fetchKnowledgeSources, fetchKnowledgeWorkspace, importFeishuKnowledgeExport, initializeKnowledgeWorkspace,
  fetchWeeklyDistillation, fetchWeeklyDistillations, lintKnowledgeProposal, publishKnowledgeProposal,
  rejectKnowledgeProposal, restoreKnowledgePageRevision, retryKnowledgeRun, runKnowledgeJob, saveKnowledgeEvaluationCase, setKnowledgePluginTrust, setKnowledgeScheduleState,
  semanticTriageKnowledgeSource, streamKnowledgeRunEvents, transitionKnowledgeSource,
  type FeishuKnowledgeExport, type KnowledgeEvaluationCaseInput, type KnowledgeGraphNode, type KnowledgeHealth, type KnowledgeWorkspaceData,
  type KnowledgePage, type KnowledgePageDetail, type KnowledgePluginBridge, type KnowledgeProposal, type KnowledgeRun,
  type KnowledgeRunEvent, type KnowledgeSchedule, type KnowledgeSource, type KnowledgeSourceTriage,
  type WeeklyDistillation, type WeeklyDistillationDetail,
} from '../api/knowledgeWorkspaceApi';
import { useKnowledgeWorkspaceStore, type KnowledgeProposalBaselines } from '../store/knowledgeWorkspaceStore';
import { InformationOperationsPanel } from './knowledge/InformationOperationsPanel';
import { resolveStudioAccessStatus } from './knowledgeWorkspaceAccess';
import { describeKnowledgeSource, selectDefaultKnowledgePage } from './knowledgePresentation';

type Props = { onClose: () => void; runtimeAccessKey?: string };
type GraphNodeData = { record: KnowledgeGraphNode; label: string };

export const KNOWLEDGE_JOB_OPTIONS = [
  { id: 'source_sync', label: 'Sync declared exports', defaultCron: '0 8 * * 1' },
  { id: 'horizon_capture', label: 'Capture Horizon run', defaultCron: '0 8 * * 1' },
  { id: 'wiki_maintenance', label: 'Compile Wiki proposal', defaultCron: '0 9 * * 1' },
  { id: 'knowledge_lint_eval', label: 'Evaluate knowledge health', defaultCron: '0 10 * * 1' },
  { id: 'weekly_distillation', label: 'Legacy weekly distillation', defaultCron: '0 17 * * 5' },
  { id: 'growth_daily', label: 'Daily growth cycle', defaultCron: '0 17 * * *' },
  { id: 'growth_weekly_distillation', label: 'Friday weekly growth distillation', defaultCron: '30 17 * * 5' },
] as const;
const TERMINAL_RUNS = new Set(['completed', 'failed', 'cancelled', 'unavailable']);
const TrendChart = lazy(() => import('echarts-for-react'));
export const OBSIDIAN_PLUGIN_PRESETS = [
  { id: 'custom', name: 'Custom evidence export', adapter: 'filesystem_drop', input_paths: ['00_Inbox/custom'] },
  { id: 'readwise', name: 'Readwise / Reader export', adapter: 'filesystem_drop', input_paths: ['00_Inbox/readwise'] },
  { id: 'obsidian-clipper', name: 'Obsidian Clipper export', adapter: 'filesystem_drop', input_paths: ['00_Inbox/web-clipper'] },
  { id: 'xiaohongshu-importer', name: 'Xiaohongshu Importer export', adapter: 'filesystem_drop', input_paths: ['00_Inbox/social'] },
  { id: 'feishu-cli', name: 'Feishu CLI export', adapter: 'filesystem_drop', input_paths: ['01_Sources/feishu'] },
  { id: 'docxer', name: 'Docxer export', adapter: 'filesystem_drop', input_paths: ['01_Sources/docxer'] },
  { id: 'obsidian-importer', name: 'Obsidian Importer export', adapter: 'filesystem_drop', input_paths: ['01_Sources/importer'] },
  { id: 'hyperframes', name: 'HyperFrames output feedback', adapter: 'filesystem_output', input_paths: ['04_Outputs/hyperframes'] },
  { id: 'markdown-output', name: 'Markdown formatter output feedback', adapter: 'filesystem_output', input_paths: ['04_Outputs/articles'] },
  { id: 'project-raw', name: 'Legacy raw/ export', adapter: 'filesystem_drop', input_paths: ['raw/custom'] },
  { id: 'project-inbox', name: 'Legacy inbox/ export', adapter: 'filesystem_drop', input_paths: ['inbox/custom'] },
] as const;

const VAULT_CONNECTION_LABELS: Record<NonNullable<KnowledgeWorkspaceData['vault']['connection']>['state'], string> = {
  unconfigured: 'No project Vault mapped',
  unavailable: 'Vault unavailable to this runtime',
  mapped_uninitialized: 'Vault mapped, Wiki not initialized',
  mapped_incomplete: 'Vault reachable, baseline incomplete',
  ready: 'Vault connected and Wiki ready',
};

export function KnowledgeWorkspace({ onClose, runtimeAccessKey = '' }: Props) {
  const {
    projectId, workspace, sources, runs, schedules, graph, proposals, pages, distillations, health, trend,
    selectedPage, selectedSource, selectedProposal, selectedRun, selectedDistillation, proposalBaselines,
    runEvents, centerView, mobilePane, graphEdgeType, graphNodeType, graphNodeStatus, pendingNavigationTargetId, error, actionMessage,
    loading, actionBusy, setProjectId, beginLoad, applyLoad, failLoad, setSelectedPage, setSelectedSource,
    setSelectedProposal, setSelectedRun, setSelectedDistillation, setProposalBaselines, clearRunEvents,
    appendRunEvents, setCenterView, setMobilePane, setGraphEdgeType, setGraphNodeType, setGraphNodeStatus, clearNavigationTarget,
    setError, setActionMessage, setActionBusy,
  } = useKnowledgeWorkspaceStore();
  const [isCompactViewport, setIsCompactViewport] = useState(() => window.matchMedia('(max-width: 780px)').matches);
  const [scheduleJobType, setScheduleJobType] = useState('source_sync');
  const [scheduleCron, setScheduleCron] = useState('0 8 * * 1');
  const [vaultPath, setVaultPath] = useState('projects/default');
  const [pluginPreset, setPluginPreset] = useState('custom');
  const [pluginId, setPluginId] = useState('');
  const [pluginName, setPluginName] = useState('');
  const [pluginAdapter, setPluginAdapter] = useState<KnowledgePluginBridge['adapter']>('filesystem_drop');
  const [pluginPaths, setPluginPaths] = useState('00_Inbox/custom');
  const [includeDistillationHistory, setIncludeDistillationHistory] = useState(false);
  const [selectedSourceTriage, setSelectedSourceTriage] = useState<KnowledgeSourceTriage | null>(null);
  const feishuExportInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async (graphFilter = graphEdgeType) => {
    const requestedProject = projectId;
    const version = beginLoad(requestedProject);
    try {
      const [nextWorkspace, nextSources, nextRuns, nextGraph, nextSchedules, nextProposals, nextPages, nextDistillations, nextHealth, nextTrend] = await Promise.all([
        fetchKnowledgeWorkspace(projectId), fetchKnowledgeSources(projectId), fetchKnowledgeRuns(projectId), fetchKnowledgeGraph(projectId, graphFilter),
        fetchKnowledgeSchedules(projectId), fetchKnowledgeProposals(projectId), fetchKnowledgePages(projectId), fetchWeeklyDistillations(projectId, includeDistillationHistory),
        fetchKnowledgeHealth(projectId), fetchKnowledgeHealthTrend(projectId),
      ]);
      applyLoad(version, requestedProject, {
        workspace: nextWorkspace,
        sources: nextSources.sources,
        runs: nextRuns.runs,
        graph: nextGraph,
        schedules: nextSchedules.schedules,
        proposals: nextProposals.proposals,
        pages: nextPages.pages,
        distillations: nextDistillations.distillations,
        health: nextHealth,
        trend: nextTrend,
      });
    } catch (reason) {
      failLoad(version, requestedProject, reason instanceof Error ? reason.message : 'Knowledge workspace failed to load');
    }
  }, [applyLoad, beginLoad, failLoad, graphEdgeType, includeDistillationHistory, projectId]);

  useEffect(() => { void load(graphEdgeType); }, [graphEdgeType, load, runtimeAccessKey]);
  useEffect(() => {
    if (workspace?.vault.vault_path) setVaultPath(workspace.vault.vault_path);
  }, [workspace?.vault.vault_path]);
  useEffect(() => {
    if (loading || pendingNavigationTargetId || selectedPage || !pages.length) return undefined;
    const page = selectDefaultKnowledgePage(pages);
    if (!page) return undefined;
    let active = true;
    void fetchKnowledgePage(projectId, page.id)
      .then((detail) => { if (active) setSelectedPage(detail); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Published page failed to load'); });
    return () => { active = false; };
  }, [loading, pages, pendingNavigationTargetId, projectId, selectedPage, setError, setSelectedPage]);
  useEffect(() => {
    if (loading || !pendingNavigationTargetId) return undefined;
    const targetId = pendingNavigationTargetId;
    const source = sources.find((item) => item.id === targetId);
    if (source) {
      setSelectedSource(source); setSelectedSourceTriage(null); setCenterView('page'); setMobilePane('inspector'); clearNavigationTarget();
      return undefined;
    }
    const proposal = proposals.find((item) => item.id === targetId);
    if (proposal) {
      setSelectedProposal(proposal); setCenterView('proposal'); setMobilePane('main'); clearNavigationTarget();
      return undefined;
    }
    const run = runs.find((item) => item.id === targetId);
    if (run) {
      setSelectedRun(run); setCenterView('run'); setMobilePane('main'); clearNavigationTarget();
      return undefined;
    }
    const page = pages.find((item) => item.id === targetId);
    if (page) {
      let active = true;
      void fetchKnowledgePage(projectId, page.id).then((detail) => {
        if (!active) return;
        setSelectedPage(detail); setCenterView('page'); setMobilePane('main'); clearNavigationTarget();
      }).catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : 'Requested Wiki page failed to load'); clearNavigationTarget();
      });
      return () => { active = false; };
    }
    setActionMessage(`The requested operations record (${targetId}) is no longer available in this project.`);
    clearNavigationTarget();
    return undefined;
  }, [clearNavigationTarget, loading, pages, pendingNavigationTargetId, projectId, proposals, runs, setActionMessage, setCenterView, setError, setMobilePane, setSelectedPage, setSelectedProposal, setSelectedRun, setSelectedSource, sources]);
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
      appendRunEvents(projectId, selectedRun.id, incoming);
      lastSequence = Math.max(lastSequence, ...incoming.map((event) => event.sequence));
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
    clearRunEvents();
    void connect();
    return () => { active = false; controller.abort(); };
  }, [appendRunEvents, clearRunEvents, projectId, selectedRun, setError]);

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
  }, [pages, projectId, selectedProposal, setError, setProposalBaselines]);

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
  const setDistillationHistory = (includeHistory: boolean) => {
    setIncludeDistillationHistory(includeHistory);
    if (!includeHistory && selectedDistillation?.distillation.record_type === 'growth' && selectedDistillation.distillation.current === false) {
      setSelectedDistillation(null);
    }
  };
  const inspectSource = (sourceId: string) => {
    const source = sources.find((item) => item.id === sourceId);
    if (!source) return;
    setSelectedSource(source);
    setSelectedSourceTriage(null);
    void fetchKnowledgeSourceTriage(projectId, source.id)
      .then(({ triage }) => setSelectedSourceTriage(triage))
      .catch(() => setSelectedSourceTriage(null));
  };
  const followWikiLink = (path: string) => {
    const normalized = path.endsWith('.md') ? path : `${path}.md`;
    const page = pages.find((item) => item.path === normalized || item.path.endsWith(`/${normalized}`));
    if (page) void inspectPage(page);
    else showMessage(`Linked page ${normalized} is not published in this project.`);
  };

  const runJob = (jobType: string) => withAction(async () => {
    const result = await runKnowledgeJob(projectId, jobType);
    const label = KNOWLEDGE_JOB_OPTIONS.find((option) => option.id === jobType)?.label ?? jobType;
    showMessage(`${label} ${result.status}: ${result.run_id}`);
    await load();
    const persisted = (await fetchKnowledgeRuns(projectId)).runs.find((item) => item.id === result.run_id);
    if (persisted) inspectRun(persisted);
  });
  const promoteSource = (source: KnowledgeSource) => withAction(async () => {
    await transitionKnowledgeSource(projectId, source.id, 'eligible');
    showMessage(`Evidence approved for governed synthesis: ${source.origin || source.id}.`);
    await load();
  });
  const analyzeSource = (source: KnowledgeSource) => withAction(async () => {
    const result = await semanticTriageKnowledgeSource(projectId, source.id);
    setSelectedSourceTriage(result.triage);
    showMessage(`Semantic review recorded: ${result.triage.disposition} / priority ${result.triage.priority}. Approval remains explicit.`);
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
    setSelectedProposal((await fetchKnowledgeProposals(projectId)).proposals.find((item) => item.id === proposal.id) ?? null);
  });
  const saveProposalEvaluationCase = (proposal: KnowledgeProposal, evaluationCase: KnowledgeEvaluationCaseInput) => withAction(async () => {
    await saveKnowledgeEvaluationCase(projectId, evaluationCase);
    showMessage(`Evaluation baseline ${evaluationCase.case_id} saved for this project. Re-run Publish to evaluate this patch.`);
    await load();
    setSelectedProposal((await fetchKnowledgeProposals(projectId)).proposals.find((item) => item.id === proposal.id) ?? proposal);
  });
  const rejectProposal = (proposal: KnowledgeProposal) => withAction(async () => {
    await rejectKnowledgeProposal(projectId, proposal.id);
    showMessage('Proposal rejected without changing published Wiki content.');
    await load();
  });
  const restoreRevision = (revisionId: string) => withAction(async () => {
    if (!selectedPage) return;
    const result = await restoreKnowledgePageRevision(projectId, selectedPage.page.id, revisionId);
    setSelectedProposal(result.proposal);
    setCenterView('proposal');
    showMessage(`Restore proposal created from revision ${revisionId}. Review and publish it through the normal gate.`);
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
  const mapVault = () => withAction(async () => {
    const normalizedPath = vaultPath.trim();
    if (!normalizedPath) throw new Error('A project-relative Vault folder is required.');
    const result = await configureKnowledgeVault(projectId, normalizedPath);
    setVaultPath(result.vault.vault_path || normalizedPath);
    showMessage(`Vault mapped to ${result.vault.vault_path || normalizedPath}. Initialize it before the first sync.`);
    await load();
  });
  const initializeVault = () => withAction(async () => {
    const result = await initializeKnowledgeWorkspace(projectId);
    showMessage(`Knowledge workspace initialized: ${result.created.length} managed files and ${result.created_directories?.length ?? 0} operational folders created.`);
    await load();
    const persisted = (await fetchKnowledgeRuns(projectId)).runs.find((item) => item.id === result.run_id);
    if (persisted) inspectRun(persisted);
  });
  const importFeishuExport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    if (!file) return;
    void withAction(async () => {
      if (file.size > 2_000_000) throw new Error('Feishu export must be 2 MB or smaller. Export one document or meeting summary at a time.');
      let parsed: unknown;
      try {
        parsed = JSON.parse(await file.text());
      } catch {
        throw new Error('The selected file is not valid Feishu export JSON.');
      }
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        throw new Error('The selected file must contain one Feishu document or meeting-summary export.');
      }
      const result = await importFeishuKnowledgeExport(projectId, parsed as FeishuKnowledgeExport);
      setSelectedSource(result.source);
      showMessage(`${result.created ? 'Imported' : 'Matched existing'} Feishu ${result.source.source_type.replace('feishu_', '')} revision ${(result.source.metadata.feishu_revision_id as string) || 'unknown'} into immutable evidence.`);
      await load();
      const persisted = (await fetchKnowledgeRuns(projectId)).runs.find((item) => item.id === result.run_id);
      if (persisted) inspectRun(persisted);
    });
  };
  const registerPluginBridge = () => withAction(async () => {
    const id = pluginId.trim();
    const inputPaths = [...new Set(pluginPaths.split(/[\n,]/).map((path) => path.trim()).filter(Boolean))];
    if (!id || !inputPaths.length) throw new Error('Plugin ID and at least one export folder are required.');
    const existing = workspace?.plugins.plugins.map((plugin) => ({ id: plugin.id, name: plugin.name, adapter: plugin.adapter, input_paths: plugin.input_paths })) ?? [];
    const next = [...existing.filter((plugin) => plugin.id !== id), { id, name: pluginName.trim() || id, adapter: pluginAdapter, input_paths: inputPaths }] satisfies KnowledgePluginBridge[];
    const result = await configureKnowledgePlugins(projectId, next);
    const bridge = result.plugins.find((plugin) => plugin.id === id);
    setPluginPreset('custom');
    setPluginId('');
    setPluginName('');
    setPluginAdapter('filesystem_drop');
    setPluginPaths('00_Inbox/custom');
    showMessage(pluginAdapter === 'filesystem_output'
      ? `${bridge?.name || id} output bridge registered. Run Sync to copy exports into pending D-layer review.`
      : `${bridge?.name || id} bridge registered. Export into ${inputPaths.join(', ')} and run Sync to capture immutable evidence.`);
    await load();
  });
  const selectPluginPreset = (value: string) => {
    setPluginPreset(value);
    const preset = OBSIDIAN_PLUGIN_PRESETS.find((item) => item.id === value);
    if (!preset) return;
    setPluginId(preset.id === 'custom' ? '' : preset.id);
    setPluginName(preset.id === 'custom' ? '' : preset.name);
    setPluginAdapter(preset.adapter);
    setPluginPaths(preset.input_paths.join(', '));
  };
  const editPluginBridge = (plugin: KnowledgeWorkspaceData['plugins']['plugins'][number]) => {
    setPluginPreset('custom');
    setPluginId(plugin.id);
    setPluginName(plugin.name);
    setPluginAdapter(plugin.adapter);
    setPluginPaths(plugin.input_paths.join(', '));
  };
  const removePluginBridge = (id: string) => withAction(async () => {
    const existing = workspace?.plugins.plugins.map((plugin) => ({ id: plugin.id, name: plugin.name, adapter: plugin.adapter, input_paths: plugin.input_paths })) ?? [];
    await configureKnowledgePlugins(projectId, existing.filter((plugin) => plugin.id !== id));
    if (pluginId === id) {
      setPluginPreset('custom');
      setPluginId('');
      setPluginName('');
      setPluginAdapter('filesystem_drop');
      setPluginPaths('00_Inbox/custom');
    }
    showMessage(`Plugin bridge ${id} removed. Existing captured evidence remains immutable and reviewable.`);
    await load();
  });
  const setPluginTrust = (plugin: KnowledgeWorkspaceData['plugins']['plugins'][number], trusted: boolean) => withAction(async () => {
    await setKnowledgePluginTrust(projectId, [plugin.id], trusted, trusted ? 'Approved from the knowledge workspace' : 'Revoked from the knowledge workspace');
    showMessage(trusted
      ? `${plugin.name} is approved for its declared read-only export paths.`
      : `${plugin.name} access is revoked. Existing captured records remain immutable.`);
    await load();
  });

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
  const evalDeltaValues = trend?.evaluations.map((item) => item.score_delta) ?? [];
  const proposalLabels = trend?.proposal_outcomes.map((item) => item.date) ?? [];
  const proposalStatuses = [...new Set((trend?.proposal_outcomes ?? []).flatMap((item) => Object.keys(item.statuses)))].sort();
  const proposalValues = Object.fromEntries(proposalStatuses.map((status) => [
    status,
    (trend?.proposal_outcomes ?? []).map((item) => item.statuses[status] ?? 0),
  ]));
  const showTrendCharts = !isCompactViewport || mobilePane === 'inspector';
  const accessStatus = resolveStudioAccessStatus(runtimeAccessKey, workspace, loading, error);
  const canWrite = accessStatus.verified && (workspace?.access.can_write ?? false);
  const pluginCount = workspace?.plugins.plugins.length ?? 0;
  const connectedPluginCount = workspace?.plugins.plugins.filter((plugin) => plugin.captured_sources > 0 || plugin.registered_outputs > 0).length ?? 0;
  const readyPluginRouteCount = workspace?.plugins.plugins.filter((plugin) => plugin.path_status === 'ready').length ?? 0;
  const pluginRoutesVerified = pluginCount > 0 && readyPluginRouteCount === pluginCount;
  const capturedPluginSources = workspace?.plugins.plugins.reduce((total, plugin) => total + plugin.captured_sources, 0) ?? 0;
  const registeredPluginOutputs = workspace?.plugins.plugins.reduce((total, plugin) => total + plugin.registered_outputs, 0) ?? 0;
  const evaluationDetail = !health ? 'Health unavailable' : health.evaluation.status === 'unavailable' ? 'Evaluation baseline missing' : `Evaluation ${health.evaluation.status}`;
  const vaultConnection = workspace?.vault.connection;
  const vaultConnectionState = vaultConnection?.state ?? (workspace?.vault.configured ? 'mapped_uninitialized' : 'unconfigured');
  const vaultConnectionLabel = VAULT_CONNECTION_LABELS[vaultConnectionState];
  const initialized = vaultConnectionState === 'ready';
  const growth = workspace?.growth;
  const growthSync = growth?.sync;
  const horizon = workspace?.horizon;
  const horizonDetail = !horizon?.enabled
    ? 'Horizon producer is not configured for this runtime'
    : !horizon.last_run
      ? 'No Horizon intelligence has been imported into this project'
      : horizon.last_run.skipped
        ? `Latest run already imported (${horizon.captured_sources} evidence records)`
      : `${horizon.last_run.source_mode === 'run_store' ? 'Native run store' : 'Horizon import'} ${horizon.last_run.status}: ${horizon.last_run.created} new, ${horizon.last_run.duplicates} duplicate (${horizon.captured_sources} evidence records)`;
  const growthCycleDetail = !growth || growth.status === 'not_run'
    ? 'No integrated daily or weekly growth run yet'
    : growthSync
      ? `${growth.status}: ${growthSync.sources.created} evidence captured, ${growthSync.outputs.registered} outputs registered, ${growthSync.triage.eligible}/${growthSync.triage.evaluated} passed triage`
      : `${growth.status}: sync evidence was not recorded`;

  return <section className="knowledge-workspace" aria-label="Knowledge workspace">
    <header className="knowledge-workspace__header">
      <div className="knowledge-workspace__title"><span className="eyebrow"><BookOpen size={14} /> KNOWLEDGE WORKSPACE</span><h2>Evidence, proposals, and growth loops.</h2><p>Project-scoped Wiki maintenance with evidence, gates, and replayable execution.</p></div>
      <div className="knowledge-workspace__actions">
        <label><span>Project</span><input value={projectId} onChange={(event) => setProjectId(event.target.value)} aria-label="Project ID" /></label>
        <span className={`knowledge-runtime-state ${accessStatus.verified ? 'is-ready' : 'is-warning'}`} title={accessStatus.detail}>{accessStatus.label}</span>
        <button onClick={() => void runJob('source_sync')} disabled={actionBusy || !canWrite || workspace?.features.obsidian_sync === false} title={workspace?.features.obsidian_sync === false ? 'Obsidian synchronization is disabled by configuration' : 'Capture user-authored Obsidian material as immutable evidence'}><Download size={15} /> Sync</button>
        <button onClick={() => void runJob('horizon_capture')} disabled={actionBusy || !canWrite || !workspace?.vault.configured || workspace?.features.horizon === false} title="Discover the latest unimported enriched Horizon run and capture its high-scoring items as immutable evidence"><Sparkles size={15} /> Import Horizon</button>
        <input ref={feishuExportInput} className="knowledge-file-input" type="file" accept="application/json,.json" aria-label="Select a Feishu export JSON file" onChange={importFeishuExport} />
        <button onClick={() => feishuExportInput.current?.click()} disabled={actionBusy || !canWrite} title="Import one user-authorized Feishu CLI document or meeting-summary export into immutable evidence"><Upload size={15} /> Import Feishu</button>
        <button onClick={() => void runJob('growth_daily')} disabled={actionBusy || !canWrite || !workspace?.vault.configured} title="Capture declared plugin exports, triage evidence, register output feedback, and write today's governed distillation. Wiki publication remains review-gated."><Sprout size={15} /> Growth cycle</button>
        <button onClick={() => void runJob('wiki_maintenance')} disabled={actionBusy || !canWrite} title="Compile eligible evidence into a reviewable proposal"><WandSparkles size={15} /> Maintain</button>
        <button onClick={() => void load()} disabled={loading} title="Refresh current project state"><RefreshCw size={15} className={loading ? 'spin' : ''} /> Refresh</button>
        <button className="icon-button" onClick={onClose} aria-label="Close knowledge workspace"><X size={18} /></button>
      </div>
    </header>
    {error && <div className="knowledge-workspace__error" role="alert">{error}</div>}
    {actionMessage && <div className="knowledge-action-message" role="status">{actionMessage}</div>}
    {loading && !workspace ? <div className="knowledge-workspace__loading">Loading the project knowledge state...</div> : <>
      <section className="knowledge-vault-setup" aria-label="Project Vault setup">
        <div><span className="eyebrow">PROJECT VAULT</span><h3>{vaultConnectionLabel}</h3><p>{vaultConnection?.message || 'Use a folder inside the configured Obsidian Vault. BSC will only manage this project boundary.'}</p>{vaultConnection?.missing_managed_files?.length ? <small>Missing files: {vaultConnection.missing_managed_files.join(', ')}</small> : null}{vaultConnection?.missing_managed_directories?.length ? <small>Missing workspace layout: {vaultConnection.missing_managed_directories.length} folders, including {vaultConnection.missing_managed_directories.slice(0, 4).join(', ')}{vaultConnection.missing_managed_directories.length > 4 ? ', ...' : ''}</small> : null}</div>
        <div className="knowledge-vault-setup__actions"><label>Vault folder<input value={vaultPath} onChange={(event) => setVaultPath(event.target.value)} placeholder="projects/your-project" aria-label="Project Vault folder" disabled={actionBusy} /></label><button type="button" onClick={() => void mapVault()} disabled={actionBusy || !canWrite || !vaultPath.trim()} title="Map this project to the typed Vault folder"><Link2 size={15} /> {workspace?.vault.configured ? 'Update map' : 'Map Vault'}</button>{workspace?.vault.configured && !initialized && <button type="button" onClick={() => void initializeVault()} disabled={actionBusy || !canWrite} title="Create the full A/B/C/D project layout, rules, and initial Wiki pages"><BookOpen size={15} /> Initialize workspace</button>}</div>
      </section>
      {workspace?.vault.configured && <details className="knowledge-plugin-setup" aria-label="Obsidian plugin export bridge" open={pluginCount === 0}>
        <summary>
          <span className="eyebrow"><Link2 size={14} /> OBSIDIAN PLUGIN EXPORTS</span>
          <strong>{pluginCount} configured</strong>
          <small>{connectedPluginCount ? `${connectedPluginCount} bridge${connectedPluginCount === 1 ? '' : 's'} active` : pluginRoutesVerified ? `${readyPluginRouteCount}/${pluginCount} routes verified; no external export yet` : readyPluginRouteCount ? `${readyPluginRouteCount}/${pluginCount} folders ready; remaining routes need setup` : 'Declare an export bridge'}</small>
        </summary>
        <div><span className="eyebrow">OBSIDIAN PLUGIN EXPORTS</span><h3>Connect exported notes and output feedback.</h3><p>Evidence bridges read only declared <code>00_Inbox/</code>, <code>01_Sources/</code>, <code>raw/</code>, or <code>inbox/</code> folders. Output bridges copy only declared <code>04_Outputs/</code> or <code>outputs/</code> files into pending D-layer review. BSC does not inspect or execute <code>.obsidian</code> plugin code.</p><small>Horizon uses the native radar channel below, not a plugin-folder bridge. Claudian is an Obsidian-to-Codex companion. Markdown formatter and HyperFrames use an output bridge; their files never become reusable context until evaluation and feedback accept them.</small></div>
        <div className="knowledge-plugin-setup__actions">
          <label>Preset<select value={pluginPreset} onChange={(event) => selectPluginPreset(event.target.value)} aria-label="Plugin export preset" disabled={actionBusy}>{OBSIDIAN_PLUGIN_PRESETS.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label>
          <label>Plugin ID<input value={pluginId} onChange={(event) => setPluginId(event.target.value)} placeholder="readwise" aria-label="Plugin ID" disabled={actionBusy} /></label>
          <label>Name<input value={pluginName} onChange={(event) => setPluginName(event.target.value)} placeholder="Readwise Export" aria-label="Plugin display name" disabled={actionBusy} /></label>
          <label>Bridge purpose<select value={pluginAdapter} onChange={(event) => setPluginAdapter(event.target.value as KnowledgePluginBridge['adapter'])} aria-label="Plugin bridge purpose" disabled={actionBusy}><option value="filesystem_drop">Evidence import</option><option value="filesystem_output">Output feedback</option></select></label>
          <label>Export folders<input value={pluginPaths} onChange={(event) => setPluginPaths(event.target.value)} placeholder={pluginAdapter === 'filesystem_output' ? '04_Outputs/articles' : '00_Inbox/web-clipper, 01_Sources/importer'} aria-label="Plugin export folders" disabled={actionBusy} /></label>
          <button type="button" onClick={() => void registerPluginBridge()} disabled={actionBusy || !canWrite || !pluginId.trim() || !pluginPaths.trim()} title="Register a governed filesystem export bridge"><Link2 size={15} /> Register bridge</button>
        </div>
        <PluginBridgeTable plugins={workspace.plugins.plugins} busy={actionBusy} canWrite={canWrite} onEdit={editPluginBridge} onRemove={removePluginBridge} onTrust={setPluginTrust} />
      </details>}
      <section className="knowledge-connection-path" aria-label="Knowledge connection path">
        <ConnectionStep label="Studio access" detail={accessStatus.detail} ready={accessStatus.verified} />
        <ConnectionStep label="Vault boundary" detail={vaultConnectionLabel} ready={vaultConnectionState === 'ready'} />
        <ConnectionStep label="Horizon radar" detail={horizonDetail} ready={Boolean(horizon?.last_run && horizon.last_run.status === 'completed')} />
        <ConnectionStep label="Plugin bridges" detail={pluginCount ? (connectedPluginCount ? `${capturedPluginSources} evidence source${capturedPluginSources === 1 ? '' : 's'}, ${registeredPluginOutputs} pending output${registeredPluginOutputs === 1 ? '' : 's'}` : pluginRoutesVerified ? `${readyPluginRouteCount}/${pluginCount} routes verified; no external plugin export captured yet` : readyPluginRouteCount ? `${readyPluginRouteCount}/${pluginCount} export folders ready; remaining routes need setup` : 'Export folder setup is incomplete') : 'No plugin bridge registered'} ready={pluginRoutesVerified} />
        <ConnectionStep label="Growth cycle" detail={growthCycleDetail} ready={growth?.status === 'completed'} />
        <ConnectionStep label="Governed use" detail={pages.length ? `${pages.length} published Wiki page${pages.length === 1 ? '' : 's'}` : 'No published knowledge context'} ready={pages.length > 0} />
      </section>
      <div className="knowledge-status-strip">
        <StatusMetric icon={<Database size={16} />} label="Evidence" value={workspace?.sources ?? 0} detail={workspace?.vault.configured ? `${vaultConnectionLabel} / direct sync ${workspace.sync.status} / growth ${growth?.status ?? 'not_run'}` : 'Vault unconfigured'} />
        <StatusMetric icon={<GitPullRequest size={16} />} label="Proposals" value={proposals.length} detail={`${health?.pending_proposal_ids.length ?? 0} awaiting review`} />
        <StatusMetric icon={<Network size={16} />} label="Relations" value={graph.count} detail={graphEdgeType || 'all edge types'} />
        <StatusMetric icon={<ShieldCheck size={16} />} label="Citation coverage" value={health?.citation_coverage == null ? 'N/A' : `${Math.round(health.citation_coverage * 100)}%`} detail={evaluationDetail} />
      </div>
      <nav className="knowledge-mobile-tabs" aria-label="Knowledge mobile panes">
        <button className={mobilePane === 'tree' ? 'is-active' : ''} onClick={() => setMobilePane('tree')}>Navigate</button>
        <button className={mobilePane === 'main' ? 'is-active' : ''} onClick={() => setMobilePane('main')}>Workspace</button>
        <button className={mobilePane === 'inspector' ? 'is-active' : ''} onClick={() => setMobilePane('inspector')}>Inspect</button>
      </nav>
      <div className="knowledge-layout" data-mobile-pane={mobilePane}>
        <aside className="knowledge-pane knowledge-pane--tree" aria-label="Vault tree">
          <PaneHeader title="Vault" detail={workspace?.vault.configured ? `${vaultConnectionState} / sync ${workspace.sync.status}` : 'unconfigured'} />
          <div className="knowledge-vault-state"><span className={vaultConnectionState === 'ready' ? 'is-ready' : 'is-warning'}>{vaultConnectionState === 'ready' ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}</span><span>{vaultConnectionLabel}</span></div>
          <div className="knowledge-vault-state"><span className={pluginRoutesVerified ? 'is-ready' : 'is-warning'}>{pluginRoutesVerified ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}</span><span>{pluginCount ? (connectedPluginCount ? `${connectedPluginCount}/${pluginCount} bridge${pluginCount === 1 ? '' : 's'} active: ${capturedPluginSources} evidence source${capturedPluginSources === 1 ? '' : 's'}, ${registeredPluginOutputs} pending output${registeredPluginOutputs === 1 ? '' : 's'}` : pluginRoutesVerified ? `${readyPluginRouteCount}/${pluginCount} bridge routes verified; no external plugin output has been captured yet` : readyPluginRouteCount ? `${readyPluginRouteCount}/${pluginCount} export folders ready; remaining routes need a valid export folder` : `${pluginCount} bridge route${pluginCount === 1 ? '' : 's'} need a valid export folder`) : (workspace?.plugins.configured ? 'Plugin manifest has no supported adapters' : 'No BSC plugin manifest configured')}</span></div>
          <VaultTree pages={pages} selectedPageId={selectedPage?.page.id ?? ''} onSelect={inspectPage} />
          <PaneHeader title="Evidence" detail={`${sources.length} records`} />
          <div className="knowledge-list knowledge-list--tree">{sources.length ? sources.map((source) => <EvidenceRecord source={source} selected={selectedSource?.id === source.id} key={source.id} onSelect={setSelectedSource} />) : <Empty text="No evidence has been captured for this project." />}</div>
          <PaneHeader title="Review queue" detail={`${proposals.length}`} />
          <div className="knowledge-list knowledge-list--tree">{proposals.length ? proposals.map((proposal) => <button className={`knowledge-record ${selectedProposal?.id === proposal.id ? 'is-selected' : ''}`} key={proposal.id} onClick={() => inspectProposal(proposal)}><span className="record-kind">{proposal.status}</span><strong>{proposal.rationale || proposal.id}</strong><small>{proposal.operations.length} operations</small></button>) : <Empty text="No reviewable proposal has been recorded." />}</div>
        </aside>

        <main className="knowledge-pane knowledge-pane--main" aria-label="Knowledge work surface">
          <nav className="knowledge-view-tabs" aria-label="Knowledge views">
            <ViewTab active={centerView === 'page'} onClick={() => setCenterView('page')} icon={<FileText size={14} />} label="Wiki" />
            <ViewTab active={centerView === 'proposal'} onClick={() => setCenterView('proposal')} icon={<GitPullRequest size={14} />} label="Diff" />
            <ViewTab active={centerView === 'run'} onClick={() => setCenterView('run')} icon={<Clock3 size={14} />} label="Runs" />
            <ViewTab active={centerView === 'graph'} onClick={() => setCenterView('graph')} icon={<Network size={14} />} label="Graph" />
            <ViewTab active={centerView === 'intelligence'} onClick={() => setCenterView('intelligence')} icon={<Radio size={14} />} label="Intel" />
            <ViewTab active={centerView === 'distillation'} onClick={() => setCenterView('distillation')} icon={<Sparkles size={14} />} label="Weekly" />
          </nav>
          {centerView === 'page' && <WikiReader page={selectedPage} pages={pages} busy={actionBusy} canWrite={canWrite} onCitation={inspectSource} onWikiLink={followWikiLink} onRestore={restoreRevision} />}
          {centerView === 'proposal' && <ProposalReview proposal={selectedProposal} baselines={proposalBaselines} busy={actionBusy} canWrite={canWrite} onLint={lintProposal} onPublish={publishProposal} onReject={rejectProposal} onSaveEvaluationCase={saveProposalEvaluationCase} />}
          {centerView === 'run' && <RunTimeline runs={runs} selectedRun={selectedRun} events={runEvents} busy={actionBusy} onSelect={inspectRun} onRetry={retryRun} />}
          {centerView === 'graph' && <section className="knowledge-graph-view">
            <header className="knowledge-content-header"><div><span className="eyebrow">RELATIONSHIP GRAPH</span><h3>Traceable knowledge relations</h3></div><div className="knowledge-graph-filters"><label className="knowledge-select-label">Edge filter<select value={graphEdgeType} onChange={(event) => setGraphEdgeType(event.target.value)}><option value="">All edges</option>{graphTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label className="knowledge-select-label">Node type<select value={graphNodeType} onChange={(event) => setGraphNodeType(event.target.value)}><option value="">All types</option>{graphNodeTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label className="knowledge-select-label">Node status<select value={graphNodeStatus} onChange={(event) => setGraphNodeStatus(event.target.value)}><option value="">All states</option>{graphNodeStatuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label></div></header>
            <div className="knowledge-graph-canvas">{flowNodes.length ? <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              fitView
              nodesDraggable={false}
              nodesConnectable={false}
              onNodeClick={(_, node) => {
                const record = node.data.record;
                if (record.node_type === 'source') inspectSource(record.id);
                if (record.node_type === 'page') { const page = pages.find((item) => item.id === record.id); if (page) void inspectPage(page); }
                if (record.node_type === 'proposal') { const proposal = proposals.find((item) => item.id === record.id); if (proposal) inspectProposal(proposal); }
              }}
              onEdgeClick={(_, edge) => {
                const target = graph.nodes.find((record) => record.id === edge.target);
                if (!target) return;
                if (target.node_type === 'source') inspectSource(target.id);
                if (target.node_type === 'page') { const page = pages.find((item) => item.id === target.id); if (page) void inspectPage(page); }
                if (target.node_type === 'proposal') { const proposal = proposals.find((item) => item.id === target.id); if (proposal) inspectProposal(proposal); }
              }}
            ><Background gap={22} size={1} /><Controls showInteractive={false} /></ReactFlow> : <Empty text="No persisted relationships match the selected graph filters." />}</div>
            {(graph.truncated || filteredGraphNodes.length > maxNodes) && <p className="knowledge-limit-note">Showing a bounded relationship slice ({flowNodes.length} nodes / {graph.edges.length} of {graph.total} edges). Narrow the filters to inspect another slice.</p>}
          </section>}
          {centerView === 'intelligence' && <InformationOperationsPanel projectId={projectId} canWrite={canWrite} refreshToken={evidenceRefreshVersion} />}
          {centerView === 'distillation' && <DistillationReader records={distillations} selected={selectedDistillation} onSelect={inspectDistillation} includeHistory={includeDistillationHistory} onIncludeHistoryChange={setDistillationHistory} />}
        </main>

        <aside className="knowledge-pane knowledge-pane--inspector" aria-label="Evidence and health inspector">
          <PaneHeader title="Source inspector" detail={selectedSource?.status || 'select evidence'} />
          {selectedSource ? <SourceInspector source={selectedSource} triage={selectedSourceTriage} busy={actionBusy} canWrite={canWrite} onApprove={promoteSource} onAnalyze={analyzeSource} /> : <Empty text="Select evidence to inspect immutable provenance, policy state, and capture metadata." />}
          <PaneHeader title="Automation" detail={`${schedules.length} schedules`} />
          <div className="knowledge-list">{schedules.length ? schedules.map((schedule) => <div className="knowledge-schedule" key={schedule.id}><div><strong>{schedule.job_type}</strong><small>{schedule.cron} / {schedule.timezone}</small><small>{schedule.enabled ? `Next ${formatTimestamp(schedule.next_run_at)}` : schedule.scheduler_available ? 'Paused' : 'Scheduler unavailable; manual execution only'}</small><small>Last result: {schedule.last_result ? `${schedule.last_result.status} / ${formatTimestamp(schedule.last_result.updated_at)}` : 'not run'}</small></div><div className="knowledge-schedule__actions"><button className="icon-button" disabled={actionBusy || !canWrite} title={`Run ${schedule.job_type} now`} aria-label={`Run ${schedule.job_type} now`} onClick={() => void runJob(schedule.job_type)}><Play size={14} /></button><button className="icon-button" disabled={actionBusy || !canWrite || !schedule.scheduler_available} title={schedule.enabled ? 'Pause schedule' : 'Enable schedule'} aria-label={schedule.enabled ? 'Pause schedule' : 'Enable schedule'} onClick={() => void toggleSchedule(schedule)}>{schedule.enabled ? <Pause size={14} /> : <Clock3 size={14} />}</button></div></div>) : <Empty text={workspace?.scheduler.available ? 'No schedules configured for this project.' : 'Durable scheduling is unavailable. Manual governed runs remain available.'} />}</div>
          <form className="knowledge-schedule-form" onSubmit={createSchedule}><label>Job<select value={scheduleJobType} onChange={(event) => { const selected = KNOWLEDGE_JOB_OPTIONS.find((option) => option.id === event.target.value); setScheduleJobType(event.target.value); if (selected) setScheduleCron(selected.defaultCron); }} disabled={workspace?.features.schedules === false}>{KNOWLEDGE_JOB_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label><label>Cron<input value={scheduleCron} onChange={(event) => setScheduleCron(event.target.value)} aria-label="Schedule cron" disabled={workspace?.features.schedules === false} /></label><button disabled={actionBusy || !canWrite || workspace?.features.schedules === false} type="submit"><Clock3 size={14} /> Save cadence</button></form>
          <PaneHeader title="Knowledge health" detail={health?.status || 'unavailable'} />
          <HealthInspector health={health} />
          <PaneHeader title="Observed trends" detail="persisted records only" />
          {showTrendCharts && <><section className="knowledge-chart"><Suspense fallback={<Empty text="Loading source trend..." />}><TrendChart option={trendOption('Sources captured', sourceLabels, sourceValues, '#64d5a9')} style={{ height: 180 }} notMerge lazyUpdate /></Suspense></section><section className="knowledge-chart"><Suspense fallback={<Empty text="Loading proposal trend..." />}><TrendChart option={proposalTrendOption(proposalLabels, proposalValues)} style={{ height: 180 }} notMerge lazyUpdate /></Suspense></section><section className="knowledge-chart"><Suspense fallback={<Empty text="Loading evaluation trend..." />}><TrendChart option={trendOption('Evaluation score', evalLabels, evalValues, '#88b9ff', true)} style={{ height: 180 }} notMerge lazyUpdate /></Suspense></section><section className="knowledge-chart"><Suspense fallback={<Empty text="Loading evaluation delta..." />}><TrendChart option={trendOption('Evaluation delta', evalLabels, evalDeltaValues, '#e8ba62')} style={{ height: 180 }} notMerge lazyUpdate /></Suspense></section>{health && <section className="knowledge-chart"><Suspense fallback={<Empty text="Loading knowledge debt..." />}><TrendChart option={qualityDebtOption(health)} style={{ height: 180 }} notMerge lazyUpdate /></Suspense></section>}</>}
        </aside>
      </div>
    </>}
  </section>;
}

function PaneHeader({ title, detail }: { title: string; detail: string }) { return <header className="knowledge-pane-header"><span>{title}</span><small>{detail}</small></header>; }
function Empty({ text }: { text: string }) { return <p className="knowledge-empty">{text}</p>; }
function ViewTab({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) { return <button className={active ? 'is-active' : ''} onClick={onClick}>{icon}{label}</button>; }
function StatusMetric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: number | string; detail: string }) { return <div className="knowledge-status-metric"><span>{icon}</span><div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div></div>; }
function ConnectionStep({ label, detail, ready }: { label: string; detail: string; ready: boolean }) { return <div className={ready ? 'is-ready' : 'is-pending'}><span>{ready ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}</span><div><strong>{label}</strong><small>{detail}</small></div></div>; }
function pluginRuntimeDetail(plugin: KnowledgeWorkspaceData['plugins']['plugins'][number]): string {
  switch (plugin.runtime_configuration?.state) {
    case 'configured': return 'Plugin destination matches this governed bridge.';
    case 'interactive_destination': return 'Choose this declared folder in the plugin import dialog before importing.';
    case 'mismatch': return 'Plugin destination differs from this bridge; correct the plugin setting before Sync.';
    case 'unavailable': return 'Plugin settings could not be verified from the Vault.';
    case 'unverified': return 'Plugin settings cannot be checked until the Vault is available.';
    default: return 'No settings probe is defined; BSC will read only the declared export folder.';
  }
}
function PluginBridgeTable({ plugins, busy, canWrite, onEdit, onRemove, onTrust }: { plugins: KnowledgeWorkspaceData['plugins']['plugins']; busy: boolean; canWrite: boolean; onEdit: (plugin: KnowledgeWorkspaceData['plugins']['plugins'][number]) => void; onRemove: (id: string) => void; onTrust: (plugin: KnowledgeWorkspaceData['plugins']['plugins'][number], trusted: boolean) => void }) {
  if (!plugins.length) return <p className="knowledge-plugin-empty">No plugin export bridge is registered. A bridge is only considered connected after Sync captures an exported source.</p>;
  return <div className="knowledge-plugin-table" role="list" aria-label="Registered plugin export bridges">{plugins.map((plugin) => {
    const outputBridge = plugin.adapter === 'filesystem_output';
    const trusted = plugin.trust_state === 'trusted';
    const connected = trusted && (outputBridge ? plugin.status === 'registered_output' : plugin.status === 'captured');
    const count = outputBridge ? plugin.registered_outputs : plugin.captured_sources;
    const timestamp = outputBridge ? plugin.last_registered_at : plugin.last_captured_at;
    const pathReady = plugin.path_status === 'ready';
    const detectedFiles = plugin.export_observation?.file_count ?? 0;
    const filesAwaitingSync = plugin.capture_state === 'files_detected_pending_capture' || plugin.capture_state === 'files_detected_pending_registration';
    const waitingLabel = !trusted ? (plugin.trust_state === 'configuration_changed' ? 'bridge changed; trust again' : plugin.trust_state === 'unavailable' ? 'trust record unavailable' : 'awaiting read approval') : filesAwaitingSync ? `${detectedFiles} file${detectedFiles === 1 ? '' : 's'} detected; Sync pending` : pathReady ? (outputBridge ? 'bridge online; no output file yet' : 'bridge online; no external file yet') : plugin.path_status === 'missing' ? 'export folder missing' : 'folder unavailable';
    const waitingDetail = !trusted ? 'BSC will not read this declared path until the exact configuration is approved.' : filesAwaitingSync ? `${pluginRuntimeDetail(plugin)} The next Sync run will register the detected file without changing its original content.` : pathReady ? `${pluginRuntimeDetail(plugin)} This route is ready; a Sync run will capture the first external file automatically.` : `Folder status: ${plugin.path_status}`;
    return <div key={plugin.id} role="listitem"><div><strong>{plugin.name}</strong><small>{plugin.id} / {outputBridge ? 'output feedback' : 'evidence import'} / {plugin.input_paths.join(', ')}</small></div><span className={connected ? 'is-ready' : 'is-pending'}>{connected ? (outputBridge ? `${count} pending output${count === 1 ? '' : 's'}` : `${count} captured`) : waitingLabel}</span><small>{timestamp ? `Last ${formatTimestamp(timestamp)}` : waitingDetail}</small><div className="knowledge-plugin-table__actions"><button type="button" className="icon-button" disabled={busy || !canWrite} title={trusted ? `Revoke ${plugin.name} read approval` : `Approve ${plugin.name} declared paths`} aria-label={trusted ? `Revoke ${plugin.name} read approval` : `Approve ${plugin.name} declared paths`} onClick={() => void onTrust(plugin, !trusted)}>{trusted ? <ShieldCheck size={14} /> : <ShieldCheck size={14} />}</button><button type="button" className="icon-button" disabled={busy || !canWrite} title={`Edit ${plugin.name} bridge`} aria-label={`Edit ${plugin.name} bridge`} onClick={() => onEdit(plugin)}><Pencil size={14} /></button><button type="button" className="icon-button is-danger" disabled={busy || !canWrite} title={`Remove ${plugin.name} bridge`} aria-label={`Remove ${plugin.name} bridge`} onClick={() => void onRemove(plugin.id)}><Trash2 size={14} /></button></div></div>;
  })}</div>;
}

function VaultTree({ pages, selectedPageId, onSelect }: { pages: KnowledgePage[]; selectedPageId: string; onSelect: (page: KnowledgePage) => void }) {
  const grouped = new Map<string, KnowledgePage[]>();
  for (const page of pages) { const folder = page.path.split('/').slice(0, -1).join('/') || 'wiki'; grouped.set(folder, [...(grouped.get(folder) || []), page]); }
  if (!pages.length) return <Empty text="Published Wiki pages will appear here after a gated proposal is accepted." />;
  return <nav className="knowledge-vault-tree">{[...grouped.entries()].map(([folder, children]) => <section key={folder}><p><ChevronRight size={12} />{folder}</p>{children.map((page) => <button key={page.id} className={selectedPageId === page.id ? 'is-selected' : ''} onClick={() => onSelect(page)}><FileText size={13} />{page.title}</button>)}</section>)}</nav>;
}

export function WikiReader({ page, pages, busy, canWrite, onCitation, onWikiLink, onRestore }: { page: KnowledgePageDetail | null; pages: KnowledgePage[]; busy: boolean; canWrite: boolean; onCitation: (id: string) => void; onWikiLink: (path: string) => void; onRestore: (revisionId: string) => void }) {
  if (!page) return <section className="knowledge-reader-empty"><BookOpen size={26} /><h3>Choose a published page</h3><p>The reader displays stored Markdown, revision metadata, citations, and safe internal page links.</p></section>;
  return <section className="knowledge-reader-view"><header className="knowledge-content-header"><div><span className="eyebrow">PUBLISHED WIKI</span><h3>{page.page.title}</h3><p>{page.page.path} / revision {page.page.version}</p></div><span className="record-kind">{page.page.page_kind}</span></header><SafeMarkdown content={page.content} pages={pages} onCitation={onCitation} onWikiLink={onWikiLink} /><section className="knowledge-citations"><h4><Link2 size={14} /> Citations</h4>{page.citations.length ? page.citations.map((citation) => <button key={`${citation.source_id}-${citation.claim_text}`} onClick={() => onCitation(citation.source_id)}><span>[source:{citation.source_id}]</span>{citation.claim_text || citation.anchor || 'Open source provenance'}</button>) : <Empty text="This page has no active source citations." />}</section><section className="knowledge-backlinks"><h4><Network size={14} /> Backlinks</h4>{page.backlinks.length ? page.backlinks.map((backlink) => { const sourcePage = pages.find((candidate) => candidate.id === backlink.from_id); return <button key={backlink.id} disabled={!sourcePage} onClick={() => sourcePage && onWikiLink(sourcePage.path)}>{sourcePage?.title || backlink.from_id}</button>; }) : <Empty text="No published page links here yet." />}</section><section className="knowledge-revisions"><h4><RotateCcw size={14} /> Revision history</h4>{page.revisions.map((revision) => <div key={revision.id}><span>v{revision.version} / {formatTimestamp(revision.created_at)}</span><button disabled={busy || !canWrite || revision.version === page.page.version || page.page.path === 'wiki/log.md'} onClick={() => onRestore(revision.id)}>Restore as proposal</button></div>)}</section></section>;
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

export function ProposalReview({ proposal, baselines, busy, canWrite, onLint, onPublish, onReject, onSaveEvaluationCase }: {
  proposal: KnowledgeProposal | null;
  baselines: KnowledgeProposalBaselines;
  busy: boolean;
  canWrite: boolean;
  onLint: (proposal: KnowledgeProposal) => void;
  onPublish: (proposal: KnowledgeProposal) => void;
  onReject: (proposal: KnowledgeProposal) => void;
  onSaveEvaluationCase?: (proposal: KnowledgeProposal, evaluationCase: KnowledgeEvaluationCaseInput) => void;
}) {
  const [evaluationCaseId, setEvaluationCaseId] = useState('');
  const [evaluationType, setEvaluationType] = useState<KnowledgeEvaluationCaseInput['case_type']>('content');
  const [evaluationConstraints, setEvaluationConstraints] = useState('');
  const [evaluationSourceIds, setEvaluationSourceIds] = useState('');
  const [requireCitations, setRequireCitations] = useState(true);
  const proposalId = proposal?.id || '';
  const proposalSourceIds = proposal?.source_ids.join(', ') || '';
  useEffect(() => {
    setEvaluationCaseId(proposalId ? `${proposalId}-content` : '');
    setEvaluationType('content');
    setEvaluationConstraints('');
    setEvaluationSourceIds(proposalSourceIds);
    setRequireCitations(true);
  }, [proposalId, proposalSourceIds]);
  if (!proposal) return <section className="knowledge-reader-empty"><GitPullRequest size={26} /><h3>Select a proposal</h3><p>Review each persisted operation against its current page body before asking the governed publication gate to apply it.</p></section>;
  const canAct = canWrite && ['draft', 'failed'].includes(proposal.status);
  const saveBaseline = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!onSaveEvaluationCase) return;
    const constraints = evaluationConstraints.split('\n').map((item) => item.trim()).filter(Boolean);
    const sourceIds = evaluationSourceIds.split(',').map((item) => item.trim()).filter(Boolean);
    const expected = evaluationType === 'content' || evaluationType === 'sop'
      ? { constraints, require_citations: requireCitations }
      : { source_ids: sourceIds };
    onSaveEvaluationCase(proposal, { case_id: evaluationCaseId.trim(), case_type: evaluationType, expected });
  };
  return <section className="proposal-review">
    <header className="knowledge-content-header"><div><span className="eyebrow">GOVERNED PATCH</span><h3>{proposal.rationale || proposal.id}</h3><p>{proposal.source_ids.length} evidence references / {proposal.operations.length} operations</p></div><span className="record-kind">{proposal.status}</span></header>
    <div className="proposal-actions"><button disabled={busy || !canAct} onClick={() => onLint(proposal)}><Search size={14} /> Lint</button><button disabled={busy || !canAct} onClick={() => onPublish(proposal)}><ShieldCheck size={14} /> Validate &amp; publish</button><button className="is-danger" disabled={busy || !canAct} onClick={() => onReject(proposal)}><X size={14} /> Reject</button></div>
    {onSaveEvaluationCase && <form className="proposal-evaluation-form" onSubmit={saveBaseline}>
      <header><span className="eyebrow">PROJECT EVALUATION BASELINE</span><small>Persisted rules are applied by the publication gate.</small></header>
      <label>Case ID<input value={evaluationCaseId} onChange={(event) => setEvaluationCaseId(event.target.value)} aria-label="Evaluation case ID" required disabled={busy || !canWrite} /></label>
      <label>Evaluation type<select value={evaluationType} onChange={(event) => setEvaluationType(event.target.value as KnowledgeEvaluationCaseInput['case_type'])} aria-label="Evaluation case type" disabled={busy || !canWrite}><option value="content">Content</option><option value="sop">SOP</option><option value="citation">Citation</option><option value="retrieval">Retrieval</option></select></label>
      {evaluationType === 'content' || evaluationType === 'sop' ? <><label>Required project constraints<textarea value={evaluationConstraints} onChange={(event) => setEvaluationConstraints(event.target.value)} aria-label="Required project constraints" placeholder="One testable phrase per line" disabled={busy || !canWrite} /></label><label className="knowledge-check"><input type="checkbox" checked={requireCitations} onChange={(event) => setRequireCitations(event.target.checked)} disabled={busy || !canWrite} /> Require source citations</label></> : <label>Expected source IDs<input value={evaluationSourceIds} onChange={(event) => setEvaluationSourceIds(event.target.value)} aria-label="Expected source IDs" placeholder="source-a, source-b" required disabled={busy || !canWrite} /></label>}
      <button type="submit" disabled={busy || !canWrite || !evaluationCaseId.trim()}><CheckCircle2 size={14} /> Save evaluation baseline</button>
    </form>}
    <div className="proposal-operations">{proposal.operations.map((operation) => { const before = baselines[operation.path] ?? ''; const after = operation.operation === 'append' ? `${before}${operation.content}` : operation.operation === 'archive' ? '' : operation.content; return <article key={operation.id}><header><span>{operation.operation}</span><strong>{operation.path}</strong>{operation.destination_path && <small>to {operation.destination_path}</small>}</header><div className="proposal-diff"><pre><small>Before</small>{before || '(new page or no stored revision)'}</pre><pre><small>After</small>{after || '(archived)'}</pre></div><p>Evidence: {operation.source_ids.length ? operation.source_ids.join(', ') : 'manual operation; no immutable source claim'}</p></article>; })}</div>
  </section>;
}

function RunTimeline({ runs, selectedRun, events, busy, onSelect, onRetry }: { runs: KnowledgeRun[]; selectedRun: KnowledgeRun | null; events: KnowledgeRunEvent[]; busy: boolean; onSelect: (run: KnowledgeRun) => void; onRetry: (run: KnowledgeRun) => void }) {
  return <section className="run-timeline"><header className="knowledge-content-header"><div><span className="eyebrow">RUN LEDGER</span><h3>{selectedRun ? selectedRun.run_type : 'Select a governed run'}</h3><p>{selectedRun ? `${selectedRun.status} / ${selectedRun.trigger}` : 'Runs remain durable even after an SSE reconnect.'}</p></div>{selectedRun && <span className={`run-status run-status--${selectedRun.status}`}>{selectedRun.status}</span>}</header><div className="run-timeline__body"><nav>{runs.length ? runs.map((run) => <button key={run.id} className={selectedRun?.id === run.id ? 'is-selected' : ''} onClick={() => onSelect(run)}><span>{run.status}</span><strong>{run.run_type}</strong><small>{formatTimestamp(run.created_at)}</small></button>) : <Empty text="No governed knowledge run has been recorded yet." />}</nav><section>{selectedRun ? <><div className="run-summary"><p><strong>Trigger:</strong> {selectedRun.trigger}</p>{selectedRun.retry_of && <p><strong>Retry of:</strong> {selectedRun.retry_of}</p>}{selectedRun.error && <p className="run-error"><strong>Error:</strong> {selectedRun.error}</p>}{['failed', 'unavailable', 'cancelled'].includes(selectedRun.status) && <button disabled={busy} onClick={() => onRetry(selectedRun)}><RotateCcw size={14} /> Retry through the normal pipeline</button>}</div><ol className="run-events">{events.length ? events.map((event) => <li key={event.id}><span>{event.sequence}</span><div><strong>{event.event_type}</strong><small>{formatTimestamp(event.created_at)}</small><code>{Object.keys(event.payload).length ? JSON.stringify(event.payload) : 'No event payload'}</code></div></li>) : <Empty text="This run has no persisted events yet." />}</ol></> : <Empty text="Select a run to inspect its durable ordered events." />}</section></div></section>;
}

export function DistillationReader({ records, selected, onSelect, includeHistory = false, onIncludeHistoryChange }: { records: WeeklyDistillation[]; selected: WeeklyDistillationDetail | null; onSelect: (item: WeeklyDistillation) => void; includeHistory?: boolean; onIncludeHistoryChange?: (includeHistory: boolean) => void }) {
  const documentEntries = selected ? Object.entries(selected.documents) : [];
  const selectedPeriod = selected?.distillation.period || selected?.distillation.week;
  return <section className="distillation-reader"><header className="knowledge-content-header"><div><span className="eyebrow">KNOWLEDGE DISTILLATION</span><h3>{selectedPeriod || 'Choose a governed bundle'}</h3><p>{selected ? `${selected.distillation.kind || 'weekly'} / source cutoff ${selected.distillation.source_cutoff}` : 'Daily and weekly bundles are generated from governed project evidence.'}</p></div><div className="distillation-reader__header-actions"><label className="distillation-history-toggle"><input type="checkbox" checked={includeHistory} onChange={(event) => onIncludeHistoryChange?.(event.target.checked)} disabled={!onIncludeHistoryChange} /> Revision history</label><FileClock size={20} /></div></header><div className="distillation-reader__body"><nav>{records.length ? records.map((item) => <button key={item.id} className={selected?.distillation.id === item.id ? 'is-selected' : ''} onClick={() => onSelect(item)}><span>{item.kind || 'weekly'} / {item.status}{item.current === false ? ' / historical' : ''}</span><strong>{item.period || item.week}</strong><small>{formatTimestamp(item.created_at)}{(item.revision_count ?? 1) > 1 ? ` / ${item.revision_count} revisions` : ''}</small></button>) : <Empty text="No source-backed knowledge distillation has been generated." />}</nav><section>{documentEntries.length ? documentEntries.map(([path, content]) => <article key={path}><h4>{path.split('/').at(-1)}</h4><pre>{content}</pre></article>) : <Empty text="Select a bundle to read its stored evidence-backed documents." />}</section></div></section>;
}

export function EvidenceRecord({ source, selected, onSelect }: { source: KnowledgeSource; selected: boolean; onSelect: (source: KnowledgeSource) => void }) {
  const presentation = describeKnowledgeSource(source);
  return <button className={`knowledge-record knowledge-record--source ${selected ? 'is-selected' : ''}`} onClick={() => onSelect(source)} title={presentation.origin}>
    <span className={`source-status source-status--${source.status}`}>{source.status}</span>
    <span className="knowledge-record__body"><strong>{presentation.headline}</strong><small>{presentation.provenance}</small></span>
    {presentation.score && <span className="knowledge-signal-score" aria-label={`Signal score ${presentation.score}`}>{presentation.score}</span>}
  </button>;
}

export function SourceInspector({
  source,
  triage = null,
  busy,
  canWrite,
  onApprove,
  onAnalyze,
}: {
  source: KnowledgeSource;
  triage?: KnowledgeSourceTriage | null;
  busy: boolean;
  canWrite: boolean;
  onApprove: (source: KnowledgeSource) => void;
  onAnalyze?: (source: KnowledgeSource) => void;
}) {
  const presentation = describeKnowledgeSource(source);
  const curated = Boolean(source.metadata.curated || source.metadata.user_annotation || source.metadata.annotation);
  const pluginName = typeof source.metadata.plugin_name === 'string' ? source.metadata.plugin_name : source.metadata.obsidian_plugin;
  return <section className="source-inspector"><span className={`source-status source-status--${source.status}`}>{source.status}</span><h3>{presentation.headline}</h3><p className="source-inspector__provenance">{presentation.provenance}{presentation.score ? ` / signal ${presentation.score}` : ''}</p><dl><div><dt>Type</dt><dd>{presentation.typeLabel}</dd></div>{pluginName ? <div><dt>Plugin export</dt><dd>{String(pluginName)}</dd></div> : null}<div><dt>Origin</dt><dd>{presentation.origin}</dd></div><div><dt>Trust</dt><dd>{source.trust_level}</dd></div><div><dt>Captured</dt><dd>{formatTimestamp(source.captured_at)}</dd></div><div><dt>SHA-256</dt><dd>{source.content_hash}</dd></div><div><dt>Vault path</dt><dd>{source.vault_path || 'external or API import'}</dd></div><div><dt>Interpretation</dt><dd>{curated ? 'Curated opinion or user annotation' : 'Immutable evidence record'}</dd></div></dl>{triage && <div className="source-triage"><h4>Project fit review</h4><dl><div><dt>Recommendation</dt><dd>{triage.disposition} / priority {triage.priority}</dd></div><div><dt>Reliability gate</dt><dd>{triage.reliability_pass ? 'passed' : 'not passed'}</dd></div><div><dt>Evaluator</dt><dd>{triage.evaluator_revision} / {triage.evaluator_status}</dd></div><div><dt>Scores</dt><dd>R {triage.relevance} V {triage.value} F {triage.freshness} O {triage.outputability} C {triage.connectedness}</dd></div></dl><ul>{triage.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></div>}{source.supersedes_id && <p className="source-supersedes">Supersedes source {source.supersedes_id}</p>}{source.status === 'validated' && <div className="source-inspector__actions">{onAnalyze && <button disabled={busy || !canWrite} onClick={() => onAnalyze(source)} title="Use the configured model to record a project-specific recommendation without changing source status"><Sparkles size={14} /> Analyze semantic fit</button>}<button disabled={busy || !canWrite} onClick={() => onApprove(source)}><CheckCircle2 size={14} /> Approve for synthesis</button></div>}</section>;
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

function qualityDebtOption(health: KnowledgeHealth) {
  const labels = ['Stale pages', 'Orphan pages', 'Dangling citations', 'Stale citations', 'Uncited evidence'];
  const values = [health.stale_page_ids.length, health.orphan_page_ids.length, health.dangling_citation_count, health.stale_citation_count, health.uncited_eligible_source_ids.length];
  return { animation: false, title: { text: 'Current knowledge debt', textStyle: { color: '#b9c9d9', fontSize: 11, fontWeight: 500 } }, tooltip: { trigger: 'axis' }, grid: { top: 34, right: 12, bottom: 48, left: 32 }, xAxis: { type: 'category', data: labels, axisLabel: { color: '#8093a5', fontSize: 9, rotate: 25 }, axisLine: { lineStyle: { color: '#2e4051' } } }, yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#8093a5', fontSize: 10 }, splitLine: { lineStyle: { color: '#1b2935' } } }, series: [{ type: 'bar', data: values, itemStyle: { color: '#e78787' }, barMaxWidth: 28 }] };
}

function formatTimestamp(value: string | undefined) { if (!value) return 'Not recorded'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }

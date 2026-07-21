import { create } from 'zustand';

import type {
  KnowledgeGraph,
  KnowledgeHealth,
  KnowledgeHealthTrend,
  KnowledgePage,
  KnowledgePageDetail,
  KnowledgeProposal,
  KnowledgeRun,
  KnowledgeRunEvent,
  KnowledgeSchedule,
  KnowledgeSource,
  KnowledgeWorkspaceData,
  WeeklyDistillation,
  WeeklyDistillationDetail,
} from '../api/knowledgeWorkspaceApi';

export type KnowledgeCenterView = 'page' | 'proposal' | 'run' | 'graph' | 'distillation';
export type KnowledgeMobilePane = 'tree' | 'main' | 'inspector';
export type KnowledgeProposalBaselines = Record<string, string>;

export type KnowledgeSnapshot = {
  workspace: KnowledgeWorkspaceData;
  sources: KnowledgeSource[];
  runs: KnowledgeRun[];
  schedules: KnowledgeSchedule[];
  graph: KnowledgeGraph;
  proposals: KnowledgeProposal[];
  pages: KnowledgePage[];
  distillations: WeeklyDistillation[];
  health: KnowledgeHealth;
  trend: KnowledgeHealthTrend;
};

type KnowledgeWorkspaceState = {
  projectId: string;
  workspace: KnowledgeWorkspaceData | null;
  sources: KnowledgeSource[];
  runs: KnowledgeRun[];
  schedules: KnowledgeSchedule[];
  graph: KnowledgeGraph;
  proposals: KnowledgeProposal[];
  pages: KnowledgePage[];
  distillations: WeeklyDistillation[];
  health: KnowledgeHealth | null;
  trend: KnowledgeHealthTrend | null;
  selectedPage: KnowledgePageDetail | null;
  selectedSource: KnowledgeSource | null;
  selectedProposal: KnowledgeProposal | null;
  selectedRun: KnowledgeRun | null;
  selectedDistillation: WeeklyDistillationDetail | null;
  proposalBaselines: KnowledgeProposalBaselines;
  runEvents: KnowledgeRunEvent[];
  centerView: KnowledgeCenterView;
  mobilePane: KnowledgeMobilePane;
  graphEdgeType: string;
  graphNodeType: string;
  graphNodeStatus: string;
  error: string;
  actionMessage: string;
  loading: boolean;
  actionBusy: boolean;
  requestEpoch: number;
  setProjectId: (projectId: string) => void;
  beginLoad: (projectId: string) => number;
  applyLoad: (epoch: number, projectId: string, snapshot: KnowledgeSnapshot) => boolean;
  failLoad: (epoch: number, projectId: string, message: string) => void;
  setSelectedPage: (page: KnowledgePageDetail | null) => void;
  setSelectedSource: (source: KnowledgeSource | null) => void;
  setSelectedProposal: (proposal: KnowledgeProposal | null) => void;
  setSelectedRun: (run: KnowledgeRun | null) => void;
  setSelectedDistillation: (distillation: WeeklyDistillationDetail | null) => void;
  setProposalBaselines: (baselines: KnowledgeProposalBaselines) => void;
  clearRunEvents: () => void;
  appendRunEvents: (projectId: string, runId: string, events: KnowledgeRunEvent[]) => void;
  setCenterView: (view: KnowledgeCenterView) => void;
  setMobilePane: (pane: KnowledgeMobilePane) => void;
  setGraphEdgeType: (value: string) => void;
  setGraphNodeType: (value: string) => void;
  setGraphNodeStatus: (value: string) => void;
  setError: (value: string) => void;
  setActionMessage: (value: string) => void;
  setActionBusy: (value: boolean) => void;
};

const emptyGraph: KnowledgeGraph = {
  nodes: [],
  edges: [],
  count: 0,
  total: 0,
  limit: 500,
  offset: 0,
  truncated: false,
};

export const useKnowledgeWorkspaceStore = create<KnowledgeWorkspaceState>((set, get) => ({
  projectId: 'default',
  workspace: null,
  sources: [],
  runs: [],
  schedules: [],
  graph: emptyGraph,
  proposals: [],
  pages: [],
  distillations: [],
  health: null,
  trend: null,
  selectedPage: null,
  selectedSource: null,
  selectedProposal: null,
  selectedRun: null,
  selectedDistillation: null,
  proposalBaselines: {},
  runEvents: [],
  centerView: 'page',
  mobilePane: 'main',
  graphEdgeType: '',
  graphNodeType: '',
  graphNodeStatus: '',
  error: '',
  actionMessage: '',
  loading: true,
  actionBusy: false,
  requestEpoch: 0,
  setProjectId: (projectId) => set((state) => ({
    projectId,
    requestEpoch: state.requestEpoch + 1,
    workspace: null,
    selectedPage: null,
    selectedSource: null,
    selectedProposal: null,
    selectedRun: null,
    selectedDistillation: null,
    proposalBaselines: {},
    runEvents: [],
    error: '',
  })),
  beginLoad: (projectId) => {
    if (get().projectId !== projectId) return get().requestEpoch;
    const epoch = get().requestEpoch + 1;
    set({ requestEpoch: epoch, loading: true, error: '' });
    return epoch;
  },
  applyLoad: (epoch, projectId, snapshot) => {
    const current = get();
    if (current.requestEpoch !== epoch || current.projectId !== projectId) return false;
    set({ ...snapshot, loading: false });
    return true;
  },
  failLoad: (epoch, projectId, message) => {
    const current = get();
    if (current.requestEpoch === epoch && current.projectId === projectId) set({ error: message, loading: false });
  },
  setSelectedPage: (selectedPage) => set({ selectedPage }),
  setSelectedSource: (selectedSource) => set({ selectedSource }),
  setSelectedProposal: (selectedProposal) => set({ selectedProposal }),
  setSelectedRun: (selectedRun) => set({ selectedRun, runEvents: [] }),
  setSelectedDistillation: (selectedDistillation) => set({ selectedDistillation }),
  setProposalBaselines: (proposalBaselines) => set({ proposalBaselines }),
  clearRunEvents: () => set({ runEvents: [] }),
  appendRunEvents: (projectId, runId, events) => set((state) => {
    if (state.projectId !== projectId || state.selectedRun?.id !== runId) return state;
    const priorLast = state.runEvents.at(-1)?.sequence ?? 0;
    const accepted = events
      .filter((event) => event.project_id === projectId && event.run_id === runId && event.sequence > priorLast)
      .sort((left, right) => left.sequence - right.sequence);
    const unique = accepted.filter((event, index) => index === 0 || event.sequence !== accepted[index - 1].sequence);
    if (!unique.length) return state;
    const terminal = [...unique].reverse().find((event) => event.event_type.startsWith('knowledge.run.') && ['completed', 'failed', 'cancelled', 'unavailable'].includes(String(event.payload.status || event.event_type.split('.').at(-1))));
    const terminalStatus = terminal ? String(terminal.payload.status || terminal.event_type.split('.').at(-1)) : '';
    const statusChanged = Boolean(terminalStatus && state.selectedRun?.status !== terminalStatus);
    const selectedRun = statusChanged ? { ...state.selectedRun, status: terminalStatus } : state.selectedRun;
    const runs = statusChanged
      ? state.runs.map((run) => run.id === runId && run.status !== terminalStatus ? { ...run, status: terminalStatus } : run)
      : state.runs;
    return { runEvents: [...state.runEvents, ...unique], selectedRun, runs };
  }),
  setCenterView: (centerView) => set({ centerView }),
  setMobilePane: (mobilePane) => set({ mobilePane }),
  setGraphEdgeType: (graphEdgeType) => set({ graphEdgeType }),
  setGraphNodeType: (graphNodeType) => set({ graphNodeType }),
  setGraphNodeStatus: (graphNodeStatus) => set({ graphNodeStatus }),
  setError: (error) => set({ error }),
  setActionMessage: (actionMessage) => set({ actionMessage }),
  setActionBusy: (actionBusy) => set({ actionBusy }),
}));

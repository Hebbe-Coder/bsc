import { create } from 'zustand';
import type { DashboardData } from '../api/compilerDashboardApi';
import type { OrchestratorEvent } from '../api/orchestrateApi';
import { appendOrderedTerminalEvent } from './terminalEventReducer';

export type TerminalEvent = OrchestratorEvent;

interface WorkspaceState {
  sessionId: string | null;
  idea: string;
  project: Record<string, unknown>;
  requirements: unknown[];
  businessModel: DashboardData['business_model'];
  sop: DashboardData['sop'];
  review: Record<string, unknown>;
  presentation: Record<string, unknown>;
  risk: DashboardData['risk'];
  stages: Record<string, string>;
  log: { stage: string; msg: string }[];
  terminalEvents: TerminalEvent[];
  eventSeqBySession: Record<string, number>;
  set: (patch: Partial<WorkspaceState>) => void;
  beginSession: (sessionId: string, idea: string) => void;
  pushLog: (stage: string, msg: string) => void;
  appendEvent: (event: TerminalEvent) => void;
  clearTerminal: () => void;
  setStage: (stage: string, status: string) => void;
  applyDashboard: (dashboard: DashboardData) => void;
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  sessionId: null,
  idea: '',
  project: {},
  requirements: [],
  businessModel: {},
  sop: {
    sops: [],
    _citation_coverage: { coverage: 0, covered: 0, total: 0, flagged: [] },
  },
  review: {},
  presentation: {},
  risk: {
    overall_score: null,
    gate: { decision: 'PENDING', reason: '' },
    coverage: { total: 0, covered: 0, coverage_pct: 0, uncovered_ids: [] },
    risks: [],
  },
  stages: {},
  log: [],
  terminalEvents: [],
  eventSeqBySession: {},
  set: (patch) => set(patch),
  beginSession: (sessionId, idea) => set({
    sessionId,
    idea,
    terminalEvents: [],
    eventSeqBySession: { [sessionId]: 0 },
  }),
  pushLog: (stage, msg) => set((state) => ({
    log: [...state.log.slice(-299), { stage, msg }],
  })),
  appendEvent: (event) => set((state) => {
    const next = appendOrderedTerminalEvent({
      activeSessionId: state.sessionId,
      events: state.terminalEvents,
      seqBySession: state.eventSeqBySession,
    }, event);
    if (next.events === state.terminalEvents) return state;
    return {
      terminalEvents: next.events,
      eventSeqBySession: next.seqBySession,
    };
  }),
  clearTerminal: () => set({
    terminalEvents: [],
    eventSeqBySession: {},
  }),
  setStage: (stage, status) => set((state) => ({
    stages: { ...state.stages, [stage]: status },
  })),
  applyDashboard: (dashboard) => set({
    businessModel: dashboard.business_model,
    sop: dashboard.sop,
    risk: dashboard.risk,
  }),
}));

import { create } from 'zustand';
import type { DashboardData } from '../api/compilerDashboardApi';

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
  set: (patch: Partial<WorkspaceState>) => void;
  pushLog: (stage: string, msg: string) => void;
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
  set: (patch) => set(patch),
  pushLog: (stage, msg) => set((state) => ({
    log: [...state.log, { stage, msg }],
  })),
  setStage: (stage, status) => set((state) => ({
    stages: { ...state.stages, [stage]: status },
  })),
  applyDashboard: (dashboard) => set({
    businessModel: dashboard.business_model,
    sop: dashboard.sop,
    risk: dashboard.risk,
  }),
}));

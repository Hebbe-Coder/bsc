import { create } from "zustand";

export const useWorkspace = create<{
  sessionId: string | null;
  idea: string;
  project: any; requirements: any[]; businessModel: any; sop: any; review: any; presentation: any; risk: any;
  stages: Record<string, string>;   // planner|architect|sop|reviewer|presenter -> pending|running|done|loopback
  log: { stage: string; msg: string }[];
  set: (p: Partial<any>) => void;
  pushLog: (stage: string, msg: string) => void;
  setStage: (stage: string, status: string) => void;
}>(set => ({
  sessionId: null, idea: "", project: {}, requirements: [], businessModel: {}, sop: {}, review: {}, presentation: {}, risk: {},
  stages: {}, log: [],
  set: (p) => set(p),
  pushLog: (stage, msg) => set(s => ({ log: [...s.log, { stage, msg }] })),
  setStage: (stage, status) => set(s => ({ stages: { ...s.stages, [stage]: status } })),
}));

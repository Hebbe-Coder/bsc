import type { OrchestratorEvent } from '../api/orchestrateApi';

export interface TerminalEventState {
  activeSessionId: string | null;
  events: OrchestratorEvent[];
  seqBySession: Record<string, number>;
}

export function appendOrderedTerminalEvent(
  state: TerminalEventState,
  event: OrchestratorEvent,
  limit = 500,
): TerminalEventState {
  if (state.activeSessionId !== event.session_id) return state;
  const lastSeq = state.seqBySession[event.session_id] ?? 0;
  if (event.seq <= lastSeq) return state;

  return {
    activeSessionId: state.activeSessionId,
    events: [...state.events.slice(-(limit - 1)), event],
    seqBySession: {
      ...state.seqBySession,
      [event.session_id]: event.seq,
    },
  };
}

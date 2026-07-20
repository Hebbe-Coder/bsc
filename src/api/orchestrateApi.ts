export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface StartOrchestrateResponse {
  session_id: string;
  status: JobStatus;
  status_url: string;
  events_url: string;
}

export interface OrchestratorEvent {
  session_id: string;
  seq: number;
  type:
    | 'pipeline.started'
    | 'stage.started'
    | 'stage.completed'
    | 'stage.loopback'
    | 'pipeline.completed'
    | 'pipeline.failed'
    | 'pipeline.cancelled';
  stage: string;
  status: string;
  message: string;
  terminal: boolean;
  timestamp: string;
  data: Record<string, unknown>;
}

export async function startOrchestrate(
  idea: string,
): Promise<StartOrchestrateResponse> {
  const response = await apiFetch('/api/orchestrate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idea }),
  });
  if (!response.ok) {
    throw new Error(`orchestrate failed: ${response.status}`);
  }
  return response.json() as Promise<StartOrchestrateResponse>;
}

export async function cancelOrchestrate(sessionId: string): Promise<void> {
  const response = await apiFetch(
    `/api/orchestrate/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    throw new Error(`cancel failed: ${response.status}`);
  }
}

export function subscribeStream(
  response: StartOrchestrateResponse | string,
  onEvent: (event: OrchestratorEvent) => void,
  onTransportError: () => void = () => undefined,
): EventSource {
  const url = typeof response === 'string'
    ? `/api/orchestrate/stream?session_id=${encodeURIComponent(response)}`
    : response.events_url;
  const source = new EventSource(url, { withCredentials: true });
  const eventTypes: OrchestratorEvent['type'][] = [
    'pipeline.started',
    'stage.started',
    'stage.completed',
    'stage.loopback',
    'pipeline.completed',
    'pipeline.failed',
    'pipeline.cancelled',
  ];
  const handle = (raw: MessageEvent<string>) => {
    onEvent(JSON.parse(raw.data) as OrchestratorEvent);
  };
  eventTypes.forEach((type) => source.addEventListener(type, handle as EventListener));
  source.onerror = onTransportError;
  return source;
}
import { apiFetch } from './fetchWrapper';

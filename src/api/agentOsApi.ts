import { fetchWrapper } from './fetchWrapper';
import { AGENT_OS_TIMEOUT } from '../config';
import type { AgentAnalysisResponse, AgentOSRequest } from './generated/agentOsContracts';

export type { AgentAnalysisResponse, AgentOSRequest } from './generated/agentOsContracts';

export interface AgentHealth {
  status: string;
  version: string;
  architecture: string;
  capabilities: number;
  llm_ready: boolean;
  endpoints: { analyze: string; health: string };
}

export async function getHealth(): Promise<AgentHealth> {
  return fetchWrapper.fetch<AgentHealth>('/agent/health');
}

export async function runAnalysis(req: AgentOSRequest): Promise<AgentAnalysisResponse> {
  return fetchWrapper.fetch<AgentAnalysisResponse>('/agent/analyze', {
    method: 'POST',
    timeout: AGENT_OS_TIMEOUT,
    body: JSON.stringify({
      input: req.input,
      mode: req.mode || 'llm',
      domain: req.domain || '',
      project_id: req.project_id || '',
      board: req.board || false,
    }),
  });
}

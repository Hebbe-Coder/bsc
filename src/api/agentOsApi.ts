import { fetchWrapper } from './fetchWrapper';

export interface AgentHealth {
  status: string;
  version: string;
  architecture: string;
  capabilities: number;
  llm_ready: boolean;
  endpoints: { analyze: string; health: string };
}

export interface AgentAnalysisRequest {
  input: string;
  mode?: string;
  domain?: string;
  board?: boolean;
}

export interface MissionInfo {
  title: string;
  steps: number;
  mode: string;
}

export interface GapDetail {
  description: string;
  category: string;
  severity: string;
}

export interface AgentAnalysisResponse {
  status: string;
  mission: MissionInfo;
  artifacts: number;
  gaps: number;
  gap_details: GapDetail[];
  board_verdict: string;
  board_consensus: string;
  board_votes?: Record<string, string>;
  report: Record<string, any>;
}

export async function getHealth(): Promise<AgentHealth> {
  return fetchWrapper.fetch<AgentHealth>('/agent/health');
}

export async function runAnalysis(req: AgentAnalysisRequest): Promise<AgentAnalysisResponse> {
  return fetchWrapper.fetch<AgentAnalysisResponse>('/agent/analyze', {
    method: 'POST',
    body: JSON.stringify({
      input: req.input,
      mode: req.mode || 'llm',
      domain: req.domain || '',
      board: req.board || false,
    }),
  });
}

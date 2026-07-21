import { useEffect, useState } from 'react';
import { useWorkspace } from '../store/workspaceStore';
import { fetchCompilerDashboard, type DashboardData } from '../api/compilerDashboardApi';
import { runAnalysis, type AgentAnalysisResponse } from '../api/agentOsApi';
import { adaptAgentOsToDashboard } from '../utils/agentOsAdapter';
import { RiskPanel } from './RiskPanel';
import { ConstraintCoveragePanel } from './ConstraintCoveragePanel';
import { CitationPanel } from './CitationPanel';
import { TrustedAuditPanel } from './TrustedAuditPanel';
import { CompilerEvalPanel } from './CompilerEvalPanel';
import { EvolutionPanel } from './EvolutionPanel';

type DashboardMode = 'orchestrator' | 'agent-os';

interface Props {
  mode?: DashboardMode;
  agentOsResponse?: AgentAnalysisResponse;
}

export function MethodologyDashboard({ mode = 'orchestrator', agentOsResponse }: Props) {
  const sessionId = useWorkspace((s) => s.sessionId);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (mode === 'agent-os' && agentOsResponse) {
      try {
        const adapted = adaptAgentOsToDashboard(agentOsResponse);
        setData(adapted);
        setError(null);
      } catch (e: any) {
        setError(e.message || 'Adaptation failed');
      }
      return;
    }

    if (mode === 'orchestrator') {
      if (!sessionId) { setData(null); return; }
      let cancelled = false;
      setLoading(true); setError(null);
      fetchCompilerDashboard(sessionId)
        .then((d) => { if (!cancelled) setData(d); })
        .catch((e) => { if (!cancelled) setError(e.message || 'Load failed'); })
        .finally(() => { if (!cancelled) setLoading(false); });
      return () => { cancelled = true; };
    }
  }, [sessionId, mode, agentOsResponse]);

  if (mode === 'orchestrator' && !sessionId) {
    return (
      <div className='flex h-full items-center justify-center p-8 text-center text-sm text-slate-400'>
        Run a compilation first in the Workbench, then come here to view the dashboard.
      </div>
    );
  }
  if (mode === 'agent-os' && !agentOsResponse) {
    return (
      <div className='flex h-full items-center justify-center p-8 text-center text-sm text-slate-400'>
        No Agent OS data yet. Enter a business idea above and click Analyze.
      </div>
    );
  }
  if (loading) return <div className='p-8 text-sm text-slate-400'>Loading...</div>;
  if (error) return <div className='p-8 text-sm text-red-500'>{error}</div>;
  if (!data) return <div className='p-8 text-sm text-slate-400'>No data</div>;

  return (
    <div className='h-full overflow-auto p-4'>
      <div className='mx-auto grid max-w-5xl gap-4 md:grid-cols-2'>
        <div className='md:col-span-2'>
          <RiskPanel risk={data.risk} />
        </div>
        <ConstraintCoveragePanel coverage={data.risk.coverage} />
        <CitationPanel sop={data.sop} />
        {data.trusted_audit && (
          <div className='md:col-span-2'>
            <TrustedAuditPanel trustedAudit={data.trusted_audit} />
          </div>
        )}
        {data.evaluation && (
          <div className='md:col-span-2'>
            <CompilerEvalPanel evaluation={data.evaluation} coverage={data.risk.coverage} />
          </div>
        )}
        {data.evolution && (
          <div className='md:col-span-2'>
            <EvolutionPanel evolution={data.evolution} />
          </div>
        )}
      </div>
    </div>
  );
}

export function AgentOsDashboard() {
  const [agentOsData, setAgentOsData] = useState<AgentAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<'llm' | 'mock'>('llm');
  const [withBoard, setWithBoard] = useState(false);

  const handleAnalyze = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await runAnalysis({
        input: input.trim(),
        mode,
        board: withBoard,
      });
      setAgentOsData(result);
    } catch (e: any) {
      setError(e.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className='flex h-full flex-col'>
      <div className='border-b border-slate-200 bg-white px-4 py-3'>
        <div className='mx-auto flex max-w-3xl gap-2'>
          <input
            type='text'
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
            placeholder='Enter your business idea or PRD...'
            className='flex-1 rounded-lg border border-slate-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500'
            disabled={loading}
          />
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as 'llm' | 'mock')}
            className='rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none'
          >
            <option value='llm'>LLM (DeepSeek)</option>
            <option value='mock'>Mock</option>
          </select>
          <label className='flex items-center gap-1 text-sm text-slate-600'>
            <input type='checkbox' checked={withBoard} onChange={(e) => setWithBoard(e.target.checked)} />
            Board
          </label>
          <button
            type='button'
            onClick={handleAnalyze}
            disabled={loading || !input.trim()}
            className='rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition'
          >
            {loading ? 'Analyzing...' : 'Analyze'}
          </button>
        </div>
      </div>
      <div className='flex-1 overflow-auto'>
        {error && (
          <div className='mx-auto max-w-3xl mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>
            {error}
          </div>
        )}
        <MethodologyDashboard mode='agent-os' agentOsResponse={agentOsData || undefined} />
      </div>
    </div>
  );
}

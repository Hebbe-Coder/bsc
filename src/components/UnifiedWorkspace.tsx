import { useState, useEffect, useRef, useCallback } from 'react';
import { useWorkspace } from '../store/workspaceStore';
import {
  cancelOrchestrate,
  startOrchestrate,
  subscribeStream,
  type OrchestratorEvent,
} from '../api/orchestrateApi';
import { runAnalysis, type AgentAnalysisResponse } from '../api/agentOsApi';
import { adaptAgentOsToDashboard } from '../utils/agentOsAdapter';
import { fetchCompilerDashboard, type DashboardData } from '../api/compilerDashboardApi';
import { RiskPanel } from './RiskPanel';
import { ConstraintCoveragePanel } from './ConstraintCoveragePanel';
import { CitationPanel } from './CitationPanel';
import { TrustedAuditPanel } from './TrustedAuditPanel';
import { CompilerEvalPanel } from './CompilerEvalPanel';
import { EvolutionPanel } from './EvolutionPanel';
import { BusinessGraph } from './BusinessGraph';
import { SopPanel } from './SopPanel';
import PipelineProgress from './PipelineProgress';

// ---- Types ----
type Mode = 'auto' | 'analyze' | 'compile' | 'board';
type LogType = 'system' | 'agent' | 'tool' | 'error' | 'result' | 'thinking' | 'stage';
interface LogEntry { id: string; type: LogType; text: string; time: string; }
type EffectiveMode = 'analyze' | 'compile' | 'board';

// ---- Auto-detect ----
function detectMode(input: string): { mode: EffectiveMode; confidence: number; reason: string } {
  const text = input.toLowerCase(); const len = input.length;
  const boardSignals = ['board', '??', '??', 'ceo', 'cfo', 'cto', 'board review', 'multi-agent', '???'];
  const compileSignals = ['prd', '????', '????', 'compile', '??', 'sop', '????', 'pipeline', '????', '????', '???', '## ', '??', '??', '???'];
  const analyzeSignals = ['??', '??', '??', '??', '????', '??', '??', '??', 'analyze', 'gap', 'coverage', 'assumption', 'risk', '???', 'how', 'what', 'strategy'];
  const boardHits = boardSignals.filter(s => text.includes(s.toLowerCase())).length;
  const compileHits = compileSignals.filter(s => text.includes(s.toLowerCase())).length;
  const analyzeHits = analyzeSignals.filter(s => text.includes(s.toLowerCase())).length;
  if (len > 500 && compileHits >= 2) return { mode: 'compile', confidence: 0.85, reason: 'Long structured document with PRD signals' };
  if (boardHits >= 2) return { mode: 'board', confidence: 0.9, reason: 'Explicit board/multi-agent review request' };
  if (boardHits === 1 && len < 200) return { mode: 'board', confidence: 0.7, reason: 'Board review signal detected' };
  if (compileHits >= 3) return { mode: 'compile', confidence: 0.85, reason: 'Strong compile/PRD signals detected' };
  if (compileHits >= 1 && len > 300) return { mode: 'compile', confidence: 0.7, reason: 'Structured content with compile signals' };
  if (analyzeHits >= 1) return { mode: 'analyze', confidence: 0.8, reason: 'Analysis/evaluation question detected' };
  if (len > 400) return { mode: 'compile', confidence: 0.55, reason: 'Long content, defaulting to compile' };
  return { mode: 'analyze', confidence: 0.6, reason: 'Default analysis mode' };
}

// ---- Constants ----
const MODE_LABELS: Record<Mode, string> = { auto: 'Auto', analyze: 'Agent OS', compile: 'Compiler', board: 'Board' };
const MODE_HINTS: Record<EffectiveMode, string> = {
  analyze: 'Deep LLM analysis: assumptions, risks, gaps, coverage',
  compile: 'Real-time pipeline: PRD \u2192 Business Model \u2192 Risk \u2192 SOP \u2192 KPI \u2192 Review',
  board: 'Multi-agent board review with CEO, CFO, CTO perspectives',
};
const LOG_COLORS: Record<LogType, string> = {
  system: 'text-[#8b949e]', agent: 'text-[#58a6ff]', tool: 'text-[#d29922]',
  error: 'text-[#f85149]', result: 'text-[#3fb950]', thinking: 'text-[#a371f7]',
  stage: 'text-[#58a6ff]',
};
let logCounter = 0;

// ---- Pipeline stages (in order) ----
const PIPELINE_STAGES = ['planner', 'architect', 'sop', 'risk', 'reviewer', 'presenter'];

export function UnifiedWorkspace() {
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<Mode>('auto');
  const [detectedMode, setDetectedMode] = useState<EffectiveMode | null>(null);
  const [detectReason, setDetectReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [dashData, setDashData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const [pipelineStages, setPipelineStages] = useState<Record<string, string>>({});
  const logEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Workspace store
  const workspaceSet = useWorkspace((s) => s.set);
  const applyDashboard = useWorkspace((s) => s.applyDashboard);
  const businessModel = useWorkspace((s) => s.businessModel);
  const sop = useWorkspace((s) => s.sop);

  const addLog = useCallback((type: LogType, text: string) => {
    const entry: LogEntry = { id: String(++logCounter), type, text, time: new Date().toLocaleTimeString('en-US', { hour12: false }) };
    setLogs(prev => [...prev.slice(-300), entry]);
  }, []);

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  // Keyboard shortcut
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); inputRef.current?.focus(); } };
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h);
  }, []);

  // Auto-detect on input change
  useEffect(() => {
    if (mode === 'auto' && input.trim()) {
      const d = detectMode(input); setDetectedMode(d.mode); setDetectReason(d.reason);
    }
  }, [input, mode]);

  const effectiveMode: EffectiveMode = mode === 'auto' ? (detectedMode || 'analyze') : (mode as EffectiveMode);

  // ---- Submit Handler ----
  const handleSubmit = async () => {
    if (!input.trim() || loading) return;
    const value = input.trim();
    setInput(''); setLoading(true); setError(null); setDashData(null); setLogs([]);
    logCounter = 0; setPipelineStages({});

    addLog('system', 'Mode: ' + MODE_LABELS[effectiveMode] + (mode === 'auto' ? ' (auto)' : ''));
    addLog('system', 'Input: ' + (value.length > 80 ? value.slice(0, 80) + '...' : value));

    try {
      if (effectiveMode === 'compile') {
        // ---- Real-time Pipeline Compilation ----
        setCompiling(true);
        addLog('agent', 'Starting compiler pipeline...');
        const res = await startOrchestrate(value);
        workspaceSet({ sessionId: res.session_id, idea: value });
        setSessionId(res.session_id);
        addLog('system', 'Session ' + res.session_id.slice(0, 8));

        let source: EventSource | null = null;
        source = subscribeStream(
          res,
          (event: OrchestratorEvent) => {
            const status = event.status === 'done'
              ? 'completed'
              : (event.status || 'running');
            setPipelineStages((previous) => ({
              ...previous,
              [event.stage]: status,
            }));
            addLog(
              'stage',
              `[${event.stage}] ${event.type}${event.message ? `: ${event.message}` : ''}`,
            );

            if (!event.terminal) return;
            source?.close();
            setCompiling(false);

            if (event.type === 'pipeline.completed') {
              void fetchCompilerDashboard(res.session_id)
                .then((dashboard) => {
                  applyDashboard(dashboard);
                  setDashData(dashboard);
                  if (dashboard.execution?.degraded) {
                    addLog('error', 'Completed with degraded LLM fallback output');
                  }
                  addLog('result', 'Pipeline completed');
                })
                .catch((dashboardError: unknown) => {
                  const message = dashboardError instanceof Error
                    ? dashboardError.message
                    : 'Dashboard request failed';
                  setError(message);
                  addLog('error', message);
                })
                .finally(() => setLoading(false));
              return;
            }

            const message = event.message || `Pipeline ended with ${event.status}`;
            setError(message);
            addLog('error', message);
            setLoading(false);
          },
          () => {
            addLog('system', 'Event stream disconnected; browser will retry');
          },
        );

      } else {
        // ---- Agent OS / Board ----
        const isBoard = effectiveMode === 'board';
        addLog('thinking', isBoard ? 'Convening board: CEO, CFO, CTO, Ops...' : 'Planning mission capabilities...');
        const result = await runAnalysis({ input: value, mode: 'llm', board: isBoard });
        setSessionId(result.execution_id);
        addLog('agent', 'Mission: ' + result.mission.title);
        addLog('system', 'Steps: ' + result.mission.steps + ' | Mode: ' + result.mission.mode);
        if (result.artifacts > 0) addLog('result', 'Artifacts: ' + result.artifacts);
        if (result.gaps > 0) {
          addLog('tool', 'Gaps: ' + result.gaps);
          result.gap_details.forEach(g => addLog('tool', '[' + g.severity.toUpperCase() + '] ' + g.category + ': ' + g.description));
        }
        if (result.runtime.degraded) {
          addLog('error', 'Analysis completed with degraded LLM fallback output');
        }
        if (result.board_verdict) {
          addLog('result', 'Verdict: ' + result.board_verdict.toUpperCase());
          if (result.board_consensus) addLog('agent', 'Consensus: ' + result.board_consensus);
        }
        setDashData(adaptAgentOsToDashboard(result));
        addLog('result', 'Analysis complete');
        setLoading(false);
      }
    } catch (e: any) {
      addLog('error', e.message || 'Failed');
      setError(e.message || 'Analysis failed');
      setCompiling(false);
      setLoading(false);
    }
  };

  const statusColor = loading ? 'status-dot--running' : error ? 'status-dot--error' : 'status-dot--active';
  const statusLabel = loading ? (compiling ? 'Compiling' : 'Running') : error ? 'Error' : 'Ready';

  return (
    <div className='flex h-full flex-col bg-[var(--bg-primary)] text-[var(--text-primary)]' role='application' aria-label='BSC Studio'>
      {/* Header */}
      <header className='flex items-center gap-3 border-b border-[var(--border-default)] px-4 py-2.5 bg-[var(--bg-secondary)]'>
        <span className='text-sm font-bold tracking-tight gradient-text'>BSC Studio</span>
        <span className='hidden sm:inline text-[11px] text-[var(--text-muted)] font-medium uppercase tracking-wider'>Business Agent OS</span>
        <div className='ml-auto flex items-center gap-3'>
          <div className='flex items-center gap-2 text-xs text-[var(--text-muted)]'>
            <span className={'status-dot ' + statusColor}></span><span>{statusLabel}</span>
          </div>
          {sessionId && <span className='text-[10px] text-[var(--text-placeholder)] font-mono'>{sessionId.slice(0,8)}</span>}
        </div>
      </header>

      {/* Input Bar */}
      <div className='border-b border-[var(--border-default)] bg-[var(--bg-secondary)] px-4 py-3'>
        <div className='flex gap-2'>
          <div className='flex rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] overflow-hidden shrink-0' role='radiogroup'>
            {(['auto', 'analyze', 'compile', 'board'] as Mode[]).map(m => (
              <button key={m} role='radio' aria-checked={mode === m} onClick={() => setMode(m)}
                className={'px-3 py-1.5 text-xs font-medium transition-colors duration-150 ' + (mode === m ? 'bg-[var(--accent-blue)] text-white' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]')}>
                {m === 'auto' && detectedMode ? MODE_LABELS[detectedMode] + ' \u2192' : MODE_LABELS[m]}
              </button>
            ))}
          </div>
          <input ref={inputRef} type='text' value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); } }}
            placeholder='Describe your business idea, PRD, or strategic question...'
            className='flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-4 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-placeholder)] focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)] focus:outline-none disabled:opacity-50 transition-colors duration-150'
            disabled={loading} aria-label='Business analysis input' />
          <button onClick={handleSubmit} disabled={loading || !input.trim()}
            className='shrink-0 rounded-lg bg-[var(--status-success)] px-5 py-2 text-sm font-semibold text-white hover:bg-[#2ea043] active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150'
            aria-label={loading ? 'Running' : 'Submit'}>
            {loading ? <span className='flex items-center gap-1.5'><span className='inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin-slow'></span>Running</span> : 'Run \u21B5'}
          </button>
        </div>
        <div className='mt-1.5 flex items-center gap-3 text-[11px] text-[var(--text-placeholder)]'>
          <span>{mode === 'auto' && detectedMode ? 'Auto \u2192 ' + MODE_LABELS[detectedMode] + ': ' + detectReason : MODE_HINTS[effectiveMode]}</span>
          <span className='ml-auto hidden sm:block'><kbd className='px-1 py-0.5 rounded bg-[var(--bg-tertiary)] border border-[var(--border-default)] text-[10px]'>Ctrl+K</kbd> focus</span>
        </div>
      </div>

      {/* Main Content */}
      <div className='flex flex-1 overflow-hidden'>
        {/* Activity Log */}
        <aside className='w-[40%] min-w-[300px] border-r border-[var(--border-default)] flex flex-col bg-[var(--bg-primary)]' aria-label='Activity log'>
          <div className='flex items-center justify-between border-b border-[var(--border-default)] px-4 py-2'>
            <span className='text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider'>Activity</span>
            {logs.length > 0 && <span className='text-[10px] text-[var(--text-placeholder)]'>{logs.length} entries</span>}
          </div>
          <div className='flex-1 overflow-auto p-3' role='log' aria-live='polite'>
            {logs.length === 0 && !loading && (
              <div className='flex flex-col items-center justify-center h-full text-center px-4'>
                <div className='text-3xl mb-3 opacity-20'>{'\u25B6'}</div>
                <p className='text-sm text-[var(--text-muted)] font-medium'>Start your analysis</p>
                <p className='text-xs text-[var(--text-placeholder)] mt-1 max-w-[240px]'>Enter a business idea above and press Enter</p>
              </div>
            )}
            <div className='space-y-0.5'>
              {logs.map(entry => (
                <div key={entry.id} className='log-entry' style={{ animationDelay: '0ms' }}>
                  <span className='text-[var(--text-placeholder)] shrink-0 w-14 text-right select-none font-mono text-[11px]'>{entry.time}</span>
                  <span className={LOG_COLORS[entry.type] + ' break-words'}>{entry.text}</span>
                </div>
              ))}
            </div>
            {loading && (
              <div className='log-entry' style={{ opacity: 1 }}>
                <span className='text-[var(--text-placeholder)] shrink-0 w-14 text-right select-none font-mono text-[11px]'>{new Date().toLocaleTimeString('en-US', { hour12: false })}</span>
                <span className='text-[var(--accent-purple)] animate-pulse'>{compiling ? 'Pipeline running...' : 'Thinking\u2026'}</span>
              </div>
            )}
            <div ref={logEndRef} />
          </div>
        </aside>

        {/* Results Panel */}
        <main className='flex-1 overflow-auto p-4' aria-label='Results'>
          {/* Error */}
          {error && !dashData && (
            <div className='bento-card border-[var(--status-error)]/30 bg-[var(--status-error)]/5 mb-4' role='alert'>
              <div className='flex items-start gap-3'>
                <span className='text-[var(--accent-red)] text-lg'>{'\u26A0'}</span>
                <div><h3 className='text-sm font-semibold text-[var(--accent-red)]'>Error</h3><p className='text-xs text-[var(--text-secondary)] mt-1 font-mono'>{error}</p></div>
              </div>
            </div>
          )}

          {/* Loading Skeleton */}
          {loading && !dashData && (
            <div className='space-y-4 max-w-4xl mx-auto'>
              {compiling && (
                <div className='bento-card'>
                  <h3 className='text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3'>Pipeline Progress</h3>
                  <PipelineProgress
                    stages={PIPELINE_STAGES.map(s => ({
                      id: s,
                      name: s.charAt(0).toUpperCase() + s.slice(1),
                      description: '',
                      status: (pipelineStages[s] || 'pending') as any,
                      progress: pipelineStages[s] === 'completed' ? 100 : pipelineStages[s] === 'running' ? 50 : 0
                    }))}
                    isCompiling={compiling}
                    onCancel={() => {
                      if (!sessionId) return;
                      addLog('system', 'Cancellation requested');
                      void cancelOrchestrate(sessionId).catch((cancelError: unknown) => {
                        const message = cancelError instanceof Error
                          ? cancelError.message
                          : 'Cancellation request failed';
                        setError(message);
                        addLog('error', message);
                      });
                    }}
                    onReset={() => { setPipelineStages({}); }}
                  />
                </div>
              )}
              <div className='skeleton h-48 rounded-lg'></div>
              <div className='grid grid-cols-2 gap-4'>
                <div className='skeleton h-32 rounded-lg'></div>
                <div className='skeleton h-32 rounded-lg'></div>
              </div>
            </div>
          )}

          {/* Empty State */}
          {!loading && !error && !dashData && (
            <div className='flex flex-col items-center justify-center h-full text-center px-4'>
              <div className='w-16 h-16 rounded-2xl bg-[var(--bg-tertiary)] border border-[var(--border-default)] flex items-center justify-center mb-4'>
                <span className='text-2xl opacity-30'>{'\u25A3'}</span>
              </div>
              <h2 className='text-sm font-semibold text-[var(--text-muted)]'>Results Panel</h2>
              <p className='text-xs text-[var(--text-placeholder)] mt-1 max-w-[300px]'>
                {effectiveMode === 'compile'
                  ? 'Pipeline progress, Business Graph, and SOP will appear here during compilation'
                  : 'Risk matrix, coverage analysis, and board review will appear here after analysis'}
              </p>
            </div>
          )}

          {/* Results */}
          {dashData && (
            <div className='space-y-4 max-w-4xl mx-auto animate-fade-in-up'>
              <div className='bento-card flex items-center gap-4 flex-wrap'>
                <span className='text-sm font-semibold'>{dashData.risk.gate.decision}</span>
                <span className='text-[var(--border-default)]'>|</span>
                <span className='text-xs text-[var(--text-muted)]'>Risks: <strong className='text-[var(--text-secondary)]'>{dashData.risk.risks.length}</strong></span>
                <span className='text-xs text-[var(--text-muted)]'>Coverage: <strong className='text-[var(--accent-blue)]'>{dashData.risk.coverage.coverage_pct}%</strong></span>
              </div>
              <div className='bento-card'><RiskPanel risk={dashData.risk} /></div>
              <div className='grid grid-cols-1 lg:grid-cols-2 gap-4'>
                <div className='bento-card'><ConstraintCoveragePanel coverage={dashData.risk.coverage} /></div>
                <div className='bento-card'><CitationPanel sop={dashData.sop} /></div>
              </div>
              {dashData.trusted_audit && <div className='bento-card'><TrustedAuditPanel trustedAudit={dashData.trusted_audit} /></div>}
              {dashData.evaluation && <div className='bento-card'><CompilerEvalPanel evaluation={dashData.evaluation} /></div>}
              {dashData.evolution && <div className='bento-card'><EvolutionPanel evolution={dashData.evolution} /></div>}
            </div>
          )}

          {/* Compile Mode: Business Graph + SOP (real-time) */}
          {compiling && (
            <div className='space-y-4 max-w-4xl mx-auto mt-4'>
              {businessModel && Object.keys(businessModel).length > 0 && (
                <div className='bento-card'>
                  <h3 className='text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3'>Business Graph</h3>
                  <BusinessGraph model={businessModel} />
                </div>
              )}
              {sop && Object.keys(sop).length > 0 && (
                <div className='bento-card'>
                  <h3 className='text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3'>SOP</h3>
                  <SopPanel sop={sop} />
                </div>
              )}
            </div>
          )}
        </main>
      </div>

      {/* Status Bar */}
      <footer className='border-t border-[var(--border-default)] px-4 py-1.5 flex items-center gap-4 text-[11px] text-[var(--text-placeholder)] bg-[var(--bg-secondary)]'>
        <span className='font-medium text-[var(--text-muted)]'>{mode === 'auto' && detectedMode ? 'Auto \u2192 ' + MODE_LABELS[detectedMode] : MODE_LABELS[effectiveMode]}</span>
        {sessionId && <><span className='text-[var(--border-default)]'>|</span><span className='font-mono'>session: {sessionId.slice(0, 12)}</span></>}
        {compiling && <><span className='text-[var(--border-default)]'>|</span><span className='text-[var(--accent-yellow)] animate-pulse'>Pipeline active</span></>}
        {dashData && <><span className='text-[var(--border-default)]'>|</span><span>risks: {dashData.risk.risks.length}</span><span>coverage: {dashData.risk.coverage.coverage_pct}%</span></>}
        <span className='ml-auto text-[10px]'>BSC Studio v5.0</span>
      </footer>
    </div>
  );
}

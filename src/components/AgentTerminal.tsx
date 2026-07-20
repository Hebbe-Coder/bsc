import { useEffect, useRef } from 'react';
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  LoaderCircle,
  TerminalSquare,
  XCircle,
} from 'lucide-react';
import { useWorkspace, type TerminalEvent } from '../store/workspaceStore';

const EVENT_TONE: Record<TerminalEvent['type'], string> = {
  'pipeline.started': 'text-cyan-300',
  'stage.started': 'text-sky-300',
  'stage.completed': 'text-emerald-300',
  'stage.loopback': 'text-amber-300',
  'capability.completed': 'text-teal-300',
  'capability.failed': 'text-rose-300',
  'pipeline.completed': 'text-emerald-200',
  'pipeline.failed': 'text-rose-300',
  'pipeline.cancelled': 'text-amber-200',
};

function EventIcon({ event }: { event: TerminalEvent }) {
  if (
    event.type === 'pipeline.completed'
    || event.type === 'stage.completed'
    || event.type === 'capability.completed'
  ) {
    return <CheckCircle2 size={14} aria-hidden="true" />;
  }
  if (event.type === 'pipeline.failed' || event.type === 'capability.failed') {
    return <CircleAlert size={14} aria-hidden="true" />;
  }
  if (event.type === 'pipeline.cancelled') return <XCircle size={14} aria-hidden="true" />;
  if (event.status === 'running') return <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />;
  return <Activity size={14} aria-hidden="true" />;
}

function formatTime(timestamp: string) {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? '--:--:--'
    : date.toLocaleTimeString([], { hour12: false });
}

export function AgentTerminal() {
  const sessionId = useWorkspace((state) => state.sessionId);
  const events = useWorkspace((state) => state.terminalEvents);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    const nearBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 96;
    if (nearBottom) node.scrollTop = node.scrollHeight;
  }, [events.length]);

  return (
    <section className="flex h-full min-h-[220px] flex-col overflow-hidden bg-[#090d12]" aria-label="Runtime terminal">
      <header className="flex min-h-10 items-center gap-2 border-b border-[var(--border-default)] bg-[var(--bg-secondary)] px-3">
        <TerminalSquare size={15} className="text-[var(--accent-blue)]" aria-hidden="true" />
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">Runtime terminal</span>
        <span className="ml-auto font-mono text-[10px] text-[var(--text-placeholder)]">
          {sessionId ? sessionId.slice(0, 12) : 'idle'}
        </span>
      </header>
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto p-3 font-mono text-[11px] leading-5" role="log" aria-live="polite">
        {events.length === 0 ? (
          <div className="flex min-h-[160px] items-center justify-center text-[var(--text-placeholder)]">
            <span>Waiting for runtime events...</span>
          </div>
        ) : (
          <div className="space-y-2">
            {events.map((event) => {
              const tone = EVENT_TONE[event.type] ?? 'text-[var(--text-secondary)]';
              const hasData = Object.keys(event.data ?? {}).length > 0;
              return (
                <article key={`${event.session_id}:${event.seq}`} className="border-l border-[var(--border-default)] pl-3">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-[var(--text-placeholder)]">
                    <span>{formatTime(event.timestamp)}</span>
                    <span className="text-[var(--accent-blue)]">#{event.seq}</span>
                    <span className="rounded border border-[var(--border-default)] px-1.5 py-0.5 uppercase tracking-wide">{event.stage}</span>
                    <span className={`inline-flex items-center gap-1 ${tone}`}><EventIcon event={event} />{event.type}</span>
                  </div>
                  <p className="mt-0.5 break-words text-[var(--text-secondary)]">{event.message || event.status}</p>
                  {hasData && (
                    <details className="mt-1 text-[10px] text-[var(--text-muted)]">
                      <summary className="inline-flex cursor-pointer items-center gap-1 select-none hover:text-[var(--text-secondary)]">
                        <ChevronDown size={12} aria-hidden="true" /> payload
                      </summary>
                      <pre className="mt-1 max-w-full overflow-auto whitespace-pre-wrap break-all rounded bg-[var(--bg-secondary)] p-2 text-[10px] text-[var(--text-muted)]">{JSON.stringify(event.data, null, 2)}</pre>
                    </details>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

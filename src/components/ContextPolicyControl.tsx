import { FilePlus2, GitFork, RotateCcw } from 'lucide-react';
import type { ContextPolicy } from '../api/orchestrateApi';

interface ContextPolicyControlProps {
  policy: ContextPolicy;
  parentSessionId: string;
  disabled?: boolean;
  onPolicyChange: (policy: ContextPolicy) => void;
  onParentSessionIdChange: (sessionId: string) => void;
}

const OPTIONS = [
  { id: 'fresh' as const, label: 'Fresh', detail: 'Begin with an empty, bounded context.', icon: FilePlus2 },
  { id: 'fork' as const, label: 'Fork', detail: 'Branch from a completed parent session.', icon: GitFork },
  { id: 'resume' as const, label: 'Resume', detail: 'Continue the same validated session.', icon: RotateCcw },
];

export function ContextPolicyControl({
  policy,
  parentSessionId,
  disabled = false,
  onPolicyChange,
  onParentSessionIdChange,
}: ContextPolicyControlProps) {
  return (
    <div className="context-policy-control" aria-label="Context policy">
      <div className="context-policy-options" role="radiogroup" aria-label="Context inheritance mode">
        {OPTIONS.map(({ id, label, detail, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={policy === id}
            disabled={disabled}
            onClick={() => onPolicyChange(id)}
            className={policy === id ? 'is-selected' : ''}
          >
            <Icon size={14} aria-hidden="true" />
            <span><strong>{label}</strong><small>{detail}</small></span>
          </button>
        ))}
      </div>
      {policy !== 'fresh' && (
        <label className="context-parent-input">
          <span>Source session</span>
          <input
            value={parentSessionId}
            onChange={(event) => onParentSessionIdChange(event.target.value)}
            disabled={disabled}
            aria-label="Parent session id"
            placeholder="Paste the completed session id"
          />
        </label>
      )}
    </div>
  );
}

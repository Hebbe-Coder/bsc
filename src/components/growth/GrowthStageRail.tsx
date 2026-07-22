import { CheckCircle2 } from 'lucide-react';
import type { KeyboardEvent } from 'react';

import type { GrowthStage } from '../../api/growthApi';
import { GROWTH_STAGES } from './growthModel';

type Props = {
  projectId: string;
  stage: GrowthStage;
  counts: Partial<Record<GrowthStage, number>>;
  truncated?: Partial<Record<GrowthStage, boolean>>;
  onChange: (stage: GrowthStage) => void;
};

export function GrowthStageRail({ projectId, stage, counts, truncated = {}, onChange }: Props) {
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, current: number) => {
    let next = current;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (current + 1) % GROWTH_STAGES.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (current - 1 + GROWTH_STAGES.length) % GROWTH_STAGES.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = GROWTH_STAGES.length - 1;
    else return;
    event.preventDefault();
    onChange(GROWTH_STAGES[next].id);
    const buttons = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[next]?.focus();
  };

  return <nav className="growth-stage-rail" aria-label="Knowledge growth stages">
    <div className="growth-stage-rail__heading"><span>PROJECT</span><strong title={projectId}>{projectId}</strong></div>
    <div className="growth-stage-rail__tabs" role="tablist" aria-orientation="vertical">
      {GROWTH_STAGES.map((item, index) => {
        const count = counts[item.id];
        return <button
          type="button"
          role="tab"
          key={item.id}
          id={`growth-stage-${item.id}`}
          aria-selected={stage === item.id}
          aria-controls="growth-stage-panel"
          tabIndex={stage === item.id ? 0 : -1}
          className={stage === item.id ? 'is-active' : ''}
          onClick={() => onChange(item.id)}
          onKeyDown={(event) => handleKeyDown(event, index)}
        >
          <span className="growth-stage-rail__index" aria-hidden="true">{item.index}</span>
          <span className="growth-stage-rail__copy"><strong>{item.label}</strong><small>{item.detail}</small></span>
          <b aria-label={count === undefined ? 'count unavailable' : `${count}${truncated[item.id] ? ' or more' : ''} records`}>
            {count === undefined ? '-' : `${count}${truncated[item.id] ? '+' : ''}`}
          </b>
        </button>;
      })}
    </div>
    <div className="growth-rail-note"><CheckCircle2 size={14} /><span>Counts come from the selected project. A plus sign marks a server-bounded result.</span></div>
  </nav>;
}

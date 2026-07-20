import { useEffect, useState } from 'react';
import {
  BarChart3,
  CheckCircle2,
  FileText,
  LoaderCircle,
  Play,
  Search,
  Sparkles,
  Target,
  X,
} from 'lucide-react';
import { skillManager, type SkillConfig } from '../skill';

interface SkillMarketProps {
  context?: string;
  onClose: () => void;
}

type ExecutionView = {
  status: 'idle' | 'running' | 'completed' | 'failed';
  message?: string;
  output?: string;
};

const SKILL_ICONS: Record<string, typeof Sparkles> = {
  'prd-analysis': FileText,
  'objective-extraction': Target,
  'kpi-extraction': BarChart3,
};

const CATEGORIES: Array<SkillConfig['category'] | 'all'> = [
  'all',
  'analysis',
  'generation',
  'visualization',
  'export',
  'data',
];

function toOutput(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value === undefined || value === null) return '';
  return JSON.stringify(value, null, 2);
}

export default function SkillMarket({ context = '', onClose }: SkillMarketProps) {
  const [skills, setSkills] = useState<SkillConfig[]>(() => skillManager.getAllSkills());
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<SkillConfig['category'] | 'all'>('all');
  const [selected, setSelected] = useState<SkillConfig | null>(null);
  const [execution, setExecution] = useState<ExecutionView>({ status: 'idle' });

  useEffect(() => {
    let alive = true;
    void skillManager.fetchSkillsFromBackend().then((discovered) => {
      if (alive) setSkills(discovered);
    });
    return () => { alive = false; };
  }, []);

  const filteredSkills = skills.filter((skill) => {
    const q = query.trim().toLowerCase();
    const matchesText = !q || `${skill.name} ${skill.description} ${skill.id}`.toLowerCase().includes(q);
    return matchesText && (category === 'all' || skill.category === category);
  });

  const runSelectedSkill = async () => {
    if (!selected) return;
    if (!context.trim()) {
      setExecution({ status: 'failed', message: 'Add a mission in the workspace before running a Skill.' });
      return;
    }
    setExecution({ status: 'running', message: `Executing ${selected.name} through the approved runtime...` });
    const result = await skillManager.executeSkill(selected.id, { input: context.trim() });
    const output = toOutput(result.result?.data.result ?? result.result?.data);
    setExecution({
      status: result.status === 'completed' ? 'completed' : 'failed',
      message: result.status === 'completed' ? 'Execution completed and was recorded by the backend.' : result.result?.error || 'Skill execution failed.',
      output,
    });
  };

  return (
    <div className="skill-market-backdrop" role="presentation">
      <section className="skill-market" role="dialog" aria-modal="true" aria-label="Skill catalog">
        <header className="skill-market__header">
          <div><p>PLUGIN CATALOG</p><h2>Approved Skills</h2><span>Discover from the backend registry, then execute against the current mission.</span></div>
          <button type="button" onClick={onClose} aria-label="Close Skill catalog"><X size={18} /></button>
        </header>
        <div className="skill-market__toolbar">
          <label><Search size={16} aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search Skills" aria-label="Search Skills" /></label>
          <div role="tablist" aria-label="Skill category">
            {CATEGORIES.map((item) => <button key={item} type="button" role="tab" aria-selected={category === item} className={category === item ? 'is-selected' : ''} onClick={() => setCategory(item)}>{item}</button>)}
          </div>
        </div>
        <div className="skill-market__content">
          <div className="skill-catalog" aria-label="Available Skills">
            <p className="skill-market__count">{filteredSkills.length} available</p>
            {filteredSkills.map((skill) => {
              const Icon = SKILL_ICONS[skill.id] || Sparkles;
              const isSelected = selected?.id === skill.id;
              return <button type="button" key={skill.id} className={'skill-card ' + (isSelected ? 'is-selected' : '')} onClick={() => { setSelected(skill); setExecution({ status: 'idle' }); }}>
                <span className="skill-card__icon"><Icon size={17} /></span>
                <span className="skill-card__content"><strong>{skill.name}</strong><small>{skill.description}</small><em>{skill.source || 'builtin'} / {skill.version || '1.0.0'}</em></span>
                {isSelected && <CheckCircle2 size={16} className="skill-card__check" aria-hidden="true" />}
              </button>;
            })}
            {filteredSkills.length === 0 && <div className="skill-market__empty"><Search size={22} /><p>No matching Skills found.</p></div>}
          </div>
          <aside className="skill-inspector">
            {selected ? <>
              <p>EXECUTION PLAN</p><h3>{selected.name}</h3><span>{selected.description}</span>
              <dl><div><dt>Source</dt><dd>{selected.source || 'builtin'}</dd></div><div><dt>Produces</dt><dd>{selected.produces.length ? selected.produces.join(', ') : 'runtime output'}</dd></div><div><dt>Permission</dt><dd>{selected.executable === false ? 'read only' : 'approved execution'}</dd></div></dl>
              {execution.status !== 'idle' && <div className={'skill-execution skill-execution--' + execution.status}>{execution.status === 'running' && <LoaderCircle size={15} className="animate-spin" />}<strong>{execution.status}</strong><span>{execution.message}</span>{execution.output && <pre>{execution.output}</pre>}</div>}
              <button type="button" className="skill-run" disabled={execution.status === 'running' || selected.executable === false} onClick={() => void runSelectedSkill()}>{execution.status === 'running' ? <><LoaderCircle size={15} className="animate-spin" /> Running</> : <><Play size={15} fill="currentColor" /> Run with current mission</>}</button>
            </> : <div className="skill-inspector__empty"><BlocksPlaceholder /><h3>Select a Skill</h3><p>Each catalog entry is discovered from the backend manifest registry and shows its source before execution.</p></div>}
          </aside>
        </div>
      </section>
    </div>
  );
}

function BlocksPlaceholder() {
  return <span className="skill-placeholder-icon"><Sparkles size={22} /></span>;
}

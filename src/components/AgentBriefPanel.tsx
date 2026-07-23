type Artifact = Record<string, unknown>;

function list(graph: Record<string, unknown>, key: string): Artifact[] {
  const value = graph[key];
  return Array.isArray(value) ? value.filter((item): item is Artifact => Boolean(item && typeof item === 'object')) : [];
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

export function AgentBriefPanel({ businessModel }: { businessModel: Record<string, unknown> }) {
  const graph = (businessModel.artifacts && typeof businessModel.artifacts === 'object')
    ? businessModel.artifacts as Record<string, unknown>
    : {};
  const model = list(graph, 'biz_models')[0] ?? {};
  const assumptions = list(graph, 'assumptions').slice(0, 4);
  const constraints = list(graph, 'constraints').slice(0, 4);
  const decisions = list(graph, 'decisions').slice(0, 2);
  const deliverables = list(graph, 'deliverables').slice(0, 3);
  const objectives = Array.isArray(model.objectives) ? model.objectives.filter((item): item is string => typeof item === 'string') : [];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">BUSINESS BRIEF</p>
          <h3 className="text-sm font-semibold tracking-wide text-slate-800">商业分析摘要</h3>
        </div>
        <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">
          {text(model.domain) || text(businessModel.domain) || 'General'}
        </span>
      </div>

      <div className="space-y-4 px-5 py-4">
        {text(model.value_proposition) && (
          <p className="rounded-xl border border-sky-100 bg-sky-50/70 px-4 py-3 text-sm leading-relaxed text-slate-700">
            {text(model.value_proposition)}
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <section>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">Objectives</p>
            <ul className="space-y-1.5 text-sm text-slate-700">
              {objectives.map((objective, index) => <li key={`${objective}-${index}`}>• {objective}</li>)}
              {objectives.length === 0 && <li className="text-slate-400">No objectives generated</li>}
            </ul>
          </section>
          <section>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">First Decision</p>
            {decisions.map((decision, index) => (
              <div key={`${text(decision.artifact_id)}-${index}`} className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-2">
                <p className="text-sm font-medium text-slate-800">{text(decision.decision_statement)}</p>
                {text(decision.rationale) && <p className="mt-1 text-xs leading-relaxed text-slate-600">{text(decision.rationale)}</p>}
              </div>
            ))}
            {decisions.length === 0 && <p className="text-sm text-slate-400">No decision generated</p>}
          </section>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <section>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">Critical Assumptions</p>
            <div className="space-y-1.5">
              {assumptions.map((assumption, index) => <p key={`${text(assumption.artifact_id)}-${index}`} className="text-xs leading-relaxed text-slate-600">{text(assumption.statement)}</p>)}
              {assumptions.length === 0 && <p className="text-sm text-slate-400">No assumptions generated</p>}
            </div>
          </section>
          <section>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">Operating Constraints</p>
            <div className="space-y-1.5">
              {constraints.map((constraint, index) => <p key={`${text(constraint.artifact_id)}-${index}`} className="text-xs leading-relaxed text-slate-600">{text(constraint.constraint_statement)}</p>)}
              {constraints.length === 0 && <p className="text-sm text-slate-400">No constraints generated</p>}
            </div>
          </section>
        </div>
        {deliverables.length > 0 && <section>
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">Project Deliverables</p>
          <div className="space-y-2">
            {deliverables.map((deliverable, index) => <div key={`${text(deliverable.artifact_id)}-${index}`} className="rounded-xl border border-emerald-100 bg-emerald-50/50 px-3 py-2">
              <p className="text-sm font-medium text-slate-800">{text(deliverable.title) || text(deliverable.label)}</p>
              {text(deliverable.summary) && <p className="mt-1 text-xs leading-relaxed text-slate-600">{text(deliverable.summary)}</p>}
              {Array.isArray(deliverable.differentiators) && deliverable.differentiators.length > 0 && <p className="mt-1 text-xs text-emerald-700">{String(deliverable.differentiators[0])}</p>}
            </div>)}
          </div>
        </section>}
      </div>
    </div>
  );
}

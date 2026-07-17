import type { RiskPayload } from "../api/compilerDashboardApi";

function healthColor(pct: number): string {
  if (pct >= 100) return "bg-emerald-500";
  if (pct >= 60) return "bg-amber-500";
  return "bg-red-500";
}

export function ConstraintCoveragePanel({
  coverage,
}: {
  coverage: RiskPayload["coverage"];
}) {
  const pct = Math.max(0, Math.min(100, coverage?.coverage_pct ?? 0));
  const total = coverage?.total ?? 0;
  const covered = coverage?.covered ?? 0;
  const uncovered = coverage?.uncovered_ids ?? [];
  const barColor = healthColor(pct);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
      <div className="border-b border-slate-100 px-5 py-4">
        <h3 className="text-sm font-semibold tracking-wide text-slate-800">约束覆盖健康度</h3>
      </div>

      <div className="space-y-4 px-5 py-4">
        <div>
          <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
            <span>覆盖率</span>
            <span className="font-medium text-slate-700">
              {covered}/{total}
            </span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full rounded-full transition-all duration-500 ${barColor}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-1.5 text-right text-xs font-semibold text-slate-600">{pct}%</p>
        </div>

        {uncovered.length === 0 ? (
          <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">
            全部约束已覆盖
          </p>
        ) : (
          <div>
            <p className="mb-2 text-xs font-medium text-slate-500">未覆盖约束</p>
            <div className="flex flex-wrap gap-1.5">
              {uncovered.map((id) => (
                <span
                  key={id}
                  className="rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600"
                >
                  {id}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

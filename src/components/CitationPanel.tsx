import type { DashboardData } from "../api/compilerDashboardApi";

export function CitationPanel({ sop }: { sop: DashboardData["sop"] }) {
  const coverage = sop?._citation_coverage;
  const covPct = Math.max(0, Math.min(1, coverage?.coverage ?? 0)) * 100;
  const sops = sop?.sops ?? [];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
      <div className="border-b border-slate-100 px-5 py-4">
        <h3 className="text-sm font-semibold tracking-wide text-slate-800">方法论引用</h3>
      </div>

      <div className="space-y-4 px-5 py-4">
        <div>
          <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
            <span>引用覆盖率</span>
            <span className="font-medium text-slate-700">
              {coverage?.covered ?? 0}/{coverage?.total ?? 0}
            </span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-indigo-500 transition-all duration-500"
              style={{ width: `${covPct}%` }}
            />
          </div>
        </div>

        <div className="space-y-3">
          {sops.map((s: any, i: number) => {
            const refs: string[] = s?.source_ref ?? [];
            return (
              <div
                key={s?.id ?? i}
                className="rounded-xl border border-slate-100 bg-white px-4 py-3"
              >
                <p className="mb-2 text-sm font-medium text-slate-800">{s?.title}</p>
                {refs.length === 0 ? (
                  <p className="text-xs text-slate-400">无引用</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {refs.map((ref, j) => (
                      <button
                        key={`${ref}-${j}`}
                        type="button"
                        title={ref}
                        className="group flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-600 transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
                      >
                        <span className="text-[10px] text-slate-400 group-hover:text-indigo-400">
                          引用
                        </span>
                        <span className="font-mono">{ref}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

import type { Evaluation, QualityDimension } from "../api/compilerDashboardApi";

function scoreColor(score: number): string {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 60) return "bg-amber-500";
  return "bg-red-500";
}

function scoreTextColor(score: number): string {
  if (score >= 80) return "text-emerald-700";
  if (score >= 60) return "text-amber-700";
  return "text-red-700";
}

function levelLabel(score: number): string {
  if (score >= 90) return "优秀";
  if (score >= 80) return "良好";
  if (score >= 70) return "合格";
  if (score >= 60) return "待改进";
  return "不合格";
}

function DimensionBar({ dim }: { dim: QualityDimension }) {
  const pct = Math.max(0, Math.min(100, dim.score));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-slate-700">{dim.name}</span>
        <span className={`font-semibold ${scoreTextColor(dim.score)}`}>{dim.score}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${scoreColor(dim.score)} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {dim.feedback ? (
        <p className="text-[11px] leading-snug text-slate-400">{dim.feedback}</p>
      ) : null}
    </div>
  );
}

export function CompilerEvalPanel({ evaluation }: { evaluation?: Evaluation | null }) {
  if (!evaluation) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="text-sm font-semibold tracking-wide text-slate-800">编译器产物质量评分</h3>
        </div>
        <div className="px-5 py-6 text-sm text-slate-400">暂无评分数据</div>
      </div>
    );
  }

  const passed = evaluation.is_passed;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <h3 className="text-sm font-semibold tracking-wide text-slate-800">编译器产物质量评分</h3>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${
            passed
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-amber-200 bg-amber-50 text-amber-700"
          }`}
        >
          {passed ? "✓ 质量合格" : "⚠ 待改进"}
        </span>
      </div>

      <div className="space-y-4 px-5 py-4">
        {/* 总分 */}
        <div className="flex items-end gap-3">
          <span className={`text-4xl font-bold leading-none ${scoreTextColor(evaluation.overall_score)}`}>
            {evaluation.overall_score}
          </span>
          <span className="pb-1 text-sm font-medium text-slate-500">
            分 · {levelLabel(evaluation.overall_score)}
            <span className="ml-1 text-xs font-normal text-slate-400">
              （{evaluation.improvement_points} 个改进点）
            </span>
          </span>
        </div>

        {/* 维度条 */}
        <div className="space-y-3">
          {(evaluation.dimensions ?? []).map((d) => (
            <DimensionBar key={d.name} dim={d} />
          ))}
        </div>

        {/* 改进建议 */}
        {evaluation.suggestions && evaluation.suggestions.length > 0 ? (
          <div className="rounded-xl border border-amber-100 bg-amber-50/60 px-4 py-3">
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-amber-600">
              改进建议
            </p>
            <ul className="list-inside list-disc space-y-0.5 text-xs text-amber-800">
              {evaluation.suggestions.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}

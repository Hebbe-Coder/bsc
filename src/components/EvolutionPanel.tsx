import type { Evolution, EvolutionFeedback } from "../api/compilerDashboardApi";

const TYPE_STYLE: Record<string, string> = {
  thumbs_up: "border-emerald-200 bg-emerald-50 text-emerald-700",
  thumbs_down: "border-red-200 bg-red-50 text-red-700",
  comment: "border-amber-200 bg-amber-50 text-amber-700",
  correction: "border-blue-200 bg-blue-50 text-blue-700",
};

const TYPE_LABEL: Record<string, string> = {
  thumbs_up: "👍 高分",
  thumbs_down: "👎 低分",
  comment: "💬 中等",
  correction: "✏ 修正",
};

function fmtTs(ts: number): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function FeedbackRow({ fb }: { fb: EvolutionFeedback }) {
  const style = TYPE_STYLE[fb.feedback_type] ?? "border-slate-200 bg-slate-50 text-slate-600";
  const label = TYPE_LABEL[fb.feedback_type] ?? fb.feedback_type;
  return (
    <div className="rounded-lg border border-slate-100 bg-white px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${style}`}>
            {label}
          </span>
          <span className="truncate text-xs text-slate-700" title={fb.query}>{fb.query || "—"}</span>
        </div>
        <span className="shrink-0 font-mono text-[10px] text-slate-400">{fmtTs(fb.timestamp)}</span>
      </div>
      {fb.comment ? (
        <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-slate-500">{fb.comment}</p>
      ) : null}
    </div>
  );
}

export function EvolutionPanel({ evolution }: { evolution?: Evolution | null }) {
  if (!evolution) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="text-sm font-semibold tracking-wide text-slate-800">自进化闭环</h3>
        </div>
        <div className="px-5 py-6 text-sm text-slate-400">暂无自进化数据</div>
      </div>
    );
  }

  const stats = evolution.stats ?? { total: 0, by_type: { thumbs_up: 0, thumbs_down: 0, correction: 0, comment: 0 }, by_user: {}, positive_rate: 0 };
  const total = stats.total ?? 0;
  const rate = stats.positive_rate ?? 0;
  const recent = evolution.recent_feedback ?? [];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <h3 className="text-sm font-semibold tracking-wide text-slate-800">自进化闭环</h3>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">
          累计 {total} 条 · 好评率 {(rate * 100).toFixed(0)}%
        </span>
      </div>

      <div className="space-y-4 px-5 py-4">
        {/* 统计行 */}
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-2 text-center">
            <p className="text-[10px] font-medium uppercase tracking-wide text-emerald-600">高分</p>
            <p className="mt-0.5 text-lg font-bold text-emerald-700">{stats.by_type?.thumbs_up ?? 0}</p>
          </div>
          <div className="rounded-xl border border-amber-100 bg-amber-50/60 px-3 py-2 text-center">
            <p className="text-[10px] font-medium uppercase tracking-wide text-amber-600">中等</p>
            <p className="mt-0.5 text-lg font-bold text-amber-700">{stats.by_type?.comment ?? 0}</p>
          </div>
          <div className="rounded-xl border border-red-100 bg-red-50/60 px-3 py-2 text-center">
            <p className="text-[10px] font-medium uppercase tracking-wide text-red-600">低分</p>
            <p className="mt-0.5 text-lg font-bold text-red-700">{stats.by_type?.thumbs_down ?? 0}</p>
          </div>
        </div>

        {/* 时间线 */}
        <div>
          <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
            最近反馈（{recent.length}）
          </p>
          {recent.length === 0 ? (
            <p className="text-sm text-slate-400">尚无反馈记录</p>
          ) : (
            <div className="space-y-1.5">
              {recent.map((fb) => (
                <FeedbackRow key={`${fb.trace_id}-${fb.timestamp}`} fb={fb} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

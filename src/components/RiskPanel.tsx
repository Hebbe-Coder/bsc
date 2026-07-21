import { useState } from "react";
import type { RiskPayload, RiskItem } from "../api/compilerDashboardApi";

const SEVERITY_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

const SEVERITY_DOT: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-amber-500",
  low: "bg-emerald-500",
};

const SEVERITY_TEXT: Record<string, string> = {
  high: "text-red-600",
  medium: "text-amber-600",
  low: "text-emerald-600",
};

const GATE_STYLE: Record<string, string> = {
  pass: "bg-emerald-50 text-emerald-700 border-emerald-200",
  review: "bg-amber-50 text-amber-700 border-amber-200",
  warn: "bg-amber-50 text-amber-700 border-amber-200",
  block: "bg-red-50 text-red-700 border-red-200",
};

const GATE_LABEL: Record<string, string> = {
  pass: "通过",
  review: "复核",
  warn: "警告",
  block: "阻断",
};

function sortedRisks(risks: RiskItem[]): RiskItem[] {
  return [...risks].sort(
    (a, b) => (SEVERITY_RANK[b.severity] ?? 0) - (SEVERITY_RANK[a.severity] ?? 0)
  );
}

export function RiskPanel({ risk }: { risk: RiskPayload }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const gate = risk.gate?.decision ?? "pass";
  const items = sortedRisks(risk.risks ?? []);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <h3 className="text-sm font-semibold tracking-wide text-slate-800">风险与约束</h3>
        <div className="flex items-center gap-2">
          {risk.overall_score && (
            <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium capitalize text-slate-600">
              {risk.overall_score}
            </span>
          )}
          <span
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${
              GATE_STYLE[gate] ?? GATE_STYLE.pass
            }`}
          >
            {GATE_LABEL[gate] ?? gate}
          </span>
        </div>
      </div>

      {risk.gate?.reason && (
        <p className="px-5 pt-3 text-xs leading-relaxed text-slate-500">{risk.gate.reason}</p>
      )}

      <div className="space-y-2 px-5 py-4">
        {items.length === 0 && (
          <p className="text-sm text-slate-400">暂无风险项</p>
        )}
        {items.map((r) => {
          const expanded = openId === r.id;
          return (
            <button
              key={r.id}
              type="button"
              onClick={() => setOpenId(expanded ? null : r.id)}
              className="w-full rounded-xl border border-slate-100 bg-white px-4 py-3 text-left transition hover:border-slate-200 hover:bg-slate-50"
            >
              <div className="flex items-center gap-2.5">
                <span
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                    SEVERITY_DOT[r.severity] ?? "bg-slate-300"
                  }`}
                />
                <span className="flex-1 text-sm font-medium text-slate-800">{r.title}</span>
                <span
                  className={`text-xs font-medium capitalize ${
                    SEVERITY_TEXT[r.severity] ?? "text-slate-400"
                  }`}
                >
                  {r.severity}
                </span>
              </div>

              {expanded && (
                <div className="mt-3 space-y-3 border-t border-slate-100 pt-3">
                  {r.detail && (
                    <p className="text-xs leading-relaxed text-slate-600">{r.detail}</p>
                  )}
                  {r.linked_constraints?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {r.linked_constraints.map((c) => (
                        <span
                          key={c}
                          className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-500"
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

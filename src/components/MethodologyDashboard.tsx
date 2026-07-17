import { useEffect, useState } from "react";
import { useWorkspace } from "../store/workspaceStore";
import { fetchCompilerDashboard, type DashboardData } from "../api/compilerDashboardApi";
import { RiskPanel } from "./RiskPanel";
import { ConstraintCoveragePanel } from "./ConstraintCoveragePanel";
import { CitationPanel } from "./CitationPanel";
import { TrustedAuditPanel } from "./TrustedAuditPanel";
import { CompilerEvalPanel } from "./CompilerEvalPanel";

export function MethodologyDashboard() {
  const sessionId = useWorkspace((s) => s.sessionId);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) { setData(null); return; }
    let cancelled = false;
    setLoading(true); setError(null);
    fetchCompilerDashboard(sessionId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message || "加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId]);

  if (!sessionId) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-slate-400">
        先运行一次编排（在「工作台」输入想法并启动），再回到这里查看可交互产物仪表盘。
      </div>
    );
  }
  if (loading) return <div className="p-8 text-sm text-slate-400">加载仪表盘…</div>;
  if (error) return <div className="p-8 text-sm text-red-500">{error}</div>;
  if (!data) return <div className="p-8 text-sm text-slate-400">暂无数据</div>;

  return (
    <div className="h-full overflow-auto p-4">
      <div className="mx-auto grid max-w-5xl gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <RiskPanel risk={data.risk} />
        </div>
        <ConstraintCoveragePanel coverage={data.risk.coverage} />
        <CitationPanel sop={data.sop} />
        {data.trusted_audit && (
          <div className="md:col-span-2">
            <TrustedAuditPanel trustedAudit={data.trusted_audit} />
          </div>
        )}
        {data.evaluation && (
          <div className="md:col-span-2">
            <CompilerEvalPanel evaluation={data.evaluation} />
          </div>
        )}
      </div>
    </div>
  );
}

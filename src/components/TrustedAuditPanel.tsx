import type { TrustedAudit, AuditEntry } from "../api/compilerDashboardApi";

function shortHash(h: string): string {
  if (!h) return "—";
  return h.length > 20 ? `${h.slice(0, 12)}…${h.slice(-8)}` : h;
}

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

function truncateHash(h: string): string {
  return h.length > 16 ? `${h.slice(0, 10)}…${h.slice(-6)}` : h;
}

function ChainRow({ entry }: { entry: AuditEntry }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 bg-white px-3 py-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
            #{entry.seq}
          </span>
          <span className="text-xs font-medium text-slate-700">
            {entry.agent} · {entry.action}
          </span>
        </div>
        <p className="mt-1 truncate font-mono text-[10px] text-slate-400" title={entry.hash}>
          {truncateHash(entry.hash)}
        </p>
      </div>
      <span className="shrink-0 font-mono text-[10px] text-slate-400">{entry.timestamp}</span>
    </div>
  );
}

export function TrustedAuditPanel({ trustedAudit }: { trustedAudit: TrustedAudit }) {
  const verified = trustedAudit?.verified ?? false;
  const gate = trustedAudit?.coverage?.gate_decision ?? "pass";
  const refs = trustedAudit?.source_refs ?? [];
  const covPct = trustedAudit?.coverage?.coverage_pct;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm backdrop-blur transition hover:shadow-md">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <h3 className="text-sm font-semibold tracking-wide text-slate-800">可信审计链</h3>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${
            verified
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-red-200 bg-red-50 text-red-700"
          }`}
        >
          {verified ? "✓ 链完整可验证" : "✗ 检测到篡改"}
        </span>
      </div>

      <div className="space-y-4 px-5 py-4">
        {/* 链头哈希 + 覆盖率快照 */}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-100 bg-white px-4 py-3">
            <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
              链头哈希 (SHA-256)
            </p>
            <p
              className="mt-1 break-all font-mono text-xs text-slate-700"
              title={trustedAudit?.chain_hash}
            >
              {shortHash(trustedAudit?.chain_hash ?? "")}
            </p>
          </div>
          <div className="rounded-xl border border-slate-100 bg-white px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                约束覆盖
              </p>
              <span
                className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                  GATE_STYLE[gate] ?? GATE_STYLE.pass
                }`}
              >
                {GATE_LABEL[gate] ?? gate}
              </span>
            </div>
            <p className="mt-1 text-sm font-semibold text-slate-800">
              {covPct == null ? "—" : `${covPct}%`}
              <span className="ml-1 text-xs font-normal text-slate-400">
                （{trustedAudit?.coverage?.covered ?? 0}/
                {trustedAudit?.coverage?.total ?? 0} 约束满足）
              </span>
            </p>
          </div>
        </div>

        {/* 引用集合 */}
        <div>
          <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
            方法论引用（{refs.length}）
          </p>
          {refs.length === 0 ? (
            <p className="text-sm text-slate-400">无引用</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {refs.map((r) => (
                <span
                  key={r}
                  className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs text-slate-600"
                >
                  {r}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 链节点 */}
        <div>
          <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
            审计链节点（{trustedAudit?.audit?.length ?? 0}）
          </p>
          <div className="space-y-1.5">
            {(trustedAudit?.audit ?? []).map((e) => (
              <ChainRow key={e.seq} entry={e} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function SopPanel({ sop }: { sop: any }) {
  const sops = sop?.sops || [];
  return (
    <div className="space-y-2">
      {sops.map((s: any) => (
        <div key={s.id} className="border rounded p-2">
          <h4 className="font-medium">{s.title} <span className="text-xs text-gray-400">{s.owner_role}</span></h4>
          <ul className="text-sm list-decimal pl-5">
            {(s.steps || []).map((st: any) => <li key={st.seq}>{st.action}{st.sla ? ` (SLA ${st.sla})` : ""}</li>)}
          </ul>
          {s.escalation && <p className="text-xs text-amber-600">升级：{s.escalation}</p>}
          {s.review_cycle && <p className="text-xs text-gray-400">复审：{s.review_cycle}</p>}
        </div>
      ))}
    </div>
  );
}

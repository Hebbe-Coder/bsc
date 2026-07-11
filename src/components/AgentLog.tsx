import { useWorkspace } from "../store/workspaceStore";
export function AgentLog() {
  const log = useWorkspace(s => s.log);
  return (
    <div className="h-full overflow-auto text-xs font-mono space-y-1 p-2">
      {log.map((l, i) => (
        <div key={i} className={
          l.msg.includes("↺") ? "text-amber-600" : (l.stage === "done") ? "text-green-600" : "text-gray-600"
        }>[{l.stage}] {l.msg}</div>
      ))}
    </div>
  );
}

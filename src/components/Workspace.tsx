import { useWorkspace } from "../store/workspaceStore";
import { fetchCompilerDashboard } from "../api/compilerDashboardApi";
import {
  startOrchestrate,
  subscribeStream,
  type OrchestratorEvent,
} from "../api/orchestrateApi";
import { ChatPanel } from "./ChatPanel";
import { BusinessGraph } from "./BusinessGraph";
import { SopPanel } from "./SopPanel";
import { AgentLog } from "./AgentLog";

export function Workspace() {
  const set = useWorkspace((s) => s.set);
  const pushLog = useWorkspace((s) => s.pushLog);
  const setStage = useWorkspace((s) => s.setStage);
  const applyDashboard = useWorkspace((s) => s.applyDashboard);
  const businessModel = useWorkspace((s) => s.businessModel);
  const sop = useWorkspace((s) => s.sop);

  const start = async (idea: string) => {
    const res = await startOrchestrate(idea);
    set({ sessionId: res.session_id, idea });
    let source: EventSource | null = null;
    source = subscribeStream(
      res,
      (event: OrchestratorEvent) => {
        const status = event.status === "done" ? "completed" : event.status;
        setStage(event.stage, status);
        pushLog(event.stage, event.message);
        if (!event.terminal) return;

        source?.close();
        if (event.type === "pipeline.completed") {
          void fetchCompilerDashboard(res.session_id)
            .then(applyDashboard)
            .catch((error: unknown) => {
              const message = error instanceof Error
                ? error.message
                : "Dashboard request failed";
              pushLog("error", message);
            });
          return;
        }
        pushLog("error", event.message || `Pipeline ended with ${event.status}`);
      },
      () => pushLog("system", "Event stream disconnected; browser will retry"),
    );
  };

  return (
    <div className="grid grid-cols-[1fr_2fr_1fr] grid-rows-[1fr_200px] h-screen gap-2 p-2">
      <div className="row-span-1 border rounded"><ChatPanel onSend={start} /></div>
      <div className="border rounded overflow-hidden"><BusinessGraph model={businessModel} /></div>
      <div className="border rounded overflow-auto"><SopPanel sop={sop} /></div>
      <div className="col-span-3 border rounded bg-gray-50"><AgentLog /></div>
    </div>
  );
}

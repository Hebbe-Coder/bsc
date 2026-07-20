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
  const pushLog = useWorkspace((s) => s.pushLog);
  const beginSession = useWorkspace((s) => s.beginSession);
  const appendEvent = useWorkspace((s) => s.appendEvent);
  const setStage = useWorkspace((s) => s.setStage);
  const applyDashboard = useWorkspace((s) => s.applyDashboard);
  const businessModel = useWorkspace((s) => s.businessModel);
  const sop = useWorkspace((s) => s.sop);

  const start = async (idea: string) => {
    const res = await startOrchestrate(idea);
    beginSession(res.session_id, idea);
    let source: EventSource | null = null;
    source = subscribeStream(
      res,
      (event: OrchestratorEvent) => {
        appendEvent(event);
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
    <div className="grid h-full min-h-0 grid-cols-1 auto-rows-[minmax(280px,auto)] gap-2 overflow-y-auto p-2 lg:grid-cols-[minmax(240px,1fr)_minmax(0,2fr)_minmax(240px,1fr)] lg:grid-rows-[minmax(0,1fr)_200px] lg:auto-rows-auto lg:overflow-hidden">
      <div className="min-h-[280px] border rounded lg:min-h-0"><ChatPanel onSend={start} /></div>
      <div className="min-h-[320px] border rounded overflow-hidden lg:min-h-0"><BusinessGraph model={businessModel} /></div>
      <div className="min-h-[280px] border rounded overflow-auto lg:min-h-0"><SopPanel sop={sop} /></div>
      <div className="min-h-[200px] border rounded bg-gray-50 lg:col-span-3"><AgentLog /></div>
    </div>
  );
}

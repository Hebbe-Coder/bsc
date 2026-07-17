import { useState } from "react";
import { Workspace } from "./components/Workspace";
import { MethodologyDashboard } from "./components/MethodologyDashboard";

type Tab = "workbench" | "dashboard";

export default function App() {
  const [tab, setTab] = useState<Tab>("workbench");
  const tabCls = (t: Tab) =>
    `px-4 py-2 text-sm font-medium rounded-t-lg transition ${
      tab === t ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"
    }`;
  return (
    <div className="flex h-screen flex-col">
      <div className="flex gap-1 border-b border-slate-200 bg-slate-50 px-3 pt-2">
        <button type="button" className={tabCls("workbench")} onClick={() => setTab("workbench")}>工作台</button>
        <button type="button" className={tabCls("dashboard")} onClick={() => setTab("dashboard")}>产物仪表盘</button>
      </div>
      <div className="flex-1 overflow-hidden">
        {tab === "workbench" ? <Workspace /> : <MethodologyDashboard />}
      </div>
    </div>
  );
}

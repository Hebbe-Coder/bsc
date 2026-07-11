import { useState } from "react";
import { useWorkspace } from "../store/workspaceStore";

export function ChatPanel({ onSend }: { onSend: (t: string) => void }) {
  const { idea, set } = useWorkspace();
  const [text, setText] = useState("");
  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto space-y-2 p-2">
        {idea && (
          <div className="bg-blue-50 border rounded p-2 text-sm">
            <span className="text-gray-400 text-xs">你：</span>{idea}
          </div>
        )}
      </div>
      <input
        className="border p-2 m-2 rounded"
        placeholder="描述你的业务点子…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && text.trim()) {
            set({ idea: text.trim() });
            onSend(text.trim());
            setText("");
          }
        }}
      />
    </div>
  );
}

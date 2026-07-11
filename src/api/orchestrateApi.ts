import { fetchWrapper } from "./fetchWrapper";
import { API_BASE } from "../config";

export async function startOrchestrate(idea: string): Promise<{ session_id: string; status: string }> {
  return fetchWrapper.fetch<{ session_id: string; status: string }>("/api/orchestrate", {
    method: "POST",
    body: JSON.stringify({ idea }),
  });
}

export function subscribeStream(sessionId: string, onEvent: (e: any) => void) {
  // 必须用 API_BASE（开发环境指向 :8000 后端），相对路径会被 vite dev server 拦截
  const url = `${API_BASE}/api/orchestrate/stream?session_id=${encodeURIComponent(sessionId)}`;
  const es = new EventSource(url);
  es.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data));
    } catch {
      /* 忽略格式错误的帧 */
    }
  };
  return es;
}

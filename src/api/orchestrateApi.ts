// 使用相对路径 + vite dev proxy（/api -> :8000），规避跨域：
// 开发环境浏览器请求同源的 /api/*，由 vite 代理转发到后端；
// 生产环境静态资源由后端同域托管，相对路径同样命中后端。SSE（EventSource）亦走同源，稳定流式转发。

export async function startOrchestrate(
  idea: string,
): Promise<{ session_id: string; status: string }> {
  const res = await fetch("/api/orchestrate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea }),
  });
  if (!res.ok) {
    throw new Error(`orchestrate failed: ${res.status}`);
  }
  return res.json();
}

export function subscribeStream(
  sessionId: string,
  onEvent: (e: any) => void,
): EventSource {
  const url = `/api/orchestrate/stream?session_id=${encodeURIComponent(sessionId)}`;
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

import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";

export function resolveApiProxyTarget(
  processEnv: Record<string, string | undefined>,
  fileEnv: Record<string, string | undefined>,
): string {
  return processEnv.BSC_VITE_API_PROXY_TARGET
    || processEnv.VITE_API_PROXY_TARGET
    || fileEnv.BSC_VITE_API_PROXY_TARGET
    || fileEnv.VITE_API_PROXY_TARGET
    || 'http://localhost:8000';
}

export function resolveLocalRuntimeApiKey(
  command: string,
  mode: string,
  processEnv: Record<string, string | undefined>,
  fileEnv: Record<string, string | undefined>,
): string {
  if (command !== 'serve' || mode === 'production') return '';
  // Both locations are server-side Vite configuration. The credential is
  // injected only into the development proxy, never into import.meta.env.
  return processEnv.BSC_LOCAL_API_KEY || fileEnv.BSC_LOCAL_API_KEY || '';
}

// https://vite.dev/config/
export default defineConfig(({ mode, command }) => {
  // Vite config executes before it exposes .env values to import.meta.env.
  const env = loadEnv(mode, process.cwd(), '');
  // BSC_VITE_API_PROXY_TARGET is the explicit local API endpoint. It keeps a
  // refreshed Studio independent of stale inherited VITE_API_PROXY_TARGET
  // values without changing generic Vite behavior for other processes.
  const apiProxyTarget = resolveApiProxyTarget(process.env, env);
  // A local development key must be opted in with BSC_LOCAL_API_KEY. Falling
  // back to API_KEY would silently replace the key entered in Studio and make
  // an isolated/local runtime impossible to verify.
  const localRuntimeApiKey = resolveLocalRuntimeApiKey(command, mode, process.env, env);
  const authorizedProxy = {
    target: apiProxyTarget,
    changeOrigin: true,
    // `headers` covers every proxied request before its body is streamed.
    // The event hook below remains as a defensive override for callers that
    // attach their own non-secret placeholder Authorization value.
    headers: localRuntimeApiKey ? { Authorization: `Bearer ${localRuntimeApiKey}` } : undefined,
    configure(proxy: { on: (event: string, handler: (request: { setHeader: (name: string, value: string) => void }, incoming: { headers: Record<string, string | string[] | undefined> }) => void) => void }) {
      proxy.on('proxyReq', (request, incoming) => {
        const authorization = incoming.headers.authorization;
        if (typeof authorization === 'string' && authorization) {
          request.setHeader('Authorization', authorization);
        }
        if (localRuntimeApiKey) {
          // Force an explicitly opted-in loopback key server-side so the browser never receives it.
          request.setHeader('Authorization', `Bearer ${localRuntimeApiKey}`);
        }
      });
    },
  };

  return {
  build: {
    sourcemap: 'hidden',
  },
  server: {
    watch: {
      ignored: ['**/static/presentations/**', '**/output/**'],
    },
    proxy: {
      // 开发环境：前端（:5173）的所有 /api 请求经 vite 代理到后端（:8000），
      // 规避跨域，同时让 SSE（EventSource）走同源、稳定流式转发。
      // 生产构建由后端同域托管，相对路径同样生效。
      '/api': {
        ...authorizedProxy,
      },
      // Agent OS uses root-level routes in FastAPI rather than the /api router.
      // Keep development requests same-origin so they reach the backend instead
      // of falling through to Vite's SPA HTML response.
      '/agent': {
        ...authorizedProxy,
      },
      '/knowledge': {
        ...authorizedProxy,
      },
    },
  },
  plugins: [
    react({
      babel: {
        plugins: [
          'react-dev-locator',
        ],
      },
    }),
    tsconfigPaths()
  ],
  };
})

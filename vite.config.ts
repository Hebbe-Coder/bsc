import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";

// https://vite.dev/config/
export default defineConfig(({ mode, command }) => {
  // Vite config executes before it exposes .env values to import.meta.env.
  const env = loadEnv(mode, process.cwd(), '');
  // A command-line target must win over checked-in local defaults so isolated
  // Studio instances can verify a specific backend without editing .env.
  let apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000';
  if (!process.env.VITE_API_PROXY_TARGET && env.VITE_API_PROXY_TARGET) {
    apiProxyTarget = env.VITE_API_PROXY_TARGET;
  }
  // A local development key stays inside the Vite process. It is never exposed
  // through import.meta.env or included in a production build.
  const localRuntimeApiKey = command === 'serve' && mode !== 'production'
    ? process.env.BSC_LOCAL_API_KEY || env.BSC_LOCAL_API_KEY || ''
    : '';
  const authorizedProxy = {
    target: apiProxyTarget,
    changeOrigin: true,
    // `headers` covers every proxied request before its body is streamed.
    // The event hook below remains as a defensive override for callers that
    // attach their own non-secret placeholder Authorization value.
    headers: localRuntimeApiKey ? { Authorization: `Bearer ${localRuntimeApiKey}` } : undefined,
    configure(proxy: { on: (event: string, handler: (request: { setHeader: (name: string, value: string) => void }) => void) => void }) {
      if (!localRuntimeApiKey) return;
      proxy.on('proxyReq', (request) => {
        // Force the loopback key server-side so the browser never receives it.
        request.setHeader('Authorization', `Bearer ${localRuntimeApiKey}`);
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

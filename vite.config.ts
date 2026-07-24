import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Vite config executes before it exposes .env values to import.meta.env.
  const env = loadEnv(mode, process.cwd(), '');
  // A command-line target must win over checked-in local defaults so isolated
  // Studio instances can verify a specific backend without editing .env.
  let apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000';
  if (!process.env.VITE_API_PROXY_TARGET && env.VITE_API_PROXY_TARGET) {
    apiProxyTarget = env.VITE_API_PROXY_TARGET;
  }

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
        target: apiProxyTarget,
        changeOrigin: true,
      },
      // Agent OS uses root-level routes in FastAPI rather than the /api router.
      // Keep development requests same-origin so they reach the backend instead
      // of falling through to Vite's SPA HTML response.
      '/agent': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      '/knowledge': {
        target: apiProxyTarget,
        changeOrigin: true,
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

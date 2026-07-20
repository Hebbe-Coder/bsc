// Keep browser requests same-origin. Vite proxies /api in development and the
// FastAPI application serves the production bundle, so this works in both modes.
export const API_BASE = import.meta.env.VITE_API_BASE || '';

export const API_TIMEOUT = 60000;

export const STREAM_TIMEOUT = 120000;

export const DEFAULT_MODEL_PROVIDER = 'deepseek';

export const MODEL_PROVIDERS = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qianwen', label: '通义千问' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'doubao', label: '豆包' },
];

// Keep browser requests same-origin. Vite proxies /api in development and the
// FastAPI application serves the production bundle, so this works in both modes.
export const API_BASE = import.meta.env.VITE_API_BASE || '';

export const API_TIMEOUT = 60000;

const DEFAULT_AGENT_OS_TIMEOUT = 600000;
const MIN_AGENT_OS_TIMEOUT = 60000;

export function resolveAgentOsTimeout(value: string | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= MIN_AGENT_OS_TIMEOUT
    ? parsed
    : DEFAULT_AGENT_OS_TIMEOUT;
}

// A capability runtime can make several sequential model calls in one
// user-visible run. Its request budget must exceed the normal six-step path.
export const AGENT_OS_TIMEOUT = resolveAgentOsTimeout(import.meta.env.VITE_AGENT_OS_TIMEOUT);

export const STREAM_TIMEOUT = 120000;

export const DEFAULT_MODEL_PROVIDER = 'deepseek';

export const MODEL_PROVIDERS = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qianwen', label: '通义千问' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'doubao', label: '豆包' },
];

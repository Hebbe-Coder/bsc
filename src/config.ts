export const API_BASE = import.meta.env.NODE_ENV === 'development' 
  ? 'http://localhost:8000' 
  : '/';

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
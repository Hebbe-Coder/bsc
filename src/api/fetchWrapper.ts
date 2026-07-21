import { API_BASE, API_TIMEOUT } from '../config';

export interface FetchOptions extends RequestInit {
  skipRetry?: boolean;
  maxRetries?: number;
  retryDelay?: number;
  timeout?: number;
}

export interface InterceptorConfig {
  authToken?: string;
  logRequests?: boolean;
  logResponses?: boolean;
}

const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY = 1000;

const shouldRetry = (response: Response, error?: Error): boolean => {
  if (error) {
    return error instanceof DOMException && error.name === 'NetworkError';
  }
  return response.status >= 500 && response.status < 600;
};

const getRetryDelay = (attempt: number, baseDelay: number): number => {
  return baseDelay * Math.pow(2, attempt);
};

export class FetchWrapper {
  private baseUrl: string;
  private timeout: number;
  private interceptorConfig: InterceptorConfig;

  constructor(config: { baseUrl?: string; timeout?: number } = {}) {
    this.baseUrl = config.baseUrl || API_BASE;
    this.timeout = config.timeout || API_TIMEOUT;
    this.interceptorConfig = {
      logRequests: true,
      logResponses: true,
    };
  }

  setAuthToken(token: string | undefined) {
    this.interceptorConfig.authToken = token;
  }

  async fetch<T>(
    url: string,
    options: FetchOptions = {}
  ): Promise<T> {
    const {
      skipRetry = false,
      maxRetries = DEFAULT_MAX_RETRIES,
      retryDelay = DEFAULT_RETRY_DELAY,
      timeout,
      ...requestInit
    } = options;
    
    const fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${url}`;
    
    const requestWithAuth = this.applyAuthHeaders(requestInit);
    
    if (this.interceptorConfig.logRequests) {
      this.logRequest(fullUrl, requestWithAuth);
    }

    let attempt = 0;
    let lastError: Error | undefined;

    while (attempt < (skipRetry ? 1 : maxRetries)) {
      try {
        const response = await this.executeRequest<T>(fullUrl, requestWithAuth, timeout);
        
        if (this.interceptorConfig.logResponses) {
          this.logResponse(response);
        }

        if (response.ok) {
          const data = await response.json();
          return data as T;
        }

        if (!skipRetry && shouldRetry(response)) {
          attempt++;
          if (attempt < maxRetries) {
            await this.delay(getRetryDelay(attempt - 1, retryDelay));
            continue;
          }
        }

        const errorData = await this.parseErrorResponse(response);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorData.error || 'Unknown error'}`);

      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        
        if (skipRetry || !shouldRetry(new Response(), lastError)) {
          throw lastError;
        }

        attempt++;
        if (attempt < maxRetries) {
          await this.delay(getRetryDelay(attempt - 1, retryDelay));
          continue;
        }

        throw lastError;
      }
    }

    throw lastError || new Error('Request failed');
  }

  async request(url: string, options: FetchOptions = {}): Promise<Response> {
    const { timeout, ...requestInit } = options;
    const fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${url}`;
    const requestWithAuth = this.applyAuthHeaders(requestInit);
    if (this.interceptorConfig.logRequests) {
      this.logRequest(fullUrl, requestWithAuth);
    }
    const response = await this.executeRequest(fullUrl, requestWithAuth, timeout);
    if (this.interceptorConfig.logResponses) {
      this.logResponse(response);
    }
    return response;
  }

  async fetchStream(url: string, options: FetchOptions = {}): Promise<ReadableStream> {
    const { timeout, ...requestInit } = options;
    
    const fullUrl = url.startsWith('http') ? url : `${this.baseUrl}${url}`;
    
    const requestWithAuth = this.applyAuthHeaders(requestInit);
    
    if (this.interceptorConfig.logRequests) {
      this.logRequest(fullUrl, requestWithAuth);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout ?? this.timeout);

    try {
      const response = await fetch(fullUrl, {
        ...requestWithAuth,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (this.interceptorConfig.logResponses) {
        this.logResponse(response);
      }

      if (!response.ok) {
        const errorData = await this.parseErrorResponse(response);
        throw new Error(`Stream request failed! status: ${response.status}, message: ${errorData.error || 'Unknown error'}`);
      }

      if (!response.body) {
        throw new Error('Stream response body is null');
      }

      return response.body;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }

  private applyAuthHeaders(options: RequestInit): RequestInit {
    const headers = new Headers(options.headers);
    
    if (this.interceptorConfig.authToken) {
      headers.set('Authorization', `Bearer ${this.interceptorConfig.authToken}`);
    }
    
    headers.set('Content-Type', 'application/json');
    
    return {
      ...options,
      headers,
      credentials: options.credentials ?? 'same-origin',
    };
  }

  private async executeRequest<T>(
    url: string,
    options: RequestInit,
    timeout: number = this.timeout,
  ): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }

  private async parseErrorResponse(response: Response): Promise<{ error?: string; message?: string }> {
    const body = await response.text();
    if (!body) return {};
    try {
      const parsed = JSON.parse(body) as { error?: string; message?: string; detail?: unknown };
      if (typeof parsed.detail === 'string' && !parsed.error && !parsed.message) {
        return { error: parsed.detail };
      }
      return parsed;
    } catch {
      return { error: body };
    }
  }

  private async delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  private logRequest(url: string, options: RequestInit): void {
    console.debug(`[API Request] ${options.method || 'GET'} ${url}`);
  }

  private logResponse(response: Response): void {
    console.debug(`[API Response] ${response.status} ${response.url}`);
  }
}

export const createFetchWrapper = (config?: { baseUrl?: string; timeout?: number }) => {
  return new FetchWrapper(config);
};

export const fetchWrapper = new FetchWrapper();
export const apiFetch = (url: string, options?: FetchOptions) => fetchWrapper.request(url, options);

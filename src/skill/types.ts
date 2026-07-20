import { API_BASE, STREAM_TIMEOUT, API_TIMEOUT } from '../config';
import { apiFetch } from '../api/fetchWrapper';

export type SkillStatus = 'idle' | 'running' | 'completed' | 'failed' | 'waiting';

export interface SkillConfig {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: 'analysis' | 'generation' | 'visualization' | 'export' | 'data';
  requires: string[];
  produces: string[];
  params: SkillParam[];
  source?: 'builtin' | 'project';
  version?: string;
  executable?: boolean;
}

export interface SkillParam {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  required: boolean;
  description: string;
  default?: any;
}

export interface SkillContext {
  [key: string]: any;
}

export interface SkillResult {
  success: boolean;
  data: SkillContext;
  error?: string;
  logs: string[];
}

export interface SkillExecution {
  id: string;
  skillId: string;
  status: SkillStatus;
  progress: number;
  context: SkillContext;
  result?: SkillResult;
  startTime?: Date;
  endTime?: Date;
}

export interface SkillPlan {
  id: string;
  tasks: SkillTask[];
  status: 'draft' | 'confirmed' | 'executing' | 'completed' | 'failed';
  createdAt: Date;
}

export interface SkillTask {
  id: string;
  skillId: string;
  name: string;
  description: string;
  params: Record<string, any>;
  dependsOn: string[];
  status: SkillStatus;
  result?: SkillResult;
}

export type ProgressCallback = (progress: number, status: string, message: string) => void;
export type StreamCallback = (content: string, done: boolean, error?: string) => void;

export abstract class BaseSkill {
  abstract getConfig(): SkillConfig;
  
  abstract execute(context: SkillContext, params?: Record<string, any>): Promise<SkillResult>;

  protected getApiBase(): string {
    return API_BASE;
  }

  protected async callBackendApi(
    skillId: string, 
    inputData: Record<string, any>, 
    streaming: boolean = false,
    llmProvider: string = 'mock',
    useCache: boolean = true
  ): Promise<any> {
    const requestBody = {
      skill_id: skillId,
      params: inputData,
      streaming,
      llm_provider: llmProvider,
      model_name: '',
      use_cache: useCache,
    };

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);

      const response = await apiFetch(`${API_BASE}/api/skill/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.error || `HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`Backend API call failed for skill ${skillId}:`, error);
      throw error;
    }
  }

  protected async streamBackendApi(
    executionId: string,
    onStream: StreamCallback,
    timeout: number = STREAM_TIMEOUT
  ): Promise<string> {
    const decoder = new TextDecoder();
    let fullResult = '';
    const startTime = Date.now();

    try {
      const response = await apiFetch(`${API_BASE}/api/skill/stream/${executionId}`);

      if (!response.ok) {
        throw new Error(`Stream request failed! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No readable stream');
      }

      while (true) {
        if (Date.now() - startTime > timeout) {
          throw new Error('Stream timeout');
        }

        const { done, value } = await reader.read();
        if (done) break;

        const chunks = decoder.decode(value).split('\n\n');
        for (const chunk of chunks) {
          if (chunk.startsWith('data:')) {
            try {
              const data = JSON.parse(chunk.replace(/^data:\s*/, ''));
              if (data.content) {
                fullResult += data.content;
                onStream(data.content, false);
              }
              if (data.status === 'completed') {
                onStream('', true);
                return fullResult;
              }
              if (data.status === 'failed') {
                const errorMsg = data.error || 'Stream failed';
                onStream('', true, errorMsg);
                throw new Error(errorMsg);
              }
            } catch (parseError) {
              console.warn('Failed to parse stream data:', chunk, parseError);
            }
          }
        }
      }

      onStream('', true);
      return fullResult;
    } catch (error) {
      console.error(`Stream API failed for execution ${executionId}:`, error);
      onStream('', true, error instanceof Error ? error.message : 'Unknown error');
      throw error;
    }
  }

  protected async pollExecutionResult(
    executionId: string,
    onProgress?: ProgressCallback,
    timeout: number = 60000,
    pollInterval: number = 1000
  ): Promise<any> {
    const API_BASE = this.getApiBase();
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      try {
        const response = await apiFetch(`${API_BASE}/api/skill/execution/${executionId}`);
        const result = await response.json();

        if (onProgress && result.status) {
          const progress = result.status === 'completed' ? 100 : 
                          result.status === 'failed' ? 0 : 50;
          onProgress(progress, result.status, '');
        }

        if (result.status === 'completed' || result.status === 'failed') {
          return result;
        }
      } catch (error) {
        console.error(`Polling failed for ${executionId}:`, error);
      }

      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }

    throw new Error('Polling timeout');
  }

  protected parseJsonResult(result: string): any {
    try {
      const jsonMatch = result.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
      return JSON.parse(result);
    } catch {
      return null;
    }
  }

  protected parseMarkdownResult(result: string): any {
    const lines = result.split('\n');
    const parsed: any = {};
    let currentSection = '';
    let currentList: string[] = [];

    for (const line of lines) {
      const trimmed = line.trim();
      
      if (trimmed.startsWith('# ')) {
        if (currentSection && currentList.length > 0) {
          parsed[currentSection] = currentList;
        }
        parsed.title = trimmed.replace('# ', '');
        currentSection = '';
        currentList = [];
      } else if (trimmed.startsWith('## ')) {
        if (currentSection && currentList.length > 0) {
          parsed[currentSection] = currentList;
        }
        currentSection = trimmed.replace('## ', '');
        currentList = [];
      } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ') || trimmed.startsWith('1.')) {
        const item = trimmed.replace(/^[-*] |^\d+\./, '').trim();
        currentList.push(item);
      } else if (trimmed && !trimmed.startsWith('#')) {
        if (currentSection) {
          parsed[currentSection] = trimmed;
        } else if (!parsed.description) {
          parsed.description = trimmed;
        }
      }
    }

    if (currentSection && currentList.length > 0) {
      parsed[currentSection] = currentList;
    }

    return parsed;
  }

  protected log(message: string): string[] {
    return [message];
  }
}

export type SkillConstructor = new () => BaseSkill;

import { fetchWrapper } from './fetchWrapper';
import { mockBscApi } from './mockApi';
import { 
  isBusinessSystem, 
  isCompileResult, 
  isSkillExecutionResponse, 
  isSkillsArray 
} from './typeGuards';

export interface BusinessSystem {
  name?: string;
  description?: string;
  version?: string;
  business_domain: string;
  objectives: Array<{
    objective: string;
    target: string;
    priority?: string;
    kpi?: string;
  }>;
  roles: Array<{
    role: string;
    responsibilities: string[];
  }>;
  workflow: Array<{
    step: number;
    name: string;
    action: string;
    owner?: string;
    sla?: string;
  }>;
  metrics: Array<{
    name: string;
    formula: string;
    target: string;
    owner?: string;
    current?: number;
    target_value?: number;
  }>;
  risks: Array<{
    risk: string;
    severity: string;
    mitigation: string;
    category?: string;
  }>;
  strategy: {
    growth_opportunities?: Array<{
      opportunity: string;
      potential: string;
    }>;
  };
  optimization: {
    recommendations?: Array<{
      recommendation: string;
      impact: string;
    }>;
  };
  report?: {
    title?: string;
    executive_summary?: string;
    sections?: Array<{
      title: string;
      content: string;
    }>;
  };
  composed?: {
    report?: {
      title?: string;
      executive_summary?: string;
      sections?: Array<{
        title: string;
        content: string;
      }>;
    };
  };
}

export interface CompileResult {
  business_system: BusinessSystem;
  pipeline: {
    stages: Array<{
      agent: string;
      key: string;
      display: string;
      status: string;
      duration_ms: number;
    }>;
    total_ms: number;
  };
  summary: string;
  workspace: {
    dashboard?: {
      business_domain?: string;
      objectives_count?: number;
      workflow_steps?: number;
      risk_count?: number;
      strategy_count?: number;
      recommendation_count?: number;
    };
    report?: {
      title?: string;
      summary?: string;
      sections?: Array<{
        title: string;
        content: string;
      }>;
    };
    ppt_blueprint?: {
      slide_count?: number;
      slides?: Array<{
        type: string;
        title?: string;
        content?: string;
        items?: string[];
        steps?: string[];
        headers?: string[];
        data?: string[][];
      }>;
    };
  };
}

export interface ExportResult {
  exports: {
    json?: BusinessSystem;
    html?: string;
    ppt?: {
      slides: Array<{
        slide_type: string;
        title?: string;
        subtitle?: string;
        items?: string[];
        steps?: string[];
        headers?: string[];
        data?: string[][];
        content?: string;
      }>;
      theme: string;
      slide_count: number;
    };
    word?: {
      content_base64: string;
      mime_type: string;
    };
    markdown?: string;
    pdf?: {
      content_base64: string;
      mime_type: string;
    };
    visuals?: { type: string; content: string }[];
  };
  formats: string[];
  summary: string;
  errors: string[];
}

export interface Skill {
  id: string;
  name: string;
  description: string;
}

export interface ExecuteSkillRequest {
  skill_id: string;
  params: Record<string, string>;
  streaming?: boolean;
  llm_provider?: string;
  model_name?: string;
  use_cache?: boolean;
}

export interface SkillExecutionResponse {
  execution_id: string;
  status: string;
  result?: string;
  from_cache?: boolean;
}

export interface StageRequest {
  input: string;
  stage_key: string;
}

export interface StageResponse {
  stage: string;
  data: Record<string, unknown>;
}

const extractData = <T>(data: unknown, shouldExtract: boolean = true): T => {
  if (shouldExtract && typeof data === 'object' && data !== null && 'data' in data) {
    return (data as { data: T }).data;
  }
  return data as T;
};

const realBscApi = {
  compile: async (input: string, templateId?: string): Promise<CompileResult> => {
    const response = await fetchWrapper.fetch<unknown>('/bsc/compile', {
      method: 'POST',
      body: JSON.stringify({
        input,
        output_types: ['json'],
        template_id: templateId,
      }),
    });
    const result = extractData<unknown>(response);
    if (!isCompileResult(result)) {
      throw new Error('Invalid CompileResult structure');
    }
    return result;
  },

  compileSync: async (input: string): Promise<CompileResult> => {
    const response = await fetchWrapper.fetch<unknown>('/bsc/compile/sync', {
      method: 'POST',
      body: JSON.stringify({
        input,
        output_types: ['json'],
      }),
    });
    const result = extractData<unknown>(response);
    if (!isCompileResult(result)) {
      throw new Error('Invalid CompileResult structure');
    }
    return result;
  },

  export: async (businessSystem: BusinessSystem, outputTypes: string[] = ['html', 'json']): Promise<ExportResult> => {
    const response = await fetchWrapper.fetch<ExportResult>('/bsc/export', {
      method: 'POST',
      body: JSON.stringify({
        business_system: businessSystem,
        output_types: outputTypes,
      }),
    });
    return extractData(response);
  },

  health: async (): Promise<{ pipeline: string; llm: { status: string; provider: string } }> => {
    const response = await fetchWrapper.fetch<{ pipeline: string; llm: { status: string; provider: string } }>('/bsc/health');
    return extractData(response);
  },

  stages: async (): Promise<Array<{ key: string; agent: string; display: string; type: string }>> => {
    const response = await fetchWrapper.fetch<unknown>('/bsc/stages');
    const data = extractData<{ stages: Array<{ key: string; agent: string; display: string; type: string }> }>(response);
    return data.stages || [];
  },

  getSkills: async (): Promise<Skill[]> => {
    const response = await fetchWrapper.fetch<unknown>('/api/skill/list');
    const result = extractData(response, false);
    
    if (isObjectWithValue(result)) {
      return isSkillsArray(result.value) ? result.value : [];
    }
    
    if (isSkillsArray(result)) {
      return result;
    }
    
    return [];
  },

  executeSkill: async (request: ExecuteSkillRequest): Promise<SkillExecutionResponse> => {
    const response = await fetchWrapper.fetch<unknown>('/api/skill/execute', {
      method: 'POST',
      body: JSON.stringify(request),
    });
    const result = extractData(response, false);
    if (!isSkillExecutionResponse(result)) {
      throw new Error('Invalid SkillExecutionResponse structure');
    }
    return result;
  },

  streamSkill: async (executionId: string, signal?: AbortSignal): Promise<ReadableStream> => {
    return fetchWrapper.fetchStream(`/api/skill/stream/${executionId}`, { signal });
  },

  getSkillResult: async (executionId: string): Promise<SkillExecutionResponse> => {
    const response = await fetchWrapper.fetch<unknown>(`/api/skill/execution/${executionId}`);
    const result = extractData(response, false);
    if (!isSkillExecutionResponse(result)) {
      throw new Error('Invalid SkillExecutionResponse structure');
    }
    return result;
  },

  executeStage: async (request: StageRequest): Promise<StageResponse> => {
    const response = await fetchWrapper.fetch<StageResponse>('/bsc/stage', {
      method: 'POST',
      body: JSON.stringify(request),
    });
    return extractData(response);
  },
};

const isObjectWithValue = (obj: unknown): obj is { value: unknown } => {
  return typeof obj === 'object' && obj !== null && 'value' in obj;
};

export const bscApi = import.meta.env.VITE_USE_MOCK === 'true' ? mockBscApi : realBscApi;

export default bscApi;
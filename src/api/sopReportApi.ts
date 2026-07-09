import { fetchWrapper } from './fetchWrapper';
import type { BusinessSystem } from './bscApi';

export interface SOPReport {
  title: string;
  generated_at: string;
  overview: SOPOverview;
  workflow_detail: SOPWorkflowDetail;
  role_responsibilities: SOPRoleResponsibilities;
  sla_summary: SLASummary;
  risk_assessment: RiskAssessment;
  flowchart: FlowchartData;
}

export interface SOPOverview {
  title: string;
  description: string;
  business_domain: string;
  core_objectives: string[];
  total_steps: number;
  total_roles: number;
  total_sla_items: number;
  has_escalation: boolean;
  estimated_duration: string;
}

export interface SOPWorkflowDetail {
  title: string;
  description: string;
  steps: WorkflowStep[];
  total_steps: number;
}

export interface WorkflowStep {
  step: string | number;
  name: string;
  action: string;
  role: string;
  input: string;
  output: string;
  sla: string;
  risks: string[];
  mitigations: string[];
}

export interface SOPRoleResponsibilities {
  title: string;
  description: string;
  roles: RoleDetail[];
  total_roles: number;
}

export interface RoleDetail {
  name: string;
  department: string;
  level: string;
  headcount: number;
  responsible_steps: { step: string | number; name: string }[];
  responsibilities: string[];
}

export interface SLASummary {
  title: string;
  description: string;
  sla_items: SLAMetric[];
  step_slas: StepSLA[];
  total_sla_items: number;
  total_step_slas: number;
  estimated_total_duration: string;
}

export interface SLAMetric {
  metric: string;
  target: string;
  owner: string;
  type: string;
  formula?: string;
}

export interface StepSLA {
  step: string | number;
  name: string;
  sla: string;
}

export interface RiskAssessment {
  title: string;
  description: string;
  risks: RiskItem[];
  total_risks: number;
  severity_distribution: Record<string, number>;
}

export interface RiskItem {
  risk: string;
  severity: string;
  probability: string;
  mitigation: string;
  category: string;
}

export interface FlowchartData {
  title: string;
  description: string;
  nodes: FlowchartNode[];
  edges: FlowchartEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface FlowchartNode {
  id: string;
  step: string | number;
  name: string;
  role: string;
  type: string;
}

export interface FlowchartEdge {
  from: string;
  to: string;
  label: string;
}

const extractData = <T>(data: unknown): T => {
  if (typeof data === 'object' && data !== null && 'data' in data) {
    return (data as { data: T }).data;
  }
  return data as T;
};

export const sopReportApi = {
  generateReport: async (businessSystem: BusinessSystem): Promise<SOPReport> => {
    const response = await fetchWrapper.fetch<unknown>('/sop-report/generate', {
      method: 'POST',
      body: JSON.stringify({ business_system: businessSystem }),
    });
    return extractData(response);
  },

  exportReport: async (businessSystem: BusinessSystem, format: 'html' | 'markdown' | 'pptx'): Promise<string> => {
    const response = await fetch('/sop-report/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ business_system: businessSystem, format }),
    });
    return response.text();
  },

  getOverview: async (businessSystem: BusinessSystem): Promise<SOPOverview> => {
    const response = await fetchWrapper.fetch<unknown>('/sop-report/overview', {
      method: 'POST',
      body: JSON.stringify({ business_system: businessSystem }),
    });
    return extractData(response);
  },

  getWorkflow: async (businessSystem: BusinessSystem): Promise<SOPWorkflowDetail> => {
    const response = await fetchWrapper.fetch<unknown>('/sop-report/workflow', {
      method: 'POST',
      body: JSON.stringify({ business_system: businessSystem }),
    });
    return extractData(response);
  },

  getRoles: async (businessSystem: BusinessSystem): Promise<SOPRoleResponsibilities> => {
    const response = await fetchWrapper.fetch<unknown>('/sop-report/roles', {
      method: 'POST',
      body: JSON.stringify({ business_system: businessSystem }),
    });
    return extractData(response);
  },

  getSLA: async (businessSystem: BusinessSystem): Promise<SLASummary> => {
    const response = await fetchWrapper.fetch<unknown>('/sop-report/sla', {
      method: 'POST',
      body: JSON.stringify({ business_system: businessSystem }),
    });
    return extractData(response);
  },

  getRisk: async (businessSystem: BusinessSystem): Promise<RiskAssessment> => {
    const response = await fetchWrapper.fetch<unknown>('/sop-report/risk', {
      method: 'POST',
      body: JSON.stringify({ business_system: businessSystem }),
    });
    return extractData(response);
  },

  getFlowchart: async (businessSystem: BusinessSystem): Promise<FlowchartData> => {
    const response = await fetchWrapper.fetch<unknown>('/sop-report/flowchart', {
      method: 'POST',
      body: JSON.stringify({ business_system: businessSystem }),
    });
    return extractData(response);
  },

  downloadReport: async (businessSystem: BusinessSystem, format: 'html' | 'markdown') => {
    const response = await fetch('/sop-report/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ business_system: businessSystem, format }),
    });

    if (!response.ok) {
      throw new Error('下载失败');
    }

    const blob = await response.blob();
    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = `sop_report.${format}`;
    
    if (contentDisposition) {
      const match = contentDisposition.match(/filename=(.+)/);
      if (match) {
        filename = match[1].replace(/['"]/g, '');
      }
    }

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },
};

export default sopReportApi;
import { BaseSkill, SkillConfig, SkillContext, SkillResult } from '../types';

export class PrdAnalysisSkill extends BaseSkill {
  getConfig(): SkillConfig {
    return {
      id: 'prd-analysis',
      name: 'PRD分析',
      description: '解析PRD文档结构，提取关键信息',
      icon: 'FileText',
      category: 'analysis',
      requires: ['raw_prd'],
      produces: ['prd_structure', 'business_domain', 'objectives', 'workflow', 'risks'],
      params: [
        { name: 'prdContent', type: 'string', required: true, description: 'PRD文档内容' },
      ],
    };
  }

  async execute(context: SkillContext, params?: Record<string, string>): Promise<SkillResult> {
    const prdContent = params?.prdContent || context.raw_prd;
    
    if (!prdContent) {
      return {
        success: false,
        data: {},
        error: 'PRD内容不能为空',
        logs: ['错误：PRD内容为空'],
      };
    }

    try {
      const logs: string[] = [];
      logs.push('开始分析PRD文档...');
      logs.push('正在调用AI分析引擎...');

      const response = await this.callBackendApi('prd-analysis', { prd_content: prdContent }, true);
      
      let resultContent = '';
      if (response.status === 'streaming') {
        resultContent = await this.streamBackendApi(response.execution_id, () => {});
      } else if (response.status === 'completed') {
        resultContent = response.result || '';
      }

      if (!resultContent) {
        return {
          success: false,
          data: {},
          error: 'AI分析返回为空',
          logs: [...logs, '错误：AI分析返回为空'],
        };
      }

      logs.push('AI分析完成，正在解析结果...');

      const structure = this.parsePrdResult(resultContent);
      logs.push(`识别到业务领域: ${structure.business_domain}`);
      logs.push(`识别到${structure.objectives.length}个业务目标`);
      logs.push(`识别到${structure.workflow.length}个流程步骤`);
      logs.push(`识别到${structure.risks.length}个风险点`);

      return {
        success: true,
        data: {
          prd_structure: structure,
          business_domain: structure.business_domain,
          objectives: structure.objectives,
          workflow: structure.workflow,
          risks: structure.risks,
          raw_result: resultContent,
        },
        logs,
      };
    } catch (error) {
      console.error('PRD分析失败:', error);
      return {
        success: false,
        data: {},
        error: error instanceof Error ? error.message : 'PRD分析失败',
        logs: ['PRD分析失败'],
      };
    }
  }

  private parsePrdResult(content: string) {
    const lines = content.split('\n');
    const structure: any = {
      business_domain: '',
      objectives: [],
      workflow: [],
      risks: [],
      features: [],
      requirements: [],
    };

    let currentSection = '';

    for (const line of lines) {
      const trimmed = line.trim();
      
      if (trimmed.startsWith('# ')) {
        structure.business_domain = trimmed.replace('# ', '').trim();
      } else if (trimmed.startsWith('## ') || trimmed.startsWith('### ')) {
        currentSection = trimmed.replace(/^#+\s*/, '').trim();
      } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ') || trimmed.startsWith('1.')) {
        const item = trimmed.replace(/^[-*] |^\d+\./, '').trim();
        
        switch (currentSection) {
          case '业务目标':
          case '目标':
          case 'Objectives':
          case '产品目标':
            structure.objectives.push({ objective: item, target: '待定义' });
            break;
          case '流程设计':
          case '工作流程':
          case 'Workflow':
          case '业务流程':
            structure.workflow.push({ step: structure.workflow.length + 1, name: item, action: item });
            break;
          case '风险分析':
          case '风险':
          case 'Risks':
            structure.risks.push({ risk: item, severity: 'medium', mitigation: '待定义' });
            break;
          case '核心功能':
          case '功能需求':
          case 'Features':
            structure.features.push(item);
            break;
          default:
            if (!structure.business_domain && item.length > 0) {
              structure.business_domain = item.substring(0, 50);
            }
        }
      }
    }

    if (!structure.business_domain) {
      structure.business_domain = '业务系统分析';
    }

    if (structure.objectives.length === 0) {
      structure.objectives = [{ objective: '提升业务效率', target: '待定义' }];
    }

    return structure;
  }
}
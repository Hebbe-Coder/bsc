import { BaseSkill, SkillConfig, SkillContext, SkillResult } from '../types';

export class ObjectiveExtractionSkill extends BaseSkill {
  getConfig(): SkillConfig {
    return {
      id: 'objective-extraction',
      name: '目标提取',
      description: '从PRD结构中提取业务目标和关键结果',
      icon: 'Target',
      category: 'analysis',
      requires: ['prd_structure'],
      produces: ['objectives_detail', 'kpi_list', 'target_values'],
      params: [],
    };
  }

  async execute(context: SkillContext): Promise<SkillResult> {
    const prdStructure = context.prd_structure;
    
    if (!prdStructure) {
      return {
        success: false,
        data: {},
        error: '缺少PRD结构数据',
        logs: ['错误：缺少PRD结构数据'],
      };
    }

    try {
      const logs: string[] = [];
      logs.push('开始提取业务目标...');
      logs.push('正在调用AI分析引擎...');

      const businessContent = JSON.stringify(prdStructure, null, 2);
      const response = await this.callBackendApi('objective-extraction', { business_content: businessContent }, true);
      
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

      const objectives = prdStructure.objectives || [];
      const details = objectives.map((obj: any, idx: number) => ({
        id: `obj-${idx + 1}`,
        objective: obj.objective || obj,
        target: obj.target || '待定义',
        priority: this.determinePriority(idx),
        kpi: this.generateKpi(obj.objective || obj),
        status: 'pending',
      }));

      const kpiList = details.map(d => d.kpi);
      logs.push(`提取到${details.length}个目标`);
      logs.push(`生成${kpiList.length}个KPI指标`);

      return {
        success: true,
        data: {
          objectives_detail: details,
          kpi_list: kpiList,
          target_values: details.map(() => ({ current: 0, target: 100 })),
          raw_result: resultContent,
        },
        logs,
      };
    } catch (error) {
      console.error('目标提取失败:', error);
      return {
        success: false,
        data: {},
        error: error instanceof Error ? error.message : '目标提取失败',
        logs: ['目标提取失败'],
      };
    }
  }

  private determinePriority(index: number): string {
    const priorities = ['high', 'high', 'medium', 'medium', 'low'];
    return priorities[index] || 'low';
  }

  private generateKpi(objective: string): string {
    const kpiTemplates: Record<string, string> = {
      '效率': '效率提升率',
      '增长': '增长率',
      '成本': '成本降低率',
      '质量': '质量合格率',
      '用户': '用户满意度',
      '营收': '营收增长率',
      '转化': '转化率',
      '留存': '留存率',
    };

    for (const [keyword, kpi] of Object.entries(kpiTemplates)) {
      if (objective.includes(keyword)) {
        return kpi;
      }
    }

    return '达成率';
  }
}
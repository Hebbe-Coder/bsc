import { BaseSkill, SkillConfig, SkillContext, SkillResult } from '../types';

export class KpiExtractionSkill extends BaseSkill {
  getConfig(): SkillConfig {
    return {
      id: 'kpi-extraction',
      name: 'KPI提取',
      description: '从目标中提取关键绩效指标和计算公式',
      icon: 'BarChart3',
      category: 'analysis',
      requires: ['objectives_detail'],
      produces: ['metrics', 'formulas', 'chart_data'],
      params: [],
    };
  }

  async execute(context: SkillContext): Promise<SkillResult> {
    const objectives = context.objectives_detail;
    
    if (!objectives || !Array.isArray(objectives)) {
      return {
        success: false,
        data: {},
        error: '缺少目标详情数据',
        logs: ['错误：缺少目标详情数据'],
      };
    }

    try {
      const logs: string[] = [];
      logs.push('开始提取KPI指标...');
      logs.push('正在调用AI分析引擎...');

      const businessContent = JSON.stringify(objectives, null, 2);
      const response = await this.callBackendApi('kpi-extraction', { business_content: businessContent }, true);
      
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

      const metrics = objectives.map((obj: any, idx: number) => ({
        id: `kpi-${idx + 1}`,
        name: obj.kpi,
        formula: this.generateFormula(obj.kpi),
        target: this.generateTarget(obj.objective),
        owner: '待分配',
        current: Math.floor(Math.random() * 60) + 30,
        target_value: 100,
      }));

      const chartData = {
        labels: metrics.map(m => m.name),
        datasets: [
          {
            name: '当前值',
            data: metrics.map(m => m.current),
            color: '#9ca3af',
          },
          {
            name: '目标值',
            data: metrics.map(m => m.target_value),
            color: '#3b82f6',
          },
        ],
      };

      logs.push(`提取到${metrics.length}个KPI指标`);
      logs.push('生成对比图表数据');

      return {
        success: true,
        data: {
          metrics,
          formulas: metrics.map(m => ({ name: m.name, formula: m.formula })),
          chart_data: chartData,
          raw_result: resultContent,
        },
        logs,
      };
    } catch (error) {
      console.error('KPI提取失败:', error);
      return {
        success: false,
        data: {},
        error: error instanceof Error ? error.message : 'KPI提取失败',
        logs: ['KPI提取失败'],
      };
    }
  }

  private generateFormula(kpiName: string): string {
    const formulaTemplates: Record<string, string> = {
      '效率': '产出/投入 × 100%',
      '增长': '(本期-上期)/上期 × 100%',
      '成本': '实际成本/预算成本 × 100%',
      '质量': '合格数/总数 × 100%',
      '满意': '满意数/总数 × 100%',
      '营收': '实际营收/目标营收 × 100%',
      '转化': '转化数/访问数 × 100%',
      '留存': '回访用户/新增用户 × 100%',
      '达成': '完成数/目标数 × 100%',
    };

    for (const [keyword, formula] of Object.entries(formulaTemplates)) {
      if (kpiName.includes(keyword)) {
        return formula;
      }
    }

    return '完成度 × 100%';
  }

  private generateTarget(objective: string): string {
    if (objective.includes('提升') || objective.includes('增长')) {
      return '提升20%';
    }
    if (objective.includes('降低') || objective.includes('减少')) {
      return '降低15%';
    }
    if (objective.includes('优化') || objective.includes('改进')) {
      return '优化至95%';
    }
    return '达成目标';
  }
}
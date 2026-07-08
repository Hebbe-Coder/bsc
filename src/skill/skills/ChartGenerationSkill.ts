import { BaseSkill, SkillConfig, SkillContext, SkillResult } from '../types';

export class ChartGenerationSkill extends BaseSkill {
  getConfig(): SkillConfig {
    return {
      id: 'chart-generation',
      name: '图表生成',
      description: '根据数据生成多种类型的可视化图表',
      icon: 'PieChart',
      category: 'visualization',
      requires: ['metrics', 'objectives_detail'],
      produces: ['charts', 'visualization_data'],
      params: [
        { name: 'chartType', type: 'string', required: false, description: '图表类型', default: 'bar' },
      ],
    };
  }

  async execute(context: SkillContext, params?: Record<string, any>): Promise<SkillResult> {
    const metrics = context.metrics;
    const objectives = context.objectives_detail;
    
    if (!metrics || !Array.isArray(metrics)) {
      return {
        success: false,
        data: {},
        error: '缺少指标数据',
        logs: ['错误：缺少指标数据'],
      };
    }

    try {
      const logs: string[] = [];
      logs.push('开始生成图表...');
      logs.push('正在调用AI分析引擎...');

      const dataDescription = JSON.stringify({ metrics, objectives }, null, 2);
      const response = await this.callBackendApi('chart-generation', { data_description: dataDescription }, true);
      
      let resultContent = '';
      if (response.status === 'streaming') {
        resultContent = await this.streamBackendApi(response.execution_id, () => {});
      } else if (response.status === 'completed') {
        resultContent = response.result || '';
      }

      logs.push('AI分析完成，正在生成图表...');

      const charts = this.generateCharts(metrics, objectives);
      logs.push(`生成${charts.length}种图表`);

      let chartConfig = null;
      if (resultContent) {
        chartConfig = this.parseJsonResult(resultContent);
        if (chartConfig) {
          logs.push('AI生成的图表配置已解析');
        }
      }

      return {
        success: true,
        data: {
          charts,
          chart_config: chartConfig,
          visualization_data: {
            kpi_bar: charts.find(c => c.type === 'bar'),
            risk_pie: charts.find(c => c.type === 'pie'),
            objective_radar: charts.find(c => c.type === 'radar'),
          },
          raw_result: resultContent,
        },
        logs,
      };
    } catch (error) {
      console.error('图表生成失败:', error);
      return {
        success: false,
        data: {},
        error: error instanceof Error ? error.message : '图表生成失败',
        logs: ['图表生成失败'],
      };
    }
  }

  private generateCharts(metrics: any[], objectives: any[]) {
    const charts = [];

    charts.push({
      type: 'bar',
      title: 'KPI完成情况',
      data: {
        type: 'bar',
        labels: metrics.map(m => m.name),
        datasets: [
          { name: '当前值', data: metrics.map(m => m.current), color: '#3b82f6' },
          { name: '目标值', data: metrics.map(m => m.target_value), color: '#9ca3af' },
        ],
      },
    });

    const priorityCounts = { high: 0, medium: 0, low: 0 };
    (objectives || []).forEach((obj: any) => {
      if (priorityCounts[obj.priority as keyof typeof priorityCounts] !== undefined) {
        priorityCounts[obj.priority as keyof typeof priorityCounts]++;
      }
    });
    charts.push({
      type: 'pie',
      title: '目标优先级分布',
      data: {
        type: 'pie',
        labels: ['高优先级', '中优先级', '低优先级'],
        datasets: [{ name: '数量', data: [priorityCounts.high, priorityCounts.medium, priorityCounts.low], color: ['#ef4444', '#f59e0b', '#10b981'] }],
      },
    });

    const riskSeverity = { critical: 2, high: 3, medium: 2, low: 1 };
    charts.push({
      type: 'radar',
      title: '能力雷达图',
      data: {
        type: 'radar',
        labels: ['业务能力', '技术能力', '运营能力', '创新能力', '团队协作'],
        datasets: [{ name: '当前能力', data: [75, 80, 65, 70, 85], color: '#8b5cf6' }],
      },
    });

    charts.push({
      type: 'funnel',
      title: '业务流程转化',
      data: {
        type: 'funnel',
        labels: ['需求收集', '方案设计', '开发实现', '测试验证', '上线发布'],
      },
    });

    return charts;
  }
}
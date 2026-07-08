import { BaseSkill, SkillConfig, SkillContext, SkillResult } from '../types';

export class ReportGenerationSkill extends BaseSkill {
  getConfig(): SkillConfig {
    return {
      id: 'report-generation',
      name: '报告生成',
      description: '生成详细的业务分析报告文档',
      icon: 'FileText',
      category: 'generation',
      requires: ['business_domain', 'objectives_detail', 'metrics', 'risk_assessment', 'growth_opportunities'],
      produces: ['report_content', 'executive_summary', 'sections'],
      params: [],
    };
  }

  async execute(context: SkillContext): Promise<SkillResult> {
    const businessDomain = context.business_domain;
    const objectives = context.objectives_detail;
    const metrics = context.metrics;
    const riskAssessment = context.risk_assessment;
    const growthOpportunities = context.growth_opportunities;
    
    if (!businessDomain) {
      return {
        success: false,
        data: {},
        error: '缺少业务领域数据',
        logs: ['错误：缺少业务领域数据'],
      };
    }

    try {
      const logs: string[] = [];
      logs.push('开始生成报告...');
      logs.push('正在调用AI分析引擎...');

      const businessContent = JSON.stringify({ 
        business_domain: businessDomain, 
        objectives, 
        metrics, 
        risk_assessment: riskAssessment,
        growth_opportunities: growthOpportunities
      }, null, 2);
      const response = await this.callBackendApi('report-generation', { business_content: businessContent }, true);
      
      let resultContent = '';
      if (response.status === 'streaming') {
        resultContent = await this.streamBackendApi(response.execution_id, () => {});
      } else if (response.status === 'completed') {
        resultContent = response.result || '';
      }

      logs.push('AI分析完成，正在生成报告...');

      const executiveSummary = this.generateExecutiveSummary(businessDomain, objectives || [], metrics || []);
      const sections = this.generateSections(objectives || [], metrics || [], riskAssessment || [], growthOpportunities || []);
      const reportContent = this.generateFullReport(businessDomain, executiveSummary, sections);

      logs.push('生成执行摘要');
      logs.push(`生成${sections.length}个章节`);
      logs.push('生成完整报告');

      return {
        success: true,
        data: {
          report_content: reportContent,
          executive_summary: executiveSummary,
          sections,
          raw_result: resultContent,
        },
        logs,
      };
    } catch (error) {
      console.error('报告生成失败:', error);
      return {
        success: false,
        data: {},
        error: error instanceof Error ? error.message : '报告生成失败',
        logs: ['报告生成失败'],
      };
    }
  }

  private generateExecutiveSummary(domain: string, objectives: any[], metrics: any[]): string {
    const achievedMetrics = metrics.filter((m: any) => m.current >= m.target_value * 0.8).length;
    const totalMetrics = metrics.length;
    const achievementRate = totalMetrics > 0 ? Math.round((achievedMetrics / totalMetrics) * 100) : 0;

    return `本报告对${domain}进行了全面的业务分析。通过深入研究，我们识别了${objectives.length}个核心业务目标，建立了${metrics.length}个关键绩效指标体系。当前关键指标达成率为${achievementRate}%，整体业务运行状况良好。报告还分析了潜在风险因素，并提出了针对性的优化建议，为业务发展提供决策支持。`;
  }

  private generateSections(objectives: any[], metrics: any[], riskAssessment: any[], growthOpportunities: any[]): Array<{ title: string; content: string }> {
    const sections: Array<{ title: string; content: string }> = [];

    if (objectives.length > 0) {
      sections.push({
        title: '业务目标',
        content: objectives.map((o: any, i: number) => 
          `${i + 1}. ${o.objective} - 目标：${o.target}（优先级：${o.priority}）`
        ).join('\n'),
      });
    }

    if (metrics.length > 0) {
      sections.push({
        title: '关键指标',
        content: metrics.map((m: any) => 
          `${m.name}：当前值${m.current}，目标值${m.target_value}，计算公式：${m.formula}`
        ).join('\n'),
      });
    }

    if (riskAssessment.length > 0) {
      sections.push({
        title: '风险评估',
        content: riskAssessment.map((r: any) => 
          `${r.risk}（严重程度：${r.severity}，优先级：${r.priority}）\n应对策略：${r.mitigation}`
        ).join('\n\n'),
      });
    }

    if (growthOpportunities.length > 0) {
      sections.push({
        title: '增长机会',
        content: growthOpportunities.map((o: any, i: number) => 
          `${i + 1}. ${o.opportunity} - 潜在增长：${o.potential}（优先级：${o.priority}）`
        ).join('\n'),
      });
    }

    return sections;
  }

  private generateFullReport(domain: string, summary: string, sections: Array<{ title: string; content: string }>): string {
    let report = `# ${domain}业务分析报告\n\n`;
    report += `## 执行摘要\n\n${summary}\n\n`;
    
    sections.forEach((section, idx) => {
      report += `${idx + 2}. ${section.title}\n\n${section.content}\n\n`;
    });
    
    report += `---\n\n*报告生成时间：${new Date().toLocaleString('zh-CN')}*\n*分析工具：BSC智能分析系统*`;
    
    return report;
  }
}
import { BaseSkill, SkillConfig, SkillContext, SkillResult } from '../types';

export class RiskAssessmentSkill extends BaseSkill {
  getConfig(): SkillConfig {
    return {
      id: 'risk-assessment',
      name: '风险评估',
      description: '分析风险等级、影响程度和应对策略',
      icon: 'AlertTriangle',
      category: 'analysis',
      requires: ['risks'],
      produces: ['risk_assessment', 'mitigation_strategies', 'risk_chart'],
      params: [],
    };
  }

  async execute(context: SkillContext): Promise<SkillResult> {
    const risks = context.risks;
    
    if (!risks || !Array.isArray(risks)) {
      return {
        success: false,
        data: {},
        error: '缺少风险数据',
        logs: ['错误：缺少风险数据'],
      };
    }

    try {
      const logs: string[] = [];
      logs.push('开始风险评估...');
      logs.push('正在调用AI分析引擎...');

      const businessContext = JSON.stringify(risks, null, 2);
      const response = await this.callBackendApi('risk-assessment', { business_context: businessContext }, true);
      
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

      const assessment = risks.map((risk: any, idx: number) => {
        const severity = this.determineSeverity(risk);
        const impact = this.calculateImpact(severity);
        const probability = this.calculateProbability(risk);
        const priority = this.calculatePriority(impact, probability);
        const strategy = this.generateMitigationStrategy(risk, severity);

        return {
          id: `risk-${idx + 1}`,
          risk: risk.risk || risk,
          category: risk.category || '运营风险',
          severity,
          impact,
          probability,
          priority,
          mitigation: strategy,
        };
      });

      const riskChart = {
        type: 'pie',
        labels: ['严重', '高', '中', '低'],
        datasets: [{
          name: '风险数量',
          data: [
            assessment.filter(a => a.severity === 'critical').length,
            assessment.filter(a => a.severity === 'high').length,
            assessment.filter(a => a.severity === 'medium').length,
            assessment.filter(a => a.severity === 'low').length,
          ],
          color: ['#ef4444', '#f59e0b', '#3b82f6', '#10b981'],
        }],
      };

      logs.push(`评估${assessment.length}个风险`);
      logs.push(`严重风险: ${assessment.filter(a => a.severity === 'critical').length}个`);
      logs.push(`高风险: ${assessment.filter(a => a.severity === 'high').length}个`);

      return {
        success: true,
        data: {
          risk_assessment: assessment,
          mitigation_strategies: assessment.map(a => ({
            risk: a.risk,
            strategy: a.mitigation,
            priority: a.priority,
          })),
          risk_chart: riskChart,
          raw_result: resultContent,
        },
        logs,
      };
    } catch (error) {
      console.error('风险评估失败:', error);
      return {
        success: false,
        data: {},
        error: error instanceof Error ? error.message : '风险评估失败',
        logs: ['风险评估失败'],
      };
    }
  }

  private determineSeverity(risk: any): string {
    const severity = risk.severity?.toLowerCase();
    if (severity === 'critical' || severity === '严重') return 'critical';
    if (severity === 'high' || severity === '高') return 'high';
    if (severity === 'low' || severity === '低') return 'low';
    
    const keywords: Record<string, string> = {
      '系统崩溃': 'critical',
      '数据丢失': 'critical',
      '安全漏洞': 'critical',
      '无法访问': 'critical',
      '性能问题': 'high',
      '延迟': 'high',
      '功能缺陷': 'medium',
      '用户体验': 'medium',
      '文档缺失': 'low',
      '界面优化': 'low',
    };
    
    const riskText = risk.risk || '';
    for (const [keyword, level] of Object.entries(keywords)) {
      if (riskText.includes(keyword)) {
        return level;
      }
    }
    
    return 'medium';
  }

  private calculateImpact(severity: string): number {
    const impacts: Record<string, number> = {
      critical: 90,
      high: 70,
      medium: 45,
      low: 20,
    };
    return impacts[severity] || 45;
  }

  private calculateProbability(risk: any): number {
    const riskText = risk.risk || '';
    const keywords: Record<string, number> = {
      '可能': 70,
      '预计': 60,
      '可能会': 65,
      '存在': 55,
      '潜在': 40,
      '可能发生': 65,
      '偶尔': 30,
      '罕见': 15,
    };
    
    for (const [keyword, prob] of Object.entries(keywords)) {
      if (riskText.includes(keyword)) {
        return prob;
      }
    }
    
    return 50;
  }

  private calculatePriority(impact: number, probability: number): string {
    const score = (impact * probability) / 100;
    if (score >= 60) return 'P0';
    if (score >= 40) return 'P1';
    if (score >= 20) return 'P2';
    return 'P3';
  }

  private generateMitigationStrategy(risk: any, severity: string): string {
    const riskText = risk.risk || '';
    const strategies: Record<string, string> = {
      '安全': '实施安全审计，加强访问控制，定期漏洞扫描',
      '性能': '优化代码，增加缓存，扩容服务器',
      '数据': '定期备份，实施数据冗余，建立恢复机制',
      '功能': '增加测试覆盖，实施灰度发布，准备回滚方案',
      '用户': '收集用户反馈，提供替代方案，加强沟通',
      '运营': '制定应急预案，建立监控告警，定期演练',
    };
    
    for (const [keyword, strategy] of Object.entries(strategies)) {
      if (riskText.includes(keyword)) {
        return strategy;
      }
    }
    
    const severityStrategies: Record<string, string> = {
      critical: '立即处理，组建专项小组，制定详细方案',
      high: '优先处理，制定时间表，安排专人负责',
      medium: '计划处理，纳入迭代计划，定期跟进',
      low: '观察监控，积累经验，适时处理',
    };
    
    return severityStrategies[severity] || '制定应对计划，定期评估';
  }
}
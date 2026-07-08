import { BaseSkill, SkillConfig, SkillContext, SkillResult } from '../types';
import { Presentation, ThemeType, Slide, Component, StyleConfig } from '../../types';
import { themes } from '../../theme/themes';

const generateId = () => Math.random().toString(36).substring(2, 11);

const defaultStyle: StyleConfig = {
  fontFamily: 'Inter',
  fontSize: 16,
  fontWeight: '400',
  color: '#1f2937',
  backgroundColor: 'transparent',
  borderRadius: 0,
  borderWidth: 0,
  borderColor: '#e5e7eb',
  shadow: 'none',
};

export class PresentationGenerationSkill extends BaseSkill {
  getConfig(): SkillConfig {
    return {
      id: 'presentation-generation',
      name: '演示文稿生成',
      description: '根据分析结果生成完整的演示文稿',
      icon: 'Presentation',
      category: 'generation',
      requires: ['prd_structure', 'objectives_detail', 'metrics', 'charts'],
      produces: ['presentation'],
      params: [
        { name: 'theme', type: 'string', required: false, description: '主题', default: 'business' },
      ],
    };
  }

  async execute(context: SkillContext, params?: Record<string, any>): Promise<SkillResult> {
    const prdStructure = context.prd_structure;
    const objectives = context.objectives_detail;
    const metrics = context.metrics;
    const charts = context.charts;
    
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
      logs.push('开始生成演示文稿...');
      logs.push('正在调用AI分析引擎...');

      const businessContent = JSON.stringify({ prdStructure, objectives, metrics }, null, 2);
      const response = await this.callBackendApi('presentation-generation', { business_content: businessContent }, true);
      
      let resultContent = '';
      if (response.status === 'streaming') {
        resultContent = await this.streamBackendApi(response.execution_id, () => {});
      } else if (response.status === 'completed') {
        resultContent = response.result || '';
      }

      logs.push('AI分析完成，正在生成演示文稿...');

      const theme = (params?.theme || 'business') as ThemeType;
      const themeConfig = themes[theme];
      
      const presentation = this.createPresentation(prdStructure, objectives, metrics, charts, theme);
      
      logs.push(`生成${presentation.slides.length}页演示文稿`);

      return {
        success: true,
        data: {
          presentation,
          raw_result: resultContent,
        },
        logs,
      };
    } catch (error) {
      console.error('演示文稿生成失败:', error);
      return {
        success: false,
        data: {},
        error: error instanceof Error ? error.message : '演示文稿生成失败',
        logs: ['演示文稿生成失败'],
      };
    }
  }

  private createPresentation(prdStructure: any, objectives: any[], metrics: any[], charts: any[], theme: ThemeType): Presentation {
    const themeConfig = themes[theme];
    const slides: Slide[] = [];

    slides.push(this.createTitleSlide(prdStructure.business_domain, themeConfig));
    slides.push(this.createTocSlide(objectives, metrics, prdStructure, charts, themeConfig));
    
    if (objectives?.length) {
      slides.push(this.createObjectivesSlide(objectives, themeConfig));
    }
    
    if (prdStructure.workflow?.length) {
      slides.push(this.createWorkflowSlide(prdStructure.workflow, themeConfig));
    }
    
    if (metrics?.length) {
      slides.push(this.createMetricsSlide(metrics, charts, themeConfig));
    }
    
    if (prdStructure.risks?.length) {
      slides.push(this.createRisksSlide(prdStructure.risks, themeConfig));
    }
    
    slides.push(this.createConclusionSlide(prdStructure.business_domain, themeConfig));

    return {
      id: generateId(),
      title: prdStructure.business_domain || '业务分析报告',
      theme,
      currentSlideIndex: 0,
      slides,
    };
  }

  private createTitleSlide(title: string, theme: any): Slide {
    return {
      id: generateId(),
      index: 0,
      backgroundColor: theme.background,
      components: [
        this.createText(50, 120, 700, 80, title, { fontSize: 48, fontWeight: '700', color: theme.primary, textAlign: 'center' }, 0),
        this.createText(50, 220, 700, 40, '业务系统分析报告', { fontSize: 24, fontWeight: '500', color: theme.textLight, textAlign: 'center' }, 200),
      ],
      transition: 'fade',
    };
  }

  private createTocSlide(objectives: any[], metrics: any[], prdStructure: any, charts: any[], theme: any): Slide {
    const items: string[] = [];
    if (objectives?.length) items.push('业务目标');
    if (prdStructure.workflow?.length) items.push('流程设计');
    if (metrics?.length) items.push('关键指标');
    if (prdStructure.risks?.length) items.push('风险分析');
    
    return {
      id: generateId(),
      index: 1,
      backgroundColor: theme.background,
      components: [
        this.createText(50, 80, 700, 60, '目录', { fontSize: 36, fontWeight: '600', color: theme.primary }, 0),
        ...items.map((item, idx) => this.createText(50, 160 + idx * 50, 700, 40, `● ${item}`, { fontSize: 22, fontWeight: '500', color: theme.text }, 100 + idx * 100)),
      ],
      transition: 'slide-left',
    };
  }

  private createObjectivesSlide(objectives: any[], theme: any): Slide {
    return {
      id: generateId(),
      index: 2,
      backgroundColor: theme.background,
      components: [
        this.createText(50, 60, 700, 50, '业务目标', { fontSize: 32, fontWeight: '600', color: theme.primary }, 0),
        ...objectives.map((obj, idx) => this.createText(50, 140 + idx * 80, 700, 60, `${obj.objective}: ${obj.target}`, { fontSize: 20, fontWeight: '500', color: theme.text }, 100 + idx * 150)),
      ],
      transition: 'fade',
    };
  }

  private createWorkflowSlide(workflow: any[], theme: any): Slide {
    return {
      id: generateId(),
      index: 3,
      backgroundColor: theme.background,
      components: [
        this.createText(50, 60, 700, 50, '流程设计', { fontSize: 32, fontWeight: '600', color: theme.primary }, 0),
        ...workflow.slice(0, 6).map((step, idx) => this.createText(50, 140 + idx * 60, 700, 50, `步骤${step.step}: ${step.name}`, { fontSize: 18, fontWeight: '500', color: theme.text }, 100 + idx * 100)),
      ],
      transition: 'slide-left',
    };
  }

  private createMetricsSlide(metrics: any[], charts: any[], theme: any): Slide {
    const barChart = charts?.find((c: any) => c.type === 'bar');
    
    return {
      id: generateId(),
      index: 4,
      backgroundColor: theme.background,
      components: [
        this.createText(50, 60, 700, 50, '关键指标', { fontSize: 32, fontWeight: '600', color: theme.primary }, 0),
        {
          id: generateId(),
          type: 'chart',
          x: 50,
          y: 130,
          width: 700,
          height: 350,
          content: '',
          style: defaultStyle,
          animation: { type: 'fadeIn', delay: 200, duration: 800, easing: 'easeOut' },
          data: barChart?.data || {
            type: 'bar',
            labels: metrics.map((m: any) => m.name),
            datasets: [
              { name: '当前值', data: metrics.map((m: any) => m.current), color: '#9ca3af' },
              { name: '目标值', data: metrics.map((m: any) => m.target_value), color: theme.primary },
            ],
          },
        },
      ],
      transition: 'fade',
    };
  }

  private createRisksSlide(risks: any[], theme: any): Slide {
    return {
      id: generateId(),
      index: 5,
      backgroundColor: theme.background,
      components: [
        this.createText(50, 60, 700, 50, '风险分析', { fontSize: 32, fontWeight: '600', color: theme.primary }, 0),
        ...risks.slice(0, 4).map((risk, idx) => {
          const severityColors: Record<string, string> = {
            critical: '#ef4444',
            high: '#f59e0b',
            medium: '#3b82f6',
            low: '#10b981',
          };
          return this.createText(50, 140 + idx * 70, 700, 60, `${risk.risk} (${risk.severity})`, { fontSize: 18, fontWeight: '500', color: severityColors[risk.severity] || theme.text }, 100 + idx * 150);
        }),
      ],
      transition: 'zoom-in',
    };
  }

  private createConclusionSlide(title: string, theme: any): Slide {
    return {
      id: generateId(),
      index: 6,
      backgroundColor: theme.background,
      components: [
        this.createText(50, 200, 700, 80, '感谢您的观看！', { fontSize: 36, fontWeight: '600', color: theme.primary, textAlign: 'center' }, 0),
        this.createText(50, 300, 700, 40, title, { fontSize: 20, fontWeight: '400', color: theme.textLight, textAlign: 'center' }, 200),
      ],
      transition: 'fade',
    };
  }

  private createText(x: number, y: number, width: number, height: number, content: string, style: Partial<StyleConfig>, delay: number): Component {
    return {
      id: generateId(),
      type: 'text',
      x,
      y,
      width,
      height,
      content,
      style: { ...defaultStyle, ...style },
      animation: { type: 'fadeIn', delay, duration: 500, easing: 'easeOut' },
    };
  }
}
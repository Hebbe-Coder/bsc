import { Presentation, Slide, Component, ThemeType, StyleConfig } from '../types';
import { themes } from '../theme/themes';
import { BusinessSystem } from '../api/bscApi';

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

export const convertBusinessSystemToPresentation = (
  businessSystem: BusinessSystem,
  theme: ThemeType = 'business'
): Presentation => {
  const themeConfig = themes[theme];
  const slides: Slide[] = [];
  let animationDelay = 0;

  const createTextComponent = (
    x: number,
    y: number,
    width: number,
    height: number,
    content: string,
    style: Partial<StyleConfig>,
    delay: number = 0
  ): Component => ({
    id: generateId(),
    type: 'text',
    x,
    y,
    width,
    height,
    content,
    style: { ...defaultStyle, ...style, color: style.color || themeConfig.text },
    animation: {
      type: 'fadeIn',
      delay,
      duration: 500,
      easing: 'easeOut',
    },
  });

  const createChartComponent = (
    x: number,
    y: number,
    width: number,
    height: number,
    data: any,
    delay: number = 0
  ): Component => ({
    id: generateId(),
    type: 'chart',
    x,
    y,
    width,
    height,
    content: '',
    style: defaultStyle,
    animation: {
      type: 'fadeIn',
      delay,
      duration: 800,
      easing: 'easeOut',
    },
    data,
  });

  slides.push({
    id: generateId(),
    index: 0,
    backgroundColor: themeConfig.background,
    components: [
      createTextComponent(50, 120, 700, 80, businessSystem.business_domain || '业务分析报告', {
        fontSize: 48,
        fontWeight: '700',
        color: themeConfig.primary,
        textAlign: 'center',
      }, 0),
      createTextComponent(50, 220, 700, 40, '基于PRD的业务系统分析报告', {
        fontSize: 24,
        fontWeight: '500',
        color: themeConfig.textLight,
        textAlign: 'center',
      }, 200),
    ],
    transition: 'fade',
  });

  const tocItems: string[] = [];
  if (businessSystem.objectives?.length) tocItems.push('业务目标');
  if (businessSystem.workflow?.length) tocItems.push('流程设计');
  if (businessSystem.metrics?.length) tocItems.push('关键指标');
  if (businessSystem.risks?.length) tocItems.push('风险分析');
  if (businessSystem.strategy?.growth_opportunities?.length) tocItems.push('战略机会');
  if (businessSystem.optimization?.recommendations?.length) tocItems.push('优化建议');

  slides.push({
    id: generateId(),
    index: 1,
    backgroundColor: themeConfig.background,
    components: [
      createTextComponent(50, 80, 700, 60, '目录', {
        fontSize: 36,
        fontWeight: '600',
        color: themeConfig.primary,
      }, 0),
      ...tocItems.map((item, idx) =>
        createTextComponent(50, 160 + idx * 50, 700, 40, `● ${item}`, {
          fontSize: 22,
          fontWeight: '500',
          color: themeConfig.text,
        }, 100 + idx * 100)
      ),
    ],
    transition: 'slide-left',
  });

  if (businessSystem.report?.executive_summary || businessSystem.composed?.report?.executive_summary) {
    const summary = businessSystem.report?.executive_summary || businessSystem.composed?.report?.executive_summary || '';
    slides.push({
      id: generateId(),
      index: slides.length,
      backgroundColor: themeConfig.background,
      components: [
        createTextComponent(50, 80, 700, 60, '执行摘要', {
          fontSize: 36,
          fontWeight: '600',
          color: themeConfig.primary,
        }, 0),
        createTextComponent(50, 160, 700, 200, summary, {
          fontSize: 18,
          fontWeight: '400',
          color: themeConfig.text,
          textAlign: 'justify',
        }, 200),
      ],
      transition: 'fade',
    });
  }

  if (businessSystem.objectives?.length) {
    animationDelay = 0;
    slides.push({
      id: generateId(),
      index: slides.length,
      backgroundColor: themeConfig.background,
      components: [
        createTextComponent(50, 60, 700, 50, '业务目标', {
          fontSize: 32,
          fontWeight: '600',
          color: themeConfig.primary,
        }, animationDelay),
        ...businessSystem.objectives.map((obj, idx) =>
          createTextComponent(50, 140 + idx * 80, 700, 60, `${obj.objective}: ${obj.target}`, {
            fontSize: 20,
            fontWeight: '500',
            color: themeConfig.text,
          }, animationDelay + 100 + idx * 150)
        ),
      ],
      transition: 'fade',
    });
  }

  if (businessSystem.workflow?.length) {
    animationDelay = 0;
    slides.push({
      id: generateId(),
      index: slides.length,
      backgroundColor: themeConfig.background,
      components: [
        createTextComponent(50, 60, 700, 50, '流程设计', {
          fontSize: 32,
          fontWeight: '600',
          color: themeConfig.primary,
        }, animationDelay),
        ...businessSystem.workflow.slice(0, 6).map((step, idx) =>
          createTextComponent(50, 140 + idx * 60, 700, 50, `步骤${step.step}: ${step.name}`, {
            fontSize: 18,
            fontWeight: '500',
            color: themeConfig.text,
          }, animationDelay + 100 + idx * 100)
        ),
      ],
      transition: 'slide-left',
    });

    if (businessSystem.workflow.length > 6) {
      slides.push({
        id: generateId(),
        index: slides.length,
        backgroundColor: themeConfig.background,
        components: [
          createTextComponent(50, 60, 700, 50, '流程设计（续）', {
            fontSize: 32,
            fontWeight: '600',
            color: themeConfig.primary,
          }, 0),
          ...businessSystem.workflow.slice(6).map((step, idx) =>
            createTextComponent(50, 140 + idx * 60, 700, 50, `步骤${step.step}: ${step.name}`, {
              fontSize: 18,
              fontWeight: '500',
              color: themeConfig.text,
            }, 100 + idx * 100)
          ),
        ],
        transition: 'slide-left',
      });
    }
  }

  if (businessSystem.metrics?.length) {
    const metricLabels = businessSystem.metrics.map(m => m.name);
    const currentData = businessSystem.metrics.map(m => m.current || 50);
    const targetData = businessSystem.metrics.map(m => {
      const val = parseFloat(m.target) || parseFloat(m.target_value?.toString() || '100');
      return isNaN(val) ? 100 : val;
    });

    slides.push({
      id: generateId(),
      index: slides.length,
      backgroundColor: themeConfig.background,
      components: [
        createTextComponent(50, 60, 700, 50, '关键指标', {
          fontSize: 32,
          fontWeight: '600',
          color: themeConfig.primary,
        }, 0),
        createChartComponent(50, 130, 700, 350, {
          type: 'bar',
          labels: metricLabels,
          datasets: [
            { name: '当前值', data: currentData, color: '#9ca3af' },
            { name: '目标值', data: targetData, color: themeConfig.primary },
          ],
        }, 200),
      ],
      transition: 'fade',
    });
  }

  if (businessSystem.risks?.length) {
    animationDelay = 0;
    slides.push({
      id: generateId(),
      index: slides.length,
      backgroundColor: themeConfig.background,
      components: [
        createTextComponent(50, 60, 700, 50, '风险分析', {
          fontSize: 32,
          fontWeight: '600',
          color: themeConfig.primary,
        }, animationDelay),
        ...businessSystem.risks.slice(0, 4).map((risk, idx) => {
          const severityColors: Record<string, string> = {
            critical: '#ef4444',
            high: '#f59e0b',
            medium: '#3b82f6',
            low: '#10b981',
          };
          return createTextComponent(50, 140 + idx * 70, 700, 60, 
            `${risk.risk} (${risk.severity})`, {
            fontSize: 18,
            fontWeight: '500',
            color: severityColors[risk.severity] || themeConfig.text,
          }, animationDelay + 100 + idx * 150);
        }),
      ],
      transition: 'zoom-in',
    });

    if (businessSystem.risks.length > 4) {
      slides.push({
        id: generateId(),
        index: slides.length,
        backgroundColor: themeConfig.background,
        components: [
          createTextComponent(50, 60, 700, 50, '风险分析（续）', {
            fontSize: 32,
            fontWeight: '600',
            color: themeConfig.primary,
          }, 0),
          ...businessSystem.risks.slice(4).map((risk, idx) => {
            const severityColors: Record<string, string> = {
              critical: '#ef4444',
              high: '#f59e0b',
              medium: '#3b82f6',
              low: '#10b981',
            };
            return createTextComponent(50, 140 + idx * 60, 700, 50, 
              `${risk.risk} (${risk.severity})`, {
              fontSize: 18,
              fontWeight: '500',
              color: severityColors[risk.severity] || themeConfig.text,
            }, 100 + idx * 100);
          }),
        ],
        transition: 'zoom-in',
      });
    }
  }

  if (businessSystem.strategy?.growth_opportunities?.length) {
    animationDelay = 0;
    slides.push({
      id: generateId(),
      index: slides.length,
      backgroundColor: themeConfig.background,
      components: [
        createTextComponent(50, 60, 700, 50, '战略机会', {
          fontSize: 32,
          fontWeight: '600',
          color: themeConfig.primary,
        }, animationDelay),
        ...businessSystem.strategy.growth_opportunities.map((op, idx) =>
          createTextComponent(50, 140 + idx * 70, 700, 60, `${op.opportunity}: ${op.potential}`, {
            fontSize: 18,
            fontWeight: '500',
            color: themeConfig.text,
          }, animationDelay + 100 + idx * 150)
        ),
      ],
      transition: 'fade',
    });
  }

  if (businessSystem.optimization?.recommendations?.length) {
    animationDelay = 0;
    slides.push({
      id: generateId(),
      index: slides.length,
      backgroundColor: themeConfig.background,
      components: [
        createTextComponent(50, 60, 700, 50, '优化建议', {
          fontSize: 32,
          fontWeight: '600',
          color: themeConfig.primary,
        }, animationDelay),
        ...businessSystem.optimization.recommendations.map((rec, idx) =>
          createTextComponent(50, 140 + idx * 70, 700, 60, `${rec.recommendation}`, {
            fontSize: 18,
            fontWeight: '500',
            color: themeConfig.success,
          }, animationDelay + 100 + idx * 150)
        ),
      ],
      transition: 'slide-left',
    });
  }

  slides.push({
    id: generateId(),
    index: slides.length,
    backgroundColor: themeConfig.background,
    components: [
      createTextComponent(50, 200, 700, 80, '感谢您的观看！', {
        fontSize: 36,
        fontWeight: '600',
        color: themeConfig.primary,
        textAlign: 'center',
      }, 0),
      createTextComponent(50, 300, 700, 40, businessSystem.business_domain || '业务系统分析报告', {
        fontSize: 20,
        fontWeight: '400',
        color: themeConfig.textLight,
        textAlign: 'center',
      }, 200),
    ],
    transition: 'fade',
  });

  return {
    id: generateId(),
    title: businessSystem.business_domain || '业务分析报告',
    theme,
    currentSlideIndex: 0,
    slides,
  };
};

export default convertBusinessSystemToPresentation;
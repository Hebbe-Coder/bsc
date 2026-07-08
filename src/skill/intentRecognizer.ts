export type IntentType = 'compile_prd' | 'analyze_prd' | 'extract_objectives' | 'design_workflow' | 'evaluate_risks' | 'generate_presentation' | 'modify_theme' | 'modify_slide' | 'regenerate_section' | 'help' | 'unknown';

export interface IntentResult {
  intent: IntentType;
  confidence: number;
  keywords: string[];
  prdContent?: string;
}

const intentPatterns: Record<IntentType, { patterns: RegExp[], keywords: string[] }> = {
  compile_prd: {
    patterns: [
      /(prd|产品需求文档|产品设计文档)/i,
      /(转换|生成|编译|创建|制作).*(演示文稿|ppt|幻灯片|汇报)/i,
      /(分析|设计|评估).*(业务系统|业务流程|项目)/i,
      /(帮我|我想|我需要|请).*(生成|创建|做).*(ppt|演示文稿|汇报材料)/i,
    ],
    keywords: ['prd', '产品需求', '产品设计', '演示文稿', 'ppt', '幻灯片', '编译', '转换', '生成'],
  },
  analyze_prd: {
    patterns: [
      /(分析|解读|理解).*(prd|产品需求|业务需求)/i,
      /(业务理解|需求分析|需求理解)/i,
    ],
    keywords: ['分析', '解读', '理解', '业务理解', '需求分析'],
  },
  extract_objectives: {
    patterns: [
      /(提取|识别|确定).*(目标|指标|kpi|okr)/i,
      /(目标分析|目标提取|关键指标)/i,
    ],
    keywords: ['提取', '目标', '指标', 'kpi', 'okr'],
  },
  design_workflow: {
    patterns: [
      /(设计|规划|梳理).*(流程|工作流|业务流程|步骤)/i,
      /(流程设计|工作流程|业务流程设计)/i,
    ],
    keywords: ['设计', '流程', '工作流', '步骤'],
  },
  evaluate_risks: {
    patterns: [
      /(评估|识别|分析).*(风险|问题|隐患)/i,
      /(风险评估|风险分析|风险识别)/i,
    ],
    keywords: ['风险', '评估', '分析', '识别'],
  },
  generate_presentation: {
    patterns: [
      /(生成|创建|制作).*(演示文稿|ppt|幻灯片|汇报|报告)/i,
      /(演示文稿生成|ppt生成|汇报材料)/i,
    ],
    keywords: ['生成', '创建', '演示文稿', 'ppt', '汇报'],
  },
  modify_theme: {
    patterns: [
      /(改|修改|换|调整).*(主题|配色|风格|颜色)/i,
      /(主题|配色|风格).*(改|修改|换|调整)/i,
      /(暖色|冷色|深色|浅色|商务|科技).*(主题|风格)/i,
    ],
    keywords: ['修改', '主题', '配色', '风格', '颜色', '暖色', '冷色', '深色', '浅色', '商务', '科技'],
  },
  modify_slide: {
    patterns: [
      /(改|修改|编辑|更新).*(第.*页|幻灯片|slide)/i,
      /(第.*页|幻灯片|slide).*(改|修改|编辑|更新)/i,
      /(内容|标题|副标题|图片).*(改|修改|更换)/i,
    ],
    keywords: ['修改', '编辑', '更新', '第', '页', '幻灯片', '内容', '标题', '图片'],
  },
  regenerate_section: {
    patterns: [
      /(重新生成|再生成|换一个).*(目标|流程|风险|章节|部分)/i,
      /(目标|流程|风险|章节|部分).*(重新生成|再生成)/i,
    ],
    keywords: ['重新生成', '再生成', '换一个', '目标', '流程', '风险', '章节', '部分'],
  },
  help: {
    patterns: [
      /(帮助|指南|教程|怎么用|使用说明)/i,
      /(你能做什么|功能|能力)/i,
    ],
    keywords: ['帮助', '指南', '教程', '怎么用', '功能'],
  },
  unknown: {
    patterns: [],
    keywords: [],
  },
};

export const recognizeIntent = (input: string): IntentResult => {
  const results: Array<{ intent: IntentType; score: number; keywords: string[] }> = [];
  
  Object.entries(intentPatterns).forEach(([intent, config]) => {
    let score = 0;
    
    config.patterns.forEach(pattern => {
      if (pattern.test(input)) {
        score += 3;
      }
    });
    
    config.keywords.forEach(keyword => {
      if (input.toLowerCase().includes(keyword.toLowerCase())) {
        score += 1;
      }
    });
    
    if (score > 0) {
      const matchedKeywords = config.keywords.filter(
        keyword => input.toLowerCase().includes(keyword.toLowerCase())
      );
      results.push({
        intent: intent as IntentType,
        score,
        keywords: matchedKeywords,
      });
    }
  });
  
  if (results.length === 0) {
    return {
      intent: 'unknown',
      confidence: 0,
      keywords: [],
      prdContent: input.trim().length > 50 ? input : undefined,
    };
  }
  
  results.sort((a, b) => b.score - a.score);
  const bestResult = results[0];
  
  const isPrd = input.length > 100 || 
    input.includes('# ') || 
    input.includes('## ') ||
    input.includes('- ') ||
    input.includes('1. ') ||
    input.includes('业务') ||
    input.includes('功能');
  
  return {
    intent: bestResult.intent,
    confidence: Math.min(bestResult.score / 10, 1),
    keywords: bestResult.keywords,
    prdContent: isPrd ? input : undefined,
  };
};

export const getIntentDescription = (intent: IntentType): string => {
  const descriptions: Record<IntentType, string> = {
    compile_prd: '将PRD文档转换为演示文稿',
    analyze_prd: '分析PRD文档内容',
    extract_objectives: '提取核心目标和指标',
    design_workflow: '设计业务流程',
    evaluate_risks: '评估潜在风险',
    generate_presentation: '生成演示文稿',
    modify_theme: '修改演示文稿主题/配色',
    modify_slide: '修改特定幻灯片内容',
    regenerate_section: '重新生成某个章节',
    help: '获取帮助信息',
    unknown: '未知意图',
  };
  return descriptions[intent];
};

export const getIntentResponse = (intent: IntentType, input?: string): string => {
  const responses: Record<IntentType, (input?: string) => string> = {
    compile_prd: () => '好的！我来帮您将这份PRD文档转换为专业的演示文稿。',
    analyze_prd: () => '好的！我来分析这份PRD文档的业务需求。',
    extract_objectives: () => '好的！我来帮您提取核心目标和关键指标。',
    design_workflow: () => '好的！我来帮您设计业务流程。',
    evaluate_risks: () => '好的！我来帮您评估潜在风险。',
    generate_presentation: () => '好的！我来帮您生成演示文稿。',
    modify_theme: () => '好的！我来帮您修改演示文稿的主题和配色。',
    modify_slide: () => '好的！我来帮您修改指定的幻灯片内容。',
    regenerate_section: () => '好的！我来帮您重新生成指定的章节。',
    help: () => `我是BSC智能助手，可以帮您：
- 将PRD文档转换为演示文稿
- 分析业务需求和目标
- 设计业务流程
- 评估潜在风险
- 修改演示文稿主题和配色
- 重新生成某个章节

您可以直接输入PRD文档内容，或者用自然语言描述您的需求。`,
    unknown: (text) => {
      if (text && text.length > 50) {
        return '我理解您输入了一段内容，我将尝试将其作为PRD文档进行编译。';
      }
      return '我不太理解您的需求，请输入PRD文档内容或描述您的业务需求。';
    },
  };
  return responses[intent](input);
};
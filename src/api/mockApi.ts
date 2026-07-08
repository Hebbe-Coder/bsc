import { 
  BusinessSystem, 
  CompileResult, 
  ExportResult, 
  Skill, 
  ExecuteSkillRequest, 
  SkillExecutionResponse, 
  StageRequest, 
  StageResponse 
} from './bscApi';

const mockSkills: Skill[] = [
  { id: 'prd-analysis', name: 'PRD分析', description: '分析产品需求文档' },
  { id: 'objective-extraction', name: '目标提取', description: '从文档内容提取目标' },
  { id: 'kpi-extraction', name: 'KPI提取', description: '识别关键绩效指标' },
  { id: 'chart-generation', name: '图表生成', description: '生成ECharts图表' },
  { id: 'risk-assessment', name: '风险评估', description: '评估项目风险' },
  { id: 'strategy-analysis', name: '战略分析', description: 'SWOT分析与战略规划' },
  { id: 'presentation-generation', name: '演示文稿生成', description: '生成PPT大纲' },
  { id: 'report-generation', name: '报告生成', description: '生成项目分析报告' },
];

const mockBusinessSystem: BusinessSystem = {
  business_domain: '电商平台业务系统',
  objectives: [
    { objective: '提升用户转化率', target: '从当前3%提升至5%', priority: '高', kpi: '转化率' },
    { objective: '降低运营成本', target: '降低15%', priority: '中', kpi: '运营成本' },
    { objective: '提高客户满意度', target: '达到90%', priority: '高', kpi: '满意度评分' },
  ],
  roles: [
    { role: '产品经理', responsibilities: ['需求分析', '产品规划', '优先级管理'] },
    { role: '开发工程师', responsibilities: ['功能开发', '代码维护', '性能优化'] },
    { role: '运营专员', responsibilities: ['活动策划', '用户运营', '数据分析'] },
  ],
  workflow: [
    { step: 1, name: '需求收集', action: '收集用户反馈和市场分析', owner: '产品经理', sla: '5个工作日' },
    { step: 2, name: '需求评审', action: '组织跨部门评审会议', owner: '产品经理', sla: '2个工作日' },
    { step: 3, name: '开发实现', action: '按计划进行功能开发', owner: '开发工程师', sla: '14个工作日' },
    { step: 4, name: '测试验证', action: '进行功能测试和性能测试', owner: '测试工程师', sla: '7个工作日' },
    { step: 5, name: '上线发布', action: '部署到生产环境', owner: '运维工程师', sla: '1个工作日' },
  ],
  metrics: [
    { name: '转化率', formula: '转化用户数/总访问数', target: '5%', owner: '运营专员', current: 3, target_value: 5 },
    { name: '平均订单金额', formula: '总销售额/订单数', target: '¥200', owner: '运营专员', current: 150, target_value: 200 },
    { name: '用户留存率', formula: '30天活跃用户/新注册用户', target: '70%', owner: '数据分析师', current: 60, target_value: 70 },
  ],
  risks: [
    { risk: '技术架构瓶颈', severity: '高', mitigation: '进行架构升级和性能优化', category: '技术风险' },
    { risk: '市场竞争加剧', severity: '中', mitigation: '持续创新和差异化竞争', category: '市场风险' },
    { risk: '供应链中断', severity: '低', mitigation: '建立多供应商策略', category: '运营风险' },
  ],
  strategy: {
    growth_opportunities: [
      { opportunity: '拓展海外市场', potential: '预计新增30%用户' },
      { opportunity: '推出会员体系', potential: '提升用户粘性20%' },
    ],
  },
  optimization: {
    recommendations: [
      { recommendation: '优化首页加载速度', impact: '预计提升转化率10%' },
      { recommendation: '简化下单流程', impact: '预计降低弃购率15%' },
    ],
  },
  report: {
    title: '电商平台业务分析报告',
    executive_summary: '本报告对电商平台业务系统进行了全面分析，包括目标设定、角色职责、工作流程、关键指标和风险评估等方面。',
    sections: [
      { title: '业务概述', content: '电商平台致力于为用户提供优质的购物体验，涵盖商品浏览、购物车、订单管理等核心功能。' },
      { title: '目标分析', content: '基于业务需求，制定了三大核心目标：提升转化率、降低成本和提高客户满意度。' },
      { title: '风险评估', content: '识别了技术、市场和运营三个维度的风险，并制定了相应的缓解措施。' },
    ],
  },
};

const mockCompileResult: CompileResult = {
  business_system: mockBusinessSystem,
  pipeline: {
    stages: [
      { agent: '业务理解代理', key: 'business_understanding', display: '业务理解', status: 'completed', duration_ms: 2000 },
      { agent: '目标提取代理', key: 'objective_extraction', display: '目标提取', status: 'completed', duration_ms: 1500 },
      { agent: '流程设计代理', key: 'workflow_design', display: '流程设计', status: 'completed', duration_ms: 1800 },
      { agent: '风险分析代理', key: 'risk_analysis', display: '风险分析', status: 'completed', duration_ms: 1200 },
    ],
    total_ms: 6500,
  },
  summary: '已成功完成业务系统分析，生成了完整的业务系统数据结构。',
  workspace: {
    dashboard: {
      business_domain: '电商平台业务系统',
      objectives_count: 3,
      workflow_steps: 5,
      risk_count: 3,
      strategy_count: 2,
      recommendation_count: 2,
    },
    report: {
      title: '电商平台业务分析报告',
      summary: '全面的业务分析报告',
      sections: [
        { title: '业务概述', content: '电商平台业务系统分析报告内容' },
        { title: '目标分析', content: '三大核心目标分析' },
      ],
    },
    ppt_blueprint: {
      slide_count: 8,
      slides: [
        { type: 'title', title: '电商平台业务分析', content: '业务系统全面分析报告' },
        { type: 'objective', title: '核心目标', items: ['提升转化率', '降低运营成本', '提高客户满意度'] },
        { type: 'workflow', title: '工作流程', steps: ['需求收集', '需求评审', '开发实现', '测试验证', '上线发布'] },
        { type: 'metrics', title: '关键指标', headers: ['指标', '目标', '当前'], data: [['转化率', '5%', '3%'], ['平均订单金额', '¥200', '¥150']] },
      ],
    },
  },
};

const mockExportResult: ExportResult = {
  exports: {
    json: mockBusinessSystem,
    html: '<html><body><h1>业务分析报告</h1></body></html>',
    ppt: {
      slides: [
        { slide_type: 'title', title: '业务分析报告', subtitle: '电商平台' },
        { slide_type: 'content', title: '核心目标', items: ['提升转化率', '降低运营成本'] },
      ],
      theme: 'business',
      slide_count: 8,
    },
    markdown: '# 业务分析报告\n\n## 核心目标\n\n- 提升转化率\n- 降低运营成本',
  },
  formats: ['json', 'html', 'ppt', 'markdown'],
  summary: '成功导出业务系统数据',
  errors: [],
};

const mockSkillExecutionResponses: Record<string, SkillExecutionResponse> = {};

const generateExecutionId = (): string => {
  return `exec-${Math.random().toString(36).substring(2, 10)}`;
};

const createMockStream = (content: string): ReadableStream => {
  const encoder = new TextEncoder();
  const chunks = content.split(/(?=[。！？\n])/).filter(chunk => chunk.trim());
  
  let index = 0;
  
  return new ReadableStream({
    async start(controller) {
      const pushNextChunk = () => {
        if (index >= chunks.length) {
          controller.enqueue(encoder.encode('data: {"status": "completed"}\n\n'));
          controller.close();
          return;
        }
        
        const chunk = chunks[index++];
        const data = JSON.stringify({
          content: chunk,
          status: 'running' as const,
        });
        
        controller.enqueue(encoder.encode(`data: ${data}\n\n`));
        
        setTimeout(pushNextChunk, 100 + Math.random() * 200);
      };
      
      setTimeout(pushNextChunk, 500);
    },
  });
};

export const mockBscApi = {
  compile: async (input: string, templateId?: string): Promise<CompileResult> => {
    await new Promise(resolve => setTimeout(resolve, 1500));
    return mockCompileResult;
  },

  compileSync: async (input: string): Promise<CompileResult> => {
    await new Promise(resolve => setTimeout(resolve, 1000));
    return mockCompileResult;
  },

  export: async (businessSystem: BusinessSystem, outputTypes: string[] = ['html', 'json']): Promise<ExportResult> => {
    await new Promise(resolve => setTimeout(resolve, 800));
    return mockExportResult;
  },

  health: async (): Promise<{ pipeline: string; llm: { status: string; provider: string } }> => {
    return {
      pipeline: 'ready',
      llm: { status: 'ready', provider: 'mock' },
    };
  },

  stages: async (): Promise<Array<{ key: string; agent: string; display: string; type: string }>> => {
    return [
      { key: 'business_understanding', agent: '业务理解代理', display: '业务理解', type: 'analyzer' },
      { key: 'objective_extraction', agent: '目标提取代理', display: '目标提取', type: 'extractor' },
      { key: 'workflow_design', agent: '流程设计代理', display: '流程设计', type: 'designer' },
      { key: 'risk_analysis', agent: '风险分析代理', display: '风险分析', type: 'analyzer' },
      { key: 'strategy_planning', agent: '战略规划代理', display: '战略规划', type: 'planner' },
    ];
  },

  getSkills: async (): Promise<Skill[]> => {
    await new Promise(resolve => setTimeout(resolve, 300));
    return mockSkills;
  },

  executeSkill: async (request: ExecuteSkillRequest): Promise<SkillExecutionResponse> => {
    await new Promise(resolve => setTimeout(resolve, 500));
    
    const executionId = generateExecutionId();
    const result = {
      execution_id: executionId,
      status: request.streaming ? 'streaming' : 'completed',
      result: request.streaming ? undefined : '这是模拟的技能执行结果。',
      from_cache: false,
    };
    
    mockSkillExecutionResponses[executionId] = result;
    return result;
  },

  streamSkill: async (executionId: string, signal?: AbortSignal): Promise<ReadableStream> => {
    await new Promise(resolve => setTimeout(resolve, 200));
    
    const mockContent = '这是一个模拟的流式输出示例。系统正在分析您的请求。首先进行业务理解，然后提取关键目标，接着设计工作流程，最后进行风险评估。分析完成，生成了完整的业务系统报告。';
    
    return createMockStream(mockContent);
  },

  getSkillResult: async (executionId: string): Promise<SkillExecutionResponse> => {
    await new Promise(resolve => setTimeout(resolve, 200));
    
    const response = mockSkillExecutionResponses[executionId];
    if (response) {
      return response;
    }
    
    return {
      execution_id: executionId,
      status: 'completed',
      result: '这是模拟的技能执行结果。',
      from_cache: false,
    };
  },

  executeStage: async (request: StageRequest): Promise<StageResponse> => {
    await new Promise(resolve => setTimeout(resolve, 800));
    
    return {
      stage: request.stage_key,
      data: {
        result: `模拟执行阶段 ${request.stage_key} 完成`,
        input: request.input,
      },
    };
  },
};

export default mockBscApi;
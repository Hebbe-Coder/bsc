from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from typing import List, AsyncIterator, Iterator, Optional

from .config import settings


class MockChatModel(BaseChatModel):
    _skill_prompts = {
        "prd-analysis": {
            "system": "你是一个专业的产品经理，擅长分析产品需求文档(PRD)并提取关键信息。",
            "template": """## {topic}分析报告

### 1. 产品目标
- 明确产品核心价值定位
- 构建完整的产品能力体系
- 提升用户体验和满意度

### 2. 核心功能
- 功能模块1：实现核心业务流程
- 功能模块2：提升效率的工具特性
- 功能模块3：数据可视化与分析能力

### 3. 目标用户
- 主要用户群体：专业人士、企业用户
- 次要用户群体：入门级用户

### 4. 技术要求
- 响应式设计，支持多端访问
- 高性能架构，确保流畅体验
- 安全合规的数据处理机制

### 5. 成功指标
- 用户满意度达到预期目标
- 核心功能使用率稳步提升
- 业务指标达成率超过基准值""",
        },
        "objective-extraction": {
            "system": "你是一个业务分析师，擅长从业务内容中提取关键目标。",
            "template": """## 业务目标提取报告

### 核心目标
1. 提升业务效率和竞争力
2. 扩大市场份额和影响力
3. 优化产品和服务质量

### 关键指标
- 核心业务指标增长50%
- 关键转化率达到15%以上
- 用户活跃度持续提升

### 实施建议
- 分阶段推进目标实现
- 建立完善的监控体系
- 定期评估和调整策略""",
        },
        "kpi-extraction": {
            "system": "你是一个数据分析师，擅长提取和定义关键绩效指标。",
            "template": """## KPI指标提取报告

### 核心指标
| 指标名称 | 计算公式 | 目标值 |
|---------|---------|--------|
| 业务完成率 | 完成数/总数 | 80% |
| 响应时效 | 平均响应时间 | <2小时 |
| 质量达标率 | 达标数/总数 | 95% |

### 运营指标
| 指标名称 | 计算公式 | 目标值 |
|---------|---------|--------|
| 用户留存率 | 活跃用户/总用户 | 60% |
| 转化率 | 转化用户/访问用户 | 15% |
| 满意度 | 满意数/总数 | 4.5/5 |

### 预警机制
- 指标低于阈值时自动告警
- 建立周/月度分析报告""",
        },
        "chart-generation": {
            "system": "你是一个数据可视化专家，擅长生成ECharts图表配置。",
            "template": """{
  "chartType": "bar",
  "title": "{topic}统计分析",
  "xAxis": {
    "type": "category",
    "data": ["阶段1", "阶段2", "阶段3", "阶段4", "阶段5"]
  },
  "yAxis": {
    "type": "value",
    "name": "数值"
  },
  "series": [{
    "name": "数据系列",
    "type": "bar",
    "data": [120, 180, 240, 300, 360],
    "itemStyle": {
      "color": "#6366f1",
      "borderRadius": [4, 4, 0, 0]
    },
    "emphasis": {
      "itemStyle": {
        "color": "#818cf8"
      }
    }
  }],
  "tooltip": {
    "trigger": "axis",
    "axisPointer": {
      "type": "shadow"
    }
  },
  "grid": {
    "left": "3%",
    "right": "4%",
    "bottom": "3%",
    "containLabel": true
  }
}""",
        },
        "risk-assessment": {
            "system": "你是一个风险评估专家，擅长识别和评估业务风险。",
            "template": """## 风险评估报告

### 高风险项
1. **技术风险**：系统稳定性和性能
   - 严重程度：高
   - 缓解措施：建立完善的测试和监控体系

2. **市场风险**：竞争压力和市场变化
   - 严重程度：中高
   - 缓解措施：差异化定位和持续创新

### 中风险项
3. **运营风险**：流程效率和执行质量
   - 严重程度：中
   - 缓解措施：优化流程和培训团队

4. **合规风险**：法律法规和政策变化
   - 严重程度：中
   - 缓解措施：定期合规审查

### 低风险项
5. **资源风险**：人力和资金配置
   - 严重程度：低
   - 缓解措施：合理规划和储备

### 风险监控建议
- 建立风险预警机制
- 定期评估风险等级
- 制定应急预案""",
        },
        "strategy-analysis": {
            "system": "你是一个战略规划专家，擅长SWOT分析和战略规划。",
            "template": """## SWOT分析报告

### 优势(S)
- 专业的团队和技术能力
- 完善的产品和服务体系
- 良好的品牌形象和口碑

### 劣势(W)
- 资源有限，规模较小
- 市场份额有待提升
- 品牌知名度不足

### 机会(O)
- 市场需求持续增长
- 政策支持和行业利好
- 技术创新带来新机遇

### 威胁(T)
- 竞争加剧，价格压力
- 技术迭代快速
- 外部环境不确定性

### 战略建议
- SO策略：利用优势抓住机会
- WO策略：克服劣势把握机会
- ST策略：利用优势应对威胁
- WT策略：减少劣势规避威胁""",
        },
        "presentation-generation": {
            "system": "你是一个演示文稿专家，擅长设计和生成PPT大纲。",
            "template": """## PPT演示大纲

### 幻灯片1：封面
- 标题：{topic}介绍
- 副标题：专业演示文稿

### 幻灯片2：概述
- 项目背景
- 核心价值
- 目标受众

### 幻灯片3：核心内容
- 主要功能展示
- 关键数据支撑
- 优势亮点

### 幻灯片4：技术架构
- 系统架构图
- 技术栈说明
- 性能指标

### 幻灯片5：市场分析
- 市场规模
- 竞争格局
- 机会分析

### 幻灯片6：实施计划
- 阶段规划
- 里程碑
- 资源需求

### 幻灯片7：预期成果
- 目标达成情况
- 效益评估
- 风险控制

### 幻灯片8：Q&A
- 提问环节""",
        },
        "report-generation": {
            "system": "你是一个商业分析师，擅长撰写专业的业务分析报告。",
            "template": """## 业务分析报告

### 一、执行摘要
本报告对{topic}进行全面分析，旨在为决策提供数据支持。

### 二、市场分析
- 市场规模和增长趋势
- 主要参与者和竞争格局
- 市场机会和挑战

### 三、业务现状
- 当前业务表现
- 核心指标完成情况
- 存在的问题和不足

### 四、用户分析
- 用户画像和特征
- 用户需求和痛点
- 用户行为分析

### 五、竞争分析
- 主要竞争对手
- 竞争优势和劣势
- 差异化策略

### 六、战略建议
- 短期策略：优化现有业务
- 中期策略：拓展新业务
- 长期策略：构建核心竞争力

### 七、实施计划
- 阶段目标和里程碑
- 资源需求和配置
- 风险评估和应对

### 八、结论
综合分析表明，{topic}具有良好的发展前景。""",
        },
    }

    def _extract_topic(self, content: str) -> str:
        keywords = ["产品", "项目", "系统", "平台", "业务", "分析", "需求", "功能", "目标", "策略"]
        for kw in keywords:
            if kw in content:
                return kw
        return "业务"

    def _determine_skill(self, messages: List[SystemMessage | HumanMessage | AIMessage]) -> str:
        content = " ".join([m.content for m in messages])
        content_lower = content.lower()
        
        skill_keywords = {
            "prd-analysis": ["prd", "产品需求", "需求文档", "产品分析"],
            "objective-extraction": ["目标", "业务目标", "提取目标", "核心目标"],
            "kpi-extraction": ["kpi", "指标", "绩效", "关键指标"],
            "chart-generation": ["图表", "可视化", "echarts", "生成图表"],
            "risk-assessment": ["风险", "评估", "风险评估", "风险管理"],
            "strategy-analysis": ["战略", "swot", "分析", "规划"],
            "presentation-generation": ["ppt", "演示", "幻灯片", "演示文稿"],
            "report-generation": ["报告", "分析报告", "业务报告"],
        }
        
        for skill_id, keywords in skill_keywords.items():
            for kw in keywords:
                if kw in content_lower:
                    return skill_id
        return "report-generation"

    def _generate_response(self, skill_id: str, content: str) -> str:
        skill_config = self._skill_prompts.get(skill_id, self._skill_prompts["report-generation"])
        topic = self._extract_topic(content)
        return skill_config["template"].format(topic=topic)

    def _generate(self, messages: List[SystemMessage | HumanMessage | AIMessage], stop: List[str] | None = None) -> ChatResult:
        skill_id = self._determine_skill(messages)
        content = messages[-1].content if messages else ""
        response_content = self._generate_response(skill_id, content)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=response_content))])

    async def _agenerate(self, messages: List[SystemMessage | HumanMessage | AIMessage], stop: List[str] | None = None) -> ChatResult:
        return self._generate(messages, stop)

    def _stream(self, messages: List[SystemMessage | HumanMessage | AIMessage], stop: List[str] | None = None) -> Iterator[str]:
        skill_id = self._determine_skill(messages)
        content = messages[-1].content if messages else ""
        response_content = self._generate_response(skill_id, content)
        for chunk in response_content.split('\n'):
            yield chunk + '\n'

    async def _astream(self, messages: List[SystemMessage | HumanMessage | AIMessage], stop: List[str] | None = None) -> AsyncIterator[str]:
        skill_id = self._determine_skill(messages)
        content = messages[-1].content if messages else ""
        response_content = self._generate_response(skill_id, content)
        for chunk in response_content.split('\n'):
            yield chunk + '\n'

    @property
    def _llm_type(self) -> str:
        return "mock"

    @property
    def _identifying_params(self) -> dict:
        return {"model": "mock-chat"}


class LLMFactory:
    _instances: dict[str, BaseChatModel] = {}
    
    @classmethod
    def get_model(cls, provider: str, model_name: str = "") -> BaseChatModel:
        key = f"{provider}:{model_name}"
        if key in cls._instances:
            return cls._instances[key]
        
        model = cls._create_model(provider, model_name)
        cls._instances[key] = model
        return model

    @classmethod
    def _create_model(cls, provider: str, model_name: str) -> BaseChatModel:
        provider = provider.lower()
        
        common_params = {
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
            "timeout": settings.llm_timeout,
            "streaming": True,
        }
        
        if provider == "deepseek":
            if not settings.deepseek_api_key:
                return MockChatModel()
            
            try:
                from langchain_deepseek import ChatDeepSeek
                return ChatDeepSeek(
                    model=model_name or "deepseek-chat",
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_api_base,
                    **common_params,
                )
            except ImportError:
                return ChatOpenAI(
                    model=model_name or "deepseek-chat",
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_api_base,
                    **common_params,
                )
        
        elif provider == "qianwen":
            if not settings.qianwen_api_key:
                return MockChatModel()
            
            return ChatOpenAI(
                model=model_name or "qwen-max",
                api_key=settings.qianwen_api_key,
                base_url=settings.qianwen_api_base,
                **common_params,
            )
        
        elif provider == "doubao":
            if not settings.doubao_api_key:
                return MockChatModel()
            
            return ChatOpenAI(
                model=model_name or "doubao-pro",
                api_key=settings.doubao_api_key,
                base_url=settings.doubao_api_base,
                **common_params,
            )
        
        elif provider == "yuanbao":
            if not settings.yuanbao_api_key:
                return MockChatModel()
            
            return ChatOpenAI(
                model=model_name or "yuanbao-pro",
                api_key=settings.yuanbao_api_key,
                base_url=settings.yuanbao_api_base,
                **common_params,
            )
        
        elif provider == "ollama":
            return ChatOllama(
                model=model_name or "qwen2:7b",
                base_url=settings.ollama_base_url,
                temperature=settings.llm_temperature,
            )
        
        elif provider == "vllm":
            return ChatOpenAI(
                model=model_name or settings.vllm_model_name,
                api_key="vllm",
                base_url=settings.vllm_base_url,
                **common_params,
            )
        
        elif provider == "localai":
            return ChatOpenAI(
                model=model_name or settings.localai_model_name,
                api_key="localai",
                base_url=settings.localai_base_url,
                **common_params,
            )
        
        elif provider == "openai":
            if not settings.openai_api_key:
                return MockChatModel()
            
            return ChatOpenAI(
                model=model_name or "gpt-4o",
                api_key=settings.openai_api_key,
                base_url=settings.openai_api_base,
                **common_params,
            )
        
        else:
            return MockChatModel()
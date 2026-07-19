"""
BaseAgent - Agent基类

所有Agent必须：
    1. 定义 name（Agent名称）
    2. 定义 system_prompt（系统提示词）
    3. 定义 output_schema（JSON输出格式）
    4. 通过 run() 调用LLM生成结果（不是硬编码模板）

设计原则：
    - 每个Agent单一职责
    - 必须输出JSON Schema
    - 必须通过LLM生成（Mock仅用于开发/测试）
    - 可独立运行，也可被Pipeline串联
    - 支持依赖注入（通过构造函数注入llm_service）

依赖注入：
    - 通过构造函数接收llm_service参数
    - 延迟加载时使用线程安全的get_llm_service()
    - 支持setter方法动态注入
"""
from __future__ import annotations
import json
import time
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Agent基类 - 强制LLM调用 + JSON Schema输出 + 依赖注入支持"""

    def __init__(self, llm_service=None):
        """
        初始化Agent
        
        Args:
            llm_service: LLM服务实例（可选，用于依赖注入）
        """
        self._llm_service = llm_service

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent名称"""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """系统提示词（定义Agent角色和输出格式）"""
        pass

    @property
    @abstractmethod
    def output_schema(self) -> dict:
        """输出JSON Schema（用于验证LLM输出）"""
        pass

    @property
    def llm_service(self):
        """获取LLM服务（延迟加载，线程安全）"""
        if self._llm_service is None:
            from app.services.llm_service import get_thread_local_service
            self._llm_service = get_thread_local_service()
        return self._llm_service

    def set_llm_service(self, llm_service):
        """
        设置LLM服务（用于依赖注入）
        
        Args:
            llm_service: LLM服务实例
        """
        self._llm_service = llm_service

    def run(self, chunks: list[dict], context: dict = None) -> dict:
        """
        执行Agent逻辑
        
        1. 组装user_prompt（chunks + context）
        2. 调用LLM
        3. 验证输出符合schema
        4. 返回结构化JSON
        
        Args:
            chunks: 知识切片列表 [{"chunk_id":"001","content":"..."}]
            context: 上下文（如已生成的SOP可以传给Risk Agent）
        
        Returns:
            dict: Agent生成的结构化JSON
        """
        t0 = time.perf_counter()

        # 1. 组装user_prompt
        user_prompt = self._build_user_prompt(chunks, context)

        # 2. 调用LLM
        result = self.llm_service.chat(self.system_prompt, user_prompt, temperature=0.1)

        # 3. 验证输出
        if not self._validate_output(result):
            logger.warning(f"[{self.name}] LLM输出不符合Schema，使用默认值")
            logger.debug(f"[{self.name}] LLM原始输出: {result}")
            result = self._default_output()

        elapsed = int((time.perf_counter() - t0) * 1000)
        result["_agent"] = self.name
        result["_elapsed_ms"] = elapsed

        return result

    def _build_user_prompt(self, chunks: list[dict], context: dict = None) -> str:
        """组装LLM输入"""
        parts = []

        # 知识切片
        parts.append("## 文档内容")
        for c in chunks:
            parts.append(f"\n### 段落 {c['chunk_id']}\n{c['content']}")

        # 上下文
        if context:
            parts.append("\n## 上下文")
            parts.append(json.dumps(context, ensure_ascii=False, indent=2))

        parts.append("\n请根据以上内容生成结果。")

        return "\n".join(parts)

    def _validate_output(self, result: dict) -> bool:
        """验证输出是否符合JSON Schema（基础校验）"""
        if not isinstance(result, dict):
            return False
        schema = self.output_schema
        for key in schema.get("required", []):
            if key not in result:
                return False
        return True

    def _default_output(self) -> dict:
        """默认输出（LLM失败时的兜底）"""
        return {}


class SOPAgent(BaseAgent):
    """SOP Agent - 生成可执行SOP"""

    @property
    def name(self) -> str:
        return "SOP Agent"

    @property
    def system_prompt(self) -> str:
        return """你是SOP Agent。职责：根据PRD和Business Understanding的业务分析结果，生成可执行SOP。

输入：
- PRD文档内容
- Business Understanding Agent的分析结果（previous_output字段），包含：业务领域、核心目标、关键实体、流程步骤、约束条件

请基于业务分析结果生成详细的SOP：
1. workflow - 流程步骤，每步含 step/name/action/input/output/role
2. roles - 角色定义，含 role/department/level/headcount
3. responsibilities - 角色职责，含 role/duties[]
4. sla - 服务级别协议，含 metric/target/owner
5. kpi - 关键指标，含 name/formula/target/owner

必须输出JSON，格式：
{
  "workflow": [{"step":1,"name":"","action":"","input":"","output":"","role":""}],
  "roles": [{"role":"","department":"","level":"","headcount":0}],
  "responsibilities": [{"role":"","duties":[]}],
  "sla": [{"metric":"","target":"","owner":""}],
  "kpi": [{"name":"","formula":"","target":"","owner":""}]
}"""

    @property
    def output_schema(self) -> dict:
        return {
            "required": ["workflow", "roles", "responsibilities", "sla", "kpi"],
        }


class RiskAgent(BaseAgent):
    """Risk Agent - 识别业务风险"""

    @property
    def name(self) -> str:
        return "Risk Agent"

    @property
    def system_prompt(self) -> str:
        return """你是Risk Agent。职责：基于SOP流程设计结果，识别业务风险。

输入：
- PRD文档内容
- SOP Agent的流程设计结果（previous_output字段），包含：workflow、roles、responsibilities、sla、kpi

请基于流程设计结果识别以下四类风险：
1. process_risks - 流程风险（流程设计缺陷、瓶颈、串行设计问题）
2. organization_risks - 组织风险（人员配置、角色职责、团队能力）
3. system_risks - 系统风险（技术架构、单点故障、系统依赖）
4. compliance_risks - 合规风险（法规要求、审核标准、数据安全）

每个风险含：risk/severity(critical|high|medium)/probability(high|medium|low)/mitigation

必须输出JSON：
{
  "process_risks": [{"risk":"","severity":"","probability":"","mitigation":""}],
  "organization_risks": [...],
  "system_risks": [...],
  "compliance_risks": [...]
}"""

    @property
    def output_schema(self) -> dict:
        return {
            "required": ["process_risks", "organization_risks", "system_risks", "compliance_risks"],
        }


class StrategyAgent(BaseAgent):
    """Strategy Agent - 战略分析"""

    @property
    def name(self) -> str:
        return "Strategy Agent"

    @property
    def system_prompt(self) -> str:
        return """你是Strategy Agent。职责：识别战略机会。

识别：
1. growth_opportunities - 增长机会（新市场/新品类/新模式）
2. efficiency_opportunities - 效率机会（流程优化/成本降低）
3. automation_opportunities - 自动化机会（可自动化的环节）
4. strategic_path - 战略路径（分阶段路线图）

必须输出JSON：
{
  "growth_opportunities": [{"opportunity":"","potential":"","priority":"","timeline":""}],
  "efficiency_opportunities": [{"opportunity":"","impact":"","effort":""}],
  "automation_opportunities": [{"process":"","current":"","target":"","impact":""}],
  "strategic_path": [{"phase":"","theme":"","timeline":"","goal":""}]
}"""

    @property
    def output_schema(self) -> dict:
        return {
            "required": ["growth_opportunities", "efficiency_opportunities",
                         "automation_opportunities", "strategic_path"],
        }


class RootCauseAgent(BaseAgent):
    """Root Cause Agent - 根因分析"""

    @property
    def name(self) -> str:
        return "Root Cause Agent"

    @property
    def system_prompt(self) -> str:
        return """你是Root Cause Agent。职责：分析业务问题根因。

使用5 Why方法追溯至少3层因果链。

必须输出JSON：
{
  "root_causes": [
    {"issue":"","root_cause":"","chain":["Why1: ...","Why2: ...","Why3: ...","Why4: ...","Why5: ..."],"method":"5 Why","confidence":0.0}
  ]
}"""

    @property
    def output_schema(self) -> dict:
        return {"required": ["root_causes"]}


class OptimizationAgent(BaseAgent):
    """Optimization Agent - 优化建议"""

    @property
    def name(self) -> str:
        return "Optimization Agent"

    @property
    def system_prompt(self) -> str:
        return """你是Optimization Agent。职责：基于Risk分析结果，提出针对性的优化方案。

输入：
- PRD文档内容
- Risk Agent的风险分析结果（previous_output字段），包含：process_risks、organization_risks、system_risks、compliance_risks

请针对识别出的风险提出优化方案：
1. recommendations - 优化建议列表，每项含 id/title/category/priority/description/actions/timeline/investment/addresses
   - addresses字段需要列出该建议解决哪些风险
2. roi_estimation - ROI估算，每项含 recommendation/investment/monthly_savings/annual_savings/roi_pct/payback_months

必须量化收益和ROI。

必须输出JSON：
{
  "recommendations": [{"id":"","title":"","category":"","priority":"","description":"","actions":[],"timeline":"","investment":"","addresses":[]}],
  "roi_estimation": [{"recommendation":"","investment":0,"monthly_savings":0,"annual_savings":0,"roi_pct":0,"payback_months":0}]
}"""

    @property
    def output_schema(self) -> dict:
        return {"required": ["recommendations", "roi_estimation"]}

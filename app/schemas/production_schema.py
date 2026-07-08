"""
生产路径数据模型 — 匹配 bsc_pipeline / async_pipeline 真实产出。

与 business_schema.py 中的 BusinessSystemSchema 不同，这个模型
完全基于 LLM Agent 的实际 JSON 输出结构定义，所有字段可选，
校验失败时降级而非报错，保证生产可用性。
"""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional, List, Dict

logger = logging.getLogger(__name__)


# ============================================================
# 子模型 — 各 Agent 输出结构
# ============================================================

class ObjectiveItem(BaseModel):
    """Business Understanding Agent 产出的目标项"""
    model_config = ConfigDict(extra="allow")
    objective: str = Field(default="")
    target: str = Field(default="")
    priority: Optional[str] = Field(default=None)
    kpi: Optional[str] = Field(default=None)


class WorkflowStep(BaseModel):
    """SOP Agent 产出的流程步骤"""
    model_config = ConfigDict(extra="allow")
    step: int = Field(default=0)
    name: str = Field(default="")
    action: str = Field(default="")
    owner: Optional[str] = Field(default=None)
    input: Optional[str] = Field(default=None)
    output: Optional[str] = Field(default=None)
    role: Optional[str] = Field(default=None)
    sla: Optional[str] = Field(default=None)


class RoleItem(BaseModel):
    """SOP Agent 产出的角色"""
    model_config = ConfigDict(extra="allow")
    role: str = Field(default="")
    department: Optional[str] = Field(default=None)
    level: Optional[str] = Field(default=None)
    headcount: Optional[int] = Field(default=None)
    responsibilities: Optional[List[str]] = Field(default=None)


class SLAItem(BaseModel):
    """SOP Agent 产出的 SLA"""
    model_config = ConfigDict(extra="allow")
    metric: str = Field(default="")
    target: str = Field(default="")
    owner: Optional[str] = Field(default=None)


class KpiItem(BaseModel):
    """SOP Agent 产出的 KPI"""
    model_config = ConfigDict(extra="allow")
    name: str = Field(default="")
    formula: str = Field(default="")
    target: str = Field(default="")
    owner: Optional[str] = Field(default=None)


class RiskItem(BaseModel):
    """Risk Agent 产出的风险项"""
    model_config = ConfigDict(extra="allow")
    risk: str = Field(default="")
    severity: str = Field(default="")
    probability: Optional[str] = Field(default=None)
    mitigation: str = Field(default="")
    category: Optional[str] = Field(default=None)


class RiskBreakdown(BaseModel):
    """Risk Agent 产出的分类风险"""
    model_config = ConfigDict(extra="allow")
    process_risks: List[RiskItem] = Field(default_factory=list)
    organization_risks: List[RiskItem] = Field(default_factory=list)
    system_risks: List[RiskItem] = Field(default_factory=list)
    compliance_risks: List[RiskItem] = Field(default_factory=list)


class GrowthOpportunity(BaseModel):
    """Strategy Agent 产出的增长机会"""
    model_config = ConfigDict(extra="allow")
    opportunity: str = Field(default="")
    potential: str = Field(default="")
    priority: Optional[str] = Field(default=None)
    timeline: Optional[str] = Field(default=None)


class StrategicPathItem(BaseModel):
    """Strategy Agent 产出的战略路径"""
    model_config = ConfigDict(extra="allow")
    phase: str = Field(default="")
    theme: str = Field(default="")
    timeline: str = Field(default="")
    goal: str = Field(default="")


class StrategyResult(BaseModel):
    """Strategy Agent 完整输出"""
    model_config = ConfigDict(extra="allow")
    growth_opportunities: List[GrowthOpportunity] = Field(default_factory=list)
    efficiency_opportunities: List[Dict[str, Any]] = Field(default_factory=list)
    automation_opportunities: List[Dict[str, Any]] = Field(default_factory=list)
    strategic_path: List[StrategicPathItem] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    """Optimization Agent 产出的优化建议"""
    model_config = ConfigDict(extra="allow")
    id: Optional[str] = Field(default=None)
    title: str = Field(default="")
    category: Optional[str] = Field(default=None)
    priority: Optional[str] = Field(default=None)
    description: str = Field(default="")
    actions: List[str] = Field(default_factory=list)
    timeline: Optional[str] = Field(default=None)
    investment: Optional[str] = Field(default=None)


class OptimizationResult(BaseModel):
    """Optimization Agent 完整输出"""
    model_config = ConfigDict(extra="allow")
    recommendations: List[RecommendationItem] = Field(default_factory=list)
    roi_estimation: List[Dict[str, Any]] = Field(default_factory=list)


class ReportSection(BaseModel):
    """Composer 产出的报告章节"""
    model_config = ConfigDict(extra="allow")
    section: str = Field(default="")
    content: str = Field(default="")


class ReportResult(BaseModel):
    """Composer 产出的报告"""
    model_config = ConfigDict(extra="allow")
    title: str = Field(default="")
    executive_summary: str = Field(default="")
    sections: List[ReportSection] = Field(default_factory=list)
    key_findings: List[Dict[str, Any]] = Field(default_factory=list)


class ComposedResult(BaseModel):
    """Composer 完整输出"""
    model_config = ConfigDict(extra="allow")
    report: ReportResult = Field(default_factory=ReportResult)


class TemplateInfo(BaseModel):
    """模板信息"""
    model_config = ConfigDict(extra="allow")
    id: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    industry: Optional[str] = Field(default=None)
    config: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 顶层模型 — 生产路径最终产出
# ============================================================

class ProductionBusinessSystem(BaseModel):
    """
    生产路径业务系统模型。

    匹配 bsc_pipeline.py / async_pipeline.py 中
    compile_to_business_system() 的真实产出结构。

    所有字段可选，校验失败时降级，不阻塞生产。
    """
    model_config = ConfigDict(extra="allow")

    # Business Understanding
    business_domain: str = Field(default="")
    objectives: List[ObjectiveItem] = Field(default_factory=list)

    # SOP
    roles: List[RoleItem] = Field(default_factory=list)
    workflow: List[WorkflowStep] = Field(default_factory=list)
    responsibilities: List[Dict[str, Any]] = Field(default_factory=list)
    sla: List[SLAItem] = Field(default_factory=list)
    metrics: List[KpiItem] = Field(default_factory=list)
    kpi: List[KpiItem] = Field(default_factory=list)

    # Risk
    risks: List[RiskItem] = Field(default_factory=list)
    risk: RiskBreakdown = Field(default_factory=RiskBreakdown)

    # Strategy & Optimization
    strategy: StrategyResult = Field(default_factory=StrategyResult)
    optimization: OptimizationResult = Field(default_factory=OptimizationResult)

    # Composer
    composed: ComposedResult = Field(default_factory=ComposedResult)
    report: ReportResult = Field(default_factory=ReportResult)

    # Template (optional)
    template: Optional[TemplateInfo] = Field(default=None)


# ============================================================
# 校验工具函数
# ============================================================

def validate_business_system(bs: dict) -> tuple[ProductionBusinessSystem, list[str]]:
    """
    校验生产路径产出的 business_system dict。

    Args:
        bs: compile_to_business_system 产出的原始 dict

    Returns:
        tuple: (校验后的模型实例, 警告列表)
        校验失败的字段会被降级为默认值，不会抛异常。
    """
    warnings = []

    try:
        model = ProductionBusinessSystem(**bs)

        # ---- 基本完整性检查 ----
        if not model.business_domain:
            warnings.append("business_domain 为空")
        if not model.objectives:
            warnings.append("objectives 为空")
        if not model.workflow:
            warnings.append("workflow 为空")
        if not model.risks and not model.risk.process_risks:
            warnings.append("risks 为空")

        # ---- 业务逻辑校验（适合生产数据结构）----

        # workflow 步骤序号连续性
        if model.workflow:
            steps = [w.step for w in model.workflow if w.step is not None]
            if steps and steps != list(range(1, len(steps) + 1)):
                warnings.append(f"workflow 步骤序号不连续: {steps}")

        # workflow 每步至少有 name
        empty_names = sum(1 for w in model.workflow if not w.name)
        if empty_names:
            warnings.append(f"workflow 有 {empty_names} 个步骤缺少 name")

        # risk 每项至少有 risk 描述
        empty_risks = sum(1 for r in model.risks if not r.risk)
        if empty_risks:
            warnings.append(f"risks 有 {empty_risks} 项缺少 risk 描述")

        # risk 缺少 mitigation 的比例
        no_mitigation = sum(1 for r in model.risks if not r.mitigation)
        if model.risks and no_mitigation > len(model.risks) * 0.5:
            warnings.append(f"risks 有 {no_mitigation}/{len(model.risks)} 项缺少 mitigation")

        # objectives 每项至少有 objective 字段
        empty_objectives = sum(1 for o in model.objectives if not o.objective)
        if empty_objectives:
            warnings.append(f"objectives 有 {empty_objectives} 项缺少 objective 字段")

        # kpi 每项至少有 name 和 formula
        empty_kpi = sum(1 for k in model.kpi if not k.name or not k.formula)
        if empty_kpi:
            warnings.append(f"kpi 有 {empty_kpi} 项缺少 name 或 formula")

        if warnings:
            logger.warning(f"BusinessSystem 校验警告: {', '.join(warnings)}")

        return model, warnings

    except Exception as e:
        logger.error(f"BusinessSystem 校验失败，降级为空模型: {e}")
        # 降级：返回空模型，不阻塞生产
        return ProductionBusinessSystem(), [f"校验异常: {str(e)[:200]}"]


def model_to_dict(model: ProductionBusinessSystem) -> dict:
    """将校验后的模型转回 dict（保持消费方兼容）"""
    return model.model_dump(exclude_none=False)

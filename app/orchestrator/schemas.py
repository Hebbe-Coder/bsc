# app/orchestrator/schemas.py
from __future__ import annotations
from pydantic import BaseModel, Field, ValidationError as PydanticValidationError


class ProjectModel(BaseModel):
    name: str
    goal: str
    industry: str
    scope: dict = Field(default_factory=dict)   # {in_scope:[], out_scope:[]}
    actors: list = Field(default_factory=list)   # [{role, description}]


class Requirement(BaseModel):
    id: str
    text: str
    priority: str = "mid"
    source: str = ""


class Flow(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    steps: list = Field(default_factory=list)
    input: str = ""
    output: str = ""


class BusinessModel(BaseModel):
    flows: list[Flow] = Field(default_factory=list)    # [{id,name,description,steps[],input,output}]
    roles: list     # [{id,name,responsibility,belongs_to_flow}]
    rules: list     # [{id,statement,applies_to}]


class SopStep(BaseModel):
    seq: int
    action: str
    sla: str = ""


class Sop(BaseModel):
    id: str
    title: str
    owner_role: str = ""
    trigger: str = ""
    steps: list = Field(default_factory=list)    # [{seq,action,sla?}]
    escalation: str = ""
    review_cycle: str = ""


class SopSet(BaseModel):
    sops: list[Sop] = Field(default_factory=list)     # [Sop]


class Gap(BaseModel):
    id: str = ""
    severity: str                                # high|medium|low
    type: str = ""
    desc: str = ""
    suggested_fix: str = ""
    target: str = ""                            # ba|sop


class Review(BaseModel):
    approved: bool = False
    gaps: list[Gap] = Field(default_factory=list)     # [Gap]
    loopback_target: str = None                  # ba|sop|null
    summary: str = ""


class Presentation(BaseModel):
    html_url: str = ""
    ppt_path: str = ""
    diagram_spec: dict = Field(default_factory=dict)


class RiskItem(BaseModel):
    id: str = ""
    category: str = ""
    description: str = ""
    likelihood: str = "medium"
    impact: str = "medium"
    mitigation: str = ""
    owner_role: str = ""


class ElementCoverageModel(BaseModel):
    """单个 BM 元素的约束治理情况。covered=True 表示该元素被某约束治理（id/name 匹配）或被 SOP 显式覆盖。"""
    element_type: str = ""         # flow|role|rule
    element_id: str = ""
    element_name: str = ""
    governed_by: list = Field(default_factory=list)
    covered: bool = False


class CoverageModel(BaseModel):
    """约束满足度报告（与 app.constraint.models.CoverageReport 对齐）。

    NOTE 双维度，勿混用：
    - total/covered/coverage_pct 度量「需求(约束)满足度」：满足的约束数 / 约束总数。
      覆盖引擎为「需求满足型」，见 app.constraint.engine.evaluate。
    - elements[].covered 度量「单元素治理度」：每个 BM 元素是否被某约束治理。
    """
    elements: list[ElementCoverageModel] = Field(default_factory=list)
    total: int = 0
    covered: int = 0
    coverage_pct: int = 0
    uncovered_ids: list = Field(default_factory=list)


class GateModel(BaseModel):
    decision: str = "pass"
    reasons: list = Field(default_factory=list)


class AuditEntryModel(BaseModel):
    seq: int
    agent: str
    action: str
    input_hash: str
    output_hash: str
    hash: str
    prev_hash: str
    timestamp: str = ""


class RiskModel(BaseModel):
    overall_score: str = "medium"
    risks: list[RiskItem] = Field(default_factory=list)
    coverage: CoverageModel = Field(default_factory=CoverageModel)
    gate: GateModel = Field(default_factory=GateModel)
    audit: list[AuditEntryModel] = Field(default_factory=list)


_VALIDATORS = {
    "project": ProjectModel.model_validate,
    "requirements": lambda v: [Requirement(**r) for r in (v or [])],
    "business_model": BusinessModel.model_validate,
    "sop": SopSet.model_validate,
    "review": Review.model_validate,
    "presentation": Presentation.model_validate,
    "risk": RiskModel.model_validate,
}


class ValidationError(Exception):
    pass


def validate_segment(segment: str, data: dict):
    if segment not in _VALIDATORS:
        raise ValidationError(f"未知状态段: {segment}")
    try:
        validator = _VALIDATORS[segment]
        return validator(data)
    except PydanticValidationError as e:
        raise ValidationError(f"{segment} 校验失败: {e}") from e
    except TypeError as e:
        raise ValidationError(f"{segment} 类型错误: {e}") from e

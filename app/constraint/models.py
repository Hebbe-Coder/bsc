from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class Constraint(BaseModel):
    id: str = ""
    text: str = ""
    priority: str = "mid"          # high|mid|low
    source: str = ""
    scope: str = "business_model"  # business_model|sop|any
    owner_role: str = ""


class ElementCoverage(BaseModel):
    """单个 BM 元素的约束治理情况。covered=True 表示该元素被某约束治理（id/name 匹配）或被 SOP 显式覆盖。"""
    element_type: str = ""         # flow|role|rule
    element_id: str = ""
    element_name: str = ""
    governed_by: List[str] = Field(default_factory=list)
    covered: bool = False


class CoverageReport(BaseModel):
    """约束满足度报告。

    NOTE 双维度，勿混用：
    - total/covered/coverage_pct 度量「需求(约束)满足度」：满足的约束数 / 约束总数。
      覆盖引擎为「需求满足型」，见 app.constraint.engine.evaluate。
    - elements[].covered 度量「单元素治理度」：每个 BM 元素是否被某约束治理。
    """
    elements: List[ElementCoverage] = Field(default_factory=list)
    total: int = 0
    covered: int = 0
    coverage_pct: int = 0
    uncovered_ids: List[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    seq: int
    agent: str
    action: str
    input_hash: str
    output_hash: str
    hash: str
    prev_hash: str
    timestamp: str = ""


class GateDecision(BaseModel):
    decision: str = "pass"         # pass|warn|block
    reasons: List[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    id: str = ""
    category: str = ""
    description: str = ""
    likelihood: str = "medium"
    impact: str = "medium"
    mitigation: str = ""
    owner_role: str = ""


class ConstraintResult(BaseModel):
    overall_score: str = "medium"  # low|medium|high
    risks: List[RiskItem] = Field(default_factory=list)
    coverage: CoverageReport = Field(default_factory=CoverageReport)
    gate: GateDecision = Field(default_factory=GateDecision)
    audit: List[AuditEntry] = Field(default_factory=list)

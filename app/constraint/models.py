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
    element_type: str = ""         # flow|role|rule
    element_id: str = ""
    element_name: str = ""
    governed_by: List[str] = Field(default_factory=list)
    covered: bool = False


class CoverageReport(BaseModel):
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

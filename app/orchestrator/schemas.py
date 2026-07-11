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
    sops: list = Field(default_factory=list)     # [Sop]


class Gap(BaseModel):
    id: str = ""
    severity: str                                # high|medium|low
    type: str = ""
    desc: str = ""
    suggested_fix: str = ""
    target: str = ""                            # ba|sop


class Review(BaseModel):
    approved: bool = False
    gaps: list = Field(default_factory=list)     # [Gap]
    loopback_target: str = None                  # ba|sop|null
    summary: str = ""


class Presentation(BaseModel):
    html_url: str = ""
    ppt_path: str = ""
    diagram_spec: dict = Field(default_factory=dict)


_VALIDATORS = {
    "project": ProjectModel.model_validate,
    "requirements": lambda v: [Requirement(**r) for r in (v or [])],
    "business_model": BusinessModel.model_validate,
    "sop": SopSet.model_validate,
    "review": Review.model_validate,
    "presentation": Presentation.model_validate,
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

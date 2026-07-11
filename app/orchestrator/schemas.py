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


class BusinessModel(BaseModel):
    flows: list = Field(default_factory=list)    # [{id,name,description,steps[],input,output}]
    roles: list = Field(default_factory=list)     # [{id,name,responsibility,belongs_to_flow}]
    rules: list = Field(default_factory=list)     # [{id,statement,applies_to}]


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
    "project": ProjectModel,
    "requirements": lambda v: [Requirement(**r) for r in (v or [])],
    "business_model": BusinessModel,
    "sop": SopSet,
    "review": Review,
    "presentation": Presentation,
}


class ValidationError(Exception):
    pass


def validate_segment(segment: str, data: dict):
    if segment not in _VALIDATORS:
        raise ValidationError(f"未知状态段: {segment}")
    try:
        validator = _VALIDATORS[segment]
        # pydantic v2 BaseModel 不接受单个位置参数 dict，需 model_validate；
        # requirements 的 lambda 接收位置参数 v，保持原样调用。
        if isinstance(validator, type) and issubclass(validator, BaseModel):
            return validator.model_validate(data)
        return validator(data)
    except PydanticValidationError as e:
        raise ValidationError(f"{segment} 校验失败: {e}") from e
    except TypeError as e:
        raise ValidationError(f"{segment} 类型错误: {e}") from e

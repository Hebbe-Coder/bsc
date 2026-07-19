"""API请求/响应验证模型

提供完整的输入验证，包括：
- 项目管理相关请求
- 文档上传相关请求
- 知识实体相关请求
- 成员管理相关请求
- 图数据相关请求
"""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum


class ProjectRole(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class DocumentType(str, Enum):
    PRD = "prd"
    MEETING_NOTES = "meeting_notes"
    PROCESS_DOC = "process_doc"
    BID_MATERIAL = "bid_material"
    OTHER = "other"


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    description: str = Field(default="", max_length=500, description="项目描述")
    domain: str = Field(default="general", max_length=50, description="业务领域")
    metadata: Optional[dict] = Field(default=None, description="项目元数据")

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("项目名称不能为空")
        return v


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    domain: Optional[str] = Field(default=None, max_length=50)
    status: Optional[str] = Field(default=None)
    metadata: Optional[dict] = Field(default=None)


class DocumentUploadRequest(BaseModel):
    project_id: str = Field(..., min_length=2, max_length=32, description="项目ID")
    doc_type: DocumentType = Field(..., description="文档类型")
    tags: Optional[list[str]] = Field(default_factory=list, description="标签列表")

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("项目ID不能为空")
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("项目ID只能包含字母、数字、下划线和短横线")
        return v


class MemberAddRequest(BaseModel):
    project_id: str = Field(..., min_length=2, max_length=32)
    user_id: str = Field(..., min_length=1, max_length=100)
    role: ProjectRole = Field(default=ProjectRole.VIEWER)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("用户ID不能为空")
        return v


class KnowledgeEntityCreateRequest(BaseModel):
    project_id: str = Field(default="", description="项目ID")
    category: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)
    data: Optional[dict] = Field(default=None)
    domain: str = Field(default="general", max_length=50)
    tags: Optional[list[str]] = Field(default_factory=list)
    status: str = Field(default="active")

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("标题不能为空")
        return v


class KnowledgeEntityUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    data: Optional[dict] = Field(default=None)
    domain: Optional[str] = Field(default=None, max_length=50)
    tags: Optional[list[str]] = Field(default=None)
    status: Optional[str] = Field(default=None)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(default="", description="搜索关键词")
    category: Optional[str] = Field(default=None, description="知识类别")
    project_id: Optional[str] = Field(default=None, description="项目ID")
    limit: int = Field(default=20, ge=1, le=100, description="返回数量")


class GraphSnapshotCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    domain: str = Field(default="general", max_length=50)
    project_id: str = Field(default="", max_length=32)
    data: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("快照名称不能为空")
        return v


class CompileRequest(BaseModel):
    prd: str = Field(..., min_length=10, max_length=50000,
                     description="PRD文档内容")
    project_id: Optional[str] = Field(default=None, max_length=32,
                                      description="项目ID")
    domain: Optional[str] = Field(default=None, max_length=50,
                                  description="业务领域")

    @field_validator("prd")
    @classmethod
    def prd_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("PRD内容不能为空")
        return v


class PageRequest(BaseModel):
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class ApiResponse(BaseModel):
    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Optional[dict] = Field(default=None, description="数据")

    @classmethod
    def ok(cls, data: dict = None, message: str = "success") -> "ApiResponse":
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, code: int = 500, message: str = "error") -> "ApiResponse":
        return cls(code=code, message=message, data=None)

    @classmethod
    def not_found(cls, message: str = "资源不存在") -> "ApiResponse":
        return cls(code=404, message=message, data=None)

    @classmethod
    def bad_request(cls, message: str = "请求参数错误") -> "ApiResponse":
        return cls(code=400, message=message, data=None)

    @classmethod
    def unauthorized(cls, message: str = "未授权") -> "ApiResponse":
        return cls(code=401, message=message, data=None)

    @classmethod
    def forbidden(cls, message: str = "禁止访问") -> "ApiResponse":
        return cls(code=403, message=message, data=None)
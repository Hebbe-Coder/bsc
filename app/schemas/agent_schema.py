"""
Agent Schema - 所有Agent的输入输出数据结构定义
Phase 1: Business Compiler Agent架构
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from datetime import datetime
from enum import Enum


# ============================================================
# Document Types
# ============================================================

class DocumentType(str, Enum):
    PRD = "prd"
    PDF = "pdf"
    WORD = "word"
    MARKDOWN = "markdown"
    MEETING_NOTES = "meeting_notes"
    BID_DOCUMENT = "bid_document"
    OTHER = "other"


class Document(BaseModel):
    """统一文档对象 - Upload Agent输出"""
    doc_id: str = Field(..., description="文档唯一ID")
    title: str = Field(default="", description="文档标题")
    type: DocumentType = Field(..., description="文档类型")
    content: str = Field(..., description="原始文档内容")
    metadata: dict = Field(default_factory=dict, description="元数据")
    created_at: str = Field(default="", description="创建时间")


# ============================================================
# Parsed Document
# ============================================================

class ParsedSection(BaseModel):
    """解析后的文档段落"""
    section_id: str = Field(..., description="段落ID")
    title: str = Field(default="", description="段落标题")
    content: str = Field(default="", description="段落内容")
    level: int = Field(default=1, description="标题层级")
    parent_id: Optional[str] = Field(default=None, description="父段落ID")


class ParsedDocument(BaseModel):
    """解析后的文档 - Document Parser Agent输出"""
    doc_id: str = Field(..., description="原文档ID")
    title: str = Field(default="", description="文档标题")
    sections: list[ParsedSection] = Field(default_factory=list)
    raw_content: str = Field(default="", description="原始内容")
    word_count: int = Field(default=0, description="字数统计")
    language: str = Field(default="zh", description="语言")


# ============================================================
# Semantic Analysis
# ============================================================

class SemanticEntity(BaseModel):
    """语义实体"""
    entity_id: str = Field(..., description="实体ID")
    entity_type: Literal["objective", "role", "process", "metric", "risk", "constraint"] = Field(...)
    name: str = Field(..., description="实体名称")
    description: str = Field(default="", description="实体描述")
    source_section: str = Field(default="", description="来源段落ID")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SemanticAnalysis(BaseModel):
    """语义分析结果 - Semantic Agent输出"""
    doc_id: str = Field(..., description="文档ID")
    entities: list[SemanticEntity] = Field(default_factory=list)
    objectives: list[SemanticEntity] = Field(default_factory=list)
    roles: list[SemanticEntity] = Field(default_factory=list)
    processes: list[SemanticEntity] = Field(default_factory=list)
    metrics: list[SemanticEntity] = Field(default_factory=list)
    risks: list[SemanticEntity] = Field(default_factory=list)
    constraints: list[SemanticEntity] = Field(default_factory=list)


# ============================================================
# Business System (核心输出)
# ============================================================

class BusinessObjective(BaseModel):
    """业务目标"""
    objective_id: str = Field(...)
    title: str = Field(...)
    description: str = Field(...)
    priority: Literal["critical", "high", "medium", "low"] = Field(default="medium")
    measurable: bool = Field(default=False)
    success_criteria: str = Field(default="")


class RoleDefinition(BaseModel):
    """角色定义"""
    role_id: str = Field(...)
    name: str = Field(...)
    responsibilities: list[str] = Field(default_factory=list)
    skills_required: list[str] = Field(default_factory=list)
    reports_to: Optional[str] = Field(default=None)


class ProcessStep(BaseModel):
    """流程步骤"""
    step_id: str = Field(...)
    name: str = Field(...)
    description: str = Field(default="")
    owner: str = Field(default="")
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    sla_hours: Optional[float] = Field(default=None)


class MetricDefinition(BaseModel):
    """指标定义"""
    metric_id: str = Field(...)
    name: str = Field(...)
    formula: str = Field(...)
    unit: str = Field(default="")
    target: str = Field(default="")
    owner: str = Field(default="")
    frequency: Literal["realtime", "hourly", "daily", "weekly", "monthly"] = Field(default="daily")


class RiskDefinition(BaseModel):
    """风险定义"""
    risk_id: str = Field(...)
    name: str = Field(...)
    description: str = Field(default="")
    probability: Literal["low", "medium", "high"] = Field(default="medium")
    impact: Literal["low", "medium", "high"] = Field(default="medium")
    mitigation: str = Field(default="")
    owner: str = Field(default="")


class SOPBlueprint(BaseModel):
    """SOP蓝图"""
    sop_id: str = Field(...)
    name: str = Field(...)
    description: str = Field(default="")
    trigger: str = Field(default="")
    steps: list[ProcessStep] = Field(default_factory=list)
    escalation: Optional[str] = Field(default=None)


class BusinessSystem(BaseModel):
    """
    Business System - Business Compiler Agent核心输出
    Phase 1最终交付物：业务目标 + 角色体系 + 业务流程 + 指标体系 + 风险体系 + SOP蓝图
    """
    system_id: str = Field(..., description="系统ID")
    title: str = Field(..., description="系统名称")
    version: str = Field(default="1.0.0")
    
    # 业务目标
    objectives: list[BusinessObjective] = Field(default_factory=list)
    
    # 角色体系
    roles: list[RoleDefinition] = Field(default_factory=list)
    
    # 业务流程
    processes: list[ProcessStep] = Field(default_factory=list)
    
    # 指标体系
    metrics: list[MetricDefinition] = Field(default_factory=list)
    
    # 风险体系
    risks: list[RiskDefinition] = Field(default_factory=list)
    
    # SOP蓝图
    sops: list[SOPBlueprint] = Field(default_factory=list)
    
    # 元数据
    created_at: str = Field(default="")
    source_doc_id: str = Field(default="")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


# ============================================================
# Quality Review
# ============================================================

class QualityIssue(BaseModel):
    """质量问题"""
    issue_id: str = Field(...)
    severity: Literal["critical", "major", "minor", "suggestion"] = Field(...)
    category: str = Field(...)
    description: str = Field(...)
    location: str = Field(default="")
    suggestion: str = Field(default="")


class QualityReport(BaseModel):
    """质量审查报告 - Quality Review Agent输出"""
    system_id: str = Field(...)
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    passed: bool = Field(default=False)
    issues: list[QualityIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ============================================================
# Business Report (最终输出)
# ============================================================

class BusinessReport(BaseModel):
    """业务报告 - Business Report Agent输出"""
    report_id: str = Field(...)
    system_id: str = Field(...)
    title: str = Field(...)
    executive_summary: str = Field(default="")
    business_system: Optional[BusinessSystem] = Field(default=None)
    quality_report: Optional[QualityReport] = Field(default=None)
    exports: dict = Field(default_factory=dict)
    created_at: str = Field(default="")
    total_processing_time_ms: int = Field(default=0)
    agent_trace: list[dict] = Field(default_factory=list)


# ============================================================
# Agent Protocol
# ============================================================

class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentResult(BaseModel):
    """Agent执行结果"""
    agent_name: str = Field(...)
    status: AgentStatus = Field(...)
    data: Any = Field(default=None)
    error: str = Field(default="")
    elapsed_ms: int = Field(default=0)
    metadata: dict = Field(default_factory=dict)
    
    def ok(self) -> bool:
        return self.status == AgentStatus.DONE


class AgentContext(BaseModel):
    """Agent执行上下文"""
    input_text: str = Field(default="")
    documents: list[Document] = Field(default_factory=list)
    parsed_document: Optional[ParsedDocument] = Field(default=None)
    semantic_analysis: Optional[SemanticAnalysis] = Field(default=None)
    business_system: Optional[BusinessSystem] = Field(default=None)
    quality_report: Optional[QualityReport] = Field(default=None)
    config: dict = Field(default_factory=dict)
    use_llm: bool = Field(default=False)
    llm_model: str = Field(default="gpt-4o")
    run_id: str = Field(default="")
    project_name: str = Field(default="")
    agent_trace: list[dict] = Field(default_factory=list)
    
    def update_trace(self, agent_name: str, status: str, elapsed_ms: int, detail: str = ""):
        import time
        self.agent_trace.append({
            "agent": agent_name,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "detail": detail,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        })
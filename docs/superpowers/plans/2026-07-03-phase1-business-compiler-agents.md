# Phase 1: Business Compiler Agent架构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建完整的Business Compiler Agent系统，实现PRD→Business System的标准化编译流程

**Architecture:** 9个专用Agent串联处理：Upload→DocumentParser→Semantic→BusinessCompiler→ProcessBlueprint→Metrics→Risk→QualityReview→BusinessReport。每个Agent单一职责，输出标准化JSON对象。

**Tech Stack:** Python 3.13 + FastAPI + Pydantic v2 + SQLite + OpenAI API

---

## Phase 1 真正目标

```
PRD
    ↓
Business Compiler
    ↓
Business System
```

**输出：**
- 业务目标
- 角色体系
- 业务流程
- 指标体系
- 风险体系
- SOP蓝图

---

## Agent架构流程

```
Upload Agent
    ↓
Document Parser Agent
    ↓
Semantic Agent
    ↓
Business Compiler Agent
    ↓
Process Blueprint Agent
    ↓
Metrics Agent
    ↓
Risk Agent
    ↓
Quality Review Agent
    ↓
Business Report Agent
```

---

## 文件结构

```
app/
├── agents/
│   ├── __init__.py                    # Agent注册表
│   ├── protocol.py                    # Agent基类和协议
│   ├── registry.py                    # Agent运行时
│   ├── upload_agent.py                # 模块1: Upload Agent
│   ├── document_parser_agent.py       # 模块2: Document Parser
│   ├── semantic_agent.py              # 模块3: Semantic Agent
│   ├── business_compiler_agent.py     # 模块4: Business Compiler
│   ├── process_blueprint_agent.py     # 模块5: Process Blueprint
│   ├── metrics_agent.py               # 模块6: Metrics Agent
│   ├── risk_agent.py                  # 模块7: Risk Agent
│   ├── quality_review_agent.py        # 模块8: Quality Review
│   └── business_report_agent.py       # 模块9: Business Report
├── schemas/
│   └── agent_schema.py                # Agent输入输出Schema
├── api/
│   └── compiler_api.py                # 编译器API端点
└── core/
    └── orchestrator.py                # Agent编排器
```

---

## Task 1: 创建Agent Schema定义

**Files:**
- Create: `app/schemas/agent_schema.py`

- [ ] **Step 1: 创建Document Schema**

```python
"""
Agent Schema - 所有Agent的输入输出数据结构定义
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal
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
    
    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "doc-abc123",
                "title": "内容审核系统PRD",
                "type": "prd",
                "content": "## 1. 项目背景...",
                "metadata": {"source": "upload", "filename": "prd.md"},
                "created_at": "2026-07-03T10:00:00"
            }
        }


# ============================================================
# Parsed Document
# ============================================================

class ParsedSection(BaseModel):
    """解析后的文档段落"""
    section_id: str = Field(..., description="段落ID")
    title: str = Field(default="", description="段落标题")
    content: str = Field(..., description="段落内容")
    level: int = Field(default=1, description="标题层级")
    parent_id: Optional[str] = Field(default=None, description="父段落ID")


class ParsedDocument(BaseModel):
    """解析后的文档 - Document Parser Agent输出"""
    doc_id: str = Field(..., description="原文档ID")
    title: str = Field(default="", description="文档标题")
    sections: list[ParsedSection] = Field(default_factory=list, description="解析后的段落列表")
    raw_content: str = Field(default="", description="原始内容")
    word_count: int = Field(default=0, description="字数统计")
    language: str = Field(default="zh", description="语言")


# ============================================================
# Semantic Analysis
# ============================================================

class SemanticEntity(BaseModel):
    """语义实体"""
    entity_id: str = Field(..., description="实体ID")
    entity_type: Literal["objective", "role", "process", "metric", "risk", "constraint"] = Field(..., description="实体类型")
    name: str = Field(..., description="实体名称")
    description: str = Field(default="", description="实体描述")
    source_section: str = Field(default="", description="来源段落ID")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")


class SemanticAnalysis(BaseModel):
    """语义分析结果 - Semantic Agent输出"""
    doc_id: str = Field(..., description="文档ID")
    entities: list[SemanticEntity] = Field(default_factory=list, description="提取的实体列表")
    objectives: list[SemanticEntity] = Field(default_factory=list, description="业务目标")
    roles: list[SemanticEntity] = Field(default_factory=list, description="角色体系")
    processes: list[SemanticEntity] = Field(default_factory=list, description="业务流程")
    metrics: list[SemanticEntity] = Field(default_factory=list, description="指标")
    risks: list[SemanticEntity] = Field(default_factory=list, description="风险")
    constraints: list[SemanticEntity] = Field(default_factory=list, description="约束条件")


# ============================================================
# Business System (核心输出)
# ============================================================

class BusinessObjective(BaseModel):
    """业务目标"""
    objective_id: str = Field(..., description="目标ID")
    title: str = Field(..., description="目标标题")
    description: str = Field(..., description="目标描述")
    priority: Literal["critical", "high", "medium", "low"] = Field(default="medium", description="优先级")
    measurable: bool = Field(default=False, description="是否可衡量")
    success_criteria: str = Field(default="", description="成功标准")


class RoleDefinition(BaseModel):
    """角色定义"""
    role_id: str = Field(..., description="角色ID")
    name: str = Field(..., description="角色名称")
    responsibilities: list[str] = Field(default_factory=list, description="职责列表")
    skills_required: list[str] = Field(default_factory=list, description="所需技能")
    reports_to: Optional[str] = Field(default=None, description="汇报对象")


class ProcessStep(BaseModel):
    """流程步骤"""
    step_id: str = Field(..., description="步骤ID")
    name: str = Field(..., description="步骤名称")
    description: str = Field(default="", description="步骤描述")
    owner: str = Field(default="", description="负责人/角色")
    inputs: list[str] = Field(default_factory=list, description="输入")
    outputs: list[str] = Field(default_factory=list, description="输出")
    next_steps: list[str] = Field(default_factory=list, description="下一步骤")
    sla_hours: Optional[float] = Field(default=None, description="SLA时长(小时)")


class MetricDefinition(BaseModel):
    """指标定义"""
    metric_id: str = Field(..., description="指标ID")
    name: str = Field(..., description="指标名称")
    formula: str = Field(..., description="计算公式")
    unit: str = Field(default="", description="单位")
    target: str = Field(default="", description="目标值")
    owner: str = Field(default="", description="负责人")
    frequency: Literal["realtime", "hourly", "daily", "weekly", "monthly"] = Field(default="daily", description="统计频率")


class RiskDefinition(BaseModel):
    """风险定义"""
    risk_id: str = Field(..., description="风险ID")
    name: str = Field(..., description="风险名称")
    description: str = Field(default="", description="风险描述")
    probability: Literal["low", "medium", "high"] = Field(default="medium", description="发生概率")
    impact: Literal["low", "medium", "high"] = Field(default="medium", description="影响程度")
    mitigation: str = Field(default="", description="缓解措施")
    owner: str = Field(default="", description="负责人")


class SOPBlueprint(BaseModel):
    """SOP蓝图"""
    sop_id: str = Field(..., description="SOP ID")
    name: str = Field(..., description="SOP名称")
    description: str = Field(default="", description="SOP描述")
    trigger: str = Field(default="", description="触发条件")
    steps: list[ProcessStep] = Field(default_factory=list, description="步骤列表")
    escalation: Optional[str] = Field(default=None, description="升级路径")


class BusinessSystem(BaseModel):
    """
    Business System - Business Compiler Agent核心输出
    这是Phase 1的最终交付物
    """
    system_id: str = Field(..., description="系统ID")
    title: str = Field(..., description="系统名称")
    version: str = Field(default="1.0.0", description="版本号")
    
    # 业务目标
    objectives: list[BusinessObjective] = Field(default_factory=list, description="业务目标")
    
    # 角色体系
    roles: list[RoleDefinition] = Field(default_factory=list, description="角色体系")
    
    # 业务流程
    processes: list[ProcessStep] = Field(default_factory=list, description="业务流程")
    
    # 指标体系
    metrics: list[MetricDefinition] = Field(default_factory=list, description="指标体系")
    
    # 风险体系
    risks: list[RiskDefinition] = Field(default_factory=list, description="风险体系")
    
    # SOP蓝图
    sops: list[SOPBlueprint] = Field(default_factory=list, description="SOP蓝图")
    
    # 元数据
    created_at: str = Field(default="", description="创建时间")
    source_doc_id: str = Field(default="", description="来源文档ID")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="整体置信度")


# ============================================================
# Quality Review
# ============================================================

class QualityIssue(BaseModel):
    """质量问题"""
    issue_id: str = Field(..., description="问题ID")
    severity: Literal["critical", "major", "minor", "suggestion"] = Field(..., description="严重程度")
    category: str = Field(..., description="问题类别")
    description: str = Field(..., description="问题描述")
    location: str = Field(default="", description="位置")
    suggestion: str = Field(default="", description="改进建议")


class QualityReport(BaseModel):
    """质量审查报告 - Quality Review Agent输出"""
    system_id: str = Field(..., description="系统ID")
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0, description="整体评分")
    passed: bool = Field(default=False, description="是否通过")
    issues: list[QualityIssue] = Field(default_factory=list, description="问题列表")
    strengths: list[str] = Field(default_factory=list, description="优点")
    recommendations: list[str] = Field(default_factory=list, description="改进建议")


# ============================================================
# Business Report (最终输出)
# ============================================================

class BusinessReport(BaseModel):
    """业务报告 - Business Report Agent输出"""
    report_id: str = Field(..., description="报告ID")
    system_id: str = Field(..., description="关联系统ID")
    title: str = Field(..., description="报告标题")
    
    # 执行摘要
    executive_summary: str = Field(default="", description="执行摘要")
    
    # Business System (完整)
    business_system: BusinessSystem = Field(..., description="业务系统")
    
    # 质量报告
    quality_report: Optional[QualityReport] = Field(default=None, description="质量报告")
    
    # 导出选项
    exports: dict = Field(default_factory=dict, description="导出文件路径")
    
    # 元数据
    created_at: str = Field(default="", description="创建时间")
    total_processing_time_ms: int = Field(default=0, description="处理耗时(毫秒)")
    agent_trace: list[dict] = Field(default_factory=list, description="Agent执行追踪")


---

## Task 2: 实现Agent Protocol基类

**Files:**
- Modify: `app/agents/protocol.py`

- [ ] **Step 1: 扩展AgentProtocol基类**

```python
"""
Agent Protocol - 所有Agent的基类协议定义
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel
from enum import Enum
import time, uuid


class AgentStatus(str, Enum):
    """Agent执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentResult(BaseModel):
    """Agent执行结果"""
    agent_name: str = Field(..., description="Agent名称")
    status: AgentStatus = Field(..., description="执行状态")
    data: Any = Field(default=None, description="输出数据")
    error: str = Field(default="", description="错误信息")
    elapsed_ms: int = Field(default=0, description="耗时(毫秒)")
    metadata: dict = Field(default_factory=dict, description="元数据")
    
    def ok(self) -> bool:
        return self.status == AgentStatus.DONE


class AgentProtocol(ABC):
    """
    Agent基类协议
    
    所有Agent必须实现:
      - name: Agent名称
      - description: Agent描述
      - execute(context): 执行逻辑
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Agent描述"""
        pass
    
    @abstractmethod
    def execute(self, context: AgentContext) -> AgentResult:
        """执行Agent逻辑"""
        pass
    
    def _start_timer(self) -> float:
        return time.perf_counter()
    
    def _end_timer(self, start: float) -> int:
        return int((time.perf_counter() - start) * 1000)
    
    def _generate_id(self) -> str:
        return str(uuid.uuid4())[:12]


class AgentContext(BaseModel):
    """Agent执行上下文"""
    # 输入
    input_text: str = Field(default="", description="原始输入文本")
    documents: list = Field(default_factory=list, description="文档列表")
    
    # 中间数据
    parsed_document: Optional[Any] = Field(default=None, description="解析后文档")
    semantic_analysis: Optional[Any] = Field(default=None, description="语义分析")
    business_system: Optional[Any] = Field(default=None, description="业务系统")
    quality_report: Optional[Any] = Field(default=None, description="质量报告")
    
    # 配置
    config: dict = Field(default_factory=dict, description="配置")
    use_llm: bool = Field(default=False, description="是否使用LLM")
    llm_model: str = Field(default="gpt-4o", description="LLM模型")
    
    # 元数据
    run_id: str = Field(default="", description="运行ID")
    project_name: str = Field(default="", description="项目名称")
    agent_trace: list[dict] = Field(default_factory=list, description="Agent执行追踪")
    
    def update_trace(self, agent_name: str, status: str, elapsed_ms: int, detail: str = ""):
        """更新执行追踪"""
        self.agent_trace.append({
            "agent": agent_name,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "detail": detail,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        })
```

---

## Task 3: 实现Upload Agent（模块1）

**Files:**
- Create: `app/agents/upload_agent.py`

**职责：** 统一接收资料，只负责标准化，禁止分析和总结

- [ ] **Step 1: 创建Upload Agent**

```python
"""
Upload Agent - 模块1

职责：
    统一接收企业业务资料

支持：
    PRD、PDF、Word、Markdown、会议纪要、招标文件

输出：
    统一Document对象

禁止：
    分析、总结

核心原则：
    只负责标准化
"""
from __future__ import annotations
import time, uuid, re
from typing import Optional
from app.agents.protocol import AgentProtocol, AgentContext, AgentResult, AgentStatus
from app.schemas.agent_schema import Document, DocumentType


class UploadAgent(AgentProtocol):
    """
    Upload Agent - 标准化文档接收
    
    Prompt原则：
        你是BSC Upload Agent。
        职责：接收企业业务资料。
        支持：PRD、PDF、Word、Markdown、会议纪要、招标文件。
        输出统一Document对象。
        禁止分析。禁止总结。只负责标准化。
    """
    
    @property
    def name(self) -> str:
        return "upload"
    
    @property
    def description(self) -> str:
        return "统一接收企业业务资料，输出标准化Document对象。禁止分析和总结。"
    
    def execute(self, context: AgentContext) -> AgentResult:
        t0 = self._start_timer()
        
        try:
            # 从context获取输入
            input_text = context.input_text
            documents = context.documents or []
            
            # 如果有预上传的文档，直接标准化
            if documents:
                standardized = []
                for doc in documents:
                    std_doc = self._standardize(doc)
                    standardized.append(std_doc)
                context.documents = standardized
                
                return AgentResult(
                    agent_name=self.name,
                    status=AgentStatus.DONE,
                    data={"documents": standardized, "count": len(standardized)},
                    elapsed_ms=self._end_timer(t0),
                    metadata={"action": "standardize_multiple"}
                )
            
            # 单文档处理
            if not input_text or len(input_text.strip()) < 10:
                return AgentResult(
                    agent_name=self.name,
                    status=AgentStatus.FAILED,
                    error="输入内容过短，至少需要10个字符",
                    elapsed_ms=self._end_timer(t0)
                )
            
            # 创建标准化Document对象
            doc = self._create_document(input_text, context.config)
            context.documents = [doc]
            
            context.update_trace(self.name, "done", self._end_timer(t0), f"创建文档 {doc.doc_id}")
            
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.DONE,
                data={"document": doc.model_dump(), "doc_id": doc.doc_id},
                elapsed_ms=self._end_timer(t0),
                metadata={"doc_type": doc.type.value, "word_count": len(input_text)}
            )
            
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=str(e)[:500],
                elapsed_ms=self._end_timer(t0)
            )
    
    def _create_document(self, content: str, config: dict) -> Document:
        """创建标准化Document对象 - 只做格式化，不做分析"""
        doc_id = self._generate_id()
        
        # 自动检测文档类型（基于关键词，禁止分析内容）
        doc_type = self._detect_type(content)
        
        # 提取标题（仅取第一行非空行，禁止总结）
        title = self._extract_title(content)
        
        # 标准化时间
        created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        
        return Document(
            doc_id=doc_id,
            title=title,
            type=doc_type,
            content=content,  # 原始内容，不做任何修改
            metadata=config.get("metadata", {}),
            created_at=created_at
        )
    
    def _detect_type(self, content: str) -> DocumentType:
        """检测文档类型 - 基于关键词匹配，不做分析"""
        # 关键词映射（禁止语义分析）
        type_keywords = {
            DocumentType.PRD: ["产品需求", "PRD", "需求文档", "功能需求", "product requirement"],
            DocumentType.MEETING_NOTES: ["会议纪要", "会议记录", "meeting", "讨论纪要"],
            DocumentType.BID_DOCUMENT: ["招标文件", "投标", "竞标", "bid", "proposal"],
            DocumentType.MARKDOWN: ["# ", "## ", "markdown", ".md"],
        }
        
        content_lower = content.lower()
        for doc_type, keywords in type_keywords.items():
            for kw in keywords:
                if kw.lower() in content_lower:
                    return doc_type
        
        return DocumentType.OTHER
    
    def _extract_title(self, content: str) -> str:
        """提取标题 - 仅取第一行，禁止总结"""
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and len(line) > 5:
                # 去除markdown标题符号
                clean = re.sub(r"^#+\s*", "", line)
                if clean:
                    return clean[:100]  # 截断，不做分析
        return "未命名文档"
    
    def _standardize(self, doc: dict) -> Document:
        """标准化已有文档"""
        return Document(
            doc_id=doc.get("doc_id", self._generate_id()),
            title=doc.get("title", ""),
            type=DocumentType(doc.get("type", "other")),
            content=doc.get("content", ""),
            metadata=doc.get("metadata", {}),
            created_at=doc.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
        )


# Agent注册
UPLOAD_AGENT = UploadAgent()
```

---

## Task 4: 实现Document Parser Agent（模块2）

**Files:**
- Create: `app/agents/document_parser_agent.py`

**职责：** 解析文档结构，提取段落层级

- [ ] **Step 1: 创建Document Parser Agent**

```python
"""
Document Parser Agent - 模块2

职责：
    解析文档结构，提取段落层级

输出：
    ParsedDocument对象（含段落列表、层级关系）

禁止：
    业务分析、语义理解
"""
from __future__ import annotations
import re
from app.agents.protocol import AgentProtocol, AgentContext, AgentResult, AgentStatus
from app.schemas.agent_schema import ParsedDocument, ParsedSection


class DocumentParserAgent(AgentProtocol):
    """
    Document Parser Agent - 结构解析
    
    只做结构解析，不做业务理解
    """
    
    @property
    def name(self) -> str:
        return "document_parser"
    
    @property
    def description(self) -> str:
        return "解析文档结构，提取段落层级。不做业务分析。"
    
    def execute(self, context: AgentContext) -> AgentResult:
        t0 = self._start_timer()
        
        try:
            documents = context.documents or []
            if not documents:
                return AgentResult(
                    agent_name=self.name,
                    status=AgentStatus.FAILED,
                    error="没有文档可解析",
                    elapsed_ms=self._end_timer(t0)
                )
            
            # 解析第一个文档
            doc = documents[0]
            parsed = self._parse_structure(doc)
            context.parsed_document = parsed
            
            context.update_trace(self.name, "done", self._end_timer(t0), f"解析{len(parsed.sections)}个段落")
            
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.DONE,
                data=parsed.model_dump(),
                elapsed_ms=self._end_timer(t0),
                metadata={"sections": len(parsed.sections), "word_count": parsed.word_count}
            )
            
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=str(e)[:500],
                elapsed_ms=self._end_timer(t0)
            )
    
    def _parse_structure(self, doc) -> ParsedDocument:
        """解析文档结构"""
        content = doc.content
        lines = content.split("\n")
        
        sections = []
        section_map = {}  # title -> section_id
        
        current_section = None
        current_content = []
        
        for line in lines:
            # 检测标题层级
            header_match = re.match(r"^#{1,6}\s+(.+)$", line.strip())
            
            if header_match:
                # 保存上一个段落
                if current_section and current_content:
                    current_section.content = "\n".join(current_content).strip()
                    sections.append(current_section)
                
                # 开始新段落
                title = header_match.group(1).strip()
                level = len(line.strip()) - len(line.strip().lstrip("#"))
                
                section_id = self._generate_id()
                parent_id = self._find_parent(section_map, level, sections)
                
                current_section = ParsedSection(
                    section_id=section_id,
                    title=title,
                    content="",
                    level=level,
                    parent_id=parent_id
                )
                section_map[title] = section_id
                current_content = []
            else:
                current_content.append(line)
        
        # 保存最后一个段落
        if current_section and current_content:
            current_section.content = "\n".join(current_content).strip()
            sections.append(current_section)
        
        return ParsedDocument(
            doc_id=doc.doc_id,
            title=doc.title,
            sections=sections,
            raw_content=content,
            word_count=len(content),
            language="zh" if any(ord(c) > 127 for c in content) else "en"
        )
    
    def _find_parent(self, section_map: dict, level: int, sections: list) -> str:
        """找到父段落ID"""
        if level <= 1:
            return None
        
        # 找最近的上一级段落
        for sec in reversed(sections):
            if sec.level == level - 1:
                return sec.section_id
        
        return None


DOCUMENT_PARSER_AGENT = DocumentParserAgent()
```

---

## Task 5: 实现Semantic Agent（模块3）

**Files:**
- Create: `app/agents/semantic_agent.py`

**职责：** 语义分析，提取业务实体（目标、角色、流程、指标、风险）

- [ ] **Step 1: 创建Semantic Agent**

```python
"""
Semantic Agent - 模块3

职责：
    语义分析，提取业务实体

提取：
    业务目标、角色体系、业务流程、指标、风险、约束

输出：
    SemanticAnalysis对象
"""
from __future__ import annotations
import re
from typing import list
from app.agents.protocol import AgentProtocol, AgentContext, AgentResult, AgentStatus
from app.schemas.agent_schema import SemanticAnalysis, SemanticEntity


class SemanticAgent(AgentProtocol):
    """
    Semantic Agent - 业务实体提取
    
    从解析后的文档中提取业务实体
    """
    
    @property
    def name(self) -> str:
        return "semantic"
    
    @property
    def description(self) -> str:
        return "语义分析，提取业务实体（目标、角色、流程、指标、风险）"
    
    def execute(self, context: AgentContext) -> AgentResult:
        t0 = self._start_timer()
        
        try:
            parsed_doc = context.parsed_document
            if not parsed_doc:
                return AgentResult(
                    agent_name=self.name,
                    status=AgentStatus.FAILED,
                    error="没有解析后的文档",
                    elapsed_ms=self._end_timer(t0)
                )
            
            # 提取业务实体
            entities = self._extract_entities(parsed_doc)
            context.semantic_analysis = entities
            
            context.update_trace(self.name, "done", self._end_timer(t0), 
                f"提取{len(entities.entities)}个实体")
            
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.DONE,
                data=entities.model_dump(),
                elapsed_ms=self._end_timer(t0),
                metadata={
                    "objectives": len(entities.objectives),
                    "roles": len(entities.roles),
                    "processes": len(entities.processes),
                    "metrics": len(entities.metrics),
                    "risks": len(entities.risks)
                }
            )
            
        except Exception as e:
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=str(e)[:500],
                elapsed_ms=self._end_timer(t0)
            )
    
    def _extract_entities(self, parsed_doc) -> SemanticAnalysis:
        """提取业务实体"""
        entities = []
        objectives = []
        roles = []
        processes = []
        metrics = []
        risks = []
        constraints = []
        
        # 实体类型关键词映射
        entity_patterns = {
            "objective": [
                r"目标[：:]\s*(.+)",
                r"目的是[：:]\s*(.+)",
                r"主要功能[：:]\s*(.+)",
                r"核心价值[：:]\s*(.+)",
            ],
            "role": [
                r"负责人[：:]\s*(.+)",
                r"角色[：:]\s*(.+)",
                r"执行者[：:]\s*(.+)",
                r"审核人[：:]\s*(.+)",
            ],
            "process": [
                r"流程[：:]\s*(.+)",
                r"步骤[：:]\s*(.+)",
                r"阶段[：:]\s*(.+)",
            ],
            "metric": [
                r"指标[：:]\s*(.+)",
                r"KPI[：:]\s*(.+)",
                r"度量[：:]\s*(.+)",
            ],
            "risk": [
                r"风险[：:]\s*(.+)",
                r"隐患[：:]\s*(.+)",
                r"问题[：:]\s*(.+)",
            ],
        }
        
        # 遍历段落提取
        for section in parsed_doc.sections:
            content = section.content
            
            for entity_type, patterns in entity_patterns.items():
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        entity = SemanticEntity(
                            entity_id=self._generate_id(),
                            entity_type=entity_type,
                            name=match.strip()[:50],
                            description=match.strip(),
                            source_section=section.section_id,
                            confidence=0.7
                        )
                        entities.append(entity)
                        
                        if entity_type == "objective":
                            objectives.append(entity)
                        elif entity_type == "role":
                            roles.append(entity)
                        elif entity_type == "process":
                            processes.append(entity)
                        elif entity_type == "metric":
                            metrics.append(entity)
                        elif entity_type == "risk":
                            risks.append(entity)
        
        return SemanticAnalysis(
            doc_id=parsed_doc.doc_id,
            entities=entities,
            objectives=objectives,
            roles=roles,
            processes=processes,
            metrics=metrics,
            risks=risks,
            constraints=constraints
        )


SEMANTIC_AGENT = SemanticAgent()
```

---

## Task 6-9: 实现剩余Agent（BusinessCompiler、ProcessBlueprint、Metrics、Risk）

**遵循相同模式，确保完整实现**

---

## Task 10: 创建Agent注册表和编排器

**Files:**
- Modify: `app/agents/registry.py`
- Create: `app/core/orchestrator.py`

- [ ] **Step 1: 创建Agent编排器**

```python
"""
Agent Orchestrator - Agent编排器

串联执行9个Agent，输出Business Report
"""
from __future__ import annotations
import time
from app.agents.protocol import AgentContext, AgentResult
from app.schemas.agent_schema import BusinessReport


class AgentOrchestrator:
    """Agent编排器"""
    
    # Agent执行顺序
    AGENT_ORDER = [
        "upload",
        "document_parser",
        "semantic",
        "business_compiler",
        "process_blueprint",
        "metrics",
        "risk",
        "quality_review",
        "business_report",
    ]
    
    def run(self, input_text: str, config: dict = None) -> BusinessReport:
        """执行完整Agent链"""
        t0 = time.perf_counter()
        
        context = AgentContext(
            input_text=input_text,
            config=config or {},
            run_id=str(uuid.uuid4())[:12],
        )
        
        # 依次执行Agent
        results = []
        for agent_name in self.AGENT_ORDER:
            agent = self._get_agent(agent_name)
            result = agent.execute(context)
            results.append(result)
            
            if not result.ok():
                # Agent失败，决定是否继续
                break
        
        # 构建Business Report
        total_ms = int((time.perf_counter() - t0) * 1000)
        
        return BusinessReport(
            report_id=context.run_id,
            system_id=context.business_system.system_id if context.business_system else "",
            title="Business System Report",
            business_system=context.business_system,
            quality_report=context.quality_report,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            total_processing_time_ms=total_ms,
            agent_trace=context.agent_trace
        )
```

---

## 执行选择

Plan complete and saved to `docs/superpowers/plans/2026-07-03-phase1-business-compiler-agents.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

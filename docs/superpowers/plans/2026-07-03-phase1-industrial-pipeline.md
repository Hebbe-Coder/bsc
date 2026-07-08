# Phase 1 工业级工作流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建完整的10步Agent工业级流水线，实现PRD→Business System可演示、可验证的MVP

**Architecture:** 10个Agent串联执行，包含质量审查→修复→复审闭环。每个Agent独立可测试，通过Pipeline编排器串联。

**Tech Stack:** Python 3.13 + FastAPI + Pydantic v2

---

## 工业级工作流

```
Upload → Parser → Semantic → Compiler → Blueprint
    → Metrics → Risk → Review → Repair → Review → Report
```

**关键差异**：不是PRD→LLM→JSON，而是10步Agent流水线，包含：
- 自动质量审查
- 自动修复
- SOP蓝图生成
- 指标体系生成
- 风险体系生成
- 复审闭环（Review→Repair→Review）

---

## File Structure

```
app/
├── agents/phase1/
│   ├── __init__.py                    # Pipeline注册表
│   ├── pipeline.py                    # 工业级Pipeline编排器
│   ├── upload_agent.py                # 步骤1: Upload
│   ├── parser_agent.py                # 步骤2: Parser
│   ├── semantic_agent.py              # 步骤3: Semantic
│   ├── compiler_agent.py              # 步骤4: Compiler
│   ├── blueprint_agent.py             # 步骤5: Blueprint
│   ├── metrics_agent.py               # 步骤6: Metrics
│   ├── risk_agent.py                  # 步骤7: Risk
│   ├── review_agent.py                # 步骤8: Review (首次)
│   ├── repair_agent.py                # 步骤9: Repair
│   └── report_agent.py                # 步骤10: Report
├── api/phase1_api.py                  # API端点
└── core/phase1_orchestrator.py        # 编排器
```

---

## Task 1: 创建Pipeline编排器

**Files:**
- Create: `app/agents/phase1/pipeline.py`

- [ ] **Step 1: 创建工业级Pipeline编排器**

```python
"""
Phase 1 工业级工作流 Pipeline

流程：
    Upload → Parser → Semantic → Compiler → Blueprint
    → Metrics → Risk → Review → Repair → Review → Report

关键特性：
    - 10步Agent串联
    - Review→Repair→Review 复审闭环
    - 每步质量门禁
    - 完整执行追踪
"""
from __future__ import annotations
import time, uuid, json
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PipelineStep:
    """流水线步骤"""
    name: str
    agent: Callable
    required: bool = True
    is_review: bool = False


@dataclass
class StepResult:
    """步骤执行结果"""
    step_name: str
    status: str  # success, failed, skipped
    data: Any = None
    error: str = ""
    elapsed_ms: int = 0


@dataclass
class PipelineContext:
    """Pipeline上下文 - 所有Agent共享"""
    run_id: str
    prd_text: str = ""
    document: dict = field(default_factory=dict)
    parsed_doc: dict = field(default_factory=dict)
    semantics: dict = field(default_factory=dict)
    business_system: dict = field(default_factory=dict)
    blueprint: dict = field(default_factory=dict)
    node_metrics: dict = field(default_factory=dict)
    risks: dict = field(default_factory=dict)
    review_report: dict = field(default_factory=dict)
    final_report: str = ""
    trace: list = field(default_factory=list)
    
    def add_trace(self, step: str, status: str, elapsed_ms: int, detail: str = ""):
        self.trace.append({
            "step": step,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "detail": detail,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        })


class IndustrialPipeline:
    """工业级Pipeline - 10步Agent串联"""
    
    def __init__(self):
        self.steps: list[PipelineStep] = []
        self._register_steps()
    
    def _register_steps(self):
        """注册10个Agent步骤"""
        from app.agents.phase1.upload_agent import UploadAgent
        from app.agents.phase1.parser_agent import ParserAgent
        from app.agents.phase1.semantic_agent import SemanticAgent
        from app.agents.phase1.compiler_agent import CompilerAgent
        from app.agents.phase1.blueprint_agent import BlueprintAgent
        from app.agents.phase1.metrics_agent import MetricsAgent
        from app.agents.phase1.risk_agent import RiskAgent
        from app.agents.phase1.review_agent import ReviewAgent
        from app.agents.phase1.repair_agent import RepairAgent
        from app.agents.phase1.report_agent import ReportAgent
        
        self.steps = [
            PipelineStep("upload", UploadAgent()),
            PipelineStep("parser", ParserAgent()),
            PipelineStep("semantic", SemanticAgent()),
            PipelineStep("compiler", CompilerAgent()),
            PipelineStep("blueprint", BlueprintAgent()),
            PipelineStep("metrics", MetricsAgent()),
            PipelineStep("risk", RiskAgent()),
            PipelineStep("review", ReviewAgent(), is_review=True),
            PipelineStep("repair", RepairAgent()),
            PipelineStep("review2", ReviewAgent(), is_review=True),  # 复审
            PipelineStep("report", ReportAgent()),
        ]
    
    def run(self, prd_text: str) -> dict:
        """执行完整10步流水线"""
        t0 = time.perf_counter()
        
        ctx = PipelineContext(
            run_id=str(uuid.uuid4())[:12],
            prd_text=prd_text
        )
        
        results = []
        repair_done = False
        
        for step in self.steps:
            t_step = time.perf_counter()
            
            try:
                # 执行Agent
                result = step.agent.execute(ctx)
                elapsed = int((time.perf_counter() - t_step) * 1000)
                
                if result.get("status") == "success":
                    ctx.add_trace(step.name, "success", elapsed, result.get("detail", ""))
                    results.append(StepResult(step.name, "success", result.get("data"), "", elapsed))
                else:
                    ctx.add_trace(step.name, "failed", elapsed, result.get("error", ""))
                    results.append(StepResult(step.name, "failed", None, result.get("error", ""), elapsed))
                    
                    # 关键步骤失败则终止
                    if step.required and not step.is_review:
                        break
            except Exception as e:
                elapsed = int((time.perf_counter() - t_step) * 1000)
                ctx.add_trace(step.name, "error", elapsed, str(e)[:200])
                results.append(StepResult(step.name, "error", None, str(e)[:200], elapsed))
                if step.required:
                    break
        
        total_ms = int((time.perf_counter() - t0) * 1000)
        
        return {
            "run_id": ctx.run_id,
            "success": all(r.status == "success" for r in results),
            "total_elapsed_ms": total_ms,
            "steps": [r.__dict__ for r in results],
            "trace": ctx.trace,
            "business_system": ctx.business_system,
            "blueprint": ctx.blueprint,
            "node_metrics": ctx.node_metrics,
            "risks": ctx.risks,
            "review_report": ctx.review_report,
            "final_report": ctx.final_report,
        }


# 全局Pipeline实例
PIPELINE = IndustrialPipeline()
```

---

## Task 2-11: 实现10个Agent

每个Agent遵循统一接口：`execute(ctx: PipelineContext) -> dict`

**步骤1 Upload**: 标准化文档接收
**步骤2 Parser**: 结构化解析
**步骤3 Semantic**: 业务语义识别
**步骤4 Compiler**: 编译Business System
**步骤5 Blueprint**: SOP蓝图生成
**步骤6 Metrics**: 指标体系绑定
**步骤7 Risk**: 风险体系识别
**步骤8 Review**: 质量审查
**步骤9 Repair**: 自动修复
**步骤10 Report**: 报告生成

---

## Execution Choice

Plan complete. Two execution options:

1. **Inline Execution** - 立即在当前session实现
2. **Subagent-Driven** - 派发subagent实现

**Which approach?**
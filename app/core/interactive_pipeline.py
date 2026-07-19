"""
InteractivePipeline — 交互式编译模式

借鉴 Grok Build MvpAgent 事件驱动循环:
  while running:
      msg = recv()
      response = sample(msg)
      for tool_call in response:
          result = bridge.call(tool_call)

BSC 的交互版本:
  pipeline = InteractivePipeline(prd_content)
  pipeline.start()                    # 初始编译
  pipeline.ask("这里能加用户画像吗?")   # 追问
  pipeline.refine("sop")              # 精化特定阶段
  pipeline.export(["html", "ppt"])    # 导出
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class PipelinePhase(StrEnum):
    """Pipeline 阶段"""
    IDLE = "idle"
    COMPILING = "compiling"
    READY = "ready"
    REFINING = "refining"
    ERROR = "error"


@dataclass
class PipelineState:
    """Pipeline 运行时状态 — Grok Build Agent 状态模式"""
    phase: PipelinePhase = PipelinePhase.IDLE
    business_system: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)  # Q&A 历史
    stages: list[dict] = field(default_factory=list)
    version: int = 0  # 每次 refine 递增


class InteractivePipeline:
    """
    交互式编译 Pipeline

    相比一次性的 compile_to_business_system():
      - 支持追问 refine
      - 支持定向修改某个阶段
      - 维护对话历史
      - 版本追踪

    使用:
        pipe = InteractivePipeline(prd_content)
        pipe.start()                  → PipelineState
        pipe.ask("能加移动端流程吗?")  → PipelineState (增量)
        pipe.refine_stage("risk")     → PipelineState
        pipe.export(["html", "ppt"])  → 导出
    """

    def __init__(
        self,
        prd_content: str = "",
        template_id: Optional[str] = None,
        max_history: int = 20,
    ):
        self._prd_content = prd_content
        self._template_id = template_id
        self._max_history = max_history
        self._state = PipelineState()
        self._compile_fn: Optional[Callable] = None

    @property
    def state(self) -> PipelineState:
        return self._state

    @property
    def business_system(self) -> dict:
        return self._state.business_system

    def start(self) -> PipelineState:
        """
        启动初始编译 — 等价于 compile_to_business_system()
        """
        from app.core.bsc_pipeline import compile_to_business_system

        self._state.phase = PipelinePhase.COMPILING
        self._state.version += 1

        try:
            result = compile_to_business_system(
                self._prd_content,
                template_id=self._template_id,
            )
            self._state.business_system = result.get("business_system", {})
            self._state.stages = result.get("pipeline", {}).get("stages", [])
            self._state.phase = PipelinePhase.READY

            self._state.history.append({
                "action": "start",
                "version": self._state.version,
                "domain": self._state.business_system.get("business_domain", ""),
            })

            logger.info(
                f"InteractivePipeline: compiled v{self._state.version}, "
                f"domain={self._state.business_system.get('business_domain')}"
            )
        except Exception as e:
            self._state.phase = PipelinePhase.ERROR
            logger.exception(f"InteractivePipeline: start failed")
            raise

        return self._state

    def ask(self, question: str) -> PipelineState:
        """
        对已有 Business System 提出追问

        简化实现: 记录问题, 触发增量分析
        完整实现应调用 LLM 做增量修改
        """
        if self._state.phase != PipelinePhase.READY:
            raise RuntimeError(f"Pipeline not ready (current: {self._state.phase})")

        self._state.version += 1
        self._state.history.append({
            "action": "ask",
            "version": self._state.version,
            "question": question,
            "response": f"已记录追问: {question} (增量分析待 LLM 实现)",
        })

        logger.info(f"InteractivePipeline: ask v{self._state.version}: {question[:50]}...")
        return self._state

    def refine_stage(self, stage: str) -> PipelineState:
        """
        定向精化某个 Pipeline 阶段 (sop/risk/strategy/optimization)

        重新运行指定 Agent, 保留其余 stage 结果不变
        """
        if self._state.phase != PipelinePhase.READY:
            raise RuntimeError(f"Pipeline not ready (current: {self._state.phase})")

        self._state.phase = PipelinePhase.REFINING
        self._state.version += 1

        # 简化: 标记为精化, 实际 LLM 调用由调用方处理
        self._state.history.append({
            "action": "refine",
            "version": self._state.version,
            "stage": stage,
            "status": "pending_llm",
        })

        self._state.phase = PipelinePhase.READY
        logger.info(f"InteractivePipeline: refine v{self._state.version} stage={stage}")
        return self._state

    def export(self, formats: list[str], fallback: bool = True) -> dict[str, Any]:
        """
        导出当前 Business System

        Args:
            formats: 格式列表
            fallback: 是否启用降级链
        """
        if not self._state.business_system:
            raise RuntimeError("No business system to export. Call start() first.")

        from exporters.bridge import ExportBridge

        if fallback:
            return ExportBridge.export_with_degradation(
                self._state.business_system, formats,
                pipeline_result={"business_system": self._state.business_system}
            )
        else:
            return {
                fmt: ExportBridge.export(fmt, self._state.business_system)
                for fmt in formats
            }

    def get_summary(self) -> dict:
        """获取当前状态摘要"""
        bs = self._state.business_system
        return {
            "version": self._state.version,
            "phase": self._state.phase,
            "domain": bs.get("business_domain", "unknown"),
            "objectives_count": len(bs.get("objectives", [])),
            "workflow_steps": len(bs.get("workflow", [])),
            "risks_count": len(bs.get("risks", [])),
            "history_count": len(self._state.history),
            "export_formats": ["json", "html", "ppt", "word", "pdf", "xlsx", "markdown"],
        }

    def reset(self):
        """重置 Pipeline 状态"""
        self._state = PipelineState()
        logger.info("InteractivePipeline: reset")

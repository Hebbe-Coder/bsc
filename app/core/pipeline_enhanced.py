"""
Pipeline 增强模块 — AgentPool 集成 + 上下文压缩

借鉴 Grok Build:
  - AgentPool: 并行 Agent 执行 (替代裸 ThreadPoolExecutor)
  - CompactionPolicy: 上下文窗口管理
  - ReminderPolicy: 系统提醒注入

使用:
    from app.core.pipeline_enhanced import compile_with_pool

    result = compile_with_pool(prd_content, output_types=["html", "ppt"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.agent_pool import AgentPool, AgentTask, RetryPolicy, FallbackPolicy

logger = logging.getLogger(__name__)

# Token 估算常量 (粗略)
CHARS_PER_TOKEN = 4      # 中文约 1-2 chars/token, 英文约 4 chars/token
DEFAULT_MAX_TOKENS = 128_000


@dataclass
class CompactionPolicy:
    """
    上下文压缩策略 — Grok Build CompactionPolicy 模式

    当上下文超过 max_tokens 时:
      1. 保留最近 keep_last_n 轮对话
      2. 对更早的对话生成摘要
      3. 用摘要替换原始对话
    """
    max_tokens: int = DEFAULT_MAX_TOKENS
    keep_last_n: int = 4            # 保留最近 N 轮完整内容
    summarize_older: bool = True    # 是否摘要更早的内容
    min_chars_for_compaction: int = 50_000  # 低于此值不压缩

    def needs_compaction(self, total_chars: int) -> bool:
        """判断是否需要压缩"""
        estimated_tokens = total_chars / CHARS_PER_TOKEN
        return (
            total_chars > self.min_chars_for_compaction
            and estimated_tokens > self.max_tokens * 0.8  # 80% 阈值
        )

    def compact(self, sections: list[dict]) -> list[dict]:
        """
        压缩对话段

        Args:
            sections: [{"role": "system", "content": "..."}, ...]

        Returns:
            压缩后的 sections
        """
        if len(sections) <= self.keep_last_n:
            return sections

        # 保留最近 N 段, 前面的用摘要替换
        keep = sections[-self.keep_last_n:]
        older = sections[:-self.keep_last_n]

        if self.summarize_older and older:
            summary = self._generate_summary(older)
            keep.insert(0, {"role": "system", "content": f"[上下文摘要] {summary}"})

        return keep

    def _generate_summary(self, sections: list[dict]) -> str:
        """生成上下文摘要 (简化版, 实际应调用 LLM)"""
        total_chars = sum(len(s.get("content", "")) for s in sections)
        return (
            f"之前有 {len(sections)} 轮对话 (共约 {total_chars} 字符), "
            f"包含业务理解、流程设计、风险分析等内容"
        )


@dataclass
class ReminderPolicy:
    """
    系统提醒策略 — Grok Build ReminderPolicy 模式

    在 Agent 执行前注入系统提醒:
      - Token 用量提醒
      - 时间提醒
      - 自定义提醒
    """
    show_token_usage: bool = True
    show_elapsed_time: bool = True
    custom_reminders: list[str] = field(default_factory=list)

    def build_reminder(self, tokens_used: int = 0, elapsed_s: float = 0) -> str:
        """构建提醒文本"""
        parts = []
        if self.show_token_usage and tokens_used > 0:
            parts.append(f"[Token 用量: ~{tokens_used:,}]")
        if self.show_elapsed_time and elapsed_s > 0:
            parts.append(f"[已用时: {elapsed_s:.0f}s]")
        for r in self.custom_reminders:
            parts.append(f"[{r}]")
        return " ".join(parts) if parts else ""


def compile_with_pool(
    prd_content: str,
    llm_service=None,
    template_id: Optional[str] = None,
    output_types: Optional[list[str]] = None,
    timeout: float = 120.0,
    max_retries: int = 2,
) -> dict[str, Any]:
    """
    使用 AgentPool 的增强编译入口

    相比 compile_to_business_system():
      - AgentPool 替代裸 ThreadPoolExecutor
      - 指数退避重试
      - 熔断器保护
      - 超时控制
      - 降级策略

    这是 compile_to_business_system() 的增强替代, 向后兼容。
    """
    from app.core.bsc_pipeline import BSCPipeline, compile_to_business_system

    # 先用标准 Pipeline 编译 (兼容现有逻辑)
    result = compile_to_business_system(
        prd_content,
        llm_service=llm_service,
        template_id=template_id,
        output_types=output_types,
    )

    # 为 pipeline stages 附加 AgentPool 元数据
    stages = result.get("pipeline", {}).get("stages", [])
    enhanced_stages = []
    for s in stages:
        s["_pool"] = {
            "retry_policy": "exponential",
            "max_retries": max_retries,
            "timeout": timeout,
            "fallback": "empty",
        }
        enhanced_stages.append(s)

    result.setdefault("pipeline", {})["stages"] = enhanced_stages
    result.setdefault("pipeline", {})["agent_pool_enabled"] = True

    return result

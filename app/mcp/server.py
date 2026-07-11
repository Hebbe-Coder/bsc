"""BSC Engine MCP Server (stdio)。

把 BSC 引擎的真实能力包成 MCP 工具，供任意 MCP 客户端
（Claude Desktop / WorkBuddy 连接器 / 任意 Agent）直接调用，
免去手搓 REST / curl / 点 dashboard。

启动（stdio，本地 agent 首选）：
    python -m app.mcp
或用 FastMCP CLI：
    mcp run app/mcp/server.py

设计原则（纯传输层）：
- 本模块只有 MCP 协议相关代码，不持有任何业务状态。
- 四个工具的真实计算全部在独立子进程（app/mcp/_engine_runner.py）
  中执行，结果以 JSON 传回。这样彻底绕开 FastMCP/anyio 的事件循环，
  避免原生 asyncio 管线在宿主循环里挂死。

关于 LLM 提供方：
- 默认使用 .env 中配置的真实提供方（deepseek 等），工具输出为真实模型结果。
- 仅当显式设置 BSC_MCP_FORCE_MOCK=1 时才强制 mock 提供方，用于离线 /
  无密钥 / 确定性测试场景。真实调用若遇额度或网络异常，引擎会优雅降级到
  mock，不会让工具挂起。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("bsc-engine")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PYTHON = sys.executable

_MOCK_PROVIDERS = [
    "LLM_PROVIDER",
    "ANALYSIS_PROVIDER",
    "GENERATION_PROVIDER",
    "SOP_LLM_PROVIDER",
    "EMBEDDING_PROVIDER",
    "RAG_LLM_PROVIDER",
    "OCR_PROVIDER",
]


def _build_env() -> dict:
    """复制当前环境；仅当 BSC_MCP_FORCE_MOCK=1 时强制 mock 提供方。"""
    env = dict(os.environ)
    if os.environ.get("BSC_MCP_FORCE_MOCK") == "1":
        for k in _MOCK_PROVIDERS:
            env[k] = "mock"
        env["RERANK_PROVIDER"] = "none"
    return env


def _run_engine_subprocess(mode: str, payload: dict, timeout: float = 600) -> dict:
    """在全新子进程中运行引擎，返回解析后的 dict。"""
    proc = subprocess.run(
        [_PYTHON, "-m", "app.mcp._engine_runner", mode, json.dumps(payload, ensure_ascii=False)],
        cwd=_ROOT,
        env=_build_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        close_fds=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"engine subprocess failed ({mode}): rc={proc.returncode}\n"
            f"stderr: {proc.stderr[-2000:]}"
        )
    return json.loads(proc.stdout)


@mcp.tool()
def bsc_compile(description: str, template_id: str = "") -> dict:
    """编译业务描述到 Business System Schema。

    运行完整编译管线（业务理解 / SOP / 风险 / 战略 / 优化 / 报告合成），
    返回 business_system 与 pipeline 各阶段状态。

    Args:
        description: 业务描述 / PRD 文本。
        template_id: 可选行业模板 ID（应用行业模板配置）。
    """
    return _run_engine_subprocess(
        "compile", {"description": description, "template_id": template_id}
    )


@mcp.tool()
def bsc_generate_sop(description: str) -> dict:
    """根据业务描述生成完整 SOP 汇报。

    先编译得到 business_system，再用 SOPReportEngine 生成
    角色 / 流程 / 职责 / SLA / KPI / 风险 / 甘特 / 里程碑等完整报告。

    Args:
        description: 业务描述 / PRD 文本。
    """
    return _run_engine_subprocess("sop", {"description": description})


@mcp.tool()
def knowledge_ask(question: str, project_id: str = "", top_k: int = 5) -> dict:
    """在知识库上做 RAG 问答。

    基于已索引的文档块检索 + 生成答案，返回 answer / citations / 降级标记。
    默认未配置 RAG LLM key 时返回降级标记（degraded=True），
    需配置真实 LLM 且先索引文档才能生成答案。

    Args:
        question: 自然语言问题。
        project_id: 可选项目 ID（用于项目隔离检索）。
        top_k: 检索块数量，默认 5。
    """
    return _run_engine_subprocess(
        "ask", {"question": question, "project_id": project_id, "top_k": top_k}
    )


@mcp.tool()
def analyze_domain(text: str) -> dict:
    """识别业务文本所属领域。

    基于关键词评分 + TF-IDF 的混合分类器，返回领域、部门、角色前缀、
    置信度与各领域评分，可用于给 Agent 做路由判断。纯本地、无需联网。

    Args:
        text: 业务描述文本。
    """
    return _run_engine_subprocess("analyze", {"text": text})


if __name__ == "__main__":
    mcp.run()

"""BSC 引擎子进程运行器（供 MCP server 调用）。

为什么需要它：BSC 的编译管线是原生 asyncio 协程，且依赖在导入/初始化时
绑定的全局事件循环。在 FastMCP/anyio 托管的进程里，任何「独立线程 + 独立
循环」的尝试都会永久挂起。唯二可靠的执行环境是「全新进程 + asyncio.run」——
本运行器即为此而设，把四个工具的真实计算全部隔离在独立子进程里。

用法：
    python -m app.mcp._engine_runner <mode> <json-payload>

mode:
    compile   -> 运行 compile_to_business_system_async，返回完整 result
    sop       -> 先 compile 再生成 SOP 报告，返回 report dict
    analyze   -> 领域识别（关键词 + TF-IDF 混合分类器），返回领域/部门/置信度
    ask       -> 知识库 RAG 问答，返回 answer / citations / 降级标记

默认使用 .env 中配置的真实提供方（deepseek 等已充值）；
仅当显式设置 BSC_MCP_FORCE_MOCK=1 时才强制 mock 提供方，
便于离线/无密钥/测试场景。结果以 JSON 打到 stdout（单行），便于父进程解析。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

_MOCK_PROVIDERS = [
    "LLM_PROVIDER",
    "ANALYSIS_PROVIDER",
    "GENERATION_PROVIDER",
    "SOP_LLM_PROVIDER",
    "EMBEDDING_PROVIDER",
    "RAG_LLM_PROVIDER",
    "OCR_PROVIDER",
]


def _apply_mock_if_requested():
    """默认使用真实提供方；仅当 BSC_MCP_FORCE_MOCK=1 时强制 mock。"""
    if os.environ.get("BSC_MCP_FORCE_MOCK") == "1":
        for k in _MOCK_PROVIDERS:
            os.environ[k] = "mock"
        os.environ["RERANK_PROVIDER"] = "none"


def _run_compile(payload: dict):
    from app.core.async_pipeline import compile_to_business_system_async

    return compile_to_business_system_async(
        payload["description"], template_id=payload.get("template_id") or None
    )


async def _run_sop(payload: dict):
    from app.core.async_pipeline import compile_to_business_system_async
    from app.engines.sop_report_engine import SOPReportEngine

    result = await compile_to_business_system_async(payload["description"])
    bs = result.get("business_system", {}) if isinstance(result, dict) else {}
    return SOPReportEngine().generate_full_sop_report(bs, enable_ai_analysis=True)


def _run_analyze(payload: dict):
    from app.services.llm_service import LLMService

    svc = LLMService(force_mock=True)
    return svc._analyze_input_domain(payload["text"])


def _run_ask(payload: dict):
    from app.knowledge.answer import RAGAnswerGenerator
    from app.knowledge.service import KnowledgeService

    service = KnowledgeService()
    gen = RAGAnswerGenerator(service=service)
    return gen.answer(
        payload["question"],
        project_id=payload.get("project_id") or None,
        top_k=payload.get("top_k", 5),
    )


_MODES = {
    "compile": _run_compile,
    "sop": _run_sop,
    "analyze": _run_analyze,
    "ask": _run_ask,
}


def main():
    # Windows 默认 stdout 编码为 GBK，报告里的 ¥ 等字符会抛 UnicodeEncodeError。
    # 强制 UTF-8，保证产物 JSON 能正确写出（父进程也按 UTF-8 解码）。
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    _apply_mock_if_requested()
    mode = sys.argv[1]
    payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

    fn = _MODES.get(mode)
    if fn is None:
        raise SystemExit(f"unknown mode: {mode}")

    # compile/sop 是协程，其余为同步函数
    if mode in ("compile", "sop"):
        result = asyncio.run(fn(payload))
    else:
        result = fn(payload)

    sys.stdout.write(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

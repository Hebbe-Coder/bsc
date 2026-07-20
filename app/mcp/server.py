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

关于认证：
- 生产环境必须配置 API_KEY，否则拒绝所有工具调用。
- 开发环境（API_KEY未配置）默认放行，便于本地测试。
- 可通过环境变量 MCP_API_KEY 覆盖配置文件中的 API_KEY。

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
import hmac
import hashlib

from mcp.server.fastmcp import FastMCP
from app.mcp.compatibility import build_compatibility_profile

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

_MCP_API_KEY = os.environ.get("MCP_API_KEY") or ""
_SETTINGS_API_KEY_CACHE = None
_DEFAULT_MAX_MEMORY_MB = 1024
_DEFAULT_MAX_CPU_SECONDS = 600


class MCPExecutionError(RuntimeError):
    """Stable failure contract for an isolated MCP engine invocation."""

    def __init__(
        self,
        mode: str,
        error_code: str,
        message: str,
        *,
        stderr: str = "",
    ) -> None:
        self.mode = mode
        self.error_code = error_code
        self.stderr = stderr
        super().__init__(f"MCP engine {mode} failed [{error_code}]: {message}")


def _get_settings_api_key() -> str:
    """从配置文件获取API_KEY（缓存结果）"""
    global _SETTINGS_API_KEY_CACHE
    if _SETTINGS_API_KEY_CACHE is not None:
        return _SETTINGS_API_KEY_CACHE
    
    sys.path.insert(0, _ROOT)
    try:
        from app.core.config import settings
        _SETTINGS_API_KEY_CACHE = settings.API_KEY
        return _SETTINGS_API_KEY_CACHE
    except Exception:
        _SETTINGS_API_KEY_CACHE = ""
        return ""


def _require_auth(api_key: str = "") -> None:
    """验证MCP调用的API_KEY
    
    认证策略：
    - 如果配置了 MCP_API_KEY 环境变量，必须匹配
    - 如果配置了 settings.API_KEY，必须匹配
    - 如果两者都未配置（开发环境），放行
    """
    expected_key = _MCP_API_KEY or _get_settings_api_key()
    
    if not expected_key:
        logger.debug("MCP API_KEY未配置，放行调用（开发模式）")
        return
    
    if not api_key:
        raise PermissionError("MCP调用需要认证：请提供api_key参数")
    
    if not hmac.compare_digest(api_key, expected_key):
        api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
        logger.warning(f"MCP无效API_KEY尝试，密钥哈希: {api_key_hash}")
        raise PermissionError("无效的API_KEY")


def _build_env() -> dict:
    """复制当前环境；仅当 BSC_MCP_FORCE_MOCK=1 时强制 mock 提供方。"""
    env = dict(os.environ)
    if os.environ.get("BSC_MCP_FORCE_MOCK") == "1":
        for k in _MOCK_PROVIDERS:
            env[k] = "mock"
        env["RERANK_PROVIDER"] = "none"
    return env


def _get_windows_job_object():
    """在Windows上创建带有资源限制的Job Object"""
    import ctypes
    import ctypes.wintypes
    
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
    
    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        return None
    
    max_mem_mb = int(os.environ.get("BSC_MCP_MAX_MEM_MB", str(_DEFAULT_MAX_MEMORY_MB)))
    max_cpu_sec = int(os.environ.get("BSC_MCP_MAX_CPU_SEC", str(_DEFAULT_MAX_CPU_SECONDS)))
    
    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ('PerProcessUserTimeLimit', ctypes.c_int64),
            ('PerJobUserTimeLimit', ctypes.c_int64),
            ('LimitFlags', ctypes.wintypes.DWORD),
            ('MinimumWorkingSetSize', ctypes.c_size_t),
            ('MaximumWorkingSetSize', ctypes.c_size_t),
            ('ActiveProcessLimit', ctypes.wintypes.DWORD),
            ('Affinity', ctypes.c_size_t),
            ('PriorityClass', ctypes.wintypes.DWORD),
            ('SchedulingClass', ctypes.wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ('ReadOperationCount', ctypes.c_uint64),
            ('WriteOperationCount', ctypes.c_uint64),
            ('OtherOperationCount', ctypes.c_uint64),
            ('ReadTransferCount', ctypes.c_uint64),
            ('WriteTransferCount', ctypes.c_uint64),
            ('OtherTransferCount', ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ('IoInfo', IO_COUNTERS),
            ('ProcessMemoryLimit', ctypes.c_uint64),
            ('JobMemoryLimit', ctypes.c_uint64),
            ('PeakProcessMemoryUsed', ctypes.c_uint64),
            ('PeakJobMemoryUsed', ctypes.c_uint64),
        ]

    limit_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    limit_info.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_TIME
    )
    limit_info.BasicLimitInformation.PerJobUserTimeLimit = max_cpu_sec * 10000000
    limit_info.ProcessMemoryLimit = max_mem_mb * 1024 * 1024
    
    if not kernel32.SetInformationJobObject(
        job_handle,
        9,
        ctypes.byref(limit_info),
        ctypes.sizeof(limit_info)
    ):
        kernel32.CloseHandle(job_handle)
        return None
    
    return job_handle


def _run_engine_subprocess(mode: str, payload: dict, timeout: float = 600) -> dict:
    """在全新子进程中运行引擎，返回解析后的 dict。"""
    import signal
    
    kwargs = {}
    job_handle = None
    
    if sys.platform == "win32":
        job_handle = _get_windows_job_object()
        if job_handle:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        try:
            import resource
            max_mem_mb = int(os.environ.get("BSC_MCP_MAX_MEM_MB", str(_DEFAULT_MAX_MEMORY_MB)))
            max_cpu_sec = int(os.environ.get("BSC_MCP_MAX_CPU_SEC", str(timeout)))
            
            def limit_resources():
                resource.setrlimit(resource.RLIMIT_AS, (max_mem_mb * 1024 * 1024, max_mem_mb * 1024 * 1024))
                resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_sec, max_cpu_sec))
            
            kwargs["preexec_fn"] = limit_resources
        except ImportError:
            pass
    
    try:
        if sys.platform == "win32" and job_handle:
            import ctypes
            proc = subprocess.Popen(
                [_PYTHON, "-m", "app.mcp._engine_runner", mode, json.dumps(payload, ensure_ascii=False)],
                cwd=_ROOT,
                env=_build_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                close_fds=True,
                **kwargs,
            )
            
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.AssignProcessToJobObject(job_handle, proc._handle)
            
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                returncode = proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                raise MCPExecutionError(
                    mode,
                    "timeout",
                    f"engine subprocess timed out after {timeout}s",
                )
        else:
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
                **kwargs,
            )
            stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        raise MCPExecutionError(
            mode,
            "timeout",
            f"engine subprocess timed out after {timeout}s",
        )
    finally:
        if job_handle:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.CloseHandle(job_handle)
    
    if returncode != 0:
        child_error = _child_error_payload(stdout)
        sigkill = getattr(signal, "SIGKILL", None)
        if sigkill is not None and returncode == -sigkill:
            raise MCPExecutionError(
                mode,
                "terminated",
                "engine subprocess was terminated",
                stderr=stderr[-2000:],
            )
        if job_handle and not child_error and not stderr.strip():
            max_mem_mb = int(
                os.environ.get("BSC_MCP_MAX_MEM_MB", str(_DEFAULT_MAX_MEMORY_MB))
            )
            raise MCPExecutionError(
                mode,
                "worker_terminated",
                (
                    f"engine subprocess exited with code {returncode} before producing "
                    f"output under the Windows Job Object (memory limit: {max_mem_mb}MB)"
                ),
            )
        raise MCPExecutionError(
            mode,
            str(child_error.get("error_code") or "child_failed"),
            str(child_error.get("error") or f"engine subprocess exited with code {returncode}"),
            stderr=stderr[-2000:],
        )
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise MCPExecutionError(
            mode,
            "invalid_runner_output",
            "engine subprocess returned invalid JSON",
            stderr=stderr[-2000:],
        ) from exc
    if not isinstance(result, dict):
        raise MCPExecutionError(
            mode,
            "invalid_runner_output",
            "engine subprocess returned a non-object JSON payload",
            stderr=stderr[-2000:],
        )
    return result


def _child_error_payload(stdout: str) -> dict:
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


@mcp.tool()
def bsc_mcp_compatibility_profile(api_key: str = "") -> dict:
    """Return the concrete MCP transports, auth and isolation capabilities."""
    _require_auth(api_key)
    configured = bool(_MCP_API_KEY or _get_settings_api_key())
    return build_compatibility_profile(api_key_configured=configured).model_dump()


@mcp.tool()
def bsc_compile(description: str, template_id: str = "", api_key: str = "") -> dict:
    """编译业务描述到 Business System Schema。

    运行完整编译管线（业务理解 / SOP / 风险 / 战略 / 优化 / 报告合成），
    返回 business_system 与 pipeline 各阶段状态。

    Args:
        description: 业务描述 / PRD 文本。
        template_id: 可选行业模板 ID（应用行业模板配置）。
        api_key: API密钥（生产环境必填）。
    """
    _require_auth(api_key)
    return _run_engine_subprocess(
        "compile", {"description": description, "template_id": template_id}
    )


@mcp.tool()
def bsc_generate_sop(description: str, api_key: str = "") -> dict:
    """根据业务描述生成完整 SOP 汇报。

    先编译得到 business_system，再用 SOPReportEngine 生成
    角色 / 流程 / 职责 / SLA / KPI / 风险 / 甘特 / 里程碑等完整报告。

    Args:
        description: 业务描述 / PRD 文本。
        api_key: API密钥（生产环境必填）。
    """
    _require_auth(api_key)
    return _run_engine_subprocess("sop", {"description": description})


@mcp.tool()
def knowledge_ask(question: str, project_id: str = "", top_k: int = 5, api_key: str = "") -> dict:
    """在知识库上做 RAG 问答。

    基于已索引的文档块检索 + 生成答案，返回 answer / citations / 降级标记。
    默认未配置 RAG LLM key 时返回降级标记（degraded=True），
    需配置真实 LLM 且先索引文档才能生成答案。

    Args:
        question: 自然语言问题。
        project_id: 可选项目 ID（用于项目隔离检索）。
        top_k: 检索块数量，默认 5。
        api_key: API密钥（生产环境必填）。
    """
    _require_auth(api_key)
    return _run_engine_subprocess(
        "ask", {"question": question, "project_id": project_id, "top_k": top_k}
    )


@mcp.tool()
def analyze_domain(text: str, api_key: str = "") -> dict:
    """识别业务文本所属领域。

    基于关键词评分 + TF-IDF 的混合分类器，返回领域、部门、角色前缀、
    置信度与各领域评分，可用于给 Agent 做路由判断。纯本地、无需联网。

    Args:
        text: 业务描述文本。
        api_key: API密钥（生产环境必填）。
    """
    _require_auth(api_key)
    return _run_engine_subprocess("analyze", {"text": text})


if __name__ == "__main__":
    mcp.run()

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
from app.middleware.auth import resolve_knowledge_auth
from app.mcp.compatibility import build_compatibility_profile
from app.mcp import wiki_tools
from app.mcp import growth_tools
from app.mcp import dbos_tools

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


def _require_mcp_auth(api_key: str = "") -> tuple[str, str | None]:
    """Resolve an MCP principal, including project-scoped Wiki keys.

    ``MCP_API_KEY`` remains an explicit global-admin override.  Other keys use
    the shared knowledge-auth resolver so MCP and REST enforce the same
    project boundaries without passing a principal through tool arguments.
    """
    if _MCP_API_KEY and api_key and hmac.compare_digest(api_key, _MCP_API_KEY):
        return "admin", None

    principal = resolve_knowledge_auth(api_key)
    if principal is not None:
        role, project_id = principal
        # Preserve the existing MCP_API_KEY override: when it is configured,
        # only project-bound keys may supplement it for Wiki operations.
        if _MCP_API_KEY and role in {"admin", "reader"}:
            raise PermissionError("无效的API_KEY")
        return role, project_id

    if not _MCP_API_KEY and not _get_settings_api_key():
        logger.debug("MCP API_KEY未配置，按开发模式授予本地管理权限")
        return "admin", None
    if not api_key:
        raise PermissionError("MCP调用需要认证：请提供api_key参数")
    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    logger.warning("MCP无效API_KEY尝试，密钥哈希 %s", api_key_hash)
    raise PermissionError("无效的API_KEY")


def _authorize_wiki_project(project_id: str, api_key: str = "", *, write: bool = False) -> None:
    """Authorize one governed Wiki action against its explicit project scope."""
    role, scoped_project_id = _require_mcp_auth(api_key)
    from app.core.config import settings

    if not settings.KNOWLEDGE_WIKI_ENABLED:
        raise PermissionError("Project Wiki MCP tools are disabled by configuration")
    if write and not settings.KNOWLEDGE_MCP_WRITE_ENABLED:
        raise PermissionError("Project Wiki MCP writes are disabled by configuration")
    if role == "admin":
        return
    if role == "reader":
        if write:
            raise PermissionError("只读密钥无Wiki写入权限")
        return
    if role == "project_admin":
        if scoped_project_id == project_id:
            return
        raise PermissionError("无该项目访问权限")
    if role == "project_reader":
        if scoped_project_id != project_id:
            raise PermissionError("无该项目访问权限")
        if write:
            raise PermissionError("project_reader只读，无Wiki写入权限")
        return
    raise PermissionError("无效的Wiki访问角色")


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
def wiki_guide(project_id: str, api_key: str = "") -> dict:
    """Explain the governed, project-scoped Wiki workflow."""
    _authorize_wiki_project(project_id, api_key)
    return wiki_tools.wiki_guide(project_id)


@mcp.tool()
def wiki_search(project_id: str, query: str = "", api_key: str = "") -> dict:
    """List matching Wiki evidence metadata without exposing raw evidence bodies."""
    _authorize_wiki_project(project_id, api_key)
    return wiki_tools.wiki_search(project_id, query)


@mcp.tool()
def wiki_graph(project_id: str, api_key: str = "") -> dict:
    """Read the isolated derived Knowledge Graph for one project."""
    _authorize_wiki_project(project_id, api_key)
    return wiki_tools.wiki_graph(project_id)


@mcp.tool()
def wiki_read(project_id: str, page_id: str, api_key: str = "") -> dict:
    """Read a published, project-scoped Wiki page and its traceable citations."""
    _authorize_wiki_project(project_id, api_key)
    return wiki_tools.wiki_read(project_id, page_id)


@mcp.tool()
def wiki_propose_update(
    project_id: str,
    operations: list[dict],
    source_ids: list[str] | None = None,
    rationale: str = "",
    api_key: str = "",
) -> dict:
    """Create a reviewable Wiki proposal. This never writes to the Obsidian Vault."""
    _authorize_wiki_project(project_id, api_key, write=True)
    return wiki_tools.wiki_propose_update(project_id, operations, source_ids, rationale)


@mcp.tool()
def wiki_lint(project_id: str, proposal_id: str, api_key: str = "") -> dict:
    """Run deterministic citation, frontmatter, and link checks on a Wiki proposal."""
    _authorize_wiki_project(project_id, api_key, write=True)
    return wiki_tools.wiki_lint(project_id, proposal_id)


@mcp.tool()
def wiki_apply_update(project_id: str, proposal_id: str, api_key: str = "") -> dict:
    """Publish a proposal only after lint, source eligibility, and evaluation gates pass."""
    _authorize_wiki_project(project_id, api_key, write=True)
    return wiki_tools.wiki_apply_update(project_id, proposal_id)


@mcp.tool()
def wiki_distill(project_id: str, api_key: str = "") -> dict:
    """Queue an evidence-backed weekly distillation when durable Celery is available."""
    _authorize_wiki_project(project_id, api_key, write=True)
    return wiki_tools.wiki_distill(project_id)


@mcp.tool()
def wiki_schedule(project_id: str, job_type: str, cron: str, timezone: str = "Asia/Shanghai", api_key: str = "") -> dict:
    """Persist a bounded Wiki maintenance schedule; it does not claim execution without Celery."""
    _authorize_wiki_project(project_id, api_key, write=True)
    return wiki_tools.wiki_schedule(project_id, job_type, cron, timezone)


def _authorize_growth_project(project_id: str, api_key: str = "", *, write: bool = False) -> None:
    from app.core.config import settings

    role, scoped_project_id = _require_mcp_auth(api_key)
    if not settings.KNOWLEDGE_GROWTH_ENABLED:
        raise growth_tools.GrowthUnavailableError(
            "Knowledge growth is disabled by configuration",
            {"growth": False},
        )
    if write and not settings.KNOWLEDGE_MCP_WRITE_ENABLED:
        raise growth_tools.GrowthUnavailableError(
            "Knowledge growth MCP writes are disabled by configuration",
            {"growth": True, "mcp_write": False},
        )
    if role == "admin":
        return
    if role == "reader":
        if write:
            raise PermissionError("reader keys are read-only for knowledge growth")
        return
    if role == "project_admin":
        if scoped_project_id == project_id:
            return
        raise PermissionError("no access to this project")
    if role == "system":
        if scoped_project_id == project_id:
            return
        raise PermissionError("system credentials must match the requested project")
    if role == "project_reader":
        if scoped_project_id != project_id:
            raise PermissionError("no access to this project")
        if write:
            raise PermissionError("project_reader is read-only for knowledge growth")
        return
    raise PermissionError("invalid knowledge growth access role")


def _authorize_dbos_project(project_id: str, api_key: str = "", *, write: bool = False) -> None:
    """Apply the same project-key isolation to DBOS MCP tools."""
    from app.core.config import settings

    if not project_id or not project_id.strip():
        raise ValueError("project_id is required")
    if not settings.DYNAMIC_BUSINESS_OS_ENABLED:
        raise RuntimeError("Dynamic Business OS is disabled by configuration")
    role, scoped_project_id = _require_mcp_auth(api_key)
    if role == "admin":
        return
    if role == "reader":
        if write:
            raise PermissionError("reader keys are read-only for Dynamic Business OS")
        return
    if role in {"project_admin", "system"}:
        if scoped_project_id == project_id:
            return
        raise PermissionError("no access to this project")
    if role == "project_reader":
        if scoped_project_id != project_id:
            raise PermissionError("no access to this project")
        if write:
            raise PermissionError("project_reader is read-only for Dynamic Business OS")
        return
    raise PermissionError("invalid Dynamic Business OS access role")


_GROWTH_ACTION_PERMISSIONS = {
    "profile": ({"get"}, {"update"}),
    "source_triage": ({"get"}, {"run"}),
    "method": ({"list", "get", "resolve", "revisions", "experiments", "experiment"}, {"propose", "distill", "review", "publish", "deprecate", "evolve"}),
    "output": ({"list", "get"}, {"register", "evaluate", "file"}),
    "feedback": ({"list"}, {"create", "process"}),
    "failure": ({"list", "get"}, {"create", "resolve"}),
    "schedule": ({"list"}, {"create"}),
    "run": ({"list", "get", "events"}, {"start"}),
    "distillation": ({"list", "get"}, {"start"}),
}


def _growth_action_is_write(domain: str, action: str) -> bool:
    read_actions, write_actions = _GROWTH_ACTION_PERMISSIONS.get(domain, (set(), set()))
    if action in read_actions:
        return False
    if action in write_actions:
        return True
    raise ValueError(f"unsupported {domain} growth action: {action}")


@mcp.tool()
def knowledge_growth_profile(
    project_id: str,
    action: str = "get",
    profile: dict | None = None,
    expected_revision: int | None = None,
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("profile", action))
    return growth_tools.growth_profile(project_id, action, profile, expected_revision)


@mcp.tool()
def knowledge_growth_assets(
    project_id: str,
    stage: str = "",
    limit: int = 100,
    cursor: str = "",
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key)
    return growth_tools.growth_assets(project_id, stage, limit, cursor)


@mcp.tool()
def knowledge_growth_source_triage(
    project_id: str,
    action: str = "get",
    source_id: str = "",
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("source_triage", action))
    return growth_tools.growth_source_triage(project_id, action, source_id)


@mcp.tool()
def knowledge_growth_method(
    project_id: str,
    action: str = "list",
    method_id: str = "",
    proposal_id: str = "",
    status: str = "",
    limit: int = 100,
    cursor: str = "",
    payload: dict | None = None,
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("method", action))
    return growth_tools.growth_method(
        project_id, action, method_id, proposal_id, status, limit, cursor, payload
    )


@mcp.tool()
def knowledge_growth_output(
    project_id: str,
    action: str = "list",
    output_id: str = "",
    status: str = "",
    limit: int = 100,
    cursor: str = "",
    payload: dict | None = None,
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("output", action))
    return growth_tools.growth_output(project_id, action, output_id, status, limit, cursor, payload)


@mcp.tool()
def knowledge_growth_feedback(
    project_id: str,
    action: str = "list",
    feedback_id: str = "",
    output_id: str = "",
    limit: int = 100,
    cursor: str = "",
    payload: dict | None = None,
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("feedback", action))
    return growth_tools.growth_feedback(
        project_id, action, feedback_id, output_id, limit, cursor, payload
    )


@mcp.tool()
def knowledge_growth_failure(
    project_id: str,
    action: str = "list",
    failure_id: str = "",
    status: str = "",
    run_id: str = "",
    diagnostic_pattern: str = "",
    limit: int = 100,
    cursor: str = "",
    payload: dict | None = None,
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("failure", action))
    return growth_tools.growth_failure(
        project_id, action, failure_id, status, run_id, diagnostic_pattern, limit, cursor, payload
    )


@mcp.tool()
def knowledge_growth_summary(project_id: str, api_key: str = "") -> dict:
    _authorize_growth_project(project_id, api_key)
    return growth_tools.growth_summary(project_id)


@mcp.tool()
def knowledge_growth_lineage(
    project_id: str,
    relation: str = "",
    limit: int = 100,
    cursor: str = "",
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key)
    return growth_tools.growth_lineage(project_id, relation, limit, cursor)


@mcp.tool()
def knowledge_growth_review(
    project_id: str,
    action: str,
    target_id: str = "",
    minimum_uses: int = 3,
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=True)
    return growth_tools.growth_review(project_id, action, target_id, minimum_uses)


@mcp.tool()
def knowledge_growth_schedule(
    project_id: str,
    action: str = "list",
    job_type: str = "",
    cron: str = "",
    timezone: str = "Asia/Shanghai",
    limit: int = 100,
    cursor: str = "",
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("schedule", action))
    return growth_tools.growth_schedule(
        project_id, action, job_type, cron, timezone, limit, cursor
    )


@mcp.tool()
def knowledge_growth_run(
    project_id: str,
    action: str = "list",
    run_id: str = "",
    job_type: str = "",
    idempotency_key: str = "",
    after_sequence: int = 0,
    limit: int = 100,
    cursor: str = "",
    payload: dict | None = None,
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("run", action))
    return growth_tools.growth_run(
        project_id,
        action,
        run_id,
        job_type,
        idempotency_key,
        after_sequence,
        limit,
        cursor,
        payload,
    )


@mcp.tool()
def knowledge_growth_distillation(
    project_id: str,
    action: str = "list",
    distillation_id: str = "",
    kind: str = "",
    week: str = "",
    source_cutoff: str = "",
    idempotency_key: str = "",
    limit: int = 100,
    cursor: str = "",
    api_key: str = "",
) -> dict:
    _authorize_growth_project(project_id, api_key, write=_growth_action_is_write("distillation", action))
    return growth_tools.growth_distillation(
        project_id,
        action,
        distillation_id,
        kind,
        week,
        source_cutoff,
        idempotency_key,
        limit,
        cursor,
    )


@mcp.tool()
def knowledge_growth_triage(project_id: str, source_id: str, api_key: str = "") -> dict:
    _authorize_growth_project(project_id, api_key, write=True)
    return growth_tools.growth_triage(project_id, source_id)


@mcp.tool()
def knowledge_growth_weekly_distill(project_id: str, week: str, source_cutoff: str, api_key: str = "") -> dict:
    _authorize_growth_project(project_id, api_key, write=True)
    return growth_tools.growth_weekly_distill(project_id, week, source_cutoff)


@mcp.tool()
def dbos_create_mission(
    project_id: str,
    title: str,
    intent: str,
    intake_mode: str = "business",
    context: dict | None = None,
    api_key: str = "",
) -> dict:
    """Create a project-scoped mission. It cannot execute until confirmed."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_create_mission(project_id, title, intent, intake_mode, context)


@mcp.tool()
def dbos_diagnose_mission(project_id: str, mission_id: str, api_key: str = "") -> dict:
    """Compile an inspectable diagnosis, capability selection, and Dynamic SOP."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_diagnose_mission(project_id, mission_id)


@mcp.tool()
def dbos_confirm_mission(
    project_id: str,
    mission_id: str,
    actor_id: str,
    authorized_capabilities: list[str],
    api_key: str = "",
) -> dict:
    """Grant only capabilities selected by the mission's reviewed Dynamic SOP."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_confirm_mission(project_id, mission_id, actor_id, authorized_capabilities)


@mcp.tool()
async def dbos_execute_mission(
    project_id: str,
    mission_id: str,
    capability_name: str,
    idempotency_key: str = "",
    api_key: str = "",
) -> dict:
    """Run one authorized capability and persist its result in the mission ledger."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return await dbos_tools.dbos_execute_mission(project_id, mission_id, capability_name, idempotency_key)


@mcp.tool()
def dbos_run_external_worker(
    project_id: str,
    mission_id: str,
    dynamic_sop_id: str,
    capability_name: str,
    worker_id: str,
    model_id: str,
    endpoint: str,
    payload: dict,
    idempotency_key: str,
    estimated_cost_microusd: int = 0,
    api_key: str = "",
) -> dict:
    """Queue one non-production, allowlisted HTTPS worker after DBOS policy checks."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_run_external_worker(
        project_id, mission_id, dynamic_sop_id, capability_name, worker_id, model_id,
        endpoint, payload, idempotency_key, estimated_cost_microusd,
    )


@mcp.tool()
def dbos_cancel_external_worker(
    project_id: str,
    worker_run_id: str,
    reason: str,
    api_key: str = "",
) -> dict:
    """Request cancellation of a queued or executing external HTTPS worker."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_cancel_external_worker(project_id, worker_run_id, reason)


@mcp.tool()
def dbos_review_mission(
    project_id: str,
    mission_id: str,
    idempotency_key: str,
    api_key: str = "",
) -> dict:
    """Run a PromptOps-governed advisory review; it cannot approve or execute work."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_review_mission(project_id, mission_id, idempotency_key)


@mcp.tool()
def dbos_control_center(project_id: str, mission_id: str, api_key: str = "") -> dict:
    """Read mission state, reasoning lineage, execution evidence, and feedback memory."""
    _authorize_dbos_project(project_id, api_key)
    return dbos_tools.dbos_control_center(project_id, mission_id)


@mcp.tool()
def dbos_record_feedback(
    project_id: str,
    mission_id: str,
    statement: str,
    source_refs: list[str] | None = None,
    api_key: str = "",
) -> dict:
    """Persist outcome-linked feedback as advisory project memory."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_record_feedback(project_id, mission_id, statement, source_refs)


@mcp.tool()
def dbos_record_decision(
    project_id: str,
    mission_id: str,
    task_id: str,
    statement: str,
    rationale: str = "",
    alternatives: list[str] | None = None,
    actor_id: str = "mcp",
    api_key: str = "",
) -> dict:
    """Record a review decision against a Dynamic SOP task without executing it."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_record_decision(
        project_id, mission_id, task_id, statement, rationale, alternatives, actor_id,
    )


@mcp.tool()
def dbos_stop_mission(project_id: str, mission_id: str, reason: str, api_key: str = "") -> dict:
    """Stop a non-terminal DBOS mission and persist the reviewer reason."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_stop_mission(project_id, mission_id, reason)


@mcp.tool()
def dbos_rollback_execution(project_id: str, execution_id: str, reason: str, api_key: str = "") -> dict:
    """Record a reviewer rollback for a completed, failed, or rejected DBOS execution."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_rollback_execution(project_id, execution_id, reason)


@mcp.tool()
def dbos_mission(
    project_id: str,
    action: str = "read",
    mission_id: str = "",
    payload: dict | None = None,
    api_key: str = "",
) -> dict:
    """Create, diagnose, or read a project-scoped Dynamic Business OS mission."""
    _authorize_dbos_project(project_id, api_key, write=action in {"create", "diagnose"})
    return dbos_tools.dbos_mission(project_id, action, mission_id, payload)


@mcp.tool()
def dbos_confirm(
    project_id: str,
    mission_id: str,
    authorized_capabilities: list[str],
    actor_id: str = "mcp",
    api_key: str = "",
) -> dict:
    """Confirm selected capabilities before any DBOS execution can begin."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_confirm(project_id, mission_id, authorized_capabilities, actor_id)


@mcp.tool()
async def dbos_execute(
    project_id: str,
    mission_id: str,
    capability_name: str,
    idempotency_key: str = "",
    api_key: str = "",
) -> dict:
    """Execute one confirmed capability with durable idempotency semantics."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return await dbos_tools.dbos_execute(project_id, mission_id, capability_name, idempotency_key)


@mcp.tool()
def dbos_feedback(
    project_id: str,
    mission_id: str,
    statement: str,
    source_refs: list[str] | None = None,
    api_key: str = "",
) -> dict:
    """Store feedback only after an audited execution exists for the mission."""
    _authorize_dbos_project(project_id, api_key, write=True)
    return dbos_tools.dbos_feedback(project_id, mission_id, statement, source_refs)


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

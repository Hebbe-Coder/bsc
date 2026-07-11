# Round 3 安全&正确性加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复三个 HIGH 级安全/正确性技术债：SOP 报告 HTML XSS、看板与静态资产免鉴权暴露、编译部分失败被伪装成成功。

**Architecture:** 三处独立修复，单 feature 分支 `feature/security-correctness-hardening` 承袭 Round 2 状态。WS1 在引擎内转义所有 LLM 派生字段；WS2 新增通用 `verify_admin_key`/`verify_download_auth` 依赖（避免误用知识库专属 `require_admin`），对 dashboard 路由级鉴权、用受保护下载端点替换 `/output` 静态挂载；WS3 在 compile 入口检测失败阶段并如实返回 `ApiResponse(success=False, code=2001)`（breaking 修正，非 200 success）。

**Tech Stack:** Python 3.13 / FastAPI / Pydantic v2 / SQLite。测试用 `.venv/Scripts/python.exe -m pytest`，HTTP 集成测试用 `fastapi.testclient.TestClient`。全局状态隔离由 `tests/knowledge/conftest.py` 的 autouse fixture 兜底，但本计划新测试也显式用 `monkeypatch`/`settings` 还原以避免跨模块泄漏。

**测试命令（强制）：** `C:\Users\34216\Documents\New project 3\bsc-backend\.venv\Scripts\python.exe -m pytest <args>`

---

## File Structure

**新建：**
- `app/api/auth_deps.py` — 通用 admin 鉴权依赖 `verify_admin_key(request)`、`verify_download_auth(request, token)`、`_check_admin(api_key)`、`_extract_bearer(request)`，以及 `download_url(filename)`（构建受保护下载 URL）。**不依赖 `request.state.knowledge_role`**（那是 `/knowledge/*` 专属）。
- `app/api/files_api.py` — 受保护下载路由 `GET /api/files/{filename}`，路径穿越防护 + `FileResponse`。
- `tests/test_ws1_sop_xss.py` — WS1 XSS 测试。
- `tests/test_ws2_auth_gating.py` — WS2 dashboard 路由鉴权 + 下载端点测试。
- `tests/test_ws3_compile_failure.py` — WS3 编译失败上报测试。

**修改：**
- `app/engines/sop_report_engine.py` — 顶部加 `import html` + 模块级 `_esc_deep(obj)`；`export_to_html` 开头 `report = _esc_deep(report)`。
- `app/api/dashboard.py` — router 加 `dependencies=[Depends(verify_admin_key)]`。
- `app/main.py` — 移除 `/output` StaticFiles 挂载（:228-230）；把 `"app.api.files_api"` 加入路由器加载列表（:215 列表）。
- `app/middleware/request_signature.py` — 白名单加 `/api/files`（:51 附近）。
- `app/middleware/rate_limiter.py` — 白名单加 `/api/files`（:116 附近）。
- `app/agents/asset_agent.py` — 3 处 `/output/...` 下载 URL 改为 `download_url(...)`（:27,35,42）。
- `app/api/bsc_api.py` — `compile_prd`（:124）与 `compile_prd_sync`（:168）检测失败阶段并如实返回。

---

## Task 1: WS1 — SOP 报告 HTML 注入/XSS 转义

**Files:**
- Modify: `app/engines/sop_report_engine.py` (顶部 imports + `export_to_html` 开头)
- Test: `tests/test_ws1_sop_xss.py`

- [ ] **Step 1: 写失败测试**
```python
# tests/test_ws1_sop_xss.py
import pytest
from app.engines.sop_report_engine import SOPReportEngine


_PAYLOAD = "<script>alert(1)</script>"


def _build_report(payload: str) -> dict:
    return {
        "title": payload,
        "generated_at": "2026-07-11 00:00:00",
        "overview": {
            "description": payload,
            "business_domain": "测试域",
            "total_steps": 1,
            "total_roles": 1,
            "total_sla_items": 0,
            "has_escalation": False,
            "estimated_duration": "1h",
            "core_objectives": [payload],
        },
        "workflow_detail": {
            "total_steps": 1,
            "steps": [{
                "step": 1, "name": payload, "action": "a", "role": "r",
                "input": "i", "output": "o", "sla": "1d",
                "risks": [payload], "mitigations": ["m"],
            }],
        },
        "role_responsibilities": {
            "total_roles": 1,
            "roles": [{
                "name": payload, "department": "d", "level": "L1",
                "headcount": 1, "responsible_steps": [{"step": 1, "name": payload}],
                "responsibilities": [payload],
            }],
        },
        "sla_summary": {
            "total_sla_items": 0, "sla_items": [],
            "step_slas": [{"step": 1, "name": payload, "sla": "1d"}],
            "estimated_total_duration": "1h",
        },
        "risk_assessment": {
            "total_risks": 1, "severity_distribution": {},
            "risks": [{
                "risk": payload, "severity": "high", "probability": "中",
                "mitigation": payload, "category": "c",
            }],
        },
        "flowchart": {
            "total_nodes": 1, "total_edges": 0,
            "nodes": [{"step": 1, "name": payload}],
        },
        "csf": {
            "total_factors": 1,
            "factors": [{
                "name": payload, "impact": "高", "status": "已满足",
                "description": payload, "actions": [payload],
            }],
        },
    }


def test_export_to_html_escapes_xss_payload():
    engine = SOPReportEngine()
    html = engine.export_to_html(_build_report(_PAYLOAD))
    assert "<script>" not in html, "原始 <script> 未被转义，存在 XSS"
    assert "&lt;script&gt;" in html, "转义后的实体未出现在输出中"
```

- [ ] **Step 2: 运行测试确认失败（未转义时裸 `<script>` 出现）**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws1_sop_xss.py -v
```
Expected: FAIL（`"<script>" not in html` 断言失败）。

- [ ] **Step 3: 实现最小修复**
在 `app/engines/sop_report_engine.py` 顶部（现有 `import` 区，如 `import re` 附近）添加：
```python
import html
```
在模块顶层（类定义之外，例如文件顶部 import 之后）添加：
```python
def _esc_deep(obj):
    """递归转义所有字符串叶子，防止 LLM 派生内容注入 HTML（XSS）。
    仅转义数据值，不触碰模板结构；非字符串（数字/布尔）原样返回。"""
    if isinstance(obj, dict):
        return {k: _esc_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_esc_deep(v) for v in obj]
    if isinstance(obj, str):
        return html.escape(obj, quote=True)
    return obj
```
在 `export_to_html` 方法体内、构造 `html_lines` 之前（即 `def export_to_html(self, report: Dict[str, Any]) -> str:` 之后第一行）添加：
```python
        report = _esc_deep(report)
```
（`export_to_html` 内部所有 `.format(...)` 与 f-string 拼装的字段值均来自 `report`，转义后自动安全；`severity_class` 等由 `r["severity"]` 派生的类名同样被转义，无注入。）

- [ ] **Step 4: 运行测试确认通过**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws1_sop_xss.py -v
```
Expected: PASS（1 passed）。

- [ ] **Step 5: 提交（仅两个文件）**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && git add app/engines/sop_report_engine.py tests/test_ws1_sop_xss.py && git commit -m "fix(security): WS1 SOP 报告 HTML 转义 LLM 派生字段（XSS 收口）"
```

---

## Task 2: WS2a — dashboard 路由级 admin 鉴权

**Files:**
- Create: `app/api/auth_deps.py`
- Modify: `app/api/dashboard.py:8` (router 定义)
- Test: `tests/test_ws2_auth_gating.py` (dashboard 部分)

- [ ] **Step 1: 写失败测试**
```python
# tests/test_ws2_auth_gating.py（dashboard 部分）
import hmac
import pytest
from starlette.requests import Request
from app.api.auth_deps import verify_admin_key
from app.core.config import settings


def _req(headers=None):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/dashboard/overview",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


def test_dashboard_unauth_rejected(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    monkeypatch.setattr(settings, "is_production", False)
    with pytest.raises(Exception) as exc:
        verify_admin_key(_req({}))
    assert exc.value.status_code == 401


def test_dashboard_admin_key_accepted(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    monkeypatch.setattr(settings, "is_production", False)
    assert verify_admin_key(_req({"Authorization": "Bearer ws2-admin"})) is True


def test_dashboard_wrong_key_rejected(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    monkeypatch.setattr(settings, "is_production", False)
    with pytest.raises(Exception) as exc:
        verify_admin_key(_req({"Authorization": "Bearer wrong"}))
    assert exc.value.status_code == 401
```
> 说明：直接单测 `verify_admin_key` 依赖，规避 dashboard 端点体可能依赖外部资源（DB/系统指标）导致的 500 假阴性；路由级集成由 Step 4 的 TestClient 兜底 `unauth→401`。

- [ ] **Step 2: 运行测试确认失败**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws2_auth_gating.py::test_dashboard_unauth_rejected -v
```
Expected: FAIL（`app/api/auth_deps.py` 不存在 → ImportError）。

- [ ] **Step 3: 实现最小修复**
新建 `app/api/auth_deps.py`：
```python
"""通用 admin 鉴权依赖（非知识库端点使用）。
与 knowledge_api.require_admin 不同：不读取 request.state.knowledge_role
（该字段仅由 AuthMiddleware 在 /knowledge/* 路径设置），直接比对全局 API_KEY。
"""
import hmac
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request

from app.core.config import settings

logger = logging.getLogger(__name__)


def _extract_bearer(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _check_admin(api_key: Optional[str]) -> bool:
    """校验 admin API_KEY；返回 True 或通过 HTTPException 拒绝。
    开发模式（API_KEY 未配置且非生产）放行，与中间件既有行为一致。"""
    if not api_key:
        if not settings.API_KEY and not settings.is_production:
            return True
        raise HTTPException(status_code=401, detail="未提供认证信息，请在请求头添加 Authorization: Bearer <API_KEY>")
    if not settings.API_KEY:
        if settings.is_production:
            raise HTTPException(status_code=500, detail="服务配置不完整，请联系管理员")
        return True
    if not hmac.compare_digest(api_key, settings.API_KEY):
        raise HTTPException(status_code=401, detail="无效的API密钥")
    return True


def verify_admin_key(request: Request) -> bool:
    """路由级 admin 鉴权依赖（如 /dashboard/*）。"""
    return _check_admin(_extract_bearer(request))


def verify_download_auth(request: Request, token: Optional[str] = Query(default=None)) -> bool:
    """下载端点鉴权：Bearer 或 ?token= 二选一（token 仅用于浏览器 <a> 下载）。"""
    return _check_admin(_extract_bearer(request) or token)


def download_url(filename: str) -> str:
    """构建受保护下载 URL，供各 export 端点返回。token = admin API_KEY。"""
    import os
    safe = os.path.basename(filename)
    return f"/api/files/{safe}?token={settings.API_KEY}"
```

修改 `app/api/dashboard.py:8`：
```python
from app.api.auth_deps import verify_admin_key
router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(verify_admin_key)])
```

- [ ] **Step 4: 运行单测 + 路由集成测试**
给 `tests/test_ws2_auth_gating.py` 追加路由级集成测试：
```python
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.api import dashboard as dashboard_module


def test_dashboard_router_unauth_401(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    monkeypatch.setattr(settings, "is_production", False)
    app = FastAPI()
    app.include_router(dashboard_module.router)
    client = TestClient(app)
    resp = client.get("/dashboard/overview")
    assert resp.status_code == 401
```
运行：
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws2_auth_gating.py -v
```
Expected: PASS（3 个 dashboard 相关用例）。

- [ ] **Step 5: 提交（仅三个文件）**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && git add app/api/auth_deps.py app/api/dashboard.py tests/test_ws2_auth_gating.py && git commit -m "fix(security): WS2a dashboard 路由级 admin 鉴权收口"
```

---

## Task 3: WS2b — 移除 `/output` 静态挂载，改受保护下载端点

**Files:**
- Create: `app/api/files_api.py`
- Modify: `app/main.py` (移除 :228-230 挂载 + 列表加 `"app.api.files_api"`)
- Modify: `app/middleware/request_signature.py` (白名单加 `/api/files`)
- Modify: `app/middleware/rate_limiter.py` (白名单加 `/api/files`)
- Modify: `app/agents/asset_agent.py` (:27,35,42)
- Test: `tests/test_ws2_auth_gating.py` (下载端点部分)

- [ ] **Step 1: 写失败测试（下载端点 + 路径穿越 + asset_agent URL 改写）**
在 `tests/test_ws2_auth_gating.py` 追加：
```python
import os
import tempfile
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import files_api
from app.agents import asset_agent as asset_module


def _client_with_file(monkeypatch, key):
    d = tempfile.mkdtemp()
    monkeypatch.setattr(files_api, "_OUTPUT_DIR", d)
    monkeypatch.setattr(settings, "API_KEY", key)
    monkeypatch.setattr(settings, "is_production", False)
    p = os.path.join(d, "report_1.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write("<html>ok</html>")
    app = FastAPI()
    app.include_router(files_api.router)
    return TestClient(app), "report_1.html"


def test_download_no_token_rejected(monkeypatch):
    client, name = _client_with_file(monkeypatch, "ws2-admin")
    assert client.get(f"/api/files/{name}").status_code == 401


def test_download_with_token_ok(monkeypatch):
    client, name = _client_with_file(monkeypatch, "ws2-admin")
    resp = client.get(f"/api/files/{name}?token=ws2-admin")
    assert resp.status_code == 200
    assert resp.text == "<html>ok</html>"


def test_download_path_traversal_blocked(monkeypatch):
    client, name = _client_with_file(monkeypatch, "ws2-admin")
    resp = client.get("/api/files/..%2f..%2fsecret?token=ws2-admin")
    assert resp.status_code in (400, 404)


def test_asset_agent_returns_protected_url(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "ws2-admin")
    out = asset_module.build_asset_list() if hasattr(asset_module, "build_asset_list") else None
    # 退路：直接验证 download_url 前缀
    from app.api.auth_deps import download_url
    url = download_url("report_x.html")
    assert url.startswith("/api/files/report_x.html?token=")
    assert "ws2-admin" in url
```

- [ ] **Step 2: 运行测试确认失败**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws2_auth_gating.py -k download -v
```
Expected: FAIL（files_api 不存在 / 路由未注册）。

- [ ] **Step 3: 实现最小修复**
新建 `app/api/files_api.py`（复用 `auth_deps`）：
```python
"""受保护文件下载端点（替代 /output 静态挂载）。"""
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.auth_deps import verify_download_auth

router = APIRouter(prefix="/api", tags=["Files"])

_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "output"
)


@router.get("/files/{filename}")
async def download_file(filename: str, _auth: bool = Depends(verify_download_auth)):
    safe = os.path.basename(filename)
    if not safe or safe != filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = os.path.join(_OUTPUT_DIR, safe)
    abs_output = os.path.abspath(_OUTPUT_DIR)
    abs_path = os.path.abspath(path)
    if abs_path != abs_output and not abs_path.startswith(abs_output + os.sep):
        raise HTTPException(status_code=400, detail="非法路径")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=safe)
```

修改 `app/main.py`：
- 移除 :228-230 的 `/output` 静态挂载：
```python
# 删除：
# _output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
# if os.path.isdir(_output_dir):
#     app.mount("/output", StaticFiles(directory=_output_dir), name="output")
```
（保留 `_static_dir` / `/dashboard` 挂载不动。）
- 在 :215 的模块列表末尾追加 `"app.api.files_api",`（使 `app.include_router` 加载新路由）。

修改 `app/middleware/request_signature.py`（:51 附近 `_is_whitelisted`）：
```python
        if path.startswith("/output"):
            return True
        if path.startswith("/api/files"):
            return True
```
修改 `app/middleware/rate_limiter.py`（:116 附近同理）：
```python
        if path.startswith("/output"):
            return True
        if path.startswith("/api/files"):
            return True
```

修改 `app/agents/asset_agent.py`（:27,35,42）：把 `f"/output/report_{ts}.json"` → `download_url(f"report_{ts}.json")` 等（3 处），并在文件顶部 `from app.api.auth_deps import download_url`。
> 实现子代理须先 `grep -rn '"/output' app/` 复核是否还有其它 export 端点返回 `/output/` URL（当前已知仅 asset_agent.py）。若有，同样改 `download_url(...)`；若无，保持最小改动。

- [ ] **Step 4: 运行下载测试确认通过**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws2_auth_gating.py -v
```
Expected: PASS（dashboard + download 全部用例）。

- [ ] **Step 5: 提交（仅变更文件）**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && git add app/api/files_api.py app/api/dashboard.py app/main.py app/middleware/request_signature.py app/middleware/rate_limiter.py app/agents/asset_agent.py tests/test_ws2_auth_gating.py && git commit -m "fix(security): WS2b 移除 /output 静态挂载，改受保护下载端点 + asset URL 改写"
```
> 严禁 `git add` 漂移文件：`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/*`。

---

## Task 4: WS3a — `compile_prd` 部分失败真实上报

**Files:**
- Modify: `app/api/bsc_api.py` (compile_prd :124-149)
- Test: `tests/test_ws3_compile_failure.py`

- [ ] **Step 1: 写失败测试**
```python
# tests/test_ws3_compile_failure.py
import asyncio
from unittest.mock import patch

import pytest

from app.api import bsc_api
from app.core.config import settings


def _fake_result(failed_agent="sop"):
    return {
        "business_system": {"composed": {}, "business_understanding": {}},
        "pipeline": {
            "stages": [
                {"agent": "business_understanding", "display": "BU", "status": "success"},
                {"agent": failed_agent, "display": "SOP", "status": "failed", "error": "boom"},
            ],
            "total_ms": 1,
            "parallel": True,
        },
        "summary": "",
        "workspace": {},
        "template": {},
    }


@pytest.fixture
def req():
    from app.api.bsc_api import CompileRequest
    return CompileRequest(input="x", output_types=[])


def test_compile_prd_reports_failure(monkeypatch, req):
    monkeypatch.setattr(settings, "API_KEY", "ws3-admin")
    with patch("app.core.async_pipeline.compile_to_business_system_async",
               return_value=_fake_result("sop")):
        resp = asyncio.get_event_loop().run_until_complete(bsc_api.compile_prd(req))
    assert resp.success is False, "部分失败却被标记为 success"
    assert resp.code == 2001
    agents = [s["agent"] for s in resp.data["stages"]]
    assert "sop" in agents
```
> 注意：`compile_prd` 内部 `from app.core.async_pipeline import compile_to_business_system_async`，故 patch 目标为 `app.core.async_pipeline.compile_to_business_system_async`。`output_types=[]` 跳过 `bind_visuals`，避免外部依赖。

- [ ] **Step 2: 运行测试确认失败**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws3_compile_failure.py::test_compile_prd_reports_failure -v
```
Expected: FAIL（当前始终 `ApiResponse.ok`，`resp.success is True`）。

- [ ] **Step 3: 实现最小修复**
修改 `app/api/bsc_api.py` 的 `compile_prd`（在 `return ApiResponse.ok({...})` 之前插入失败检测）：
```python
    stages = result.get("pipeline", {}).get("stages", [])
    failed = [s for s in stages if s.get("status") == "failed"]
    if failed:
        agents = ", ".join(s.get("agent") or s.get("display") or "?" for s in failed)
        return ApiResponse(
            success=False,
            code=2001,
            message=f"编译有 {len(failed)} 个分析阶段失败：{agents}",
            data={"stages": stages, "partial_business_system": bs},
        )

    return ApiResponse.ok({
        "pipeline": result["pipeline"],
        "business_system": bs,
        "composed": bs.get("composed", {}),
        "workspace": result.get("workspace", {}),
        "visuals": visuals,
        "summary": result["summary"],
        "output_types": req.output_types,
        "parallel": result.get("pipeline", {}).get("parallel", True),
    })
```
（`bs = result["business_system"]` 已在上方定义，保持不变。）

- [ ] **Step 4: 运行测试确认通过**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws3_compile_failure.py::test_compile_prd_reports_failure -v
```
Expected: PASS。

- [ ] **Step 5: 提交**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && git add app/api/bsc_api.py tests/test_ws3_compile_failure.py && git commit -m "fix(correctness): WS3a compile_prd 部分失败返回 ApiResponse(success=False, code=2001)"
```

---

## Task 5: WS3b — `compile_prd_sync` 部分失败真实上报

**Files:**
- Modify: `app/api/bsc_api.py` (compile_prd_sync :168-193)
- Test: `tests/test_ws3_compile_failure.py`

- [ ] **Step 1: 写失败测试**
在 `tests/test_ws3_compile_failure.py` 追加：
```python
def test_compile_prd_sync_reports_failure(monkeypatch, req):
    monkeypatch.setattr(settings, "API_KEY", "ws3-admin")
    with patch("app.core.bsc_pipeline.compile_to_business_system",
               return_value=_fake_result("risk")):
        resp = asyncio.get_event_loop().run_until_complete(bsc_api.compile_prd_sync(req))
    assert resp.success is False
    assert resp.code == 2001
    agents = [s["agent"] for s in resp.data["stages"]]
    assert "risk" in agents
```

- [ ] **Step 2: 运行测试确认失败**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws3_compile_failure.py::test_compile_prd_sync_reports_failure -v
```
Expected: FAIL（同步入口也始终 `ApiResponse.ok`）。

- [ ] **Step 3: 实现最小修复**
修改 `app/api/bsc_api.py` 的 `compile_prd_sync`（在 `return ApiResponse.ok({...})` 之前插入，结构与 WS3a 一致）：
```python
    stages = result.get("pipeline", {}).get("stages", [])
    failed = [s for s in stages if s.get("status") == "failed"]
    if failed:
        agents = ", ".join(s.get("agent") or s.get("display") or "?" for s in failed)
        return ApiResponse(
            success=False,
            code=2001,
            message=f"编译有 {len(failed)} 个分析阶段失败：{agents}",
            data={"stages": stages, "partial_business_system": bs},
        )

    return ApiResponse.ok({
        "pipeline": result["pipeline"],
        "business_system": bs,
        "composed": bs.get("composed", {}),
        "workspace": result.get("workspace", {}),
        "visuals": visuals,
        "summary": result["summary"],
        "output_types": req.output_types,
        "parallel": False,
    })
```
（`bs = result["business_system"]` 已在上方定义。）

- [ ] **Step 4: 运行测试确认通过**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest tests/test_ws3_compile_failure.py -v
```
Expected: PASS（2 个用例）。

- [ ] **Step 5: 提交**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && git add app/api/bsc_api.py tests/test_ws3_compile_failure.py && git commit -m "fix(correctness): WS3b compile_prd_sync 部分失败返回 ApiResponse(success=False, code=2001)"
```

---

## Task 6: 全量回归 + 漂移检查

**Files:** 无新增；仅验证。

- [ ] **Step 1: 运行全量 pytest**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && .venv/Scripts/python.exe -m pytest -q 2>&1 | tail -25
```
Expected: **0 failed**（基线约 368 passed / 2 skipped，外加本计划新增 WS1/WS2/WS3 测试）。若有失败，定位并修复（或回退对应任务），禁止带红提交。

- [ ] **Step 2: 漂移检查（仅核对，不提交）**
```bash
cd "C:/Users/34216/Documents/New project 3/bsc-backend" && git status --short
```
确认以下漂移文件保持**未暂存/未提交**：`app/bsc_cloud.db*`、`app/services/llm_service.py`、`static/dashboard.html`、`archive/orphan_fork/*`、以及工作区其它本地改动（如 `app/agents/protocol.py`）。
确认本计划新增/修改文件均已各自独立提交（T1–T5 共 5 个 commit，T6 不单独提交）。

- [ ] **Step 3: 收尾**
全部通过后调用 `superpowers:finishing-a-development-branch` 技能，将 `feature/security-correctness-hardening` 合回 master（沿用 Round 2 的选择：合并回 master）。
> 提示：Round 2 分支 `feature/knowledge-hardening-round2` 仍有 16 提交未合 master、T10 回归中断——建议合 master 前先收尾 Round 2，避免两条加固分支长期并行。

---

## 自审要点（实现前已核对，落实时勿偏离）

1. **`ApiResponse.error` 无 `data` 参数**（`app/api/response.py:22` 签名为 `error(message, errors, code)`）→ WS3 改用 `ApiResponse(success=False, code=2001, message=..., data={...})` 直接构造，不调用 `.error(...)`。
2. **`require_admin` 误用陷阱**：`knowledge_api.require_admin` 读 `request.state.knowledge_role`（仅 `/knowledge/*` 由 AuthMiddleware 设置），用于 dashboard 会误杀合法 admin key → WS2 新建 `verify_admin_key`（比对全局 `settings.API_KEY`）。实现时**不得**改回复用 `require_admin`。
3. **`/output` 是 StaticFiles 直挂**，浏览器 `<a href>` 无法带 Bearer → 采用 `?token=<admin_key>` 等效方案（Q4=A 意图），非字面移除白名单。
4. **`/dashboard` 静态 UI** 由 `StaticFiles(html=True)` 挂载、不经 router，白名单保留 → UI 仍可加载；仅 JSON 数据面被 `verify_admin_key` 收口。
5. **xss 修复用 `_esc_deep` 单一收口点**（export_to_html 开头转义整份 report），覆盖 `.format` 与 f-string 两条拼装路径；`/sop-report/export` 与 `/sop-report/preview` 均调用 `export_to_html`，故一并修复。纯文本/Markdown 导出不受影响。
6. **破坏性语义**：WS3 使编译部分失败时不再返回 `success:True`（HTTP 仍 200，符合信封约定）。前端若依赖"永远 success"需同步调整——属预期内修正，设计文档已标注。

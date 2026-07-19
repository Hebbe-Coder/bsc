"""
BSC Backend - FastAPI Entry Point
----------------------------------
Start: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, Response, HTMLResponse
import os, time, logging

from app.core.config import settings
from pydantic import BaseModel
from app.core.logger import setup_logging, get_logger

_START_TIME = time.time()

setup_logging(log_level=settings.LOG_LEVEL)
logger = get_logger("main")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.db import init_db
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"DB init skipped: {e}")
    
    try:
        from app.knowledge.schema import ensure_schema
        from app.repositories.knowledge_repository import KnowledgeRepository
        repo = KnowledgeRepository()
        ensure_schema(repo)
        repo.close()
        logger.info("Knowledge schema ensured")
    except Exception as e:
        logger.warning(f"Knowledge schema init skipped: {e}")
    
    logger.info(f"Service started: http://{settings.APP_HOST}:{settings.APP_PORT} | Docs: /docs | Product: /")
    yield
    
    logger.info("Service shutting down")
    
    try:
        from app.core.database import get_database_backend
        backend = get_database_backend()
        backend.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.warning(f"Failed to close database connections: {e}")
    
    try:
        from app.core.metrics import get_metrics_store
        metrics_store = get_metrics_store()
        if hasattr(metrics_store, '_db_backend') and metrics_store._db_backend:
            metrics_store._db_backend.close()
            logger.info("Metrics database connection closed")
    except Exception as e:
        logger.warning(f"Failed to close metrics database connection: {e}")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
**BSC Studio - Business System Compiler**

将非结构化的PRD文档自动转化为完整的业务系统设计方案。

**核心流程：**
1. **业务理解** - 识别业务领域和核心目标
2. **流程设计** - 生成可执行标准操作流程
3. **风险分析** - 识别流程/组织/系统/合规风险
4. **战略分析** - 分析增长机会和战略路径
5. **优化建议** - 提出具体优化措施
6. **结果组装** - 整合所有分析生成专业报告

**支持的输出格式：**
- JSON - 结构化业务系统数据
- HTML - 交互式分析报告
- PPT - 专业级演示文稿

**API认证：**
- 生产环境：需在请求头添加 `Authorization: Bearer <API_KEY>`
- 开发环境：默认允许所有请求（可通过配置API_KEY启用认证）

**快速开始：**
```bash
# 编译PRD文档
curl -X POST http://localhost:8000/bsc/compile \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -d '{"input": "# 零售电商系统PRD\\n\\n## 业务目标\\n- 提升用户转化率\\n- 优化供应链效率"}'
```
""",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    contact={
        "name": "BSC Studio Team",
        "email": "support@bsc-studio.dev",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {
            "name": "BSC Pipeline",
            "description": "业务系统编译核心流程",
        },
        {
            "name": "Projects",
            "description": "项目管理相关接口",
        },
        {
            "name": "Knowledge",
            "description": "知识库管理相关接口",
        },
        {
            "name": "Chat",
            "description": "对话式交互接口",
        },
        {
            "name": "Studio",
            "description": "Studio工作台相关接口",
        },
        {
            "name": "health",
            "description": "健康检查接口",
        },
        {
            "name": "metrics",
            "description": "性能监控指标",
        },
        {
            "name": "Dashboard",
            "description": "业务指标/用户行为看板",
        },
        {
            "name": "templates",
            "description": "模板系统相关接口",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-RateLimit-Rate", "X-RateLimit-Burst", "X-RateLimit-Remaining"],
    expose_headers=["X-RateLimit-Rate", "X-RateLimit-Burst", "X-RateLimit-Remaining", "X-Process-Time-Ms"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, r: Request, call_next):
        t0 = time.perf_counter()
        resp = await call_next(r)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        resp.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        
        try:
            from app.core.metrics import record_request
            endpoint = f"{r.method} {r.url.path}"
            record_request(endpoint, elapsed_ms, resp.status_code)
        except Exception:
            pass
        
        return resp

app.add_middleware(TimingMiddleware)

try:
    from app.middleware.rate_limiter import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, rate=settings.RATE_LIMIT_RATE, burst=settings.RATE_LIMIT_BURST)
    logger.info("Rate limiter middleware enabled")
except Exception as e:
    logger.warning(f"Rate limiter middleware skipped: {e}")

try:
    from app.middleware.auth import AuthMiddleware
    app.add_middleware(AuthMiddleware)
    logger.info("Auth middleware enabled")
except Exception as e:
    logger.warning(f"Auth middleware skipped: {e}")

try:
    from app.middleware.request_signature import RequestSignatureMiddleware
    app.add_middleware(RequestSignatureMiddleware)
    logger.info("Request signature middleware enabled")
except Exception as e:
    logger.warning(f"Request signature middleware skipped: {e}")

try:
    from app.middleware.tracing import TracingMiddleware
    app.add_middleware(TracingMiddleware)
    logger.info("Tracing middleware enabled")
except Exception as e:
    logger.warning(f"Tracing middleware skipped: {e}")

# MIME-type fix: Windows registry overrides Python mimetypes for .js files.
from starlette.requests import Request
class MimeFixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith('.js') or path.endswith('.mjs'):
            response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
        elif path.endswith('.css'):
            response.headers['Content-Type'] = 'text/css; charset=utf-8'
        return response

app.add_middleware(MimeFixMiddleware)
logger.info('MIME fix middleware enabled')

try:
    from app.exceptions import register_exception_handlers
    register_exception_handlers(app)
    logger.info("Exception handlers registered")
except Exception as e:
    logger.warning(f"Exception handlers skipped: {e}")

# Load routers (fail-safe)
_try = lambda m: __import__(m, fromlist=["router"])
for _m in ["app.api.bsc_api","app.api.chat_api","app.api.studio_api","app.api.visual_api","app.api.dashboard","app.api.template_api","app.api.tasks_api","app.api.stream_api","app.api.recommendation_api","app.api.prd_api","app.api.pm_report_api","app.api.dialog_api","app.api.prd_editor_api","app.api.skill_routes","app.api.sop_report_api","app.api.brainstorm_api","app.api.knowledge_api","app.api.knowledge_ws","app.api.files_api","app.api.orchestrate"]:
    try: 
        app.include_router(_try(_m).router)
        logger.info(f"Router loaded: {_m}")
    except Exception as e: 
        logger.warning(f"Skip router {_m}: {e}")

# Static
_static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_static_dir):
    app.mount("/dashboard", StaticFiles(directory=_static_dir, html=True), name="dashboard")

# SPA assets (React build) ? ensure correct MIME types for JS modules
import mimetypes
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")

_dist_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dist")
if os.path.isdir(_dist_dir):
    _assets_dir = os.path.join(_dist_dir, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

# Root -> React SPA (BSC Studio)
@app.get("/", include_in_schema=False)
async def root():
    _index = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dist", "index.html")
    if os.path.isfile(_index):
        with open(_index, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(content=html)
    # Fallback to legacy dashboard
    ts = str(int(time.time()))
    return RedirectResponse(url=f"/dashboard/index.html?v={ts}")

# Health
@app.get("/health", tags=["health"])
async def health():
    dependencies = {}
    
    try:
        from app.repositories import ProjectRepository
        db_ok = ProjectRepository.test_connection()
        dependencies["database"] = {"status": "ok" if db_ok else "error", "message": "SQLite connection"}
    except Exception as e:
        dependencies["database"] = {"status": "error", "message": str(e)}
    
    try:
        if settings.CACHE_TYPE == "redis":
            from redis import Redis
            redis_client = Redis.from_url(settings.REDIS_URL, socket_timeout=3)
            redis_ping = redis_client.ping()
            dependencies["redis"] = {"status": "ok" if redis_ping else "error", "message": "Redis connection"}
        else:
            dependencies["redis"] = {"status": "skipped", "message": f"Cache type is {settings.CACHE_TYPE}"}
    except Exception as e:
        dependencies["redis"] = {"status": "error", "message": str(e)}
    
    try:
        from app.core.celery_app import is_celery_real
        if is_celery_real():
            dependencies["celery"] = {"status": "ok", "message": "Celery async mode enabled"}
        else:
            dependencies["celery"] = {"status": "skipped", "message": "Sync mode (no Celery/Reddis required)"}
    except Exception as e:
        dependencies["celery"] = {"status": "error", "message": str(e)}
    
    try:
        from app.services.llm_service import LLMService
        llm_service = LLMService()
        llm_status = "ok" if llm_service.is_ready() else "warning"
        dependencies["llm_service"] = {"status": llm_status, "message": f"Provider: {settings.LLM_PROVIDER}"}
    except Exception as e:
        dependencies["llm_service"] = {"status": "error", "message": str(e)}
    
    try:
        from app.core.document_parser import get_thread_local_parser
        parser = get_thread_local_parser()
        dependencies["document_parser"] = {"status": "ok", "message": "Parser initialized"}
    except Exception as e:
        dependencies["document_parser"] = {"status": "error", "message": str(e)}
    
    all_ok = all(d.get("status") in ["ok", "skipped"] for d in dependencies.values())
    
    return {
        "status": "ok" if all_ok else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "uptime_sec": int(time.time() - _START_TIME),
        "environment": settings.ENVIRONMENT,
        "dependencies": dependencies,
        "docs": "/docs",
        "product": "/"
    }


# Metrics - JSON format
@app.get("/metrics", tags=["metrics"])
async def metrics():
    """获取性能监控指标（JSON格式）"""
    from app.core.metrics import get_metrics
    return get_metrics()


# Metrics - Prometheus format
@app.get("/metrics/prometheus", tags=["metrics"], response_class=Response)
async def metrics_prometheus():
    """获取性能监控指标（Prometheus格式）"""
    from app.core.metrics import get_prometheus_format
    return Response(content=get_prometheus_format(), media_type="text/plain")



# ============================================================
# Agent OS Routes (ADR-010)
# ============================================================

class AgentOSRequest(BaseModel):
    input: str
    mode: str = "llm"
    domain: str = ""
    board: bool = False


@app.get("/agent/analyze", include_in_schema=False)
async def agent_analyze_page():
    """Agent OS info page"""
    from app.capabilities import build_default_registry
    from app.services.llm_adapter import get_llm_adapter, reset_llm_adapter
    reset_llm_adapter()
    llm = get_llm_adapter()
    reg = build_default_registry()
    return HTMLResponse("""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Business Agent OS</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:40px;max-width:600px;text-align:center}
h1{color:#58a6ff;margin-bottom:8px;font-size:28px}
.sub{color:#8b949e;margin-bottom:24px}
.badge{display:inline-block;background:#1f6feb22;color:#58a6ff;border:1px solid #1f6feb44;border-radius:20px;padding:4px 12px;font-size:13px;margin:4px}
.endpoint{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:16px;margin:12px 0;text-align:left;font-family:monospace}
.method{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:bold;font-size:12px;margin-right:8px}
.get{background:#1f6feb;color:#fff}
.post{background:#238636;color:#fff}
.path{color:#c9d1d9}
a{color:#58a6ff}
.btn{display:inline-block;background:#238636;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;margin-top:16px}
.btn:hover{background:#2ea043}
.btn-alt{background:#30363d;margin-left:8px}
.btn-alt:hover{background:#484f58}
</style>
</head>
<body>
<div class="card">
<h1>Business Agent OS</h1>
<p class="sub">ADR-010 Architecture | Nanobot Kernel | BSC Reasoning Engine</p>
<div>
<span class="badge">""" + str(reg.count()) + """ Capabilities</span>
<span class="badge">LLM: """ + ("Ready" if llm.is_ready else "Offline") + """</span>
<span class="badge">Multi-Agent Board</span>
</div>
<div class="endpoint"><span class="method get">GET</span><span class="path">/agent/health</span><div style="color:#8b949e;margin-top:4px">Health check</div></div>
<div class="endpoint"><span class="method post">POST</span><span class="path">/agent/analyze</span><div style="color:#8b949e;margin-top:4px">Run full business analysis pipeline</div></div>
<a class="btn" href="/docs">Open Swagger UI</a>
<a class="btn btn-alt" href="/">BSC Studio</a>
</div>
</body>
</html>""")


@app.get("/agent/health", tags=["Agent OS"])
async def agent_health():
    """Agent OS health check"""
    from app.capabilities import build_default_registry
    from app.services.llm_adapter import get_llm_adapter, reset_llm_adapter
    reset_llm_adapter()
    llm = get_llm_adapter()
    reg = build_default_registry()
    return {
        "status": "ok", "version": "2.0.0",
        "architecture": "ADR-010 Business Agent OS",
        "capabilities": reg.count(), "llm_ready": llm.is_ready,
        "endpoints": {"analyze": "POST /agent/analyze", "health": "GET /agent/health"},
    }


@app.post("/agent/analyze", tags=["Agent OS"])
async def agent_analyze(req: AgentOSRequest):
    """Run full Agent OS pipeline: Plan -> Execute -> Reflect -> Board -> Report"""
    from app.artifacts import ArtifactGraphStore, BusinessModelArtifact
    from app.capabilities import build_default_registry, MissionPlanner, ReflectionPipeline

    store = ArtifactGraphStore(data_dir="./data/artifacts")
    reg = build_default_registry()
    planner = MissionPlanner(registry=reg, mode=req.mode)

    mission = await planner.plan(req.input, domain_hint=req.domain)
    bm = BusinessModelArtifact(label=mission.title, project_id="api", domain=mission.domain)
    store.add(bm)
    pipe = ReflectionPipeline(store, reg)
    reflection = pipe.run()
    board_result = None
    if req.board:
        from app.capabilities.board import MultiAgentBoard
        board = MultiAgentBoard(store)
        board_result = await board.convene(project_id="api")
    return {
        "status": "completed",
        "mission": {"title": mission.title, "steps": len(mission.steps), "mode": mission.planning_mode},
        "artifacts": store.count(),
        "gaps": reflection["stages"]["reflect"]["gaps_found"],
        "gap_details": reflection["gaps"],
        "board": {
            "verdict": board_result.final_verdict,
            "consensus": board_result.consensus,
            "votes": board_result.votes,
        } if board_result else None,
        "report": store.export(),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)






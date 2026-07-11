"""
BSC Backend - FastAPI Entry Point
----------------------------------
Start: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, Response
import os, time, logging

from app.core.config import settings
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

try:
    from app.exceptions import register_exception_handlers
    register_exception_handlers(app)
    logger.info("Exception handlers registered")
except Exception as e:
    logger.warning(f"Exception handlers skipped: {e}")

# Load routers (fail-safe)
_try = lambda m: __import__(m, fromlist=["router"])
for _m in ["app.api.bsc_api","app.api.chat_api","app.api.studio_api","app.api.visual_api","app.api.dashboard","app.api.template_api","app.api.tasks_api","app.api.stream_api","app.api.recommendation_api","app.api.prd_api","app.api.pm_report_api","app.api.dialog_api","app.api.prd_editor_api","app.api.skill_routes","app.api.sop_report_api","app.api.brainstorm_api","app.api.knowledge_api","app.api.knowledge_ws","app.api.files_api"]:
    try: 
        app.include_router(_try(_m).router)
        logger.info(f"Router loaded: {_m}")
    except Exception as e: 
        logger.warning(f"Skip router {_m}: {e}")

# Static
_static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_static_dir):
    app.mount("/dashboard", StaticFiles(directory=_static_dir, html=True), name="dashboard")

# Root → BSC Chat (conversational interface)
@app.get("/", include_in_schema=False)
async def root():
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)






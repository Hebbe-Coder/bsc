"""Dashboard API - 业务指标/用户行为看板"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List

from app.api.response import ApiResponse
from app.api.auth_deps import verify_admin_key

router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(verify_admin_key)])


class MetricsOverview(BaseModel):
    """实时指标概览"""
    uptime_sec: int = Field(..., description="服务运行时长（秒）")
    total_requests: int = Field(..., description="总请求数")
    total_errors: int = Field(..., description="总错误数")
    total_llm_calls: int = Field(..., description="总LLM调用数")
    total_agent_executions: int = Field(..., description="总Agent执行次数")
    error_rate: float = Field(..., description="错误率（%）")
    system_cpu: float = Field(..., description="CPU使用率（%）")
    system_memory: float = Field(..., description="内存使用（MB）")


class EndpointStats(BaseModel):
    """端点统计"""
    endpoint: str = Field(..., description="端点路径")
    total_requests: int = Field(..., description="总请求数")
    min_response_ms: float = Field(..., description="最小响应时间（毫秒）")
    max_response_ms: float = Field(..., description="最大响应时间（毫秒）")
    avg_response_ms: float = Field(..., description="平均响应时间（毫秒）")
    p95_response_ms: float = Field(..., description="P95响应时间（毫秒）")
    p99_response_ms: float = Field(..., description="P99响应时间（毫秒）")
    error_rate: float = Field(..., description="错误率（%）")


class DailyStat(BaseModel):
    """每日统计"""
    date: str = Field(..., description="日期")
    total_requests: int = Field(..., description="总请求数")
    total_errors: int = Field(..., description="总错误数")
    total_llm_calls: int = Field(..., description="总LLM调用数")
    avg_response_ms: float = Field(..., description="平均响应时间（毫秒）")
    p95_response_ms: float = Field(..., description="P95响应时间（毫秒）")
    p99_response_ms: float = Field(..., description="P99响应时间（毫秒）")
    error_rate: float = Field(..., description="错误率（%）")


class APIUsageLog(BaseModel):
    """API使用日志"""
    id: str = Field(..., description="日志ID")
    endpoint: str = Field(..., description="端点路径")
    method: str = Field(..., description="HTTP方法")
    status_code: int = Field(..., description="状态码")
    duration_ms: int = Field(..., description="响应时间（毫秒）")
    timestamp: str = Field(..., description="时间戳")
    trace_id: str = Field(..., description="追踪ID")


class LLMStats(BaseModel):
    """LLM调用统计"""
    provider_model: str = Field(..., description="Provider/Model")
    total_calls: int = Field(..., description="总调用数")
    min_response_ms: float = Field(..., description="最小响应时间（毫秒）")
    max_response_ms: float = Field(..., description="最大响应时间（毫秒）")
    avg_response_ms: float = Field(..., description="平均响应时间（毫秒）")


class AgentStats(BaseModel):
    """Agent执行统计"""
    agent: str = Field(..., description="Agent名称")
    total_executions: int = Field(..., description="总执行次数")
    error_count: int = Field(..., description="错误次数")
    error_rate: float = Field(..., description="错误率（%）")
    avg_duration_ms: float = Field(..., description="平均执行时间（毫秒）")


class CacheStats(BaseModel):
    """缓存统计"""
    cache_type: str = Field(..., description="缓存类型")
    hits: int = Field(..., description="命中次数")
    misses: int = Field(..., description="未命中次数")
    hit_rate: float = Field(..., description="命中率（%）")


class DashboardSummary(BaseModel):
    """看板汇总"""
    overview: MetricsOverview = Field(..., description="实时概览")
    endpoints: List[EndpointStats] = Field(..., description="端点统计")
    daily_stats: List[DailyStat] = Field(..., description="每日趋势")
    llm_stats: List[LLMStats] = Field(..., description="LLM统计")
    agent_stats: List[AgentStats] = Field(..., description="Agent统计")
    cache_stats: List[CacheStats] = Field(..., description="缓存统计")


@router.get(
    "/overview",
    response_model=ApiResponse[MetricsOverview],
    summary="实时指标概览",
    description="获取服务的实时运行指标概览，包括请求数、错误率、系统资源使用等",
)
async def get_overview():
    from app.core.metrics import get_metrics

    metrics = get_metrics()
    
    error_rate = round(
        metrics["total_errors"] / max(metrics["total_requests"], 1) * 100, 
        2
    )

    return ApiResponse.ok({
        "uptime_sec": metrics["uptime_sec"],
        "total_requests": metrics["total_requests"],
        "total_errors": metrics["total_errors"],
        "total_llm_calls": metrics["total_llm_calls"],
        "total_agent_executions": metrics["total_agent_executions"],
        "error_rate": error_rate,
        "system_cpu": metrics["system"]["cpu_percent"],
        "system_memory": metrics["system"]["memory_mb"],
    })


@router.get(
    "/endpoints",
    response_model=ApiResponse[List[EndpointStats]],
    summary="端点统计",
    description="获取各API端点的请求统计，包括响应时间分布和错误率",
)
async def get_endpoint_stats():
    from app.core.metrics import get_metrics

    metrics = get_metrics()
    endpoint_stats = []

    for endpoint, stats in metrics["endpoints"].items():
        endpoint_stats.append({
            "endpoint": endpoint,
            "total_requests": stats["total_requests"],
            "min_response_ms": stats["min"],
            "max_response_ms": stats["max"],
            "avg_response_ms": stats["avg"],
            "p95_response_ms": stats["p95"],
            "p99_response_ms": stats["p99"],
            "error_rate": stats["error_rate"],
        })

    endpoint_stats.sort(key=lambda x: x["total_requests"], reverse=True)
    return ApiResponse.ok(endpoint_stats)


@router.get(
    "/daily",
    response_model=ApiResponse[List[DailyStat]],
    summary="每日统计趋势",
    description="获取最近N天的每日统计数据，用于趋势分析",
)
async def get_daily_stats(
    days: int = Query(7, ge=1, le=30, description="查询天数，1-30天"),
):
    from app.core.metrics import get_daily_stats

    raw_stats = get_daily_stats(days)
    
    daily_stats = []
    for stat in raw_stats:
        error_rate = round(
            stat["total_errors"] / max(stat["total_requests"], 1) * 100, 
            2
        )
        daily_stats.append({
            "date": stat["date"],
            "total_requests": stat["total_requests"],
            "total_errors": stat["total_errors"],
            "total_llm_calls": stat["total_llm_calls"],
            "avg_response_ms": stat["avg_response_ms"],
            "p95_response_ms": stat["p95_response_ms"],
            "p99_response_ms": stat["p99_response_ms"],
            "error_rate": error_rate,
        })

    daily_stats.sort(key=lambda x: x["date"])
    return ApiResponse.ok(daily_stats)


@router.get(
    "/logs",
    response_model=ApiResponse[List[APIUsageLog]],
    summary="API使用日志",
    description="获取最近的API请求日志，支持按端点筛选",
)
async def get_api_logs(
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
    endpoint: Optional[str] = Query(None, description="按端点筛选"),
):
    from app.core.metrics import get_api_usage_log

    logs = get_api_usage_log(limit, endpoint)
    return ApiResponse.ok(logs)


@router.get(
    "/llm",
    response_model=ApiResponse[List[LLMStats]],
    summary="LLM调用统计",
    description="获取LLM服务的调用统计，按provider和model分组",
)
async def get_llm_stats():
    from app.core.metrics import get_metrics

    metrics = get_metrics()
    llm_stats = []

    for llm_key, stats in metrics["llm"].items():
        llm_stats.append({
            "provider_model": llm_key,
            "total_calls": stats["total_calls"],
            "min_response_ms": stats["min"],
            "max_response_ms": stats["max"],
            "avg_response_ms": stats["avg"],
        })

    llm_stats.sort(key=lambda x: x["total_calls"], reverse=True)
    return ApiResponse.ok(llm_stats)


@router.get(
    "/agents",
    response_model=ApiResponse[List[AgentStats]],
    summary="Agent执行统计",
    description="获取各Agent的执行统计，包括错误率和执行时间",
)
async def get_agent_stats():
    from app.core.metrics import get_metrics

    metrics = get_metrics()
    agent_stats = []

    for agent_key, stats in metrics["agents"].items():
        agent_stats.append({
            "agent": agent_key,
            "total_executions": stats["total_executions"],
            "error_count": stats["error_count"],
            "error_rate": stats["error_rate"],
            "avg_duration_ms": stats["avg"],
        })

    agent_stats.sort(key=lambda x: x["total_executions"], reverse=True)
    return ApiResponse.ok(agent_stats)


@router.get(
    "/cache",
    response_model=ApiResponse[List[CacheStats]],
    summary="缓存统计",
    description="获取缓存命中率统计",
)
async def get_cache_stats():
    from app.core.metrics import get_metrics

    metrics = get_metrics()
    cache_stats = []

    for cache_type, stats in metrics["cache"].items():
        cache_stats.append({
            "cache_type": cache_type,
            "hits": stats["hits"],
            "misses": stats["misses"],
            "hit_rate": stats["hit_rate"],
        })

    return ApiResponse.ok(cache_stats)


@router.get(
    "/summary",
    response_model=ApiResponse[DashboardSummary],
    summary="看板汇总",
    description="获取完整的看板数据汇总，包括所有指标维度",
)
async def get_dashboard_summary(
    days: int = Query(7, ge=1, le=30, description="每日统计天数"),
):
    from app.core.metrics import get_metrics, get_daily_stats

    metrics = get_metrics()
    raw_daily = get_daily_stats(days)

    error_rate = round(
        metrics["total_errors"] / max(metrics["total_requests"], 1) * 100, 
        2
    )

    overview = {
        "uptime_sec": metrics["uptime_sec"],
        "total_requests": metrics["total_requests"],
        "total_errors": metrics["total_errors"],
        "total_llm_calls": metrics["total_llm_calls"],
        "total_agent_executions": metrics["total_agent_executions"],
        "error_rate": error_rate,
        "system_cpu": metrics["system"]["cpu_percent"],
        "system_memory": metrics["system"]["memory_mb"],
    }

    endpoints = []
    for endpoint, stats in metrics["endpoints"].items():
        endpoints.append({
            "endpoint": endpoint,
            "total_requests": stats["total_requests"],
            "min_response_ms": stats["min"],
            "max_response_ms": stats["max"],
            "avg_response_ms": stats["avg"],
            "p95_response_ms": stats["p95"],
            "p99_response_ms": stats["p99"],
            "error_rate": stats["error_rate"],
        })
    endpoints.sort(key=lambda x: x["total_requests"], reverse=True)

    daily_stats = []
    for stat in raw_daily:
        daily_error_rate = round(
            stat["total_errors"] / max(stat["total_requests"], 1) * 100, 
            2
        )
        daily_stats.append({
            "date": stat["date"],
            "total_requests": stat["total_requests"],
            "total_errors": stat["total_errors"],
            "total_llm_calls": stat["total_llm_calls"],
            "avg_response_ms": stat["avg_response_ms"],
            "p95_response_ms": stat["p95_response_ms"],
            "p99_response_ms": stat["p99_response_ms"],
            "error_rate": daily_error_rate,
        })
    daily_stats.sort(key=lambda x: x["date"])

    llm_stats = []
    for llm_key, stats in metrics["llm"].items():
        llm_stats.append({
            "provider_model": llm_key,
            "total_calls": stats["total_calls"],
            "min_response_ms": stats["min"],
            "max_response_ms": stats["max"],
            "avg_response_ms": stats["avg"],
        })
    llm_stats.sort(key=lambda x: x["total_calls"], reverse=True)

    agent_stats = []
    for agent_key, stats in metrics["agents"].items():
        agent_stats.append({
            "agent": agent_key,
            "total_executions": stats["total_executions"],
            "error_count": stats["error_count"],
            "error_rate": stats["error_rate"],
            "avg_duration_ms": stats["avg"],
        })
    agent_stats.sort(key=lambda x: x["total_executions"], reverse=True)

    cache_stats = []
    for cache_type, stats in metrics["cache"].items():
        cache_stats.append({
            "cache_type": cache_type,
            "hits": stats["hits"],
            "misses": stats["misses"],
            "hit_rate": stats["hit_rate"],
        })

    return ApiResponse.ok({
        "overview": overview,
        "endpoints": endpoints,
        "daily_stats": daily_stats,
        "llm_stats": llm_stats,
        "agent_stats": agent_stats,
        "cache_stats": cache_stats,
    })

"""
Metrics - 性能监控指标

提供：
1. 请求计数器（含HTTP方法、状态码维度）
2. 响应时间统计（最小/最大/平均/P95/P99）
3. 错误率统计（按错误类型分类）
4. LLM调用统计（按provider、model、agent维度）
5. Agent执行统计（按agent类型、阶段维度）
6. Pipeline执行统计（按阶段、并行/串行维度）
7. 缓存命中率统计
8. 系统资源使用统计（CPU、内存）
9. Prometheus格式指标输出
10. 请求级trace_id追踪
11. 数据库持久化（API使用日志、每日统计）
"""
from __future__ import annotations
import time
import threading
import os
import uuid
import logging
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    _PSUTIL_AVAILABLE = False

_thread_local = threading.local()


class MetricsStore:
    """性能指标存储"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._db_lock = threading.Lock()
        
        self.request_counts: Dict[str, int] = defaultdict(int)
        self.request_counts_by_method: Dict[str, int] = defaultdict(int)
        self.request_counts_by_status: Dict[int, int] = defaultdict(int)
        self.response_times: Dict[str, List[float]] = defaultdict(list)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.error_counts_by_type: Dict[str, int] = defaultdict(int)
        
        self.llm_call_counts: Dict[str, int] = defaultdict(int)
        self.llm_call_times: Dict[str, List[float]] = defaultdict(list)
        
        self.agent_execution_counts: Dict[str, int] = defaultdict(int)
        self.agent_execution_times: Dict[str, List[float]] = defaultdict(list)
        self.agent_execution_errors: Dict[str, int] = defaultdict(int)
        
        self.pipeline_stage_counts: Dict[str, int] = defaultdict(int)
        self.pipeline_stage_times: Dict[str, List[float]] = defaultdict(list)
        self.pipeline_execution_counts: Dict[str, int] = defaultdict(int)
        self.pipeline_execution_times: Dict[str, List[float]] = defaultdict(list)
        
        self.cache_hits: Dict[str, int] = defaultdict(int)
        self.cache_misses: Dict[str, int] = defaultdict(int)
        
        self.start_time = time.time()
        self.process = psutil.Process(os.getpid()) if _PSUTIL_AVAILABLE else None
        
        self._db_backend = None
        self._last_daily_stats_update = None
    
    def _get_db_backend(self):
        """获取数据库后端（懒加载）"""
        if self._db_backend is None:
            from app.core.database import get_database_backend
            self._db_backend = get_database_backend()
        return self._db_backend
    
    def _save_api_usage_log(self, endpoint: str, duration_ms: float, status_code: int,
                            http_method: str = "POST", error_type: str = ""):
        """保存API使用日志到数据库"""
        try:
            backend = self._get_db_backend()
            with self._db_lock:
                backend.execute(
                    """
                    INSERT INTO api_usage_log 
                    (id, endpoint, method, status_code, duration_ms, client_ip, 
                     api_key_hash, timestamp, trace_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        endpoint,
                        http_method,
                        status_code,
                        int(duration_ms),
                        "",
                        "",
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                        get_trace_id(),
                    )
                )
                backend.commit()
        except Exception as e:
            logger.warning(f"保存API使用日志失败: {e}")
    
    def _update_daily_stats(self):
        """更新每日统计数据"""
        now = time.strftime("%Y-%m-%d")
        
        if self._last_daily_stats_update == now:
            return
        
        try:
            backend = self._get_db_backend()
            with self._db_lock:
                metrics = self.get_metrics()
                
                avg_response = metrics.get("endpoints", {}).get("/bsc/compile", {}).get("avg", 0)
                p95_response = metrics.get("endpoints", {}).get("/bsc/compile", {}).get("p95", 0)
                p99_response = metrics.get("endpoints", {}).get("/bsc/compile", {}).get("p99", 0)
                
                backend.execute(
                    """
                    INSERT OR REPLACE INTO daily_stats 
                    (id, date, total_requests, total_errors, total_llm_calls,
                     avg_response_ms, p95_response_ms, p99_response_ms, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        now,
                        metrics["total_requests"],
                        metrics["total_errors"],
                        metrics["total_llm_calls"],
                        avg_response,
                        p95_response,
                        p99_response,
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )
                backend.commit()
                
                self._last_daily_stats_update = now
        except Exception as e:
            logger.warning(f"更新每日统计数据失败: {e}")
    
    def record_request(self, endpoint: str, duration_ms: float, status_code: int, 
                      http_method: str = "POST", error_type: str = ""):
        """记录请求指标"""
        with self._lock:
            self.request_counts[endpoint] += 1
            self.request_counts_by_method[f"{http_method}_{endpoint}"] += 1
            self.request_counts_by_status[status_code] += 1
            self.response_times[endpoint].append(duration_ms)
            
            if status_code >= 400:
                self.error_counts[endpoint] += 1
                if error_type:
                    self.error_counts_by_type[error_type] += 1
                else:
                    self.error_counts_by_type[f"{status_code}_other"] += 1
        
        self._save_api_usage_log(endpoint, duration_ms, status_code, http_method, error_type)
        self._update_daily_stats()
    
    def record_llm_call(self, provider: str, model: str, duration_ms: float, 
                        agent_type: str = ""):
        """记录LLM调用指标"""
        base_key = f"{provider}_{model}"
        agent_key = f"{provider}_{model}_{agent_type}" if agent_type else base_key
        
        with self._lock:
            self.llm_call_counts[base_key] += 1
            self.llm_call_counts[agent_key] += 1
            self.llm_call_times[base_key].append(duration_ms)
            self.llm_call_times[agent_key].append(duration_ms)
    
    def record_agent_execution(self, agent_key: str, duration_ms: float, 
                               success: bool = True):
        """记录Agent执行指标"""
        with self._lock:
            self.agent_execution_counts[agent_key] += 1
            self.agent_execution_times[agent_key].append(duration_ms)
            if not success:
                self.agent_execution_errors[agent_key] += 1
    
    def record_pipeline_stage(self, stage_key: str, duration_ms: float):
        """记录Pipeline阶段执行指标"""
        with self._lock:
            self.pipeline_stage_counts[stage_key] += 1
            self.pipeline_stage_times[stage_key].append(duration_ms)
    
    def record_pipeline_execution(self, mode: str, duration_ms: float):
        """记录Pipeline执行指标"""
        with self._lock:
            self.pipeline_execution_counts[mode] += 1
            self.pipeline_execution_times[mode].append(duration_ms)
    
    def record_cache_operation(self, cache_type: str, hit: bool):
        """记录缓存操作"""
        with self._lock:
            if hit:
                self.cache_hits[cache_type] += 1
            else:
                self.cache_misses[cache_type] += 1
    
    def get_stats(self, times: List[float]) -> Dict[str, float]:
        """计算统计指标"""
        if not times:
            return {"min": 0, "max": 0, "avg": 0, "p95": 0, "p99": 0, "count": 0}
        
        times.sort()
        n = len(times)
        return {
            "min": round(times[0], 2),
            "max": round(times[-1], 2),
            "avg": round(sum(times) / n, 2),
            "p95": round(times[int(n * 0.95)] if n > 20 else times[-1], 2),
            "p99": round(times[int(n * 0.99)] if n > 100 else times[-1], 2),
            "count": n,
        }
    
    def get_system_stats(self) -> Dict[str, float]:
        """获取系统资源使用统计"""
        if not _PSUTIL_AVAILABLE or self.process is None:
            return {
                "cpu_percent": 0.0,
                "memory_mb": 0.0,
                "thread_count": 0,
                "open_files": 0,
            }
        
        try:
            mem_info = self.process.memory_info()
            cpu_percent = self.process.cpu_percent(interval=0.1)
            thread_count = self.process.num_threads()
            
            return {
                "cpu_percent": cpu_percent,
                "memory_mb": round(mem_info.rss / 1024 / 1024, 2),
                "thread_count": thread_count,
                "open_files": len(self.process.open_files()),
            }
        except Exception:
            return {
                "cpu_percent": 0.0,
                "memory_mb": 0.0,
                "thread_count": 0,
                "open_files": 0,
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        with self._lock:
            uptime_sec = int(time.time() - self.start_time)
            
            request_stats = {}
            for endpoint, times in self.response_times.items():
                stats = self.get_stats(times)
                stats["total_requests"] = self.request_counts[endpoint]
                stats["error_rate"] = round(self.error_counts[endpoint] / max(self.request_counts[endpoint], 1) * 100, 2)
                request_stats[endpoint] = stats
            
            llm_stats = {}
            for key, times in self.llm_call_times.items():
                stats = self.get_stats(times)
                stats["total_calls"] = self.llm_call_counts[key]
                llm_stats[key] = stats
            
            agent_stats = {}
            for key in set(list(self.agent_execution_counts.keys()) + list(self.agent_execution_errors.keys())):
                times = self.agent_execution_times.get(key, [])
                stats = self.get_stats(times)
                stats["total_executions"] = self.agent_execution_counts[key]
                stats["error_count"] = self.agent_execution_errors.get(key, 0)
                stats["error_rate"] = round(stats["error_count"] / max(stats["total_executions"], 1) * 100, 2)
                agent_stats[key] = stats
            
            pipeline_stage_stats = {}
            for stage_key, times in self.pipeline_stage_times.items():
                stats = self.get_stats(times)
                stats["total_executions"] = self.pipeline_stage_counts[stage_key]
                pipeline_stage_stats[stage_key] = stats
            
            pipeline_execution_stats = {}
            for mode, times in self.pipeline_execution_times.items():
                stats = self.get_stats(times)
                stats["total_executions"] = self.pipeline_execution_counts[mode]
                pipeline_execution_stats[mode] = stats
            
            cache_stats = {}
            for cache_type in set(list(self.cache_hits.keys()) + list(self.cache_misses.keys())):
                hits = self.cache_hits.get(cache_type, 0)
                misses = self.cache_misses.get(cache_type, 0)
                total = hits + misses
                cache_stats[cache_type] = {
                    "hits": hits,
                    "misses": misses,
                    "hit_rate": round(hits / max(total, 1) * 100, 2),
                }
            
            return {
                "uptime_sec": uptime_sec,
                "total_requests": sum(self.request_counts.values()),
                "total_errors": sum(self.error_counts.values()),
                "total_llm_calls": sum(self.llm_call_counts.values()),
                "total_agent_executions": sum(self.agent_execution_counts.values()),
                "requests_by_status": dict(self.request_counts_by_status),
                "errors_by_type": dict(self.error_counts_by_type),
                "endpoints": request_stats,
                "llm": llm_stats,
                "agents": agent_stats,
                "pipeline_stages": pipeline_stage_stats,
                "pipeline_executions": pipeline_execution_stats,
                "cache": cache_stats,
                "system": self.get_system_stats(),
            }
    
    def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近N天的每日统计数据"""
        try:
            backend = self._get_db_backend()
            with self._db_lock:
                cursor = backend.execute(
                    """
                    SELECT * FROM daily_stats 
                    ORDER BY date DESC LIMIT ?
                    """,
                    (days,)
                )
                return backend.rows_to_list(cursor)
        except Exception as e:
            logger.warning(f"获取每日统计数据失败: {e}")
            return []
    
    def get_api_usage_log(self, limit: int = 100, endpoint: str = None) -> List[Dict[str, Any]]:
        """获取API使用日志"""
        try:
            backend = self._get_db_backend()
            with self._db_lock:
                if endpoint:
                    cursor = backend.execute(
                        """
                        SELECT * FROM api_usage_log 
                        WHERE endpoint = ? 
                        ORDER BY timestamp DESC LIMIT ?
                        """,
                        (endpoint, limit)
                    )
                else:
                    cursor = backend.execute(
                        """
                        SELECT * FROM api_usage_log 
                        ORDER BY timestamp DESC LIMIT ?
                        """,
                        (limit,)
                    )
                return backend.rows_to_list(cursor)
        except Exception as e:
            logger.warning(f"获取API使用日志失败: {e}")
            return []
    
    def get_api_usage_summary(self, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """获取API使用汇总统计"""
        try:
            backend = self._get_db_backend()
            with self._db_lock:
                query = "SELECT endpoint, COUNT(*) as count, AVG(duration_ms) as avg_duration, SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as errors FROM api_usage_log"
                params = []
                
                if start_date and end_date:
                    query += " WHERE timestamp BETWEEN ? AND ?"
                    params.extend([f"{start_date} 00:00:00", f"{end_date} 23:59:59"])
                
                query += " GROUP BY endpoint ORDER BY count DESC"
                
                cursor = backend.execute(query, tuple(params))
                rows = backend.rows_to_list(cursor)
                
                return {
                    "by_endpoint": rows,
                    "total_requests": sum(row["count"] for row in rows),
                    "total_errors": sum(row["errors"] for row in rows),
                    "avg_duration_ms": sum(row["avg_duration"] * row["count"] for row in rows) / max(sum(row["count"] for row in rows), 1) if rows else 0,
                }
        except Exception as e:
            logger.warning(f"获取API使用汇总统计失败: {e}")
            return {"by_endpoint": [], "total_requests": 0, "total_errors": 0, "avg_duration_ms": 0}
    
    def get_prometheus_format(self) -> str:
        """获取Prometheus格式的指标输出"""
        metrics = self.get_metrics()
        lines = []
        
        lines.append(f"# HELP bsc_uptime_seconds Service uptime in seconds")
        lines.append(f"# TYPE bsc_uptime_seconds gauge")
        lines.append(f"bsc_uptime_seconds {metrics['uptime_sec']}")
        
        lines.append(f"\n# HELP bsc_total_requests Total requests")
        lines.append(f"# TYPE bsc_total_requests counter")
        lines.append(f"bsc_total_requests {metrics['total_requests']}")
        
        lines.append(f"\n# HELP bsc_total_errors Total errors")
        lines.append(f"# TYPE bsc_total_errors counter")
        lines.append(f"bsc_total_errors {metrics['total_errors']}")
        
        lines.append(f"\n# HELP bsc_total_llm_calls Total LLM calls")
        lines.append(f"# TYPE bsc_total_llm_calls counter")
        lines.append(f"bsc_total_llm_calls {metrics['total_llm_calls']}")
        
        lines.append(f"\n# HELP bsc_total_agent_executions Total agent executions")
        lines.append(f"# TYPE bsc_total_agent_executions counter")
        lines.append(f"bsc_total_agent_executions {metrics['total_agent_executions']}")
        
        for status_code, count in metrics["requests_by_status"].items():
            lines.append(f"\n# HELP bsc_requests_by_status_total Requests by status code")
            lines.append(f"# TYPE bsc_requests_by_status_total counter")
            lines.append(f"bsc_requests_by_status_total{{status=\"{status_code}\"}} {count}")
        
        for error_type, count in metrics["errors_by_type"].items():
            lines.append(f"\n# HELP bsc_errors_by_type_total Errors by type")
            lines.append(f"# TYPE bsc_errors_by_type_total counter")
            lines.append(f"bsc_errors_by_type_total{{error_type=\"{error_type}\"}} {count}")
        
        for endpoint, stats in metrics["endpoints"].items():
            endpoint_label = f'endpoint="{endpoint}"'
            
            lines.append(f"\n# HELP bsc_request_duration_ms Request duration in milliseconds")
            lines.append(f"# TYPE bsc_request_duration_ms histogram")
            lines.append(f"bsc_request_duration_ms{{{endpoint_label},stat=\"min\"}} {stats['min']}")
            lines.append(f"bsc_request_duration_ms{{{endpoint_label},stat=\"max\"}} {stats['max']}")
            lines.append(f"bsc_request_duration_ms{{{endpoint_label},stat=\"avg\"}} {stats['avg']}")
            lines.append(f"bsc_request_duration_ms{{{endpoint_label},stat=\"p95\"}} {stats['p95']}")
            lines.append(f"bsc_request_duration_ms{{{endpoint_label},stat=\"p99\"}} {stats['p99']}")
            
            lines.append(f"\n# HELP bsc_requests_total Total requests per endpoint")
            lines.append(f"# TYPE bsc_requests_total counter")
            lines.append(f"bsc_requests_total{{{endpoint_label}}} {stats['total_requests']}")
            
            lines.append(f"\n# HELP bsc_error_rate Error rate per endpoint")
            lines.append(f"# TYPE bsc_error_rate gauge")
            lines.append(f"bsc_error_rate{{{endpoint_label}}} {stats['error_rate']}")
        
        for llm_key, stats in metrics["llm"].items():
            llm_label = f'llm="{llm_key}"'
            
            lines.append(f"\n# HELP bsc_llm_call_duration_ms LLM call duration in milliseconds")
            lines.append(f"# TYPE bsc_llm_call_duration_ms histogram")
            lines.append(f"bsc_llm_call_duration_ms{{{llm_label},stat=\"min\"}} {stats['min']}")
            lines.append(f"bsc_llm_call_duration_ms{{{llm_label},stat=\"max\"}} {stats['max']}")
            lines.append(f"bsc_llm_call_duration_ms{{{llm_label},stat=\"avg\"}} {stats['avg']}")
            
            lines.append(f"\n# HELP bsc_llm_calls_total Total LLM calls per provider/model")
            lines.append(f"# TYPE bsc_llm_calls_total counter")
            lines.append(f"bsc_llm_calls_total{{{llm_label}}} {stats['total_calls']}")
        
        for agent_key, stats in metrics["agents"].items():
            agent_label = f'agent="{agent_key}"'
            
            lines.append(f"\n# HELP bsc_agent_execution_duration_ms Agent execution duration in milliseconds")
            lines.append(f"# TYPE bsc_agent_execution_duration_ms histogram")
            lines.append(f"bsc_agent_execution_duration_ms{{{agent_label},stat=\"min\"}} {stats['min']}")
            lines.append(f"bsc_agent_execution_duration_ms{{{agent_label},stat=\"max\"}} {stats['max']}")
            lines.append(f"bsc_agent_execution_duration_ms{{{agent_label},stat=\"avg\"}} {stats['avg']}")
            
            lines.append(f"\n# HELP bsc_agent_executions_total Total agent executions")
            lines.append(f"# TYPE bsc_agent_executions_total counter")
            lines.append(f"bsc_agent_executions_total{{{agent_label}}} {stats['total_executions']}")
            
            lines.append(f"\n# HELP bsc_agent_error_rate Agent error rate")
            lines.append(f"# TYPE bsc_agent_error_rate gauge")
            lines.append(f"bsc_agent_error_rate{{{agent_label}}} {stats['error_rate']}")
        
        for stage_key, stats in metrics["pipeline_stages"].items():
            stage_label = f'stage="{stage_key}"'
            
            lines.append(f"\n# HELP bsc_pipeline_stage_duration_ms Pipeline stage duration in milliseconds")
            lines.append(f"# TYPE bsc_pipeline_stage_duration_ms histogram")
            lines.append(f"bsc_pipeline_stage_duration_ms{{{stage_label},stat=\"min\"}} {stats['min']}")
            lines.append(f"bsc_pipeline_stage_duration_ms{{{stage_label},stat=\"max\"}} {stats['max']}")
            lines.append(f"bsc_pipeline_stage_duration_ms{{{stage_label},stat=\"avg\"}} {stats['avg']}")
            
            lines.append(f"\n# HELP bsc_pipeline_stage_executions_total Total pipeline stage executions")
            lines.append(f"# TYPE bsc_pipeline_stage_executions_total counter")
            lines.append(f"bsc_pipeline_stage_executions_total{{{stage_label}}} {stats['total_executions']}")
        
        for mode, stats in metrics["pipeline_executions"].items():
            mode_label = f'mode="{mode}"'
            
            lines.append(f"\n# HELP bsc_pipeline_execution_duration_ms Pipeline execution duration in milliseconds")
            lines.append(f"# TYPE bsc_pipeline_execution_duration_ms histogram")
            lines.append(f"bsc_pipeline_execution_duration_ms{{{mode_label},stat=\"min\"}} {stats['min']}")
            lines.append(f"bsc_pipeline_execution_duration_ms{{{mode_label},stat=\"max\"}} {stats['max']}")
            lines.append(f"bsc_pipeline_execution_duration_ms{{{mode_label},stat=\"avg\"}} {stats['avg']}")
        
        for cache_type, stats in metrics["cache"].items():
            cache_label = f'cache="{cache_type}"'
            
            lines.append(f"\n# HELP bsc_cache_hits_total Total cache hits")
            lines.append(f"# TYPE bsc_cache_hits_total counter")
            lines.append(f"bsc_cache_hits_total{{{cache_label}}} {stats['hits']}")
            
            lines.append(f"\n# HELP bsc_cache_misses_total Total cache misses")
            lines.append(f"# TYPE bsc_cache_misses_total counter")
            lines.append(f"bsc_cache_misses_total{{{cache_label}}} {stats['misses']}")
            
            lines.append(f"\n# HELP bsc_cache_hit_rate Cache hit rate")
            lines.append(f"# TYPE bsc_cache_hit_rate gauge")
            lines.append(f"bsc_cache_hit_rate{{{cache_label}}} {stats['hit_rate']}")
        
        system = metrics["system"]
        lines.append(f"\n# HELP bsc_system_cpu_percent CPU usage percentage")
        lines.append(f"# TYPE bsc_system_cpu_percent gauge")
        lines.append(f"bsc_system_cpu_percent {system['cpu_percent']}")
        
        lines.append(f"\n# HELP bsc_system_memory_mb Memory usage in MB")
        lines.append(f"# TYPE bsc_system_memory_mb gauge")
        lines.append(f"bsc_system_memory_mb {system['memory_mb']}")
        
        lines.append(f"\n# HELP bsc_system_thread_count Thread count")
        lines.append(f"# TYPE bsc_system_thread_count gauge")
        lines.append(f"bsc_system_thread_count {system['thread_count']}")
        
        lines.append(f"\n# HELP bsc_system_open_files Open file count")
        lines.append(f"# TYPE bsc_system_open_files gauge")
        lines.append(f"bsc_system_open_files {system['open_files']}")
        
        return "\n".join(lines)


_metrics_store = MetricsStore()


def get_metrics_store() -> MetricsStore:
    """获取全局指标存储实例"""
    return _metrics_store


def record_request(endpoint: str, duration_ms: float, status_code: int, 
                   http_method: str = "POST", error_type: str = ""):
    """记录请求指标（便捷函数）"""
    _metrics_store.record_request(endpoint, duration_ms, status_code, http_method, error_type)


def record_llm_call(provider: str, model: str, duration_ms: float, 
                    agent_type: str = ""):
    """记录LLM调用指标（便捷函数）"""
    _metrics_store.record_llm_call(provider, model, duration_ms, agent_type)


def record_agent_execution(agent_key: str, duration_ms: float, 
                           success: bool = True):
    """记录Agent执行指标（便捷函数）"""
    _metrics_store.record_agent_execution(agent_key, duration_ms, success)


def record_pipeline_stage(stage_key: str, duration_ms: float):
    """记录Pipeline阶段执行指标（便捷函数）"""
    _metrics_store.record_pipeline_stage(stage_key, duration_ms)


def record_pipeline_execution(mode: str, duration_ms: float):
    """记录Pipeline执行指标（便捷函数）"""
    _metrics_store.record_pipeline_execution(mode, duration_ms)


def record_cache_operation(cache_type: str, hit: bool):
    """记录缓存操作（便捷函数）"""
    _metrics_store.record_cache_operation(cache_type, hit)


def get_metrics() -> Dict[str, Any]:
    """获取所有指标（便捷函数）"""
    return _metrics_store.get_metrics()


def get_prometheus_format() -> str:
    """获取Prometheus格式指标（便捷函数）"""
    return _metrics_store.get_prometheus_format()


def set_trace_id(trace_id: str):
    """设置当前线程的trace_id"""
    _thread_local.trace_id = trace_id


def get_trace_id() -> str:
    """获取当前线程的trace_id"""
    return getattr(_thread_local, 'trace_id', "")


def generate_trace_id() -> str:
    """生成唯一的trace_id"""
    import uuid
    return str(uuid.uuid4())[:16]


def get_daily_stats(days: int = 7) -> List[Dict[str, Any]]:
    """获取最近N天的每日统计数据（便捷函数）"""
    return _metrics_store.get_daily_stats(days)


def get_api_usage_log(limit: int = 100, endpoint: str = None) -> List[Dict[str, Any]]:
    """获取API使用日志（便捷函数）"""
    return _metrics_store.get_api_usage_log(limit, endpoint)


def get_api_usage_summary(start_date: str = None, end_date: str = None) -> Dict[str, Any]:
    """获取API使用汇总统计（便捷函数）"""
    return _metrics_store.get_api_usage_summary(start_date, end_date)
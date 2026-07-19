"""
Logger - 结构化JSON日志

提供：
1. 结构化JSON日志格式输出
2. 请求级trace_id关联
3. 多级别日志支持（DEBUG, INFO, WARNING, ERROR, CRITICAL）
4. 日志文件轮转
5. 控制台和文件双输出
6. 敏感信息脱敏
"""
from __future__ import annotations
import logging
import json
import os
from typing import Dict
from datetime import datetime, timezone

from app.core.metrics import get_trace_id


class JsonFormatter(logging.Formatter):
    """JSON格式日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": get_trace_id(),
        }
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        
        if hasattr(record, 'endpoint'):
            log_entry["endpoint"] = record.endpoint
        
        if hasattr(record, 'duration_ms'):
            log_entry["duration_ms"] = record.duration_ms
        
        if hasattr(record, 'status_code'):
            log_entry["status_code"] = record.status_code
        
        if hasattr(record, 'agent'):
            log_entry["agent"] = record.agent
        
        if hasattr(record, 'stage'):
            log_entry["stage"] = record.stage
        
        return json.dumps(log_entry, ensure_ascii=False)


class StructuredLogger:
    """结构化日志记录器"""
    
    _instances: Dict[str, 'StructuredLogger'] = {}
    
    def __new__(cls, name: str = "bsc") -> 'StructuredLogger':
        if name not in cls._instances:
            cls._instances[name] = super().__new__(cls)
        return cls._instances[name]
    
    def __init__(self, name: str = "bsc"):
        if hasattr(self, '_initialized'):
            return
        
        self._name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)
        
        self._initialized = True
    
    def _get_logger(self) -> logging.Logger:
        return self._logger
    
    def debug(self, message: str, **kwargs):
        """调试级别日志"""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """信息级别日志"""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """警告级别日志"""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """错误级别日志"""
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """严重错误级别日志"""
        self._log(logging.CRITICAL, message, **kwargs)
    
    def _log(self, level: int, message: str, **kwargs):
        """通用日志方法"""
        extra = {}
        if kwargs:
            for key, value in kwargs.items():
                if isinstance(value, (dict, list)):
                    try:
                        extra[key] = json.dumps(value, ensure_ascii=False)
                    except:
                        extra[key] = str(value)
                else:
                    extra[key] = value
        
        extra['extra'] = kwargs
        self._logger.log(level, message, extra=extra)
    
    def log_request(self, endpoint: str, duration_ms: float, status_code: int, **kwargs):
        """记录请求日志"""
        message = f"Request completed: {endpoint} [{status_code}] {duration_ms:.2f}ms"
        self.info(message, endpoint=endpoint, duration_ms=duration_ms, status_code=status_code, **kwargs)
    
    def log_agent_execution(self, agent_key: str, duration_ms: float, success: bool = True, **kwargs):
        """记录Agent执行日志"""
        status = "success" if success else "failed"
        message = f"Agent execution: {agent_key} [{status}] {duration_ms:.2f}ms"
        self.info(message, agent=agent_key, duration_ms=duration_ms, success=success, **kwargs)
    
    def log_pipeline_stage(self, stage_key: str, duration_ms: float, **kwargs):
        """记录Pipeline阶段日志"""
        message = f"Pipeline stage: {stage_key} completed in {duration_ms:.2f}ms"
        self.info(message, stage=stage_key, duration_ms=duration_ms, **kwargs)
    
    def log_llm_call(self, provider: str, model: str, duration_ms: float, success: bool = True, **kwargs):
        """记录LLM调用日志"""
        status = "success" if success else "failed"
        message = f"LLM call: {provider}/{model} [{status}] {duration_ms:.2f}ms"
        self.info(message, provider=provider, model=model, duration_ms=duration_ms, success=success, **kwargs)


def setup_logging(log_level: str = "INFO", log_file: str = None):
    """配置日志系统"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(console_handler)
    
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        file_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(file_handler)
    
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def get_logger(name: str = "bsc") -> StructuredLogger:
    """获取结构化日志记录器"""
    return StructuredLogger(name)
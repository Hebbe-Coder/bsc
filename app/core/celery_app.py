"""
Celery App - 异步任务队列

提供基于Celery的异步任务处理能力，支持：
1. BSC Pipeline编译任务（长耗时任务）
2. 文档解析任务（OCR扫描件识别）
3. 导出任务（多格式文档生成）
4. 任务状态跟踪（通过数据库存储）

配置方式：
- CELERY_ENABLED: 是否启用Celery（默认False，使用同步模式）
- CELERY_BROKER_URL: Redis连接地址（默认redis://localhost:6379/0）
- CELERY_RESULT_BACKEND: 结果存储（默认redis://localhost:6379/1）
- CELERY_TASK_TIMEOUT: 任务超时时间（秒）

当CELERY_ENABLED=False时，自动回退到同步执行模式，无需Redis依赖。
"""
import os
import sys
import logging
from typing import Optional, Callable, Any, Dict
import uuid

logger = logging.getLogger(__name__)


class SyncTaskResult:
    """同步任务结果模拟类，兼容Celery AsyncResult接口"""
    
    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"
    
    def __init__(self, task_id: str, result: Any = None, error: Exception = None):
        self.id = task_id
        self._result = result
        self._error = error
        if error:
            self.status = self.FAILURE
        elif result is not None:
            self.status = self.SUCCESS
        else:
            self.status = self.PENDING
    
    def successful(self) -> bool:
        return self.status == self.SUCCESS
    
    def failed(self) -> bool:
        return self.status == self.FAILURE
    
    @property
    def result(self) -> Any:
        return self._result
    
    @property
    def info(self) -> Any:
        return str(self._error) if self._error else self._result
    
    @property
    def date_done(self):
        import datetime
        return datetime.datetime.now()


class SyncCelery:
    """同步Celery模拟类，当Celery不可用时自动回退"""
    
    def __init__(self):
        self._tasks = {}
        logger.info("SyncCelery initialized (no external dependencies)")
    
    def task(self, bind=False, name=None):
        """装饰器：注册任务"""
        def decorator(func):
            task_name = name or func.__name__
            
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            wrapper.apply_async = self._create_apply_async(func, task_name)
            wrapper.delay = self._create_delay(func)
            wrapper.name = task_name
            self._tasks[task_name] = func
            return wrapper
        return decorator
    
    def _create_apply_async(self, func: Callable, task_name: str):
        """创建apply_async方法（同步执行）"""
        def apply_async(args=None, kwargs=None):
            task_id = str(uuid.uuid4())
            logger.info(f"Starting sync task: {task_name}, id: {task_id}")
            
            try:
                args = args or ()
                kwargs = kwargs or {}
                result = func(*args, **kwargs)
                logger.info(f"Sync task completed: {task_name}, id: {task_id}")
                return SyncTaskResult(task_id, result=result)
            except Exception as e:
                logger.error(f"Sync task failed: {task_name}, id: {task_id}, error: {e}")
                return SyncTaskResult(task_id, error=e)
        return apply_async
    
    def _create_delay(self, func: Callable):
        """创建delay方法（同步执行）"""
        def delay(*args, **kwargs):
            return func.apply_async(args=args, kwargs=kwargs)
        return delay
    
    def send_task(self, task_name: str, args=None, kwargs=None):
        """发送任务（同步执行）"""
        args = args or ()
        kwargs = kwargs or {}
        
        if task_name not in self._tasks:
            raise ValueError(f"Task {task_name} not found")
        
        task_func = self._tasks[task_name]
        task_id = str(uuid.uuid4())
        logger.info(f"Starting sync task via send_task: {task_name}, id: {task_id}")
        
        try:
            result = task_func(*args, **kwargs)
            logger.info(f"Sync task completed: {task_name}, id: {task_id}")
            return SyncTaskResult(task_id, result=result)
        except Exception as e:
            logger.error(f"Sync task failed: {task_name}, id: {task_id}, error: {e}")
            return SyncTaskResult(task_id, error=e)
    
    def AsyncResult(self, task_id: str) -> SyncTaskResult:
        """获取任务结果（同步模式下返回None，因为任务已立即执行）"""
        logger.warning(f"AsyncResult called in sync mode for task: {task_id}")
        return SyncTaskResult(task_id)
    
    def autodiscover_tasks(self, modules):
        """发现任务（同步模式下忽略）"""
        logger.info(f"autodiscover_tasks skipped in sync mode: {modules}")
    
    def conf(self):
        """配置对象"""
        return type('Conf', (), {'update': lambda self, d: None})()
    
    @property
    def control(self):
        """控制对象"""
        return type('Control', (), {
            'revoke': lambda self, task_id, terminate=False: None,
            'inspect': lambda self: None,
        })()


def _init_celery():
    """初始化Celery应用"""
    from app.core.config import settings
    
    if not getattr(settings, "CELERY_ENABLED", False):
        logger.info("Celery disabled by configuration, using sync mode")
        return SyncCelery()
    
    try:
        from celery import Celery
        
        celery_app = Celery(
            "bsc_tasks",
            broker=getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0"),
            backend=getattr(settings, "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
        )

        celery_app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="Asia/Shanghai",
            enable_utc=True,
            task_track_started=True,
            task_time_limit=getattr(settings, "CELERY_TASK_TIMEOUT", 3600),
            task_soft_time_limit=getattr(settings, "CELERY_TASK_SOFT_TIMEOUT", 3000),
            worker_prefetch_multiplier=1,
            worker_max_tasks_per_child=1000,
        )

        celery_app.autodiscover_tasks([
            "app.tasks.bsc_tasks",
            "app.tasks.document_tasks",
            "app.tasks.export_tasks",
        ])

        logger.info("Celery initialized successfully")
        return celery_app
    except ImportError:
        logger.warning("Celery not installed, falling back to sync mode")
        return SyncCelery()
    except Exception as e:
        logger.error(f"Celery initialization failed: {e}, falling back to sync mode")
        return SyncCelery()


_celery_app: Optional[object] = None


def get_celery_app():
    """获取Celery应用实例"""
    global _celery_app
    if _celery_app is None:
        _celery_app = _init_celery()
    return _celery_app


def is_celery_available():
    """检查Celery是否可用（同步模式也视为可用）"""
    app = get_celery_app()
    return app is not None


def is_celery_real():
    """检查是否为真正的Celery（非同步模拟）"""
    app = get_celery_app()
    return not isinstance(app, SyncCelery)

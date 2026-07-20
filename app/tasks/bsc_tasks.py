"""
BSC Tasks - BSC Pipeline编译任务

包含执行BSC编译流程的任务定义。
支持同步模式（CELERY_ENABLED=False）和异步模式（CELERY_ENABLED=True）。
"""
import logging
from app.core.celery_app import get_celery_app

celery_app = get_celery_app()
logger = logging.getLogger(__name__)


def _compile_sync(prd_content: str, template_id: str = None):
    """同步执行BSC编译"""
    from app.capabilities.runner import run_legacy_bsc_runtime_sync
    
    logger.info("Starting BSC compile task")
    
    try:
        result = run_legacy_bsc_runtime_sync(
            input_text=prd_content,
            template_id=template_id,
            async_mode=False,
        )
        logger.info("BSC compile task completed")
        return result
    except Exception as e:
        logger.error(f"BSC compile task failed: {e}")
        raise


def _compile_async_sync(prd_content: str, template_id: str = None):
    """同步执行异步BSC编译（内部使用asyncio）"""
    from app.capabilities.runner import run_legacy_bsc_runtime_sync
    
    logger.info("Starting async BSC compile task")
    
    try:
        result = run_legacy_bsc_runtime_sync(
            input_text=prd_content,
            template_id=template_id,
            async_mode=True,
        )
        logger.info("Async BSC compile task completed")
        return result
    except Exception as e:
        logger.error(f"Async BSC compile task failed: {e}")
        raise


if celery_app:
    @celery_app.task(bind=True, name="bsc.compile")
    def compile_task(self, prd_content: str, template_id: str = None):
        """
        BSC编译任务
        
        Args:
            prd_content: PRD文本内容
            template_id: 模板ID（可选）
        
        Returns:
            dict: 编译结果
        """
        return _compile_sync(prd_content, template_id)


    @celery_app.task(bind=True, name="bsc.compile_async")
    def compile_async_task(self, prd_content: str, template_id: str = None):
        """
        异步BSC编译任务（使用异步Pipeline）
        
        Args:
            prd_content: PRD文本内容
            template_id: 模板ID（可选）
        
        Returns:
            dict: 编译结果
        """
        return _compile_async_sync(prd_content, template_id)
else:
    def compile_task(prd_content: str, template_id: str = None):
        return _compile_sync(prd_content, template_id)
    
    def compile_async_task(prd_content: str, template_id: str = None):
        return _compile_async_sync(prd_content, template_id)

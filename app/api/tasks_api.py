"""Tasks API - 异步任务管理接口

支持两种模式：
1. Celery模式（CELERY_ENABLED=True）：真正的异步任务队列
2. 同步模式（CELERY_ENABLED=False）：任务立即执行，无需Redis依赖
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


class CompileTaskRequest(BaseModel):
    """编译任务请求"""
    input: str = Field(..., description="PRD文本内容", min_length=10)
    template_id: Optional[str] = Field(None, description="模板ID")


class ExportTaskRequest(BaseModel):
    """导出任务请求"""
    business_system: Dict[str, Any] = Field(..., description="业务系统数据")
    export_type: str = Field("word", description="导出类型: word, pdf, markdown")


class ParseTaskRequest(BaseModel):
    """文档解析任务请求"""
    file_content: str = Field(..., description="Base64编码的文件内容")
    filename: str = Field(..., description="文件名")


def _handle_task_result(task_result):
    """统一处理任务结果（兼容Celery和同步模式）"""
    status_map = {
        "PENDING": "pending",
        "STARTED": "running",
        "SUCCESS": "completed",
        "FAILURE": "failed",
        "RETRY": "retrying",
    }
    
    result = {
        "success": True,
        "task_id": task_result.id,
        "status": status_map.get(task_result.status, task_result.status.lower()),
        "state": task_result.status,
    }
    
    if task_result.successful():
        result["result"] = task_result.result
        result["completed_at"] = str(task_result.date_done) if task_result.date_done else None
    elif task_result.failed():
        result["error"] = str(task_result.info) if task_result.info else "任务执行失败"
    
    return result


@router.post("/compile", summary="提交编译任务")
async def submit_compile_task(req: CompileTaskRequest):
    """提交BSC编译任务
    
    根据配置自动选择异步（Celery）或同步执行模式。
    """
    from app.core.celery_app import is_celery_real
    
    try:
        from app.tasks.bsc_tasks import compile_async_task
        
        task = compile_async_task.apply_async(
            kwargs={"prd_content": req.input, "template_id": req.template_id}
        )
        
        result = _handle_task_result(task)
        
        if not is_celery_real():
            result["mode"] = "sync"
            result["message"] = "编译任务已同步完成"
        else:
            result["mode"] = "async"
            result["message"] = "编译任务已提交"
        
        return result
    except Exception as e:
        logger.error(f"Failed to submit compile task: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.post("/export", summary="提交导出任务")
async def submit_export_task(req: ExportTaskRequest):
    """提交导出任务
    
    根据配置自动选择异步（Celery）或同步执行模式。
    """
    from app.core.celery_app import get_celery_app, is_celery_real
    
    task_map = {
        "word": "export.word",
        "pdf": "export.pdf",
        "markdown": "export.markdown",
    }
    
    if req.export_type not in task_map:
        raise HTTPException(status_code=400, detail={"success": False, "error": f"不支持的导出类型: {req.export_type}"})
    
    celery_app = get_celery_app()
    
    try:
        task = celery_app.send_task(
            task_map[req.export_type],
            kwargs={"business_system": req.business_system},
        )
        
        result = _handle_task_result(task)
        
        if not is_celery_real():
            result["mode"] = "sync"
            result["message"] = f"{req.export_type}导出任务已同步完成"
        else:
            result["mode"] = "async"
            result["message"] = f"{req.export_type}导出任务已提交"
        
        return result
    except Exception as e:
        logger.error(f"Failed to submit export task: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.post("/parse", summary="提交文档解析任务")
async def submit_parse_task(req: ParseTaskRequest):
    """提交文档解析任务
    
    根据配置自动选择异步（Celery）或同步执行模式。
    """
    from app.core.celery_app import is_celery_real
    
    try:
        from app.tasks.document_tasks import parse_document_task
        
        task = parse_document_task.apply_async(
            kwargs={"file_content": req.file_content, "filename": req.filename}
        )
        
        result = _handle_task_result(task)
        
        if not is_celery_real():
            result["mode"] = "sync"
            result["message"] = f"文档解析任务已同步完成: {req.filename}"
        else:
            result["mode"] = "async"
            result["message"] = f"文档解析任务已提交: {req.filename}"
        
        return result
    except Exception as e:
        logger.error(f"Failed to submit parse task: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.get("/{task_id}", summary="查询任务状态")
async def get_task_status(task_id: str):
    """查询任务状态和结果"""
    from app.core.celery_app import get_celery_app, is_celery_real
    
    celery_app = get_celery_app()
    
    if not is_celery_real():
        return {
            "success": True,
            "task_id": task_id,
            "status": "completed",
            "state": "SUCCESS",
            "mode": "sync",
            "message": "同步模式下任务已立即执行，请查看原始请求的返回结果",
        }
    
    try:
        task_result = celery_app.AsyncResult(task_id)
        return _handle_task_result(task_result)
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.delete("/{task_id}", summary="取消任务")
async def revoke_task(task_id: str):
    """取消正在执行的任务"""
    from app.core.celery_app import get_celery_app, is_celery_real
    
    celery_app = get_celery_app()
    
    if not is_celery_real():
        return {
            "success": True,
            "task_id": task_id,
            "mode": "sync",
            "message": "同步模式下任务已立即执行，无需取消",
        }
    
    try:
        celery_app.control.revoke(task_id, terminate=True)
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "任务已取消",
        }
    except Exception as e:
        logger.error(f"Failed to revoke task: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})


@router.get("/", summary="获取任务列表")
async def list_tasks(status: Optional[str] = None):
    """获取任务列表（需要真实Celery和Redis结果后端）"""
    from app.core.celery_app import get_celery_app, is_celery_real
    
    celery_app = get_celery_app()
    
    if not is_celery_real():
        return {
            "success": True,
            "mode": "sync",
            "data": [],
            "count": 0,
            "message": "同步模式下不支持任务列表查询",
        }
    
    try:
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active() or {}
        
        tasks = []
        for worker, worker_tasks in active_tasks.items():
            for task in worker_tasks:
                if status and task.get("state") != status.upper():
                    continue
                tasks.append({
                    "task_id": task.get("id"),
                    "name": task.get("name"),
                    "state": task.get("state"),
                    "worker": worker,
                    "args": task.get("args"),
                    "kwargs": task.get("kwargs"),
                    "started_at": task.get("started"),
                })
        
        return {
            "success": True,
            "data": tasks,
            "count": len(tasks),
        }
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})

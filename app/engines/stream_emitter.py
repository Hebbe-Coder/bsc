"""
Stream Emitter - SSE事件发射器

提供流式事件发布能力，支持：
1. 实时进度推送（stage_start, stage_progress, stage_complete）
2. 错误事件推送（error_event）
3. 管道完成推送（pipeline_complete）
4. 使用asyncio.Queue实现背压安全
5. 支持多客户端并发连接

事件格式：
```json
{
  "event_id": "xxx",
  "event_type": "stage_progress",
  "data": {
    "stage": "business_understanding",
    "display": "业务理解",
    "progress": 30,
    "status": "running",
    "message": "正在分析PRD文档..."
  },
  "timestamp": 1234567890.123
}
```
"""
import asyncio
import json
import uuid
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class StreamEmitter:
    """SSE事件发射器"""
    
    def __init__(self):
        self._streams: Dict[str, asyncio.Queue] = {}
        self._stream_metadata: Dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._max_queue_size = 100
        logger.info("StreamEmitter initialized")
    
    async def create_stream(self, stream_id: Optional[str] = None) -> str:
        """创建新的事件流"""
        if stream_id is None:
            stream_id = str(uuid.uuid4())
        
        async with self._lock:
            if stream_id in self._streams:
                logger.warning(f"Stream already exists: {stream_id}")
                return stream_id
            
            self._streams[stream_id] = asyncio.Queue(maxsize=self._max_queue_size)
            self._stream_metadata[stream_id] = {
                "created_at": asyncio.get_event_loop().time(),
                "event_count": 0,
                "is_active": True,
            }
        
        logger.info(f"Created stream: {stream_id}")
        return stream_id
    
    async def emit(self, stream_id: str, event_type: str, data: Dict[str, Any]):
        """发布事件到指定流"""
        async with self._lock:
            if stream_id not in self._streams:
                logger.warning(f"Stream not found: {stream_id}")
                return False
            
            queue = self._streams[stream_id]
        
        event = {
            "event_id": f"{event_type}:{int(asyncio.get_event_loop().time() * 1000)}",
            "event_type": event_type,
            "data": data,
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        try:
            await asyncio.wait_for(queue.put(event), timeout=5.0)
            
            async with self._lock:
                if stream_id in self._stream_metadata:
                    self._stream_metadata[stream_id]["event_count"] += 1
            
            logger.debug(f"Emitted event: {event_type} to {stream_id}")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Queue full for stream: {stream_id}, dropping event")
            return False
        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
            return False
    
    async def consume(self, stream_id: str) -> Any:
        """消费流中的事件"""
        async with self._lock:
            if stream_id not in self._streams:
                raise ValueError(f"Stream not found: {stream_id}")
            queue = self._streams[stream_id]
        
        event = await queue.get()
        queue.task_done()
        return event
    
    async def close_stream(self, stream_id: str):
        """关闭事件流"""
        async with self._lock:
            if stream_id in self._streams:
                queue = self._streams.pop(stream_id)
                while not queue.empty():
                    try:
                        queue.get_nowait()
                        queue.task_done()
                    except asyncio.QueueEmpty:
                        break
                
                if stream_id in self._stream_metadata:
                    self._stream_metadata.pop(stream_id)
                
                logger.info(f"Closed stream: {stream_id}")
    
    async def stage_start(self, stream_id: str, stage: str, display: str, total_stages: int = 6):
        """发布阶段开始事件"""
        await self.emit(stream_id, "stage_start", {
            "stage": stage,
            "display": display,
            "total_stages": total_stages,
            "status": "running",
            "message": f"开始执行: {display}",
        })
    
    async def stage_progress(self, stream_id: str, stage: str, display: str, 
                            progress: int, message: str = ""):
        """发布阶段进度事件"""
        await self.emit(stream_id, "stage_progress", {
            "stage": stage,
            "display": display,
            "progress": progress,
            "status": "running",
            "message": message,
        })
    
    async def stage_complete(self, stream_id: str, stage: str, display: str, 
                             duration_ms: int, success: bool = True, error: str = ""):
        """发布阶段完成事件"""
        await self.emit(stream_id, "stage_complete", {
            "stage": stage,
            "display": display,
            "duration_ms": duration_ms,
            "success": success,
            "status": "success" if success else "failed",
            "error": error,
            "message": f"{display} {'完成' if success else '失败'}",
        })
    
    async def error_event(self, stream_id: str, stage: str, error: str):
        """发布错误事件"""
        await self.emit(stream_id, "error_event", {
            "stage": stage,
            "error": error,
            "status": "error",
            "message": f"错误: {error}",
        })
    
    async def pipeline_complete(self, stream_id: str, total_ms: int, 
                                success: bool = True, summary: str = ""):
        """发布管道完成事件"""
        await self.emit(stream_id, "pipeline_complete", {
            "total_ms": total_ms,
            "success": success,
            "status": "completed" if success else "failed",
            "summary": summary,
            "message": f"管道执行{'成功' if success else '失败'}",
        })
    
    async def agent_status(self, stream_id: str, agent_name: str, status: str, 
                           message: str = "", elapsed_ms: int = 0):
        """发布Agent状态事件"""
        await self.emit(stream_id, "agent_status", {
            "agent_name": agent_name,
            "status": status,
            "message": message,
            "elapsed_ms": elapsed_ms,
        })
    
    def get_stream_info(self, stream_id: str) -> Optional[dict]:
        """获取流信息"""
        return self._stream_metadata.get(stream_id)
    
    def get_active_streams(self) -> list:
        """获取所有活跃流"""
        return list(self._streams.keys())


_stream_emitter: Optional[StreamEmitter] = None


def get_stream_emitter() -> StreamEmitter:
    """获取事件发射器实例"""
    global _stream_emitter
    if _stream_emitter is None:
        _stream_emitter = StreamEmitter()
    return _stream_emitter


def sse_format(event: Dict[str, Any]) -> str:
    """将事件格式化为SSE格式"""
    event_type = event.get("event_type", "message")
    event_data = json.dumps(event, ensure_ascii=False)
    
    lines = []
    lines.append(f"event: {event_type}")
    lines.append(f"data: {event_data}")
    lines.append("")
    
    return "\n".join(lines)

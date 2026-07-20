"""Stream API - SSE流式进度接口"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
import logging
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


class StreamCompileRequest(BaseModel):
    """流式编译请求"""
    input: str = Field(..., description="PRD文本内容", min_length=10)
    template_id: Optional[str] = Field(None, description="模板ID")


class StreamChatRequest(BaseModel):
    """流式聊天请求"""
    system_prompt: str = Field(..., description="系统提示词")
    user_prompt: str = Field(..., description="用户输入", min_length=1)
    temperature: Optional[float] = Field(None, description="温度参数", ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, description="最大输出长度", ge=10, le=10000)


class StreamPRDRequest(BaseModel):
    """流式PRD生成请求"""
    input_text: str = Field(..., description="用户输入文本", min_length=1)
    industry: Optional[str] = Field("general", description="行业类型")


class StreamQuestionRequest(BaseModel):
    """流式问题生成请求"""
    input_text: str = Field(..., description="用户输入文本", min_length=1)
    collected_data: Optional[str] = Field("{}", description="已收集信息JSON")
    current_question_type: Optional[str] = Field("业务目标", description="当前问题类型")


async def _stream_pipeline_events(stream_id: str):
    """生成SSE事件流"""
    from app.engines.stream_emitter import get_stream_emitter, sse_format
    
    emitter = get_stream_emitter()
    
    try:
        while True:
            event = await emitter.consume(stream_id)
            yield sse_format(event)
            
            if event.get("event_type") == "pipeline_complete":
                await asyncio.sleep(1)
                break
    except asyncio.CancelledError:
        logger.info(f"Stream client disconnected: {stream_id}")
        await emitter.close_stream(stream_id)
    except Exception as e:
        logger.error(f"Stream error: {e}")
        await emitter.close_stream(stream_id)


@router.post("/compile", summary="流式编译PRD")
async def stream_compile(req: StreamCompileRequest):
    """
    流式编译PRD文档，实时返回进度事件
    
    事件类型：
    - stage_start: 阶段开始
    - stage_progress: 阶段进度
    - stage_complete: 阶段完成
    - agent_status: Agent状态
    - error_event: 错误事件
    - pipeline_complete: 管道完成
    """
    from app.engines.stream_emitter import get_stream_emitter
    
    emitter = get_stream_emitter()
    stream_id = await emitter.create_stream()
    
    async def run_pipeline():
        try:
            from app.capabilities.runner import run_legacy_bsc_runtime
            result = await run_legacy_bsc_runtime(
                input_text=req.input,
                template_id=req.template_id,
                async_mode=True,
                legacy_context={"stream_id": stream_id},
            )
            
            total_ms = result.get("total_ms", 0)
            summary = result.get("summary", "")
            await emitter.pipeline_complete(stream_id, total_ms, success=True, summary=summary)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            await emitter.error_event(stream_id, "pipeline", str(e))
            await emitter.pipeline_complete(stream_id, 0, success=False, summary=str(e))
        finally:
            await asyncio.sleep(2)
            await emitter.close_stream(stream_id)
    
    asyncio.create_task(run_pipeline())
    
    return StreamingResponse(
        _stream_pipeline_events(stream_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{stream_id}", summary="查询流状态")
async def get_stream_status(stream_id: str):
    """查询指定流的状态信息"""
    from app.engines.stream_emitter import get_stream_emitter
    
    emitter = get_stream_emitter()
    info = emitter.get_stream_info(stream_id)
    
    if not info:
        raise HTTPException(status_code=404, detail={"success": False, "error": "流不存在"})
    
    return {
        "success": True,
        "stream_id": stream_id,
        "info": info,
    }


@router.get("/", summary="获取活跃流列表")
async def list_streams():
    """获取所有活跃的事件流"""
    from app.engines.stream_emitter import get_stream_emitter
    
    emitter = get_stream_emitter()
    streams = emitter.get_active_streams()
    
    return {
        "success": True,
        "streams": streams,
        "count": len(streams),
    }


@router.delete("/{stream_id}", summary="关闭流")
async def close_stream(stream_id: str):
    """关闭指定的事件流"""
    from app.engines.stream_emitter import get_stream_emitter
    
    emitter = get_stream_emitter()
    await emitter.close_stream(stream_id)
    
    return {
        "success": True,
        "stream_id": stream_id,
        "message": "流已关闭",
    }


@router.post("/chat", summary="流式聊天接口")
async def stream_chat(req: StreamChatRequest):
    """
    流式聊天接口，返回SSE事件流
    
    事件格式:
    data: {"type": "token", "data": "内容"}
    
    结束事件:
    data: {"type": "end", "data": ""}
    """
    from app.services.async_llm_service import get_async_llm_service
    
    async def event_generator():
        try:
            async for token in get_async_llm_service().async_stream_chat(
                system_prompt=req.system_prompt,
                user_prompt=req.user_prompt,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            ):
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"
            yield f"data: {json.dumps({'type': 'end', 'data': ''})}\n\n"
        except Exception as e:
            logger.error(f"Stream chat error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/prd", summary="流式PRD生成接口")
async def stream_prd(req: StreamPRDRequest):
    """
    流式PRD文档生成接口，返回SSE事件流
    
    事件格式:
    data: {"type": "token", "data": "内容"}
    
    结束事件:
    data: {"type": "end", "data": ""}
    """
    from app.services.langchain_service import get_langchain_service
    
    async def event_generator():
        try:
            async for token in get_langchain_service().astream_generate_prd(
                input_text=req.input_text,
                industry=req.industry,
                collected_data={},
            ):
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"
            yield f"data: {json.dumps({'type': 'end', 'data': ''})}\n\n"
        except Exception as e:
            logger.error(f"Stream PRD error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/question", summary="流式问题生成接口")
async def stream_question(req: StreamQuestionRequest):
    """
    流式对话问题生成接口，返回SSE事件流
    
    事件格式:
    data: {"type": "token", "data": "内容"}
    
    结束事件:
    data: {"type": "end", "data": ""}
    """
    from app.services.langchain_service import get_langchain_service
    
    async def event_generator():
        try:
            collected_data = json.loads(req.collected_data) if req.collected_data else {}
            
            async for token in get_langchain_service().astream_generate_dialog_question(
                input_text=req.input_text,
                collected_data=collected_data,
                current_question_type=req.current_question_type,
            ):
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"
            yield f"data: {json.dumps({'type': 'end', 'data': ''})}\n\n"
        except Exception as e:
            logger.error(f"Stream question error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

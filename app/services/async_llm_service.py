"""
Async LLM Service - 异步大模型调用层

提供异步API调用支持，使用asyncio.gather()实现并行执行。
支持与同步LLMService无缝切换。
"""
from __future__ import annotations
import asyncio
import json
import time
import logging
import threading
from typing import Dict, Optional, Any, List, Tuple

from app.core.config import settings
from app.services.llm_service import LLMService, AgentType, ProviderType, get_llm_service

logger = logging.getLogger(__name__)


class AsyncLLMService:
    """
    异步LLM服务包装器
    
    提供异步API调用，支持：
    - async_chat(): 异步单轮调用
    - async_batch_chat(): 异步批量调用（并行执行）
    - async_ocr_image(): 异步OCR识别
    
    使用线程池执行同步调用，避免阻塞事件循环。
    """

    def __init__(self, provider: str = None):
        self._provider = provider or settings.LLM_PROVIDER
        self._sync_service: Optional[LLMService] = None
        self._loop = asyncio.get_event_loop()
        self._thread_pool = asyncio.new_event_loop()

    @property
    def sync_service(self) -> LLMService:
        """获取同步服务实例"""
        if self._sync_service is None:
            self._sync_service = LLMService(self._provider)
        return self._sync_service

    async def async_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
    ) -> dict:
        """
        异步调用大模型
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
        
        Returns:
            dict: 大模型返回的结构化JSON
        """
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS

        t0 = time.perf_counter()

        try:
            result = await asyncio.to_thread(
                self.sync_service.chat,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            
            if "_meta" in result:
                result["_meta"]["async"] = True
                result["_meta"]["elapsed_ms"] = elapsed_ms
            
            return result

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"Async chat failed: {e}")
            
            return {
                "error": str(e),
                "_meta": {
                    "mode": "error",
                    "elapsed_ms": elapsed_ms,
                    "async": True,
                },
            }

    async def async_batch_chat(
        self,
        requests: List[Dict[str, Any]],
        max_concurrent: int = 3,
    ) -> List[dict]:
        """
        异步批量调用大模型（并行执行）
        
        Args:
            requests: 请求列表，每个请求包含:
                - system_prompt: 系统提示词
                - user_prompt: 用户输入
                - temperature: 温度（可选）
                - max_tokens: 最大输出长度（可选）
                - task_id: 任务标识（可选，用于结果匹配）
            max_concurrent: 最大并发数（默认3）
        
        Returns:
            List[dict]: 结果列表，顺序与请求一致
        """
        t0 = time.perf_counter()
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_chat(req: Dict[str, Any]) -> dict:
            """带信号量的单轮调用"""
            async with semaphore:
                result = await self.async_chat(
                    system_prompt=req["system_prompt"],
                    user_prompt=req["user_prompt"],
                    temperature=req.get("temperature"),
                    max_tokens=req.get("max_tokens"),
                )
                if "task_id" in req:
                    result["task_id"] = req["task_id"]
                return result

        tasks = [bounded_chat(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            f"Batch chat completed: {len(requests)} requests, "
            f"{elapsed_ms}ms total, "
            f"max_concurrent={max_concurrent}"
        )

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "error": str(result),
                    "task_id": requests[i].get("task_id"),
                    "_meta": {"mode": "error", "async": True},
                })
            else:
                processed_results.append(result)

        return processed_results

    async def async_ocr_image(
        self,
        image_base64: str,
        image_format: str = "png",
    ) -> dict:
        """
        异步OCR识别
        
        Args:
            image_base64: 图片的base64编码
            image_format: 图片格式
        
        Returns:
            dict: OCR识别结果
        """
        try:
            result = await asyncio.to_thread(
                self.sync_service.ocr_image,
                image_base64=image_base64,
                image_format=image_format,
            )
            if "_meta" in result:
                result["_meta"]["async"] = True
            return result
        except Exception as e:
            logger.error(f"Async OCR failed: {e}")
            return {
                "success": False,
                "text": "",
                "error": str(e),
                "_meta": {"mode": "error", "async": True},
            }

    async def async_stream_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
    ):
        """
        异步流式调用大模型
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            
        Returns:
            异步迭代器，每次返回一个token
        """
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS

        try:
            async for chunk in self.sync_service.async_stream_chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Async stream chat failed: {e}")
            yield f"Error: {str(e)}"

    async def async_stream_chat_with_buffer(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
        buffer_size: int = 100,
    ):
        """
        带缓冲的异步流式调用
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            buffer_size: 缓冲区大小（字符数）
            
        Returns:
            异步迭代器，每次返回一个缓冲区内容
        """
        buffer = []
        buffer_length = 0
        
        async for chunk in self.async_stream_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            buffer.append(chunk)
            buffer_length += len(chunk)
            
            if buffer_length >= buffer_size:
                yield "".join(buffer)
                buffer = []
                buffer_length = 0
        
        if buffer:
            yield "".join(buffer)

    def stream_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
    ):
        """
        同步流式调用大模型
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户输入
            temperature: 温度
            max_tokens: 最大输出长度
            
        Returns:
            迭代器，每次返回一个token
        """
        if temperature is None:
            temperature = settings.LLM_TEMPERATURE
        if max_tokens is None:
            max_tokens = settings.LLM_MAX_TOKENS

        try:
            yield from self.sync_service.stream_chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.error(f"Stream chat failed: {e}")
            yield f"Error: {str(e)}"

    def status(self) -> dict:
        """返回服务状态"""
        return {
            **self.sync_service.status(),
            "async_supported": True,
            "stream_supported": True,
            "loop_running": self._loop.is_running(),
        }


_thread_local_async = threading.local()


def get_thread_local_async_service() -> AsyncLLMService:
    """获取线程本地的异步LLM服务实例"""
    if not hasattr(_thread_local_async, 'async_llm_service'):
        _thread_local_async.async_llm_service = AsyncLLMService()
    return _thread_local_async.async_llm_service


def get_async_llm_service() -> AsyncLLMService:
    """获取异步LLM服务实例"""
    try:
        return get_thread_local_async_service()
    except Exception:
        return AsyncLLMService()


__all__ = [
    "AsyncLLMService",
    "get_async_llm_service",
    "get_thread_local_async_service",
]
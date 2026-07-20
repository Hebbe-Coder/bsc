"""
LLM Adapter Layer - LLM适配器抽象层

支持私有化部署的本地模型：
1. Ollama - 本地轻量模型服务（推荐）
2. vLLM - 高性能推理服务器
3. LocalAI - 本地AI API兼容服务

设计原则：
- 统一接口：所有适配器实现相同的API
- 向后兼容：支持现有云API模式
- 零外部依赖：私有化部署不需要Redis/Celery
- 优雅降级：本地模型不可用时自动回退到Mock

配置方式：
    LLM_PROVIDER=ollama
    OLLAMA_BASE_URL=http://localhost:11434/v1
    OLLAMA_MODEL=qwen2.5:7b
"""
from __future__ import annotations
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from app.core.llm_usage import ModelUsage, extract_model_usage

logger = logging.getLogger(__name__)


class LLMAdapter(ABC):
    """LLM适配器抽象基类"""
    
    def __init__(self):
        self._client = None
    
    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.7, max_tokens: int = 8000,
             response_format: str = "json") -> dict:
        """调用大模型"""
        pass
    
    @abstractmethod
    def is_ready(self) -> bool:
        """检查服务是否就绪"""
        pass
    
    @abstractmethod
    def status(self) -> dict:
        """返回服务状态"""
        pass
    
    @staticmethod
    def _parse_json(raw: str) -> dict:
        """解析JSON响应，处理可能的markdown代码块"""
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}, raw: {raw[:500]}")
            return {"content": raw, "parse_error": str(e)}
    
    def _fallback_result(self, system_prompt: str, user_prompt: str, 
                         elapsed_ms: int, error: str, provider: str, 
                         model: str) -> dict:
        """生成降级结果（当API调用失败时）"""
        from app.core.llm_policy import ensure_fallback_allowed
        from app.services.llm_service import LLMService

        ensure_fallback_allowed("LLM adapter")
        llm = LLMService(provider=provider)
        result = llm._mock(system_prompt, user_prompt)
        result["_meta"] = {
            "provider": provider,
            "model": model,
            "mode": "fallback",
            "elapsed_ms": elapsed_ms,
            "error": error,
            "usage": ModelUsage(provider=provider, model=model).model_dump(mode="json"),
        }
        return result


class OpenAICompatibleAdapter(LLMAdapter):
    """OpenAI兼容API适配器"""
    
    def __init__(self, api_key: str, base_url: str, model: str, timeout: int = 60):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
    
    def _get_client(self):
        """延迟初始化客户端"""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
            except ImportError:
                logger.error("OpenAI SDK not installed")
                raise
        return self._client
    
    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.7, max_tokens: int = 8000,
             response_format: str = "json") -> dict:
        t0 = time.perf_counter()
        try:
            client = self._get_client()
            
            format_param = {"type": "json_object"} if response_format == "json" else None
            
            response = client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=format_param,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            
            raw = response.choices[0].message.content.strip()
            result = self._parse_json(raw)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            
            return {
                **result,
                "_meta": {
                    "provider": "openai-compatible",
                    "model": self.model,
                    "mode": "api",
                    "elapsed_ms": elapsed_ms,
                    "usage": extract_model_usage(
                        response, provider="openai-compatible", model=self.model
                    ).model_dump(mode="json"),
                },
            }
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"OpenAI compatible API call failed: {e}")
            return self._fallback_result(system_prompt, user_prompt, elapsed_ms, str(e), 
                                         "openai-compatible", self.model)
    
    def is_ready(self) -> bool:
        try:
            client = self._get_client()
            client.models.list()
            return True
        except Exception as e:
            logger.debug(f"OpenAI compatible check failed: {e}")
            return False
    
    def status(self) -> dict:
        return {
            "type": "openai-compatible",
            "base_url": self.base_url,
            "model": self.model,
            "api_key_set": bool(self.api_key),
            "ready": self.is_ready(),
        }


class OllamaAdapter(LLMAdapter):
    """Ollama本地模型适配器"""
    
    def __init__(self, base_url: str = "http://localhost:11434/v1", model: str = "qwen2.5:7b", timeout: int = 120):
        super().__init__()
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key="ollama", base_url=self.base_url, timeout=self.timeout)
            except ImportError:
                logger.error("OpenAI SDK not installed")
                raise
        return self._client
    
    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.7, max_tokens: int = 8000,
             response_format: str = "json") -> dict:
        t0 = time.perf_counter()
        try:
            client = self._get_client()
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            if response_format == "json":
                system_prompt_with_format = f"{system_prompt}\n\n输出格式要求：请以纯JSON格式输出，不要包含markdown代码块或其他文本。"
                messages[0]["content"] = system_prompt_with_format
            
            response = client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=messages,
            )
            
            raw = response.choices[0].message.content.strip()
            result = self._parse_json(raw)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            
            return {
                **result,
                "_meta": {
                    "provider": "ollama",
                    "model": self.model,
                    "mode": "local",
                    "elapsed_ms": elapsed_ms,
                    "usage": extract_model_usage(
                        response, provider="ollama", model=self.model
                    ).model_dump(mode="json"),
                },
            }
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"Ollama API call failed: {e}")
            return self._fallback_result(system_prompt, user_prompt, elapsed_ms, str(e), 
                                         "ollama", self.model)
    
    def is_ready(self) -> bool:
        try:
            client = self._get_client()
            models = client.models.list()
            model_names = [m.id for m in models.data]
            return self.model in model_names or any(self.model.split(":")[0] in m for m in model_names)
        except Exception as e:
            logger.debug(f"Ollama check failed: {e}")
            return False
    
    def status(self) -> dict:
        return {
            "type": "ollama",
            "base_url": self.base_url,
            "model": self.model,
            "ready": self.is_ready(),
        }


class vLLMAdapter(LLMAdapter):
    """vLLM高性能推理适配器"""
    
    def __init__(self, base_url: str = "http://localhost:8000/v1", model: str = "", timeout: int = 120):
        super().__init__()
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key="vllm", base_url=self.base_url, timeout=self.timeout)
            except ImportError:
                logger.error("OpenAI SDK not installed")
                raise
        return self._client
    
    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.7, max_tokens: int = 8000,
             response_format: str = "json") -> dict:
        t0 = time.perf_counter()
        try:
            client = self._get_client()
            
            format_param = {"type": "json_object"} if response_format == "json" else None
            
            response = client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=format_param,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            
            raw = response.choices[0].message.content.strip()
            result = self._parse_json(raw)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            
            return {
                **result,
                "_meta": {
                    "provider": "vllm",
                    "model": self.model,
                    "mode": "local",
                    "elapsed_ms": elapsed_ms,
                    "usage": extract_model_usage(
                        response, provider="vllm", model=self.model
                    ).model_dump(mode="json"),
                },
            }
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"vLLM API call failed: {e}")
            return self._fallback_result(system_prompt, user_prompt, elapsed_ms, str(e), 
                                         "vllm", self.model)
    
    def is_ready(self) -> bool:
        try:
            client = self._get_client()
            client.models.list()
            return True
        except Exception as e:
            logger.debug(f"vLLM check failed: {e}")
            return False
    
    def status(self) -> dict:
        return {
            "type": "vllm",
            "base_url": self.base_url,
            "model": self.model,
            "ready": self.is_ready(),
        }


class LocalAIAdapter(LLMAdapter):
    """LocalAI本地适配器"""
    
    def __init__(self, base_url: str = "http://localhost:8080/v1", model: str = "gpt-4", timeout: int = 120):
        super().__init__()
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key="localai", base_url=self.base_url, timeout=self.timeout)
            except ImportError:
                logger.error("OpenAI SDK not installed")
                raise
        return self._client
    
    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.7, max_tokens: int = 8000,
             response_format: str = "json") -> dict:
        t0 = time.perf_counter()
        try:
            client = self._get_client()
            
            format_param = {"type": "json_object"} if response_format == "json" else None
            
            response = client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=format_param,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            
            raw = response.choices[0].message.content.strip()
            result = self._parse_json(raw)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            
            return {
                **result,
                "_meta": {
                    "provider": "localai",
                    "model": self.model,
                    "mode": "local",
                    "elapsed_ms": elapsed_ms,
                    "usage": extract_model_usage(
                        response, provider="localai", model=self.model
                    ).model_dump(mode="json"),
                },
            }
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(f"LocalAI API call failed: {e}")
            return self._fallback_result(system_prompt, user_prompt, elapsed_ms, str(e), 
                                         "localai", self.model)
    
    def is_ready(self) -> bool:
        try:
            client = self._get_client()
            client.models.list()
            return True
        except Exception as e:
            logger.debug(f"LocalAI check failed: {e}")
            return False
    
    def status(self) -> dict:
        return {
            "type": "localai",
            "base_url": self.base_url,
            "model": self.model,
            "ready": self.is_ready(),
        }


class MockAdapter(LLMAdapter):
    """Mock适配器（用于开发测试）"""
    
    def __init__(self):
        super().__init__()
        from app.services.llm_service import LLMService
        self._llm = LLMService(provider="mock")
    
    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.7, max_tokens: int = 8000,
             response_format: str = "json") -> dict:
        t0 = time.perf_counter()
        result = self._llm._mock(system_prompt, user_prompt)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        
        result["_meta"] = {
            "provider": "mock",
            "model": "mock",
            "mode": "mock",
            "elapsed_ms": elapsed_ms,
            "usage": ModelUsage(provider="mock", model="mock").model_dump(mode="json"),
        }
        return result
    
    def is_ready(self) -> bool:
        return True
    
    def status(self) -> dict:
        return {
            "type": "mock",
            "model": "mock",
            "ready": True,
        }


class LLMAdapterFactory:
    """LLM适配器工厂"""
    
    ADAPTER_MAP = {
        "mock": MockAdapter,
        "ollama": OllamaAdapter,
        "vllm": vLLMAdapter,
        "localai": LocalAIAdapter,
    }
    
    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]) -> LLMAdapter:
        """创建适配器实例"""
        adapter_class = cls.ADAPTER_MAP.get(provider)
        
        if adapter_class:
            try:
                return adapter_class(**config)
            except Exception as e:
                logger.error(f"Failed to create {provider} adapter: {e}")
                return MockAdapter()
        
        if provider in ["deepseek", "doubao", "yuanbao", "qwen"]:
            return OpenAICompatibleAdapter(
                api_key=config.get("api_key", ""),
                base_url=config.get("base_url", ""),
                model=config.get("model", ""),
                timeout=config.get("timeout", 60),
            )
        
        logger.warning(f"Unknown provider: {provider}, fallback to mock")
        return MockAdapter()
    
    @classmethod
    def get_all_adapters(cls) -> List[str]:
        """获取所有支持的适配器类型"""
        return list(cls.ADAPTER_MAP.keys()) + ["deepseek", "doubao", "yuanbao", "qwen"]


__all__ = [
    "LLMAdapter",
    "OpenAICompatibleAdapter",
    "OllamaAdapter",
    "vLLMAdapter",
    "LocalAIAdapter",
    "MockAdapter",
    "LLMAdapterFactory",
]

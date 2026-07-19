"""
LangChain Cache Layer - LCEL缓存层

提供与LangChain Expression Language集成的缓存实现：
1. LangChainCache - 实现RunnableCache接口，集成项目缓存服务
2. CacheBackedChain - 带缓存的链式调用包装器
3. 缓存策略配置 - 支持不同场景的缓存策略

设计原则：
- 统一缓存：复用项目已有的缓存服务（Memory/Redis/MultiLevel）
- 透明集成：通过LCEL的RunnableCache接口无缝集成
- 灵活配置：支持不同TTL和缓存键策略
- 可观测性：记录缓存命中/未命中统计
"""
from __future__ import annotations
import hashlib
import json
import logging
from typing import Any, Optional, Dict, List
from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)


class LangChainCache:
    """基于项目缓存服务的LCEL缓存实现"""
    
    def __init__(self, ttl: int = 3600, key_prefix: str = "lcel"):
        self._ttl = ttl
        self._key_prefix = key_prefix
        self._hits = 0
        self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total) * 100 if total > 0 else 0
        return {
            "type": "lcel",
            "prefix": self._key_prefix,
            "ttl": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate": hit_rate,
        }
    
    def _build_key(self, inputs: Dict[str, Any]) -> str:
        """构建缓存键"""
        try:
            content = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            return f"{self._key_prefix}:{content_hash}"
        except Exception as e:
            logger.warning(f"Failed to build cache key: {e}")
            return f"{self._key_prefix}:hash-fallback"
    
    def lookup(self, inputs: Dict[str, Any]) -> Optional[Any]:
        """从缓存查找结果"""
        try:
            from app.services.cache_service import get_cache_service
            cache = get_cache_service()
            
            if cache is None:
                self._misses += 1
                return None
            
            key = self._build_key(inputs)
            if cache.exists(key):
                result = cache.get(key)
                self._hits += 1
                logger.debug(f"LCEL cache hit: {key}")
                return result
            
            self._misses += 1
            logger.debug(f"LCEL cache miss: {key}")
            return None
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
            self._misses += 1
            return None
    
    def update(self, inputs: Dict[str, Any], output: Any) -> None:
        """更新缓存"""
        try:
            from app.services.cache_service import get_cache_service
            cache = get_cache_service()
            
            if cache is None:
                return
            
            key = self._build_key(inputs)
            cache.set(key, output, self._ttl)
            logger.debug(f"LCEL cache set: {key}")
            
            try:
                from app.core.metrics import record_cache_operation
                record_cache_operation("lcel", hit=False)
            except Exception as e:
                logger.debug(f"Failed to record cache metric: {e}")
        except Exception as e:
            logger.warning(f"Cache update failed: {e}")
    
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total) * 100 if total > 0 else 0
        return {
            "type": "lcel",
            "prefix": self._key_prefix,
            "ttl": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate_pct": f"{hit_rate:.2f}",
        }


class CacheBackedChain:
    """带缓存的链式调用包装器"""
    
    def __init__(self, chain: Runnable, cache: LangChainCache = None):
        self._chain = chain
        self._cache = cache or LangChainCache()
    
    def invoke(self, inputs: Dict[str, Any]) -> Any:
        """带缓存的同步调用"""
        cached = self._cache.lookup(inputs)
        if cached is not None:
            return cached
        
        result = self._chain.invoke(inputs)
        self._cache.update(inputs, result)
        return result
    
    async def ainvoke(self, inputs: Dict[str, Any]) -> Any:
        """带缓存的异步调用"""
        cached = self._cache.lookup(inputs)
        if cached is not None:
            return cached
        
        result = await self._chain.ainvoke(inputs)
        self._cache.update(inputs, result)
        return result
    
    def stream(self, inputs: Dict[str, Any]):
        """流式调用（不使用缓存）"""
        return self._chain.stream(inputs)
    
    async def astream(self, inputs: Dict[str, Any]):
        """异步流式调用（不使用缓存）"""
        async for chunk in self._chain.astream(inputs):
            yield chunk
    
    def batch(self, inputs_list: List[Dict[str, Any]]) -> List[Any]:
        """批量调用（部分使用缓存）"""
        results = []
        for inputs in inputs_list:
            cached = self._cache.lookup(inputs)
            if cached is not None:
                results.append(cached)
            else:
                result = self._chain.invoke(inputs)
                self._cache.update(inputs, result)
                results.append(result)
        return results
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return self._cache.stats()
    
    @property
    def chain(self) -> Runnable:
        """获取底层链"""
        return self._chain


class CachePolicy:
    """缓存策略配置"""
    
    DEFAULT = {"ttl": 3600, "key_prefix": "lcel"}
    SHORT = {"ttl": 600, "key_prefix": "lcel_short"}
    MEDIUM = {"ttl": 1800, "key_prefix": "lcel_medium"}
    LONG = {"ttl": 86400, "key_prefix": "lcel_long"}
    PRD_GENERATION = {"ttl": 7200, "key_prefix": "lcel_prd"}
    QUESTION_GENERATION = {"ttl": 3600, "key_prefix": "lcel_question"}
    CHAT = {"ttl": 300, "key_prefix": "lcel_chat"}
    ANALYSIS = {"ttl": 7200, "key_prefix": "lcel_analysis"}
    
    @classmethod
    def get_policy(cls, policy_name: str) -> Dict[str, Any]:
        """获取指定策略配置"""
        return getattr(cls, policy_name.upper(), cls.DEFAULT)


def with_cache(chain: Runnable, policy: str = "default", ttl: int = None) -> CacheBackedChain:
    """
    为链添加缓存
    
    Args:
        chain: LCEL链
        policy: 缓存策略名称
        ttl: 自定义TTL（覆盖策略默认值）
        
    Returns:
        带缓存的链包装器
    """
    policy_config = CachePolicy.get_policy(policy)
    cache_ttl = ttl if ttl is not None else policy_config["ttl"]
    
    cache = LangChainCache(
        ttl=cache_ttl,
        key_prefix=policy_config["key_prefix"],
    )
    
    return CacheBackedChain(chain, cache)


def get_default_cache() -> LangChainCache:
    """获取默认缓存实例"""
    return LangChainCache()


def get_prd_cache() -> LangChainCache:
    """获取PRD生成专用缓存"""
    config = CachePolicy.PRD_GENERATION
    return LangChainCache(ttl=config["ttl"], key_prefix=config["key_prefix"])


def get_question_cache() -> LangChainCache:
    """获取问题生成专用缓存"""
    config = CachePolicy.QUESTION_GENERATION
    return LangChainCache(ttl=config["ttl"], key_prefix=config["key_prefix"])


def get_chat_cache() -> LangChainCache:
    """获取聊天专用缓存"""
    config = CachePolicy.CHAT
    return LangChainCache(ttl=config["ttl"], key_prefix=config["key_prefix"])


def cache_backed_chain(chain: Runnable, cache: LangChainCache = None) -> CacheBackedChain:
    """缓存链包装器（别名）"""
    return CacheBackedChain(chain, cache)


__all__ = [
    "LangChainCache",
    "CacheBackedChain",
    "CachePolicy",
    "with_cache",
    "cache_backed_chain",
    "get_default_cache",
    "get_prd_cache",
    "get_question_cache",
    "get_chat_cache",
]
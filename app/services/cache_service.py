"""
Cache Service - 多级缓存系统

提供统一的缓存接口，支持：
1. L1本地内存缓存（开发环境，无需额外依赖）
2. L2 Redis缓存（生产环境，高性能分布式缓存）
3. 多级缓存模式（L1+L2）- 缓存一致性保证

缓存策略：
- LLM响应缓存：缓存大模型调用结果，减少重复调用
- 知识检索缓存：缓存知识搜索结果
- 编译结果缓存：缓存已编译的业务系统
- Cache-Aside模式：读取先查L1→L2→源，写入同时更新L1和L2

配置方式：
- CACHE_TYPE: memory | redis | multi (默认memory)
- REDIS_URL: redis://localhost:6379 (Redis连接地址)
- CACHE_TTL: 默认缓存过期时间（秒）
- L1_CACHE_TTL: L1本地缓存过期时间（秒）
- L2_CACHE_TTL: L2分布式缓存过期时间（秒）
"""
from __future__ import annotations
import time
import json
import logging
import hashlib
import threading
from typing import Dict, Optional, Any, Callable, List
from functools import wraps
from datetime import timedelta

logger = logging.getLogger(__name__)


class CacheService:
    """
    统一缓存服务接口
    
    提供get/set/delete/clear等基础操作，以及缓存装饰器。
    """

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存"""
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        """删除缓存"""
        raise NotImplementedError

    def clear(self, pattern: str = None) -> bool:
        """清除缓存"""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        raise NotImplementedError

    def get_or_set(
        self,
        key: str,
        func: Callable[..., Any],
        ttl: int = None,
        *args,
        **kwargs,
    ) -> Any:
        """
        获取缓存或执行函数并缓存结果
        
        Args:
            key: 缓存键
            func: 如果缓存不存在则执行的函数
            ttl: 缓存过期时间（秒）
            *args, **kwargs: 传递给func的参数
        
        Returns:
            缓存值或函数执行结果
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        result = func(*args, **kwargs)
        self.set(key, result, ttl)
        return result

    def stats(self) -> dict:
        """获取缓存统计信息"""
        return {}


class MemoryCache(CacheService):
    """
    内存缓存实现
    
    使用字典存储缓存数据，适合开发环境和小规模应用。
    """

    def __init__(self, default_ttl: int = 3600, max_size: int = 10000):
        self._cache: Dict[str, dict] = {}
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._lock = threading.RLock()
        logger.info(f"MemoryCache initialized with default_ttl={default_ttl}s, max_size={max_size}")

    def _is_expired(self, entry: dict) -> bool:
        """检查缓存是否过期"""
        if entry["expire_at"] is None:
            return False
        return time.time() > entry["expire_at"]

    def _evict_oldest(self):
        """驱逐最旧的缓存"""
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]["created_at"])
            del self._cache[oldest_key]

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if self._is_expired(entry):
                del self._cache[key]
                return None
            entry["access_at"] = time.time()
            return entry["value"]

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存"""
        with self._lock:
            if ttl is None:
                ttl = self._default_ttl

            self._evict_oldest()
            
            expire_at = time.time() + ttl if ttl > 0 else None
            self._cache[key] = {
                "value": value,
                "expire_at": expire_at,
                "created_at": time.time(),
                "access_at": time.time(),
            }
        return True

    def delete(self, key: str) -> bool:
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
        return False

    def clear(self, pattern: str = None) -> bool:
        """清除缓存"""
        with self._lock:
            if pattern:
                keys_to_remove = [k for k in self._cache.keys() if pattern in k]
                for k in keys_to_remove:
                    del self._cache[k]
            else:
                self._cache.clear()
        return True

    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return False
            if self._is_expired(entry):
                del self._cache[key]
                return False
            return True

    def stats(self) -> dict:
        """获取缓存统计信息"""
        now = time.time()
        valid_count = sum(1 for e in self._cache.values() if not self._is_expired(e))
        expired_count = len(self._cache) - valid_count
        try:
            memory_usage = len(json.dumps(self._cache)) / 1024
        except Exception:
            memory_usage = 0
        return {
            "type": "memory",
            "total_keys": len(self._cache),
            "valid_keys": valid_count,
            "expired_keys": expired_count,
            "memory_usage_kb": f"{memory_usage:.2f}",
            "max_size": self._max_size,
        }


class RedisCache(CacheService):
    """
    Redis缓存实现
    
    使用Redis作为后端存储，适合生产环境和分布式场景。
    """

    def __init__(self, redis_url: str = "redis://localhost:6379", default_ttl: int = 3600):
        self._client = None
        self._memory_cache = None
        self._circuit_breaker_open = False
        self._circuit_breaker_failure_count = 0
        self._circuit_breaker_reset_time = 0
        
        try:
            import redis
            self._client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)
            self._client.ping()
            self._default_ttl = default_ttl
            logger.info(f"RedisCache initialized with url={redis_url}")
        except ImportError:
            logger.warning("redis package not installed, falling back to MemoryCache")
            self._memory_cache = MemoryCache(default_ttl)
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, falling back to MemoryCache")
            self._memory_cache = MemoryCache(default_ttl)

    def _use_memory_fallback(self) -> bool:
        """判断是否使用内存回退"""
        return self._client is None or self._circuit_breaker_open

    def _record_failure(self):
        """记录Redis失败，触发熔断"""
        self._circuit_breaker_failure_count += 1
        if self._circuit_breaker_failure_count >= 5:
            self._circuit_breaker_open = True
            self._circuit_breaker_reset_time = time.time() + 30
            logger.warning("Redis circuit breaker opened, using memory fallback")

    def _check_circuit_breaker(self):
        """检查熔断状态"""
        if self._circuit_breaker_open and time.time() > self._circuit_breaker_reset_time:
            try:
                if self._client:
                    self._client.ping()
                    self._circuit_breaker_open = False
                    self._circuit_breaker_failure_count = 0
                    logger.info("Redis circuit breaker closed")
            except Exception:
                self._circuit_breaker_reset_time = time.time() + 30

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        self._check_circuit_breaker()
        
        if self._use_memory_fallback():
            return self._memory_cache.get(key)

        try:
            value = self._client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            self._record_failure()
            logger.error(f"Redis get failed: {e}")
            if self._memory_cache:
                return self._memory_cache.get(key)
            return None

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存"""
        self._check_circuit_breaker()
        
        if self._use_memory_fallback():
            return self._memory_cache.set(key, value, ttl)

        try:
            if ttl is None:
                ttl = self._default_ttl

            value_json = json.dumps(value, ensure_ascii=False)
            if ttl > 0:
                self._client.set(key, value_json, ex=ttl)
            else:
                self._client.set(key, value_json)
            
            if self._memory_cache:
                self._memory_cache.set(key, value, min(ttl, 60) if ttl else 60)
            
            return True
        except Exception as e:
            self._record_failure()
            logger.error(f"Redis set failed: {e}")
            if self._memory_cache:
                return self._memory_cache.set(key, value, ttl)
            return False

    def delete(self, key: str) -> bool:
        """删除缓存"""
        self._check_circuit_breaker()
        
        if self._use_memory_fallback():
            return self._memory_cache.delete(key)

        try:
            self._client.delete(key)
            
            if self._memory_cache:
                self._memory_cache.delete(key)
            
            return True
        except Exception as e:
            self._record_failure()
            logger.error(f"Redis delete failed: {e}")
            if self._memory_cache:
                return self._memory_cache.delete(key)
            return False

    def clear(self, pattern: str = None) -> bool:
        """清除缓存"""
        self._check_circuit_breaker()
        
        if self._use_memory_fallback():
            return self._memory_cache.clear(pattern)

        try:
            if pattern:
                keys = self._client.keys(f"*{pattern}*")
                if keys:
                    self._client.delete(*keys)
            else:
                self._client.flushdb()
            
            if self._memory_cache:
                self._memory_cache.clear(pattern)
            
            return True
        except Exception as e:
            self._record_failure()
            logger.error(f"Redis clear failed: {e}")
            if self._memory_cache:
                return self._memory_cache.clear(pattern)
            return False

    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        self._check_circuit_breaker()
        
        if self._use_memory_fallback():
            return self._memory_cache.exists(key)

        try:
            return self._client.exists(key) == 1
        except Exception as e:
            self._record_failure()
            logger.error(f"Redis exists failed: {e}")
            if self._memory_cache:
                return self._memory_cache.exists(key)
            return False

    def stats(self) -> dict:
        """获取缓存统计信息"""
        if self._use_memory_fallback():
            return self._memory_cache.stats()

        try:
            info = self._client.info("stats")
            return {
                "type": "redis",
                "total_keys": self._client.dbsize(),
                "used_memory": info.get("used_memory_human", "N/A"),
                "keys_expired": info.get("expired_keys", 0),
                "circuit_breaker_open": self._circuit_breaker_open,
            }
        except Exception as e:
            logger.error(f"Redis stats failed: {e}")
            return {"type": "redis", "error": str(e), "circuit_breaker_open": self._circuit_breaker_open}


class MultiLevelCache(CacheService):
    """
    多级缓存实现（L1+L2）
    
    缓存策略：
    - 读取：L1 → L2 → 数据源
    - 写入：L1 + L2（同步更新）
    - 删除：L1 + L2（同步删除）
    - L1失效：自动回源到L2或数据源
    
    L1（本地内存）特点：
    - 极低延迟（内存访问）
    - 有限容量（LRU淘汰）
    - 较短TTL（防止数据过时）
    
    L2（Redis）特点：
    - 分布式共享（多实例一致）
    - 大容量
    - 较长TTL
    """

    def __init__(self, l1_ttl: int = 60, l2_ttl: int = 3600, 
                 redis_url: str = "redis://localhost:6379", l1_max_size: int = 5000):
        self._l1_cache = MemoryCache(default_ttl=l1_ttl, max_size=l1_max_size)
        self._l2_cache = RedisCache(redis_url=redis_url, default_ttl=l2_ttl)
        self._l1_ttl = l1_ttl
        self._l2_ttl = l2_ttl
        logger.info(f"MultiLevelCache initialized: L1 TTL={l1_ttl}s, L2 TTL={l2_ttl}s")

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存（多级查询）
        
        查询顺序：L1 → L2 → 返回None
        如果L2命中，自动回填L1
        """
        value = self._l1_cache.get(key)
        if value is not None:
            logger.debug(f"Cache hit (L1): {key}")
            return value

        value = self._l2_cache.get(key)
        if value is not None:
            logger.debug(f"Cache hit (L2): {key}")
            self._l1_cache.set(key, value, self._l1_ttl)
            return value

        logger.debug(f"Cache miss: {key}")
        return None

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """
        设置缓存（同步写入L1和L2）
        
        如果未指定TTL，使用各层默认TTL
        """
        l1_ttl = min(ttl, self._l1_ttl) if ttl else self._l1_ttl
        l2_ttl = ttl if ttl else self._l2_ttl
        
        self._l1_cache.set(key, value, l1_ttl)
        self._l2_cache.set(key, value, l2_ttl)
        
        return True

    def delete(self, key: str) -> bool:
        """删除缓存（同步删除L1和L2）"""
        self._l1_cache.delete(key)
        self._l2_cache.delete(key)
        return True

    def clear(self, pattern: str = None) -> bool:
        """清除缓存（同步清除L1和L2）"""
        self._l1_cache.clear(pattern)
        self._l2_cache.clear(pattern)
        return True

    def exists(self, key: str) -> bool:
        """检查缓存是否存在（L1或L2任一存在即可）"""
        if self._l1_cache.exists(key):
            return True
        return self._l2_cache.exists(key)

    def get_or_set(
        self,
        key: str,
        func: Callable[..., Any],
        ttl: int = None,
        *args,
        **kwargs,
    ) -> Any:
        """
        获取缓存或执行函数并缓存结果
        
        使用多级缓存模式
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        
        result = func(*args, **kwargs)
        self.set(key, result, ttl)
        return result

    def stats(self) -> dict:
        """获取缓存统计信息"""
        l1_stats = self._l1_cache.stats()
        l2_stats = self._l2_cache.stats()
        return {
            "type": "multi-level",
            "l1": l1_stats,
            "l2": l2_stats,
        }


def build_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    构建缓存键
    
    Args:
        prefix: 键前缀
        *args: 位置参数（用于生成哈希）
        **kwargs: 关键字参数（用于生成哈希）
    
    Returns:
        完整的缓存键
    """
    data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{content_hash}"


def cached(
    prefix: str = "cache",
    ttl: int = 3600,
    key_builder: Callable = build_cache_key,
):
    """
    缓存装饰器
    
    Args:
        prefix: 键前缀
        ttl: 缓存过期时间（秒）
        key_builder: 键生成函数
    
    Returns:
        装饰后的函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache_service()
            key = key_builder(prefix, *args, **kwargs)
            cached_result = cache.get(key)
            if cached_result is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_result
            result = func(*args, **kwargs)
            cache.set(key, result, ttl)
            logger.debug(f"Cache set: {key}")
            return result
        return wrapper
    return decorator


def cached_async(
    prefix: str = "cache",
    ttl: int = 3600,
    key_builder: Callable = build_cache_key,
):
    """
    异步缓存装饰器
    
    Args:
        prefix: 键前缀
        ttl: 缓存过期时间（秒）
        key_builder: 键生成函数
    
    Returns:
        装饰后的异步函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = get_cache_service()
            key = key_builder(prefix, *args, **kwargs)
            cached_result = cache.get(key)
            if cached_result is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_result
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl)
            logger.debug(f"Cache set: {key}")
            return result
        return wrapper
    return decorator


_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """
    获取缓存服务实例（单例）
    
    根据配置选择MemoryCache、RedisCache或MultiLevelCache。
    """
    global _cache_service
    if _cache_service is None:
        from app.core.config import settings

        cache_type = getattr(settings, "CACHE_TYPE", "memory")
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379")
        cache_ttl = getattr(settings, "CACHE_TTL", 3600)
        l1_cache_ttl = getattr(settings, "L1_CACHE_TTL", 60)
        l2_cache_ttl = getattr(settings, "L2_CACHE_TTL", 3600)

        if cache_type.lower() == "multi":
            _cache_service = MultiLevelCache(
                l1_ttl=l1_cache_ttl,
                l2_ttl=l2_cache_ttl,
                redis_url=redis_url,
            )
        elif cache_type.lower() == "redis":
            _cache_service = RedisCache(redis_url, cache_ttl)
        else:
            _cache_service = MemoryCache(cache_ttl)

    return _cache_service


__all__ = [
    "CacheService",
    "MemoryCache",
    "RedisCache",
    "MultiLevelCache",
    "get_cache_service",
    "cached",
    "cached_async",
    "build_cache_key",
]

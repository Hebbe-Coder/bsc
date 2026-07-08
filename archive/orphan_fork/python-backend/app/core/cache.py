from typing import Any, Optional
from redis import asyncio as aioredis
import hashlib
import json
from datetime import datetime

from .config import settings


class CacheManager:
    _redis: Optional[aioredis.Redis] = None
    _local_cache: dict = {}

    @classmethod
    async def get_redis(cls) -> aioredis.Redis:
        if cls._redis is None:
            cls._redis = await aioredis.from_url(settings.redis_url)
        return cls._redis

    @classmethod
    async def get(cls, key: str) -> Optional[str]:
        try:
            value = cls._local_cache.get(key)
            if value is not None:
                return value

            redis = await cls.get_redis()
            value = await redis.get(key)
            if value:
                cls._local_cache[key] = value.decode('utf-8')
            return value.decode('utf-8') if value else None
        except Exception:
            return cls._local_cache.get(key)

    @classmethod
    async def set(cls, key: str, value: str, ttl: int = None):
        ttl = ttl or settings.cache_ttl_default

        try:
            cls._local_cache[key] = value

            redis = await cls.get_redis()
            await redis.set(key, value, ex=ttl)
        except Exception:
            pass

    @classmethod
    async def delete(cls, key: str):
        try:
            cls._local_cache.pop(key, None)

            redis = await cls.get_redis()
            await redis.delete(key)
        except Exception:
            pass

    @classmethod
    async def exists(cls, key: str) -> bool:
        if key in cls._local_cache:
            return True

        try:
            redis = await cls.get_redis()
            return await redis.exists(key) > 0
        except Exception:
            return False

    @classmethod
    def generate_cache_key(cls, skill_id: str, params: dict) -> str:
        params_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        combined = f"{skill_id}:{params_str}"
        return hashlib.md5(combined.encode('utf-8')).hexdigest()

    @classmethod
    async def get_cached_result(cls, skill_id: str, params: dict) -> Optional[str]:
        key = cls.generate_cache_key(skill_id, params)
        return await cls.get(key)

    @classmethod
    async def set_cached_result(cls, skill_id: str, params: dict, result: str, ttl: int = None):
        key = cls.generate_cache_key(skill_id, params)
        await cls.set(key, result, ttl)

    @classmethod
    async def clear_local_cache(cls):
        cls._local_cache.clear()

    @classmethod
    async def get_cache_stats(cls) -> dict:
        try:
            redis = await cls.get_redis()
            info = await redis.info('stats')
            return {
                'local_cache_size': len(cls._local_cache),
                'redis_keys_count': info.get('keyspace_hits', 0),
            }
        except Exception:
            return {
                'local_cache_size': len(cls._local_cache),
                'redis_available': False,
            }


class ExecutionHistory:
    _history: list = []

    @classmethod
    async def add_record(cls, execution_id: str, skill_id: str, status: str,
                         params: dict = None, result: str = None, error: str = None,
                         duration_ms: int = 0):
        record = {
            'execution_id': execution_id,
            'skill_id': skill_id,
            'status': status,
            'params': params,
            'result': result,
            'error': error,
            'duration_ms': duration_ms,
            'timestamp': datetime.now().isoformat(),
        }
        cls._history.append(record)

        if len(cls._history) > 100:
            cls._history = cls._history[-100:]

        try:
            redis = await CacheManager.get_redis()
            await redis.lpush('execution_history', json.dumps(record))
            await redis.ltrim('execution_history', 0, 99)
        except Exception:
            pass

    @classmethod
    async def get_history(cls, limit: int = 20) -> list:
        try:
            redis = await CacheManager.get_redis()
            records = await redis.lrange('execution_history', 0, limit - 1)
            return [json.loads(r.decode('utf-8')) for r in records]
        except Exception:
            return cls._history[-limit:]

    @classmethod
    async def get_by_execution_id(cls, execution_id: str) -> Optional[dict]:
        try:
            redis = await CacheManager.get_redis()
            records = await redis.lrange('execution_history', 0, 99)
            for r in records:
                record = json.loads(r.decode('utf-8'))
                if record.get('execution_id') == execution_id:
                    return record
        except Exception:
            pass

        for record in cls._history:
            if record.get('execution_id') == execution_id:
                return record
        return None

"""Compatibility exports for the consolidated cache service module."""

from app.services.cache_service import (
    CacheService,
    MemoryCache,
    MultiLevelCache,
    RedisCache,
    get_cache_service,
)

__all__ = [
    "CacheService",
    "MemoryCache",
    "MultiLevelCache",
    "RedisCache",
    "get_cache_service",
]

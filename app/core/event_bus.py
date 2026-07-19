"""
Event Bus - 事件驱动架构

提供进程内事件发布/订阅机制，支持：
1. 进程内事件总线（基于asyncio.Event）
2. Redis Streams适配器（分布式场景）
3. 事件模式匹配订阅
4. 事件生命周期管理

事件类型：
- AgentStarted: Agent开始执行
- AgentCompleted: Agent执行完成
- AgentFailed: Agent执行失败
- PipelineStageChanged: Pipeline阶段变更
- TaskSubmitted: 任务提交
- TaskCompleted: 任务完成
- TaskFailed: 任务失败
- CacheInvalidated: 缓存失效

配置方式：
- EVENT_BACKEND: inprocess | redis (默认inprocess)
- REDIS_URL: Redis连接地址
"""
import asyncio
import logging
from typing import Dict, Callable, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class Event:
    """事件基类"""
    
    def __init__(self, event_type: str, payload: Dict[str, Any], 
                 timestamp: Optional[float] = None, event_id: Optional[str] = None):
        self.event_type = event_type
        self.payload = payload
        self.timestamp = timestamp or datetime.now().timestamp()
        self.event_id = event_id or f"{event_type}:{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """从字典创建事件"""
        return cls(
            event_type=data["event_type"],
            payload=data["payload"],
            timestamp=data.get("timestamp"),
            event_id=data.get("event_id"),
        )


class EventBus:
    """事件总线接口"""
    
    def publish(self, event: Event) -> bool:
        """发布事件"""
        raise NotImplementedError
    
    def subscribe(self, event_type: str, handler: Callable[[Event], Any]) -> str:
        """订阅事件类型"""
        raise NotImplementedError
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅"""
        raise NotImplementedError
    
    def subscribe_pattern(self, pattern: str, handler: Callable[[Event], Any]) -> str:
        """订阅事件模式（支持通配符）"""
        raise NotImplementedError


class InProcessEventBus(EventBus):
    """
    进程内事件总线
    
    使用字典存储订阅者，基于asyncio实现异步事件分发。
    适合单进程应用场景。
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[tuple[str, Callable]]] = {}
        self._pattern_subscribers: List[tuple[str, str, Callable]] = []
        self._lock = asyncio.Lock()
        self._subscription_counter = 0
        logger.info("InProcessEventBus initialized")
    
    def _match_pattern(self, event_type: str, pattern: str) -> bool:
        """模式匹配"""
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            return event_type.startswith(pattern[:-1])
        if pattern.startswith("*"):
            return event_type.endswith(pattern[1:])
        return event_type == pattern
    
    async def publish(self, event: Event) -> bool:
        """发布事件"""
        async with self._lock:
            handlers = []
            
            if event.event_type in self._subscribers:
                handlers.extend([h for _, h in self._subscribers[event.event_type]])
            
            for _, pattern, handler in self._pattern_subscribers:
                if self._match_pattern(event.event_type, pattern):
                    handlers.append(handler)
            
            if not handlers:
                logger.debug(f"No subscribers for event: {event.event_type}")
                return True
            
            tasks = [handler(event) for handler in handlers]
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.debug(f"Published event: {event.event_type}, handlers: {len(handlers)}")
        
        return True
    
    def publish_sync(self, event: Event) -> bool:
        """同步发布事件"""
        import threading
        
        async def _publish():
            await self.publish(event)
        
        if threading.current_thread() is threading.main_thread():
            asyncio.run(_publish())
        else:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_publish())
            loop.close()
        
        return True
    
    def subscribe(self, event_type: str, handler: Callable[[Event], Any]) -> str:
        """订阅事件类型"""
        self._subscription_counter += 1
        subscription_id = f"sub_{self._subscription_counter}"
        
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append((subscription_id, handler))
        logger.debug(f"Subscribed: {subscription_id} to {event_type}")
        
        return subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅"""
        for event_type, subscribers in self._subscribers.items():
            original_len = len(subscribers)
            self._subscribers[event_type] = [
                (sid, h) for sid, h in subscribers if sid != subscription_id
            ]
            if len(self._subscribers[event_type]) < original_len:
                logger.debug(f"Unsubscribed: {subscription_id} from {event_type}")
                return True
        
        for i, (sid, pattern, handler) in enumerate(self._pattern_subscribers):
            if sid == subscription_id:
                del self._pattern_subscribers[i]
                logger.debug(f"Unsubscribed pattern: {subscription_id}")
                return True
        
        return False
    
    def subscribe_pattern(self, pattern: str, handler: Callable[[Event], Any]) -> str:
        """订阅事件模式"""
        self._subscription_counter += 1
        subscription_id = f"sub_{self._subscription_counter}"
        
        self._pattern_subscribers.append((subscription_id, pattern, handler))
        logger.debug(f"Subscribed pattern: {subscription_id} to {pattern}")
        
        return subscription_id
    
    def get_subscriptions(self) -> Dict[str, List[str]]:
        """获取所有订阅信息"""
        result = {}
        for event_type, subscribers in self._subscribers.items():
            result[event_type] = [sid for sid, _ in subscribers]
        for sid, pattern, _ in self._pattern_subscribers:
            result.setdefault(f"pattern:{pattern}", []).append(sid)
        return result


class RedisEventBus(EventBus):
    """
    Redis Streams事件总线
    
    使用Redis Streams实现分布式事件发布/订阅。
    适合多进程、分布式部署场景。
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", 
                 stream_name: str = "bsc_events", consumer_group: str = "bsc_group"):
        self._client = None
        self._stream_name = stream_name
        self._consumer_group = consumer_group
        self._subscribers: Dict[str, List[tuple[str, Callable]]] = {}
        self._pattern_subscribers: List[tuple[str, str, Callable]] = []
        self._subscription_counter = 0
        self._running = False
        self._consumer_task = None
        
        try:
            import redis
            self._client = redis.Redis.from_url(redis_url, decode_responses=True)
            self._client.ping()
            
            try:
                self._client.xgroup_create(stream_name, consumer_group, id="0", mkstream=True)
            except redis.exceptions.ResponseError:
                pass
            
            logger.info(f"RedisEventBus initialized: stream={stream_name}, group={consumer_group}")
        except ImportError:
            logger.warning("redis package not installed, falling back to InProcessEventBus")
            self._fallback = InProcessEventBus()
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, falling back to InProcessEventBus")
            self._fallback = InProcessEventBus()
    
    def _use_fallback(self) -> bool:
        """判断是否使用回退"""
        return self._client is None
    
    def _match_pattern(self, event_type: str, pattern: str) -> bool:
        """模式匹配"""
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            return event_type.startswith(pattern[:-1])
        if pattern.startswith("*"):
            return event_type.endswith(pattern[1:])
        return event_type == pattern
    
    def publish(self, event: Event) -> bool:
        """发布事件"""
        if self._use_fallback():
            return self._fallback.publish_sync(event)
        
        try:
            self._client.xadd(
                self._stream_name,
                event.to_dict(),
                id="*",
            )
            logger.debug(f"Published event to Redis: {event.event_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
            return False
    
    def subscribe(self, event_type: str, handler: Callable[[Event], Any]) -> str:
        """订阅事件类型"""
        if self._use_fallback():
            return self._fallback.subscribe(event_type, handler)
        
        self._subscription_counter += 1
        subscription_id = f"sub_{self._subscription_counter}"
        
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append((subscription_id, handler))
        
        if not self._running:
            self._start_consumer()
        
        logger.debug(f"Subscribed: {subscription_id} to {event_type}")
        return subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅"""
        if self._use_fallback():
            return self._fallback.unsubscribe(subscription_id)
        
        for event_type, subscribers in self._subscribers.items():
            original_len = len(subscribers)
            self._subscribers[event_type] = [
                (sid, h) for sid, h in subscribers if sid != subscription_id
            ]
            if len(self._subscribers[event_type]) < original_len:
                logger.debug(f"Unsubscribed: {subscription_id} from {event_type}")
                return True
        
        for i, (sid, pattern, handler) in enumerate(self._pattern_subscribers):
            if sid == subscription_id:
                del self._pattern_subscribers[i]
                logger.debug(f"Unsubscribed pattern: {subscription_id}")
                return True
        
        return False
    
    def subscribe_pattern(self, pattern: str, handler: Callable[[Event], Any]) -> str:
        """订阅事件模式"""
        if self._use_fallback():
            return self._fallback.subscribe_pattern(pattern, handler)
        
        self._subscription_counter += 1
        subscription_id = f"sub_{self._subscription_counter}"
        
        self._pattern_subscribers.append((subscription_id, pattern, handler))
        
        if not self._running:
            self._start_consumer()
        
        logger.debug(f"Subscribed pattern: {subscription_id} to {pattern}")
        return subscription_id
    
    def _start_consumer(self):
        """启动Redis消费者"""
        import threading
        
        def _consume():
            self._running = True
            consumer_id = f"consumer_{id(self)}"
            
            while self._running:
                try:
                    messages = self._client.xreadgroup(
                        groupname=self._consumer_group,
                        consumername=consumer_id,
                        streams={self._stream_name: ">"},
                        count=10,
                        block=1000,
                    )
                    
                    for stream_name, stream_messages in messages:
                        for msg_id, msg_data in stream_messages:
                            try:
                                event = Event.from_dict(msg_data)
                                self._dispatch_event(event)
                                self._client.xack(self._stream_name, self._consumer_group, msg_id)
                            except Exception as e:
                                logger.error(f"Failed to process event: {e}")
                
                except Exception as e:
                    logger.error(f"Consumer error: {e}")
                    import time
                    time.sleep(5)
        
        self._consumer_thread = threading.Thread(target=_consume, daemon=True)
        self._consumer_thread.start()
    
    def _dispatch_event(self, event: Event):
        """分发事件到订阅者"""
        handlers = []
        
        if event.event_type in self._subscribers:
            handlers.extend([h for _, h in self._subscribers[event.event_type]])
        
        for _, pattern, handler in self._pattern_subscribers:
            if self._match_pattern(event.event_type, pattern):
                handlers.append(handler)
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(handler(event))
                    loop.close()
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Handler error: {e}")


_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取事件总线实例"""
    global _event_bus
    if _event_bus is None:
        from app.core.config import settings
        
        event_backend = getattr(settings, "EVENT_BACKEND", "inprocess")
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379")
        
        if event_backend.lower() == "redis":
            _event_bus = RedisEventBus(redis_url=redis_url)
        else:
            _event_bus = InProcessEventBus()
    
    return _event_bus


def publish_event(event_type: str, payload: Dict[str, Any]):
    """发布事件（便捷函数）"""
    event = Event(event_type=event_type, payload=payload)
    event_bus = get_event_bus()
    return event_bus.publish(event)


def subscribe_event(event_type: str, handler: Callable[[Event], Any]) -> str:
    """订阅事件（便捷函数）"""
    event_bus = get_event_bus()
    return event_bus.subscribe(event_type, handler)


__all__ = [
    "Event",
    "EventBus",
    "InProcessEventBus",
    "RedisEventBus",
    "get_event_bus",
    "publish_event",
    "subscribe_event",
]

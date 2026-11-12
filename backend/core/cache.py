"""JSON 缓存；Redis 不可用时降级到进程内存。"""

from __future__ import annotations

import json
import time
from typing import Any

from core.config import get_settings

try:
    import redis
except Exception:  # pragma: no cover
    redis = None

_MEMORY_CACHE: dict[str, Any] = {}

# 进程级连接状态：Redis 一次连不上就进入冷却期。否则每个请求都重付一次
# 连接超时——本地没起 Redis 时是实打实的 ~220ms/请求，且 /chat 主链路
_CLIENT: Any = None
_RETRY_AFTER: float = 0.0
_RETRY_COOLDOWN_SECONDS = 60


class Cache:
    """Redis 客户端；内存降级模式不支持 TTL 和多进程共享。

    连接推迟到首次 get/set：构造零开销；失败后 60 秒内不再试探，
    冷却期结束自动重连（Redis 中途起起来不需要重启服务）。
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def _client() -> Any:
        global _CLIENT, _RETRY_AFTER
        if _CLIENT is not None:
            return _CLIENT
        if redis is None or time.monotonic() < _RETRY_AFTER:
            return None
        try:
            client = redis.Redis.from_url(
                get_settings().redis_url,
                decode_responses=True,
                socket_connect_timeout=0.1,
                socket_timeout=0.1,
            )
            client.ping()
            _CLIENT = client
            return client
        except Exception:
            _RETRY_AFTER = time.monotonic() + _RETRY_COOLDOWN_SECONDS
            return None

    def get_json(self, key: str) -> Any | None:
        client = self._client()
        if client is None:
            return _MEMORY_CACHE.get(key)
        value = client.get(key)
        return json.loads(value) if value else None

    def set_json(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        client = self._client()
        if client is not None:
            client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))
        else:
            _MEMORY_CACHE[key] = value

"""三级缓存 —— 减少重复抓取，也是 AI 报告不重复烧钱的基础。

层级：
1. 盘中实时数据（行情/分钟资金流）：TTL 30 秒
2. 日级数据（估值/龙虎榜/股东户数）：缓存到当日收盘后失效
3. AI 分析报告：当日同股直接复用（P2 阶段接入，先落库）

P1 用进程内内存缓存（单实例够用）；后期多实例部署可换 Redis。
"""
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional

_cache: dict[str, tuple[float, Any]] = {}  # key → (过期时间戳, 值)
_lock = threading.Lock()

# 盘中数据 TTL
TTL_REALTIME = 30


def _eod_expiry() -> float:
    """当日 15:30（收盘+缓冲）的过期时间戳；已过收盘则到明日 15:30。"""
    now = datetime.now()
    eod = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now >= eod:
        eod += timedelta(days=1)
    return eod.timestamp()


def cache_get(key: str) -> Optional[Any]:
    with _lock:
        item = _cache.get(key)
        if item is None:
            return None
        expires, value = item
        if time.time() >= expires:
            del _cache[key]
            return None
        return value


def cache_set(key: str, value: Any, ttl: Optional[float] = None,
              until_eod: bool = False) -> None:
    if value is None:
        return
    expires = _eod_expiry() if until_eod else time.time() + (ttl or TTL_REALTIME)
    with _lock:
        _cache[key] = (expires, value)


def cached(prefix: str, ttl: Optional[float] = None, until_eod: bool = False):
    """缓存装饰器。按函数名+参数拼 key。

    用法：
        @cached("quote", ttl=30)          # 盘中数据 30 秒
        @cached("valuation", until_eod=True)  # 日级数据缓存到收盘
    """
    def deco(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{prefix}:{fn.__name__}:{args}:{sorted(kwargs.items())}"
            hit = cache_get(key)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            # 失败/临时不可用响应不进缓存：否则一次网络抖动/东财风控会把错误缓存住，
            # TTL 内一直返回同一个错误，掩盖了「重试即可恢复」的事实。
            is_error = isinstance(result, dict) and (
                "error" in result or result.get("available") is False)
            if not is_error:
                cache_set(key, result, ttl=ttl, until_eod=until_eod)
            return result
        return wrapper
    return deco


def cache_clear(prefix: Optional[str] = None) -> int:
    """清空缓存（可按前缀），返回清除条数。管理端点用。"""
    with _lock:
        if prefix is None:
            n = len(_cache)
            _cache.clear()
            return n
        keys = [k for k in _cache if k.startswith(prefix)]
        for k in keys:
            del _cache[k]
        return len(keys)

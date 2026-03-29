import functools
import hashlib
import json
import os
import pickle
from typing import Any, Callable

import diskcache

_DEFAULT_CACHE_DIR = os.environ.get("NEWSFACTOR_CACHE_DIR", ".cache")
_cache: diskcache.Cache | None = None


def _get_cache(cache_dir: str = _DEFAULT_CACHE_DIR) -> diskcache.Cache:
    global _cache
    if _cache is None or _cache.directory != os.path.abspath(cache_dir):
        _cache = diskcache.Cache(cache_dir)
    return _cache


def _make_key(fn: Callable, args: tuple, kwargs: dict) -> str:
    raw = {
        "fn": f"{fn.__module__}.{fn.__qualname__}",
        "args": args,
        "kwargs": kwargs,
    }
    serialized = json.dumps(raw, default=str, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def disk_cache(ttl: int | None = None, cache_dir: str = _DEFAULT_CACHE_DIR):
    """Decorator. Caches the return value of a function to disk.

    Args:
        ttl: Time-to-live in seconds. None = forever.
        cache_dir: Directory for the diskcache database.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            cache = _get_cache(cache_dir)
            key = _make_key(fn, args, kwargs)
            if key in cache:
                return cache[key]
            result = fn(*args, **kwargs)
            cache.set(key, result, expire=ttl)
            return result
        return wrapper
    return decorator

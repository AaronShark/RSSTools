"""Async LRU cache implementation for RSSTools."""

import asyncio
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class SlidingWindowRateLimiter:
    """Thread-safe rate limiter using sliding window algorithm."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def allow_request(self) -> bool:
        """Check if request is allowed, and record it if so."""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_requests:
                return False
            self._timestamps.append(now)
            return True

    def wait_time(self) -> float:
        """Return seconds to wait before next request is allowed."""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) < self.max_requests:
                return 0.0
            oldest = self._timestamps[0]
            return max(0.0, oldest + self.window_seconds - now)


class AsyncSlidingWindowRateLimiter:
    """Async rate limiter using sliding window algorithm."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def allow_request(self) -> bool:
        """Check if request is allowed, and record it if so."""
        async with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_requests:
                return False
            self._timestamps.append(now)
            return True

    async def wait_time(self) -> float:
        """Return seconds to wait before next request is allowed."""
        async with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) < self.max_requests:
                return 0.0
            oldest = self._timestamps[0]
            return max(0.0, oldest + self.window_seconds - now)


@dataclass
class LRUCache(Generic[K, V]):
    """Thread-safe async LRU cache with configurable max size."""

    max_size: int = 100
    _cache: OrderedDict = field(default_factory=OrderedDict, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def get(self, key: K) -> V | None:
        """Get value from cache, returns None if not found."""
        async with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    async def put(self, key: K, value: V) -> None:
        """Put value in cache, evicting oldest if at capacity."""
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
                return
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            self._cache[key] = value

    async def clear(self) -> None:
        """Clear all cached items."""
        async with self._lock:
            self._cache.clear()

    async def size(self) -> int:
        """Return current cache size."""
        async with self._lock:
            return len(self._cache)

    async def contains(self, key: K) -> bool:
        """Check if key exists in cache."""
        async with self._lock:
            return key in self._cache


class SyncLRUCache(Generic[K, V]):
    """Thread-safe synchronous LRU cache with configurable max size."""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: OrderedDict[K, V] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: K) -> V | None:
        """Get value from cache, returns None if not found."""
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: K, value: V) -> None:
        """Put value in cache, evicting oldest if at capacity."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
                return
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            self._cache[key] = value

    def clear(self) -> None:
        """Clear all cached items."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Return current cache size."""
        with self._lock:
            return len(self._cache)

    def contains(self, key: K) -> bool:
        """Check if key exists in cache."""
        with self._lock:
            return key in self._cache

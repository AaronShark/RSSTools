"""Tests for LRU cache and rate limiter."""

import asyncio
import time

import pytest

from rsstools.lru_cache import (
    AsyncSlidingWindowRateLimiter,
    LRUCache,
    SlidingWindowRateLimiter,
    SyncLRUCache,
)


class TestSyncLRUCache:
    def test_basic_put_get(self):
        cache = SyncLRUCache(max_size=3)
        cache.put("a", "value_a")
        assert cache.get("a") == "value_a"

    def test_cache_miss(self):
        cache = SyncLRUCache(max_size=3)
        assert cache.get("missing") is None

    def test_lru_eviction(self):
        cache = SyncLRUCache(max_size=2)
        cache.put("a", "1")
        cache.put("b", "2")
        cache.put("c", "3")
        assert cache.get("a") is None
        assert cache.get("b") == "2"
        assert cache.get("c") == "3"

    def test_lru_access_order(self):
        cache = SyncLRUCache(max_size=2)
        cache.put("a", "1")
        cache.put("b", "2")
        cache.get("a")
        cache.put("c", "3")
        assert cache.get("a") == "1"
        assert cache.get("b") is None
        assert cache.get("c") == "3"

    def test_update_existing_key(self):
        cache = SyncLRUCache(max_size=2)
        cache.put("a", "1")
        cache.put("a", "2")
        assert cache.get("a") == "2"
        assert cache.size() == 1

    def test_clear(self):
        cache = SyncLRUCache(max_size=3)
        cache.put("a", "1")
        cache.put("b", "2")
        cache.clear()
        assert cache.size() == 0
        assert cache.get("a") is None

    def test_contains(self):
        cache = SyncLRUCache(max_size=3)
        cache.put("a", "1")
        assert cache.contains("a") is True
        assert cache.contains("b") is False


class TestAsyncLRUCache:
    @pytest.mark.asyncio
    async def test_basic_put_get(self):
        cache = LRUCache(max_size=3)
        await cache.put("a", "value_a")
        assert await cache.get("a") == "value_a"

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        cache = LRUCache(max_size=3)
        assert await cache.get("missing") is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        cache = LRUCache(max_size=2)
        await cache.put("a", "1")
        await cache.put("b", "2")
        await cache.put("c", "3")
        assert await cache.get("a") is None
        assert await cache.get("b") == "2"
        assert await cache.get("c") == "3"

    @pytest.mark.asyncio
    async def test_clear(self):
        cache = LRUCache(max_size=3)
        await cache.put("a", "1")
        await cache.put("b", "2")
        await cache.clear()
        assert await cache.size() == 0


class TestSlidingWindowRateLimiter:
    def test_allows_under_limit(self):
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        assert limiter.allow_request() is True
        assert limiter.allow_request() is True
        assert limiter.allow_request() is True

    def test_blocks_over_limit(self):
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.allow_request() is True
        assert limiter.allow_request() is True
        assert limiter.allow_request() is False

    def test_wait_time(self):
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=1)
        limiter.allow_request()
        limiter.allow_request()
        assert limiter.wait_time() > 0

    def test_sliding_window_expiry(self):
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.1)
        assert limiter.allow_request() is True
        assert limiter.allow_request() is True
        assert limiter.allow_request() is False
        time.sleep(0.15)
        assert limiter.allow_request() is True


class TestAsyncSlidingWindowRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        limiter = AsyncSlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        assert await limiter.allow_request() is True
        assert await limiter.allow_request() is True
        assert await limiter.allow_request() is True

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        limiter = AsyncSlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        assert await limiter.allow_request() is True
        assert await limiter.allow_request() is True
        assert await limiter.allow_request() is False

    @pytest.mark.asyncio
    async def test_sliding_window_expiry(self):
        limiter = AsyncSlidingWindowRateLimiter(max_requests=2, window_seconds=0.1)
        assert await limiter.allow_request() is True
        assert await limiter.allow_request() is True
        assert await limiter.allow_request() is False
        await asyncio.sleep(0.15)
        assert await limiter.allow_request() is True

"""Tests for rsstools/cache.py."""

import os
import time
import hashlib
from rsstools.cache import LLMCache


class TestLLMCache:
    """Tests for LLMCache class."""

    def test_init_creates_directory(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        assert os.path.exists(temp_cache_dir)
        assert cache.cache_dir == temp_cache_dir

    def test_init_creates_missing_directory(self, temp_dir):
        cache_path = os.path.join(temp_dir, "cache", "subdir")
        assert not os.path.exists(cache_path)
        cache = LLMCache(cache_path)
        assert os.path.exists(cache_path)

    def test_key_generates_sha256(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        key = cache._key("gpt-4", "system prompt", "user message")
        expected = hashlib.sha256("gpt-4|system prompt|user message".encode()).hexdigest()
        assert key == expected

    def test_key_is_consistent(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        key1 = cache._key("model", "sys", "user")
        key2 = cache._key("model", "sys", "user")
        assert key1 == key2

    def test_key_different_for_different_inputs(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        key1 = cache._key("model1", "sys", "user")
        key2 = cache._key("model2", "sys", "user")
        assert key1 != key2

    def test_get_returns_none_for_missing(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        result = cache.get("model", "system", "user")
        assert result is None

    def test_put_and_get(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        cache.put("model", "system", "user", "test result")
        result = cache.get("model", "system", "user")
        assert result == "test result"

    def test_put_overwrites_existing(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        cache.put("model", "system", "user", "first")
        cache.put("model", "system", "user", "second")
        result = cache.get("model", "system", "user")
        assert result == "second"

    def test_put_creates_file(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        cache.put("model", "system", "user", "content")
        key = cache._key("model", "system", "user")
        cache_file = os.path.join(temp_cache_dir, key)
        assert os.path.exists(cache_file)

    def test_get_with_unicode(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        cache.put("model", "system", "user", "Unicode: \u4e2d\u6587 \U0001F600")
        result = cache.get("model", "system", "user")
        assert result == "Unicode: \u4e2d\u6587 \U0001F600"

    def test_clean_empty_directory(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        removed, size = cache.clean(max_age_days=1)
        assert removed == 0
        assert size == 0

    def test_clean_no_old_files(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        cache.put("model", "system", "user", "content")
        removed, size = cache.clean(max_age_days=1)
        assert removed == 0
        assert size == 0

    def test_clean_removes_old_files(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        cache.put("model", "system", "user", "old content")
        key = cache._key("model", "system", "user")
        cache_file = os.path.join(temp_cache_dir, key)
        old_time = time.time() - (31 * 86400)
        os.utime(cache_file, (old_time, old_time))
        removed, size = cache.clean(max_age_days=30)
        assert removed == 1
        assert size == len("old content")
        assert not os.path.exists(cache_file)

    def test_clean_dry_run_keeps_files(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        cache.put("model", "system", "user", "old content")
        key = cache._key("model", "system", "user")
        cache_file = os.path.join(temp_cache_dir, key)
        old_time = time.time() - (31 * 86400)
        os.utime(cache_file, (old_time, old_time))
        removed, size = cache.clean(max_age_days=30, dry_run=True)
        assert removed == 1
        assert size == len("old content")
        assert os.path.exists(cache_file)

    def test_clean_keeps_new_files(self, temp_cache_dir):
        cache = LLMCache(temp_cache_dir)
        cache.put("model1", "system", "user", "old content")
        cache.put("model2", "system", "user", "new content")
        key_old = cache._key("model1", "system", "user")
        cache_file_old = os.path.join(temp_cache_dir, key_old)
        old_time = time.time() - (31 * 86400)
        os.utime(cache_file_old, (old_time, old_time))
        removed, size = cache.clean(max_age_days=30)
        assert removed == 1
        assert not os.path.exists(cache_file_old)
        assert cache.get("model2", "system", "user") == "new content"

    def test_clean_nonexistent_directory(self, temp_dir):
        nonexistent = os.path.join(temp_dir, "nonexistent")
        cache = LLMCache(nonexistent)
        os.rmdir(nonexistent)
        removed, size = cache.clean()
        assert removed == 0
        assert size == 0

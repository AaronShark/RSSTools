"""LLM cache for storing results"""

import hashlib
import os
from datetime import UTC, datetime


class LLMCache:
    """File-based cache for LLM results, keyed by prompt hash."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _key(self, model: str, system: str, user: str) -> str:
        h = hashlib.sha256(f"{model}|{system}|{user}".encode()).hexdigest()
        return h

    def get(self, model: str, system: str, user: str) -> str | None:
        path = os.path.join(self.cache_dir, self._key(model, system, user))
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
        return None

    def put(self, model: str, system: str, user: str, result: str):
        path = os.path.join(self.cache_dir, self._key(model, system, user))
        with open(path, "w", encoding="utf-8") as f:
            f.write(result)

    def get_by_key(self, key: str) -> str | None:
        """Get cached result by pre-computed key."""
        path = os.path.join(self.cache_dir, key)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
        return None

    def put_by_key(self, key: str, result: str):
        """Store result with pre-computed key."""
        path = os.path.join(self.cache_dir, key)
        with open(path, "w", encoding="utf-8") as f:
            f.write(result)

    def clean(self, max_age_days: int = 30, dry_run: bool = False) -> tuple[int, int]:
        """Remove cache files older than max_age_days. Returns (files_removed, bytes_freed)."""
        if not os.path.exists(self.cache_dir):
            return 0, 0
        cutoff = datetime.now(UTC).timestamp() - (max_age_days * 86400)
        removed = 0
        size_freed = 0
        for f in os.listdir(self.cache_dir):
            path = os.path.join(self.cache_dir, f)
            if os.path.isfile(path):
                mtime = os.path.getmtime(path)
                if mtime < cutoff:
                    size_freed += os.path.getsize(path)
                    if not dry_run:
                        os.remove(path)
                    removed += 1
        return removed, size_freed

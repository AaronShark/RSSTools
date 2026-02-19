"""Prometheus-style metrics for RSSTools observability."""

import threading
from typing import Any


class Metrics:
    """Thread-safe metrics collection with Prometheus output format."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls) -> "Metrics":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._data_lock = threading.Lock()
        self.articles_downloaded_total: int = 0
        self.articles_summarized_total: int = 0
        self.llm_requests_total: dict[str, int] = {}
        self.llm_requests_failed: dict[str, int] = {}
        self.llm_latency_seconds: dict[str, list[float]] = {}
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    def record_download(self) -> None:
        with self._data_lock:
            self.articles_downloaded_total += 1

    def record_summarize(self) -> None:
        with self._data_lock:
            self.articles_summarized_total += 1

    def record_llm_request(self, model: str, latency: float, success: bool) -> None:
        with self._data_lock:
            if model not in self.llm_requests_total:
                self.llm_requests_total[model] = 0
                self.llm_requests_failed[model] = 0
                self.llm_latency_seconds[model] = []
            self.llm_requests_total[model] += 1
            if not success:
                self.llm_requests_failed[model] += 1
            self.llm_latency_seconds[model].append(latency)

    def record_cache_hit(self) -> None:
        with self._data_lock:
            self.cache_hits += 1

    def record_cache_miss(self) -> None:
        with self._data_lock:
            self.cache_misses += 1

    def _get_avg_latency(self, model: str) -> float:
        latencies = self.llm_latency_seconds.get(model, [])
        if not latencies:
            return 0.0
        return sum(latencies) / len(latencies)

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        with self._data_lock:
            lines = []
            lines.append("# HELP articles_downloaded_total Total articles downloaded")
            lines.append("# TYPE articles_downloaded_total counter")
            lines.append(f"articles_downloaded_total {self.articles_downloaded_total}")
            lines.append("")
            lines.append("# HELP articles_summarized_total Total articles summarized")
            lines.append("# TYPE articles_summarized_total counter")
            lines.append(f"articles_summarized_total {self.articles_summarized_total}")
            lines.append("")
            lines.append("# HELP llm_requests_total Total LLM API requests by model")
            lines.append("# TYPE llm_requests_total counter")
            for model, count in sorted(self.llm_requests_total.items()):
                lines.append(f'llm_requests_total{{model="{model}"}} {count}')
            lines.append("")
            lines.append("# HELP llm_requests_failed Total failed LLM API requests by model")
            lines.append("# TYPE llm_requests_failed counter")
            for model, count in sorted(self.llm_requests_failed.items()):
                lines.append(f'llm_requests_failed{{model="{model}"}} {count}')
            lines.append("")
            lines.append("# HELP llm_latency_avg_seconds Average LLM request latency by model")
            lines.append("# TYPE llm_latency_avg_seconds gauge")
            for model in sorted(self.llm_latency_seconds.keys()):
                avg = self._get_avg_latency(model)
                lines.append(f'llm_latency_avg_seconds{{model="{model}"}} {avg:.6f}')
            lines.append("")
            lines.append("# HELP cache_hits_total Total cache hits")
            lines.append("# TYPE cache_hits_total counter")
            lines.append(f"cache_hits_total {self.cache_hits}")
            lines.append("")
            lines.append("# HELP cache_misses_total Total cache misses")
            lines.append("# TYPE cache_misses_total counter")
            lines.append(f"cache_misses_total {self.cache_misses}")
            lines.append("")
            return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as dictionary."""
        with self._data_lock:
            latencies_summary = {}
            for model, latencies in self.llm_latency_seconds.items():
                if latencies:
                    latencies_summary[model] = {
                        "count": len(latencies),
                        "avg": sum(latencies) / len(latencies),
                        "min": min(latencies),
                        "max": max(latencies),
                    }
                else:
                    latencies_summary[model] = {"count": 0, "avg": 0, "min": 0, "max": 0}
            return {
                "articles_downloaded_total": self.articles_downloaded_total,
                "articles_summarized_total": self.articles_summarized_total,
                "llm_requests_total": dict(self.llm_requests_total),
                "llm_requests_failed": dict(self.llm_requests_failed),
                "llm_latency": latencies_summary,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
            }

    def reset(self) -> None:
        """Reset all metrics to zero."""
        with self._data_lock:
            self.articles_downloaded_total = 0
            self.articles_summarized_total = 0
            self.llm_requests_total = {}
            self.llm_requests_failed = {}
            self.llm_latency_seconds = {}
            self.cache_hits = 0
            self.cache_misses = 0


metrics = Metrics()

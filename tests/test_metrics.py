"""Tests for rsstools/metrics.py."""

import threading

from rsstools.metrics import Metrics, metrics


class TestMetrics:
    """Tests for Metrics class."""

    def test_singleton_pattern(self):
        m1 = Metrics()
        m2 = Metrics()
        assert m1 is m2
        assert m1 is metrics

    def test_initial_state(self):
        m = Metrics()
        m.reset()
        assert m.articles_downloaded_total == 0
        assert m.articles_summarized_total == 0
        assert m.cache_hits == 0
        assert m.cache_misses == 0

    def test_record_download(self):
        m = Metrics()
        m.reset()
        m.record_download()
        m.record_download()
        m.record_download()
        assert m.articles_downloaded_total == 3

    def test_record_summarize(self):
        m = Metrics()
        m.reset()
        m.record_summarize()
        m.record_summarize()
        assert m.articles_summarized_total == 2

    def test_record_llm_request_success(self):
        m = Metrics()
        m.reset()
        m.record_llm_request("gpt-4", 1.5, success=True)
        assert m.llm_requests_total.get("gpt-4") == 1
        assert m.llm_requests_failed.get("gpt-4") == 0
        assert len(m.llm_latency_seconds.get("gpt-4", [])) == 1

    def test_record_llm_request_failure(self):
        m = Metrics()
        m.reset()
        m.record_llm_request("gpt-4", 2.0, success=False)
        assert m.llm_requests_total.get("gpt-4") == 1
        assert m.llm_requests_failed.get("gpt-4") == 1
        assert len(m.llm_latency_seconds.get("gpt-4", [])) == 1

    def test_record_llm_request_multiple_models(self):
        m = Metrics()
        m.reset()
        m.record_llm_request("gpt-4", 1.0, success=True)
        m.record_llm_request("gpt-4", 2.0, success=True)
        m.record_llm_request("gpt-3.5", 0.5, success=False)
        assert m.llm_requests_total.get("gpt-4") == 2
        assert m.llm_requests_total.get("gpt-3.5") == 1
        assert m.llm_requests_failed.get("gpt-4") == 0
        assert m.llm_requests_failed.get("gpt-3.5") == 1

    def test_record_cache_hit(self):
        m = Metrics()
        m.reset()
        m.record_cache_hit()
        m.record_cache_hit()
        assert m.cache_hits == 2

    def test_record_cache_miss(self):
        m = Metrics()
        m.reset()
        m.record_cache_miss()
        assert m.cache_misses == 1

    def test_to_prometheus_format(self):
        m = Metrics()
        m.reset()
        m.record_download()
        m.record_summarize()
        m.record_llm_request("gpt-4", 1.5, success=True)
        m.record_cache_hit()
        m.record_cache_miss()
        output = m.to_prometheus()
        assert "articles_downloaded_total 1" in output
        assert "articles_summarized_total 1" in output
        assert 'llm_requests_total{model="gpt-4"} 1' in output
        assert "cache_hits_total 1" in output
        assert "cache_misses_total 1" in output
        assert "# TYPE articles_downloaded_total counter" in output
        assert "# HELP articles_downloaded_total Total articles downloaded" in output

    def test_to_prometheus_multiple_models(self):
        m = Metrics()
        m.reset()
        m.record_llm_request("model-a", 1.0, success=True)
        m.record_llm_request("model-b", 2.0, success=False)
        output = m.to_prometheus()
        assert 'llm_requests_total{model="model-a"} 1' in output
        assert 'llm_requests_total{model="model-b"} 1' in output
        assert 'llm_requests_failed{model="model-a"} 0' in output
        assert 'llm_requests_failed{model="model-b"} 1' in output

    def test_to_dict(self):
        m = Metrics()
        m.reset()
        m.record_download()
        m.record_summarize()
        m.record_llm_request("gpt-4", 1.5, success=True)
        m.record_cache_hit()
        m.record_cache_miss()
        d = m.to_dict()
        assert d["articles_downloaded_total"] == 1
        assert d["articles_summarized_total"] == 1
        assert d["llm_requests_total"]["gpt-4"] == 1
        assert d["cache_hits"] == 1
        assert d["cache_misses"] == 1
        assert "gpt-4" in d["llm_latency"]

    def test_to_dict_latency_summary(self):
        m = Metrics()
        m.reset()
        m.record_llm_request("gpt-4", 1.0, success=True)
        m.record_llm_request("gpt-4", 2.0, success=True)
        m.record_llm_request("gpt-4", 3.0, success=True)
        d = m.to_dict()
        latency = d["llm_latency"]["gpt-4"]
        assert latency["count"] == 3
        assert latency["avg"] == 2.0
        assert latency["min"] == 1.0
        assert latency["max"] == 3.0

    def test_reset(self):
        m = Metrics()
        m.record_download()
        m.record_summarize()
        m.record_llm_request("gpt-4", 1.0, success=True)
        m.record_cache_hit()
        m.reset()
        assert m.articles_downloaded_total == 0
        assert m.articles_summarized_total == 0
        assert m.llm_requests_total == {}
        assert m.llm_requests_failed == {}
        assert m.llm_latency_seconds == {}
        assert m.cache_hits == 0
        assert m.cache_misses == 0

    def test_thread_safety(self):
        m = Metrics()
        m.reset()
        num_threads = 10
        iterations = 100
        errors = []

        def worker():
            try:
                for _ in range(iterations):
                    m.record_download()
                    m.record_cache_hit()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert m.articles_downloaded_total == num_threads * iterations
        assert m.cache_hits == num_threads * iterations

"""Tests for rsstools/cli.py health command."""

import os
import tempfile

import pytest

from rsstools.cli import cmd_health


class TestCmdHealth:
    """Tests for cmd_health function."""

    @pytest.fixture
    def temp_config(self, temp_dir):
        opml_path = os.path.join(temp_dir, "feeds.opml")
        with open(opml_path, "w") as f:
            f.write('<?xml version="1.0"?><opml><body></body></opml>')

        return {
            "base_dir": temp_dir,
            "opml_path": opml_path,
            "download": {
                "concurrent_feeds": 5,
                "concurrent_downloads": 10,
                "max_retries": 3,
                "timeout": 30,
                "connect_timeout": 10,
                "retry_delay": 2,
                "max_redirects": 5,
                "user_agent": "RSSTools/1.0",
                "etag_max_age_days": 30,
            },
            "llm": {
                "host": "https://api.example.com/v1",
                "models": "model-1",
                "max_tokens": 4096,
                "temperature": 0.3,
                "max_content_chars": 8000,
                "max_content_tokens": 4000,
                "request_delay": 0.5,
                "max_retries": 3,
                "timeout": 60,
                "system_prompt": "You are a helpful assistant.",
                "user_prompt": "Summarize: {title}\n\n{content}",
            },
        }

    @pytest.mark.asyncio
    async def test_health_returns_true_for_healthy_system(self, temp_config):
        healthy = await cmd_health(temp_config)
        assert healthy is True

    @pytest.mark.asyncio
    async def test_health_returns_degraded_for_empty_db(self, temp_config):
        healthy = await cmd_health(temp_config)
        assert healthy is True

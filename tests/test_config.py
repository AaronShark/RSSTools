"""Tests for configuration validation with pydantic."""

import os
import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from rsstools.models import Config, LLMConfig, DownloadConfig, SummarizeConfig
from rsstools.config import load_config, _merge_config, _format_validation_errors


class TestLLMConfig:
    def test_default_values(self):
        cfg = LLMConfig()
        assert cfg.api_key == ""
        assert cfg.host == "https://api.z.ai/api/coding/paas/v4"
        assert cfg.models == ["glm-5", "glm-4.7"]
        assert cfg.max_tokens == 2048
        assert cfg.temperature == 0.3
        assert cfg.max_content_chars == 10000
        assert cfg.request_delay == 0.5
        assert cfg.max_retries == 5
        assert cfg.timeout == 60

    def test_custom_values(self):
        cfg = LLMConfig(api_key="test-key", temperature=0.7)
        assert cfg.api_key == "test-key"
        assert cfg.temperature == 0.7

    def test_models_cannot_be_empty(self):
        with pytest.raises(ValidationError) as exc_info:
            LLMConfig(models=[])
        assert "models list must not be empty" in str(exc_info.value)

    def test_temperature_range_valid(self):
        LLMConfig(temperature=0.0)
        LLMConfig(temperature=1.0)
        LLMConfig(temperature=2.0)

    def test_temperature_range_invalid_low(self):
        with pytest.raises(ValidationError) as exc_info:
            LLMConfig(temperature=-0.1)
        assert "temperature must be between 0.0 and 2.0" in str(exc_info.value)

    def test_temperature_range_invalid_high(self):
        with pytest.raises(ValidationError) as exc_info:
            LLMConfig(temperature=2.1)
        assert "temperature must be between 0.0 and 2.0" in str(exc_info.value)

    def test_max_tokens_positive(self):
        with pytest.raises(ValidationError) as exc_info:
            LLMConfig(max_tokens=0)
        assert "max_tokens must be positive" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            LLMConfig(max_tokens=-1)
        assert "max_tokens must be positive" in str(exc_info.value)

    def test_timeout_positive(self):
        with pytest.raises(ValidationError):
            LLMConfig(timeout=0)

        with pytest.raises(ValidationError):
            LLMConfig(timeout=-1)

    def test_dict_access(self):
        cfg = LLMConfig(api_key="test")
        assert cfg["api_key"] == "test"
        assert cfg["temperature"] == 0.3


class TestDownloadConfig:
    def test_default_values(self):
        cfg = DownloadConfig()
        assert cfg.timeout == 15
        assert cfg.connect_timeout == 5
        assert cfg.max_retries == 3
        assert cfg.retry_delay == 2
        assert cfg.concurrent_downloads == 5
        assert cfg.concurrent_feeds == 3
        assert cfg.max_redirects == 5
        assert cfg.etag_max_age_days == 30

    def test_concurrent_range_valid(self):
        DownloadConfig(concurrent_downloads=1, concurrent_feeds=1)
        DownloadConfig(concurrent_downloads=20, concurrent_feeds=20)

    def test_concurrent_downloads_range_invalid_low(self):
        with pytest.raises(ValidationError) as exc_info:
            DownloadConfig(concurrent_downloads=0)
        assert "must be between 1 and 20" in str(exc_info.value)

    def test_concurrent_downloads_range_invalid_high(self):
        with pytest.raises(ValidationError) as exc_info:
            DownloadConfig(concurrent_downloads=21)
        assert "must be between 1 and 20" in str(exc_info.value)

    def test_concurrent_feeds_range_invalid_low(self):
        with pytest.raises(ValidationError) as exc_info:
            DownloadConfig(concurrent_feeds=0)
        assert "must be between 1 and 20" in str(exc_info.value)

    def test_concurrent_feeds_range_invalid_high(self):
        with pytest.raises(ValidationError) as exc_info:
            DownloadConfig(concurrent_feeds=21)
        assert "must be between 1 and 20" in str(exc_info.value)

    def test_timeout_positive(self):
        with pytest.raises(ValidationError):
            DownloadConfig(timeout=0)

        with pytest.raises(ValidationError):
            DownloadConfig(connect_timeout=-1)

    def test_dict_access(self):
        cfg = DownloadConfig(timeout=30)
        assert cfg["timeout"] == 30
        assert cfg["concurrent_feeds"] == 3


class TestSummarizeConfig:
    def test_default_values(self):
        cfg = SummarizeConfig()
        assert cfg.save_every == 20

    def test_save_every_positive(self):
        with pytest.raises(ValidationError):
            SummarizeConfig(save_every=0)

        with pytest.raises(ValidationError):
            SummarizeConfig(save_every=-1)

    def test_dict_access(self):
        cfg = SummarizeConfig(save_every=50)
        assert cfg["save_every"] == 50


class TestConfig:
    def test_default_values(self):
        cfg = Config()
        assert cfg.base_dir == "~/RSSKB"
        assert cfg.opml_path == ""
        assert isinstance(cfg.llm, LLMConfig)
        assert isinstance(cfg.download, DownloadConfig)
        assert isinstance(cfg.summarize, SummarizeConfig)

    def test_nested_config(self):
        cfg = Config(llm={"api_key": "test", "temperature": 0.8})
        assert cfg.llm.api_key == "test"
        assert cfg.llm.temperature == 0.8

    def test_dict_access_top_level(self):
        cfg = Config(base_dir="/custom/path")
        assert cfg["base_dir"] == "/custom/path"
        assert cfg["llm"]["api_key"] == ""

    def test_dict_access_nested(self):
        cfg = Config()
        assert cfg["llm"]["temperature"] == 0.3
        assert cfg["download"]["concurrent_feeds"] == 3


class TestMergeConfig:
    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _merge_config(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"llm": {"api_key": "", "temperature": 0.3}}
        override = {"llm": {"api_key": "test"}}
        result = _merge_config(base, override)
        assert result == {"llm": {"api_key": "test", "temperature": 0.3}}

    def test_empty_base(self):
        result = _merge_config({}, {"a": 1})
        assert result == {"a": 1}


class TestFormatValidationErrors:
    def test_single_error(self):
        try:
            LLMConfig(temperature=3.0)
        except ValidationError as e:
            formatted = _format_validation_errors(e)
            assert "temperature" in formatted
            assert "0.0 and 2.0" in formatted

    def test_multiple_errors(self):
        try:
            LLMConfig(temperature=3.0, max_tokens=-1, models=[])
        except ValidationError as e:
            formatted = _format_validation_errors(e)
            assert "temperature" in formatted
            assert "max_tokens" in formatted
            assert "models" in formatted


class TestLoadConfig:
    def test_load_default_config(self, monkeypatch):
        monkeypatch.delenv("RSSKB_BASE_DIR", raising=False)
        monkeypatch.delenv("GLM_API_KEY", raising=False)
        monkeypatch.delenv("GLM_HOST", raising=False)
        monkeypatch.delenv("GLM_MODELS", raising=False)
        monkeypatch.delenv("RSSKB_OPML_PATH", raising=False)

        original_home = os.path.expanduser("~")
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(Path, "home", lambda: Path(tmpdir))
            cfg = load_config()
            assert isinstance(cfg, Config)
            assert cfg.base_dir.endswith("RSSKB") or cfg.base_dir == os.path.expanduser("~/RSSKB")

    def test_env_override_base_dir(self, monkeypatch, temp_dir):
        monkeypatch.setenv("RSSKB_BASE_DIR", temp_dir)
        monkeypatch.delenv("GLM_API_KEY", raising=False)
        monkeypatch.delenv("GLM_HOST", raising=False)
        monkeypatch.delenv("GLM_MODELS", raising=False)
        monkeypatch.delenv("RSSKB_OPML_PATH", raising=False)

        original_home = os.path.expanduser("~")
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(Path, "home", lambda: Path(tmpdir))
            cfg = load_config()
            assert cfg.base_dir == temp_dir

    def test_env_override_api_key(self, monkeypatch):
        monkeypatch.setenv("GLM_API_KEY", "secret-key-123")
        monkeypatch.delenv("RSSKB_BASE_DIR", raising=False)
        monkeypatch.delenv("GLM_HOST", raising=False)
        monkeypatch.delenv("GLM_MODELS", raising=False)
        monkeypatch.delenv("RSSKB_OPML_PATH", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(Path, "home", lambda: Path(tmpdir))
            cfg = load_config()
            assert cfg.llm.api_key == "secret-key-123"

    def test_env_override_models(self, monkeypatch):
        monkeypatch.setenv("GLM_MODELS", "model-a, model-b, model-c")
        monkeypatch.delenv("RSSKB_BASE_DIR", raising=False)
        monkeypatch.delenv("GLM_API_KEY", raising=False)
        monkeypatch.delenv("GLM_HOST", raising=False)
        monkeypatch.delenv("RSSKB_OPML_PATH", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(Path, "home", lambda: Path(tmpdir))
            cfg = load_config()
            assert cfg.llm.models == ["model-a", "model-b", "model-c"]

    def test_json_config_file(self, monkeypatch, temp_dir):
        config_content = {
            "base_dir": "/custom/base",
            "llm": {
                "temperature": 0.8,
                "max_tokens": 4096
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".rsstools"
            config_dir.mkdir()
            with open(config_dir / "config.json", "w") as f:
                json.dump(config_content, f)

            monkeypatch.setattr(Path, "home", lambda: Path(tmpdir))
            monkeypatch.delenv("RSSKB_BASE_DIR", raising=False)
            monkeypatch.delenv("GLM_API_KEY", raising=False)
            monkeypatch.delenv("GLM_HOST", raising=False)
            monkeypatch.delenv("GLM_MODELS", raising=False)
            monkeypatch.delenv("RSSKB_OPML_PATH", raising=False)

            cfg = load_config()
            assert cfg.base_dir == "/custom/base"
            assert cfg.llm.temperature == 0.8
            assert cfg.llm.max_tokens == 4096

    def test_validation_error_message(self, monkeypatch):
        monkeypatch.setenv("GLM_MODELS", "")  # Empty string will result in empty list
        monkeypatch.delenv("RSSKB_BASE_DIR", raising=False)
        monkeypatch.delenv("GLM_API_KEY", raising=False)
        monkeypatch.delenv("GLM_HOST", raising=False)
        monkeypatch.delenv("RSSKB_OPML_PATH", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(Path, "home", lambda: Path(tmpdir))
            with pytest.raises(ValueError) as exc_info:
                load_config()
            assert "Configuration validation failed" in str(exc_info.value)

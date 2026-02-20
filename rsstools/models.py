"""Pydantic models for RSSTools configuration."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class LLMConfig(BaseModel):
    api_key: str = ""
    host: str = "https://api.z.ai/api/coding/paas/v4"
    models: list[str] = Field(default_factory=lambda: ["glm-5", "glm-4.7"])
    max_tokens: int = 2048
    temperature: float = 0.3
    max_content_chars: int = 10000
    max_content_tokens: int = 4000
    token_counting_model: str = "gpt-4"
    request_delay: float = 0.5
    max_retries: int = 5
    timeout: int = 60
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0
    system_prompt: str = "You are a helpful assistant that summarizes articles concisely."
    user_prompt: str = (
        "Summarize this article in 2-3 sentences, "
        "in the same language as the article.\n\nTitle: {title}\n\n{content}"
    )
    rate_limit_requests_per_minute: dict[str, int] = Field(default_factory=dict)
    use_content_only_cache_key: bool = False

    @field_validator("models", mode="before")
    @classmethod
    def parse_models(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [m.strip() for m in v.split(",") if m.strip()]
        if isinstance(v, list):
            return v
        raise ValueError("models must be a string or list")

    @field_validator("models")
    @classmethod
    def models_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("models list must not be empty")
        return v

    @field_validator("temperature")
    @classmethod
    def temperature_range(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v

    @field_validator("max_tokens")
    @classmethod
    def max_tokens_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_tokens must be positive")
        return v

    @field_validator("timeout", "max_retries")
    @classmethod
    def positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class DownloadConfig(BaseModel):
    timeout: int = 15
    connect_timeout: int = 5
    max_retries: int = 3
    retry_delay: int = 2
    concurrent_downloads: int = 5
    concurrent_feeds: int = 3
    max_redirects: int = 5
    etag_max_age_days: int = 30
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    rate_limit_per_domain: dict[str, int] = Field(default_factory=dict)
    ssrf_protection_enabled: bool = True
    content_sanitization_enabled: bool = True

    @field_validator("concurrent_downloads", "concurrent_feeds")
    @classmethod
    def concurrent_range(cls, v: int) -> int:
        if not 1 <= v <= 20:
            raise ValueError("must be between 1 and 20")
        return v

    @field_validator(
        "timeout",
        "connect_timeout",
        "max_retries",
        "retry_delay",
        "max_redirects",
        "etag_max_age_days",
    )
    @classmethod
    def positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class SummarizeConfig(BaseModel):
    save_every: int = 20

    @field_validator("save_every")
    @classmethod
    def positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class Config(BaseModel):
    base_dir: str = "~/RSSKB"
    opml_path: str = ""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    summarize: SummarizeConfig = Field(default_factory=SummarizeConfig)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

"""RSSTools - RSS Knowledge Base Tool"""

from .cache import LLMCache
from .config import DEFAULT_CONFIG, load_config
from .content import ContentPreprocessor
from .database import Database
from .downloader import ArticleDownloader
from .llm import LLMClient
from .metrics import Metrics, metrics
from .models import Config, DownloadConfig, LLMConfig, SummarizeConfig
from .reader import run_reader
from .repositories import ArticleRepository, CacheRepository, FeedRepository
from .utils import (
    extract_front_matter,
    parse_date_prefix,
    parse_opml,
    rebuild_front_matter,
    safe_dirname,
)

__all__ = [
    "load_config",
    "DEFAULT_CONFIG",
    "Config",
    "LLMConfig",
    "DownloadConfig",
    "SummarizeConfig",
    "LLMCache",
    "ContentPreprocessor",
    "LLMClient",
    "Database",
    "ArticleRepository",
    "FeedRepository",
    "CacheRepository",
    "ArticleDownloader",
    "Metrics",
    "metrics",
    "safe_dirname",
    "parse_date_prefix",
    "parse_opml",
    "extract_front_matter",
    "rebuild_front_matter",
    "run_reader",
]


def __getattr__(name: str):
    if name == "IndexManager":
        import warnings

        from .index import IndexManager
        warnings.warn(
            "IndexManager is deprecated. Use ArticleRepository, FeedRepository, and CacheRepository instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return IndexManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

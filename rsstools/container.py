"""Dependency injection container for RSSTools."""

import os
from typing import TYPE_CHECKING, Any

import aiohttp

from .cache import LLMCache
from .database import Database
from .http_client import HTTPClient
from .llm import LLMClient
from .logging_config import get_logger
from .repositories import ArticleRepository, CacheRepository, FeedRepository

if TYPE_CHECKING:
  pass

logger = get_logger(__name__)


class Container:
  """DI container for managing RSSTools dependencies."""

  def __init__(self, config: Any):
    self.config = config
    self._db: Database | None = None
    self._article_repo: ArticleRepository | None = None
    self._feed_repo: FeedRepository | None = None
    self._cache_repo: CacheRepository | None = None
    self._llm_cache: LLMCache | None = None
    self._llm_client: LLMClient | None = None
    self._http_client: HTTPClient | None = None

  @property
  def db(self) -> Database:
    if self._db is None:
      db_path = os.path.join(self.config["base_dir"], "rsstools.db")
      self._db = Database(db_path)
    return self._db

  @property
  def article_repo(self) -> ArticleRepository:
    if self._article_repo is None:
      self._article_repo = ArticleRepository(self.db)
    return self._article_repo

  @property
  def feed_repo(self) -> FeedRepository:
    if self._feed_repo is None:
      self._feed_repo = FeedRepository(self.db)
    return self._feed_repo

  @property
  def cache_repo(self) -> CacheRepository:
    if self._cache_repo is None:
      self._cache_repo = CacheRepository(self.db)
    return self._cache_repo

  @property
  def llm_cache(self) -> LLMCache:
    if self._llm_cache is None:
      cache_dir = os.path.join(self.config["base_dir"], ".llm_cache")
      self._llm_cache = LLMCache(cache_dir)
    return self._llm_cache

  @property
  def llm_client(self) -> LLMClient:
    if self._llm_client is None:
      llm_cfg = self.config["llm"]
      models = llm_cfg["models"]
      if isinstance(models, list):
        llm_cfg_dict = dict(llm_cfg)
        llm_cfg_dict["models"] = ",".join(models)
        self._llm_client = LLMClient(llm_cfg_dict, self.llm_cache)
      else:
        self._llm_client = LLMClient(llm_cfg, self.llm_cache)
    return self._llm_client

  @property
  def http_client(self) -> HTTPClient:
    if self._http_client is None:
      dl = self.config["download"]
      self._http_client = HTTPClient(
        total_connections=100,
        per_host_connections=dl["concurrent_feeds"],
        connect_timeout=float(dl["connect_timeout"]),
        total_timeout=float(dl["timeout"]),
        force_close=True,
      )
    return self._http_client

  @property
  def http_session(self) -> aiohttp.ClientSession:
    return self.http_client.session

  async def connect(self) -> None:
    await self.db.connect()
    await self.http_client.connect()
    logger.info("container_connected")

  async def disconnect(self) -> None:
    if self._http_client:
      await self._http_client.disconnect()
      self._http_client = None
    if self._db:
      await self._db.close()
      self._db = None
      logger.info("container_disconnected")

  async def __aenter__(self) -> "Container":
    await self.connect()
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
    await self.disconnect()

"""Shared HTTP client with connection pooling for RSSTools."""

import asyncio

import aiohttp

from .logging_config import get_logger

logger = get_logger(__name__)


class HTTPClient:
  """Shared HTTP client with connection pooling."""

  def __init__(
    self,
    total_connections: int = 100,
    per_host_connections: int = 10,
    connect_timeout: float = 10.0,
    total_timeout: float = 60.0,
    force_close: bool = False,
  ):
    self._total_connections = total_connections
    self._per_host_connections = per_host_connections
    self._connect_timeout = connect_timeout
    self._total_timeout = total_timeout
    self._force_close = force_close
    self._session: aiohttp.ClientSession | None = None
    self._lock = asyncio.Lock()

  @property
  def session(self) -> aiohttp.ClientSession:
    if self._session is None or self._session.closed:
      raise RuntimeError("HTTPClient not connected. Call connect() first.")
    return self._session

  async def connect(self) -> None:
    async with self._lock:
      if self._session is not None and not self._session.closed:
        return

      connector = aiohttp.TCPConnector(
        limit=self._total_connections,
        limit_per_host=self._per_host_connections,
        force_close=self._force_close,
        enable_cleanup_closed=True,
      )
      timeout = aiohttp.ClientTimeout(
        total=self._total_timeout,
        connect=self._connect_timeout,
      )
      self._session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
      )
      logger.info(
        "http_client_connected",
        total_connections=self._total_connections,
        per_host_connections=self._per_host_connections,
      )

  async def disconnect(self) -> None:
    async with self._lock:
      if self._session is not None and not self._session.closed:
        await self._session.close()
        self._session = None
        logger.info("http_client_disconnected")

  async def __aenter__(self) -> "HTTPClient":
    await self.connect()
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
    await self.disconnect()

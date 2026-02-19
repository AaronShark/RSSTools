"""Feed repository for feed and failure tracking operations."""

from datetime import UTC, datetime
from typing import Any, Optional

from ..database import Database
from ..logging_config import get_logger
from ..utils import _parse_date_flexible

logger = get_logger(__name__)


class FeedRepository:
  """Repository for feed failure and article failure tracking."""

  def __init__(self, db: Database):
    self._db = db

  async def record_failure(self, url: str, error: str) -> None:
    await self._db.record_feed_failure(url, error)

  async def clear_failure(self, url: str) -> bool:
    return await self._db.clear_feed_failure(url)

  async def get_failure(self, url: str) -> Optional[dict[str, Any]]:
    return await self._db.get_feed_failure(url)

  async def should_skip(self, url: str, max_retries: int, retry_after_hours: int = 24) -> bool:
    info = await self._db.get_feed_failure(url)
    if not info:
      return False
    if info.get("retries", 0) < max_retries:
      return False
    ts = _parse_date_flexible(info.get("timestamp", ""))
    if ts:
      ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
      age_hours = (datetime.now(UTC) - ts).total_seconds() / 3600
      if age_hours >= retry_after_hours:
        await self._db.clear_feed_failure(url)
        return False
    return True

  async def record_article_failure(self, url: str, error: str) -> None:
    await self._db.record_article_failure(url, error)

  async def clear_article_failure(self, url: str) -> bool:
    return await self._db.clear_article_failure(url)

  async def should_skip_article(self, url: str, max_retries: int = 3) -> bool:
    info = await self._db.get_article_failure(url)
    if not info:
      return False
    return info.get("retries", 0) >= max_retries

  async def record_summary_failure(self, url: str, title: str, filepath: str, error: str) -> None:
    await self._db.record_summary_failure(url, title, filepath, error)

"""Cache repository for ETag and Last-Modified caching operations."""

from datetime import UTC, datetime
from typing import Any

from ..database import Database
from ..logging_config import get_logger
from ..utils import _parse_date_flexible

logger = get_logger(__name__)


class CacheRepository:
  """Repository for feed ETag/Last-Modified caching."""

  def __init__(self, db: Database):
    self._db = db

  async def get_etag(self, url: str, max_age_days: int = 30) -> dict[str, Any]:
    info = await self._db.get_feed_etag(url)
    if not info:
      return {}
    ts = _parse_date_flexible(info.get("timestamp", ""))
    if ts:
      ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
      age_days = (datetime.now(UTC) - ts).total_seconds() / 86400
      if age_days > max_age_days:
        return {}
    return info

  async def set_etag(self, url: str, etag: str = "", last_modified: str = "") -> None:
    await self._db.set_feed_etag(url, etag, last_modified)

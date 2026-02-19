"""Article repository for article-related database operations."""

from typing import Any, Literal

from ..database import Database
from ..logging_config import get_logger

logger = get_logger(__name__)

OrderBy = Literal["relevance", "date", "quality"]


class ArticleRepository:
  """Repository for article CRUD and search operations."""

  def __init__(self, db: Database):
    self._db = db

  async def add(self, url: str, article: dict[str, Any]) -> int:
    article_copy = dict(article)
    article_copy["url"] = url
    return await self._db.add_article(article_copy)

  async def get(self, url: str) -> dict[str, Any] | None:
    return await self._db.get_article(url)

  async def update(self, url: str, updates: dict[str, Any]) -> bool:
    return await self._db.update_article(url, updates)

  async def exists(self, url: str) -> bool:
    return await self._db.article_exists(url)

  async def delete(self, url: str) -> bool:
    return await self._db.delete_article(url)

  async def search(
    self,
    query: str,
    limit: int = 50,
    offset: int = 0,
    order_by: OrderBy = "relevance",
    category: str | None = None,
    source: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
  ) -> list[dict[str, Any]]:
    return await self._db.search_articles(
      query=query,
      limit=limit,
      offset=offset,
      order_by=order_by,
      category=category,
      source=source,
      date_start=date_start,
      date_end=date_end,
    )

  async def list_all(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    return await self._db.get_all_articles(limit, offset)

  async def count(self) -> int:
    stats = await self._db.get_stats()
    return stats.get("total_articles", 0)

  async def count_with_summary(self) -> int:
    stats = await self._db.get_stats()
    return stats.get("with_summary", 0)

  async def get_sources(self) -> list[str]:
    articles = await self._db.get_all_articles(limit=10000)
    sources = set()
    for article in articles:
      if article.get("source_name"):
        sources.add(article["source_name"])
    return sorted(sources)

  async def get_categories(self) -> list[str]:
    articles = await self._db.get_all_articles(limit=10000)
    categories = set()
    for article in articles:
      if article.get("category"):
        categories.add(article["category"])
    return sorted(categories)

  async def get_stats(self) -> dict[str, int]:
    return await self._db.get_stats()

"""Tests for repository classes."""

import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from rsstools.database import Database
from rsstools.repositories import ArticleRepository, CacheRepository, FeedRepository


@pytest.fixture
async def db():
  with tempfile.TemporaryDirectory() as tmpdir:
    db_path = os.path.join(tmpdir, "test.db")
    database = Database(db_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def article_repo(db):
  return ArticleRepository(db)


@pytest.fixture
async def feed_repo(db):
  return FeedRepository(db)


@pytest.fixture
async def cache_repo(db):
  return CacheRepository(db)


@pytest.fixture
def sample_article():
  return {
    "title": "Test Article",
    "source_name": "Test Feed",
    "feed_url": "https://example.com/feed.xml",
    "published": "2024-01-15T10:00:00Z",
    "downloaded": "2024-01-15T11:00:00Z",
    "filepath": "/path/to/article.html",
    "content_source": "html",
    "summary": "This is a test summary.",
    "category": "Technology",
    "score_relevance": 8,
    "score_quality": 7,
    "score_timeliness": 9,
    "keywords": ["python", "testing", "sqlite"],
  }


class TestArticleRepository:
  """Tests for ArticleRepository."""

  async def test_add_article(self, article_repo, sample_article):
    article_id = await article_repo.add("https://example.com/1", sample_article)
    assert article_id == 1

  async def test_add_sets_url(self, article_repo, sample_article):
    url = "https://example.com/specific-url"
    await article_repo.add(url, sample_article)
    article = await article_repo.get(url)
    assert article["url"] == url

  async def test_get_article(self, article_repo, sample_article):
    url = "https://example.com/1"
    await article_repo.add(url, sample_article)
    article = await article_repo.get(url)
    assert article is not None
    assert article["title"] == "Test Article"
    assert article["source_name"] == "Test Feed"

  async def test_get_article_not_found(self, article_repo):
    article = await article_repo.get("https://nonexistent.com")
    assert article is None

  async def test_update_article(self, article_repo, sample_article):
    url = "https://example.com/1"
    await article_repo.add(url, sample_article)
    updated = await article_repo.update(url, {"summary": "Updated summary"})
    assert updated
    article = await article_repo.get(url)
    assert article["summary"] == "Updated summary"

  async def test_update_article_not_found(self, article_repo):
    updated = await article_repo.update("https://nonexistent.com", {"summary": "test"})
    assert not updated

  async def test_exists_true(self, article_repo, sample_article):
    url = "https://example.com/1"
    assert not await article_repo.exists(url)
    await article_repo.add(url, sample_article)
    assert await article_repo.exists(url)

  async def test_exists_false(self, article_repo):
    assert not await article_repo.exists("https://nonexistent.com")

  async def test_delete_article(self, article_repo, sample_article):
    url = "https://example.com/1"
    await article_repo.add(url, sample_article)
    deleted = await article_repo.delete(url)
    assert deleted
    assert not await article_repo.exists(url)

  async def test_delete_article_not_found(self, article_repo):
    deleted = await article_repo.delete("https://nonexistent.com")
    assert not deleted

  async def test_search_articles(self, article_repo, sample_article):
    sample_article["title"] = "Python Programming Guide"
    await article_repo.add("https://example.com/1", sample_article)
    results = await article_repo.search("Python")
    assert len(results) == 1
    assert results[0]["title"] == "Python Programming Guide"

  async def test_search_no_results(self, article_repo, sample_article):
    await article_repo.add("https://example.com/1", sample_article)
    results = await article_repo.search("nonexistent_term_xyz")
    assert len(results) == 0

  async def test_search_with_bm25_ranking(self, article_repo, sample_article):
    sample_article["title"] = "Python Python Python"
    sample_article["summary"] = "All about Python programming"
    await article_repo.add("https://example.com/1", sample_article)

    sample_article["title"] = "Brief Python mention"
    sample_article["summary"] = "Other content here"
    await article_repo.add("https://example.com/2", sample_article)

    results = await article_repo.search("Python", order_by="relevance")
    assert len(results) == 2
    assert results[0]["title"] == "Python Python Python"

  async def test_search_order_by_date(self, article_repo, sample_article):
    sample_article["title"] = "Old Article"
    sample_article["published"] = "2023-01-01T00:00:00Z"
    await article_repo.add("https://example.com/1", sample_article)

    sample_article["title"] = "New Article"
    sample_article["published"] = "2024-01-01T00:00:00Z"
    await article_repo.add("https://example.com/2", sample_article)

    results = await article_repo.search("Article", order_by="date")
    assert len(results) == 2
    assert results[0]["title"] == "New Article"

  async def test_search_filter_by_category(self, article_repo, sample_article):
    sample_article["title"] = "Tech Article"
    sample_article["category"] = "Technology"
    await article_repo.add("https://example.com/1", sample_article)

    sample_article["title"] = "Science Article"
    sample_article["category"] = "Science"
    await article_repo.add("https://example.com/2", sample_article)

    results = await article_repo.search("Article", category="Technology")
    assert len(results) == 1
    assert results[0]["category"] == "Technology"

  async def test_search_filter_by_source(self, article_repo, sample_article):
    sample_article["title"] = "Feed A Article"
    sample_article["source_name"] = "Feed A"
    await article_repo.add("https://example.com/1", sample_article)

    sample_article["title"] = "Feed B Article"
    sample_article["source_name"] = "Feed B"
    await article_repo.add("https://example.com/2", sample_article)

    results = await article_repo.search("Article", source="Feed A")
    assert len(results) == 1
    assert results[0]["source_name"] == "Feed A"

  async def test_search_filter_by_date_range(self, article_repo, sample_article):
    sample_article["title"] = "January Article"
    sample_article["published"] = "2024-01-15T00:00:00Z"
    await article_repo.add("https://example.com/1", sample_article)

    sample_article["title"] = "March Article"
    sample_article["published"] = "2024-03-15T00:00:00Z"
    await article_repo.add("https://example.com/2", sample_article)

    results = await article_repo.search(
      "Article",
      date_start="2024-02-01",
      date_end="2024-04-01",
    )
    assert len(results) == 1
    assert results[0]["title"] == "March Article"

  async def test_search_with_offset(self, article_repo, sample_article):
    sample_article["summary"] = "unique keyword foobar"
    for i in range(5):
      sample_article["title"] = f"Article {i}"
      await article_repo.add(f"https://example.com/{i}", sample_article)

    page1 = await article_repo.search("foobar", limit=2, offset=0)
    page2 = await article_repo.search("foobar", limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0]["id"] != page2[0]["id"]

  async def test_search_respects_limit(self, article_repo, sample_article):
    sample_article["summary"] = "unique keyword foobar"
    for i in range(10):
      await article_repo.add(f"https://example.com/{i}", sample_article)
    results = await article_repo.search("foobar", limit=3)
    assert len(results) == 3

  async def test_list_all(self, article_repo, sample_article):
    await article_repo.add("https://example.com/1", sample_article)
    sample_article["title"] = "Second Article"
    await article_repo.add("https://example.com/2", sample_article)
    articles = await article_repo.list_all()
    assert len(articles) == 2

  async def test_list_all_pagination(self, article_repo, sample_article):
    for i in range(10):
      sample_article["title"] = f"Article {i}"
      await article_repo.add(f"https://example.com/{i}", sample_article)
    page1 = await article_repo.list_all(limit=5, offset=0)
    page2 = await article_repo.list_all(limit=5, offset=5)
    assert len(page1) == 5
    assert len(page2) == 5
    assert page1[0]["id"] != page2[0]["id"]

  async def test_count_empty(self, article_repo):
    count = await article_repo.count()
    assert count == 0

  async def test_count_with_articles(self, article_repo, sample_article):
    await article_repo.add("https://example.com/1", sample_article)
    await article_repo.add("https://example.com/2", sample_article)
    count = await article_repo.count()
    assert count == 2

  async def test_count_with_summary(self, article_repo, sample_article):
    await article_repo.add("https://example.com/1", sample_article)
    sample_article["url"] = "https://example.com/2"
    sample_article["summary"] = None
    await article_repo.add("https://example.com/2", sample_article)
    count = await article_repo.count_with_summary()
    assert count == 1

  async def test_get_sources(self, article_repo, sample_article):
    sample_article["source_name"] = "Feed A"
    await article_repo.add("https://example.com/1", sample_article)
    sample_article["source_name"] = "Feed B"
    await article_repo.add("https://example.com/2", sample_article)
    sample_article["source_name"] = "Feed A"
    await article_repo.add("https://example.com/3", sample_article)
    sources = await article_repo.get_sources()
    assert sources == ["Feed A", "Feed B"]

  async def test_get_categories(self, article_repo, sample_article):
    sample_article["category"] = "Technology"
    await article_repo.add("https://example.com/1", sample_article)
    sample_article["category"] = "Science"
    await article_repo.add("https://example.com/2", sample_article)
    sample_article["category"] = "Technology"
    await article_repo.add("https://example.com/3", sample_article)
    categories = await article_repo.get_categories()
    assert categories == ["Science", "Technology"]

  async def test_get_stats(self, article_repo, sample_article):
    await article_repo.add("https://example.com/1", sample_article)
    sample_article["url"] = "https://example.com/2"
    sample_article["summary"] = None
    await article_repo.add("https://example.com/2", sample_article)
    stats = await article_repo.get_stats()
    assert stats["total_articles"] == 2
    assert stats["with_summary"] == 1
    assert stats["without_summary"] == 1


class TestFeedRepository:
  """Tests for FeedRepository."""

  async def test_record_failure(self, feed_repo):
    await feed_repo.record_failure("https://feed.example.com", "Connection timeout")
    failure = await feed_repo.get_failure("https://feed.example.com")
    assert failure is not None
    assert failure["error"] == "Connection timeout"
    assert failure["retries"] == 0

  async def test_record_failure_increments_retries(self, feed_repo):
    url = "https://feed.example.com"
    await feed_repo.record_failure(url, "Error 1")
    await feed_repo.record_failure(url, "Error 2")
    failure = await feed_repo.get_failure(url)
    assert failure["retries"] == 1
    assert failure["error"] == "Error 2"

  async def test_get_failure_not_found(self, feed_repo):
    failure = await feed_repo.get_failure("https://nonexistent.com")
    assert failure is None

  async def test_clear_failure(self, feed_repo):
    url = "https://feed.example.com"
    await feed_repo.record_failure(url, "Error")
    cleared = await feed_repo.clear_failure(url)
    assert cleared
    failure = await feed_repo.get_failure(url)
    assert failure is None

  async def test_clear_failure_not_found(self, feed_repo):
    cleared = await feed_repo.clear_failure("https://nonexistent.com")
    assert not cleared

  async def test_should_skip_no_failure(self, feed_repo):
    should_skip = await feed_repo.should_skip("https://feed.example.com", max_retries=3)
    assert not should_skip

  async def test_should_skip_below_max_retries(self, feed_repo):
    url = "https://feed.example.com"
    await feed_repo.record_failure(url, "Error")
    should_skip = await feed_repo.should_skip(url, max_retries=3)
    assert not should_skip

  async def test_should_skip_at_max_retries(self, feed_repo):
    url = "https://feed.example.com"
    for _ in range(4):
      await feed_repo.record_failure(url, "Error")
    should_skip = await feed_repo.should_skip(url, max_retries=3)
    assert should_skip

  async def test_should_skip_expired_failure(self, feed_repo):
    url = "https://feed.example.com"
    for _ in range(4):
      await feed_repo.record_failure(url, "Error")
    should_skip = await feed_repo.should_skip(
      url, max_retries=3, retry_after_hours=0
    )
    assert not should_skip
    failure = await feed_repo.get_failure(url)
    assert failure is None

  async def test_record_article_failure(self, feed_repo):
    await feed_repo.record_article_failure("https://article.example.com", "404 Not Found")
    from rsstools.database import Database

    failure = await feed_repo._db.get_article_failure("https://article.example.com")
    assert failure is not None
    assert failure["error"] == "404 Not Found"

  async def test_clear_article_failure(self, feed_repo):
    url = "https://article.example.com"
    await feed_repo.record_article_failure(url, "Error")
    cleared = await feed_repo.clear_article_failure(url)
    assert cleared
    from rsstools.database import Database

    failure = await feed_repo._db.get_article_failure(url)
    assert failure is None

  async def test_should_skip_article_no_failure(self, feed_repo):
    should_skip = await feed_repo.should_skip_article("https://article.example.com")
    assert not should_skip

  async def test_should_skip_article_below_max(self, feed_repo):
    url = "https://article.example.com"
    await feed_repo.record_article_failure(url, "Error")
    should_skip = await feed_repo.should_skip_article(url, max_retries=3)
    assert not should_skip

  async def test_should_skip_article_at_max(self, feed_repo):
    url = "https://article.example.com"
    for _ in range(4):
      await feed_repo.record_article_failure(url, "Error")
    should_skip = await feed_repo.should_skip_article(url, max_retries=3)
    assert should_skip

  async def test_record_summary_failure(self, feed_repo):
    await feed_repo.record_summary_failure(
      "https://article.example.com",
      "Article Title",
      "/path/to/file.html",
      "LLM timeout",
    )
    from rsstools.database import Database

    failure = await feed_repo._db.get_summary_failure("https://article.example.com")
    assert failure is not None
    assert failure["title"] == "Article Title"
    assert failure["filepath"] == "/path/to/file.html"
    assert failure["error"] == "LLM timeout"


class TestCacheRepository:
  """Tests for CacheRepository."""

  async def test_set_etag(self, cache_repo):
    await cache_repo.set_etag(
      "https://feed.example.com",
      etag='"abc123"',
      last_modified="Mon, 15 Jan 2024 10:00:00 GMT",
    )
    etag_info = await cache_repo.get_etag("https://feed.example.com")
    assert etag_info is not None
    assert etag_info["etag"] == '"abc123"'
    assert etag_info["last_modified"] == "Mon, 15 Jan 2024 10:00:00 GMT"

  async def test_set_etag_overwrites(self, cache_repo):
    url = "https://feed.example.com"
    await cache_repo.set_etag(url, etag='"old"', last_modified="")
    await cache_repo.set_etag(url, etag='"new"', last_modified="")
    etag_info = await cache_repo.get_etag(url)
    assert etag_info["etag"] == '"new"'

  async def test_get_etag_not_found(self, cache_repo):
    etag_info = await cache_repo.get_etag("https://nonexistent.com")
    assert etag_info == {}

  async def test_get_etag_expired(self, cache_repo):
    url = "https://feed.example.com"
    await cache_repo.set_etag(url, etag='"test"', last_modified="")
    etag_info = await cache_repo.get_etag(url, max_age_days=0)
    assert etag_info == {}

  async def test_get_etag_within_max_age(self, cache_repo):
    url = "https://feed.example.com"
    await cache_repo.set_etag(url, etag='"test"', last_modified="")
    etag_info = await cache_repo.get_etag(url, max_age_days=30)
    assert etag_info["etag"] == '"test"'

  async def test_set_etag_empty_values(self, cache_repo):
    url = "https://feed.example.com"
    await cache_repo.set_etag(url)
    etag_info = await cache_repo.get_etag(url)
    assert etag_info is not None

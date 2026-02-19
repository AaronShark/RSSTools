"""Tests for database module."""

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rsstools.database import Database


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        database = Database(db_path)
        await database.connect()
        yield database
        await database.close()


@pytest.fixture
def sample_article():
    """Sample article data for testing."""
    return {
        "url": "https://example.com/article/1",
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


class TestDatabaseConnection:
    """Tests for database connection and schema creation."""

    async def test_connect_creates_database_file(self):
        """Test that connect creates the database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            database = Database(db_path)
            assert not os.path.exists(db_path)
            await database.connect()
            assert os.path.exists(db_path)
            await database.close()

    async def test_connect_creates_parent_directory(self):
        """Test that connect creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "nested", "dir", "test.db")
            database = Database(db_path)
            await database.connect()
            assert os.path.exists(db_path)
            await database.close()

    async def test_close_is_idempotent(self, db):
        """Test that close can be called multiple times."""
        await db.close()
        await db.close()

    async def test_schema_version_initial(self, db):
        """Test initial schema version is 0."""
        version = await db.get_schema_version()
        assert version == 0

    async def test_set_schema_version(self, db):
        """Test setting schema version."""
        await db.set_schema_version(1)
        version = await db.get_schema_version()
        assert version == 1

        await db.set_schema_version(2)
        version = await db.get_schema_version()
        assert version == 2

    async def test_begin_migration(self, db):
        """Test beginning a migration transaction."""
        await db.begin_migration()
        await db.set_schema_version(5)
        version = await db.get_schema_version()
        assert version == 5


class TestArticleCRUD:
    """Tests for article CRUD operations."""

    async def test_add_article(self, db, sample_article):
        """Test adding an article."""
        article_id = await db.add_article(sample_article)
        assert article_id == 1

    async def test_add_article_returns_incrementing_ids(self, db, sample_article):
        """Test that article IDs increment."""
        id1 = await db.add_article(sample_article)
        sample_article["url"] = "https://example.com/article/2"
        id2 = await db.add_article(sample_article)
        assert id2 == id1 + 1

    async def test_add_article_unique_url(self, db, sample_article):
        """Test that duplicate URLs raise an error."""
        await db.add_article(sample_article)
        with pytest.raises(Exception):
            await db.add_article(sample_article)

    async def test_get_article(self, db, sample_article):
        """Test retrieving an article."""
        await db.add_article(sample_article)
        article = await db.get_article(sample_article["url"])
        assert article is not None
        assert article["url"] == sample_article["url"]
        assert article["title"] == sample_article["title"]
        assert article["source_name"] == sample_article["source_name"]

    async def test_get_article_not_found(self, db):
        """Test retrieving a non-existent article."""
        article = await db.get_article("https://nonexistent.com")
        assert article is None

    async def test_get_article_parses_keywords_json(self, db, sample_article):
        """Test that keywords are parsed from JSON."""
        await db.add_article(sample_article)
        article = await db.get_article(sample_article["url"])
        assert article["keywords"] == ["python", "testing", "sqlite"]

    async def test_article_exists(self, db, sample_article):
        """Test checking if article exists."""
        assert not await db.article_exists(sample_article["url"])
        await db.add_article(sample_article)
        assert await db.article_exists(sample_article["url"])

    async def test_update_article(self, db, sample_article):
        """Test updating article fields."""
        await db.add_article(sample_article)
        updated = await db.update_article(
            sample_article["url"],
            {"summary": "Updated summary", "category": "Science"},
        )
        assert updated
        article = await db.get_article(sample_article["url"])
        assert article["summary"] == "Updated summary"
        assert article["category"] == "Science"

    async def test_update_article_not_found(self, db):
        """Test updating a non-existent article."""
        updated = await db.update_article("https://nonexistent.com", {"summary": "test"})
        assert not updated

    async def test_update_article_keywords(self, db, sample_article):
        """Test updating article keywords."""
        await db.add_article(sample_article)
        new_keywords = ["new", "keywords"]
        await db.update_article(sample_article["url"], {"keywords": new_keywords})
        article = await db.get_article(sample_article["url"])
        assert article["keywords"] == new_keywords

    async def test_update_article_empty_updates(self, db, sample_article):
        """Test updating with empty updates."""
        await db.add_article(sample_article)
        result = await db.update_article(sample_article["url"], {})
        assert not result

    async def test_delete_article(self, db, sample_article):
        """Test deleting an article."""
        await db.add_article(sample_article)
        deleted = await db.delete_article(sample_article["url"])
        assert deleted
        assert not await db.article_exists(sample_article["url"])

    async def test_delete_article_not_found(self, db):
        """Test deleting a non-existent article."""
        deleted = await db.delete_article("https://nonexistent.com")
        assert not deleted

    async def test_get_all_articles(self, db, sample_article):
        """Test retrieving all articles."""
        await db.add_article(sample_article)
        sample_article["url"] = "https://example.com/article/2"
        sample_article["title"] = "Second Article"
        await db.add_article(sample_article)
        articles = await db.get_all_articles()
        assert len(articles) == 2

    async def test_get_all_articles_pagination(self, db, sample_article):
        """Test pagination of get_all_articles."""
        for i in range(10):
            sample_article["url"] = f"https://example.com/article/{i}"
            sample_article["title"] = f"Article {i}"
            await db.add_article(sample_article)
        page1 = await db.get_all_articles(limit=5, offset=0)
        page2 = await db.get_all_articles(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        assert page1[0]["id"] != page2[0]["id"]


class TestFullTextSearch:
    """Tests for FTS5 full-text search."""

    async def test_search_by_title(self, db, sample_article):
        """Test searching by title."""
        sample_article["title"] = "Python Programming Guide"
        await db.add_article(sample_article)
        results = await db.search_articles("Python")
        assert len(results) == 1
        assert results[0]["title"] == "Python Programming Guide"

    async def test_search_by_summary(self, db, sample_article):
        """Test searching by summary."""
        sample_article["summary"] = "Learn about machine learning algorithms"
        await db.add_article(sample_article)
        results = await db.search_articles("machine learning")
        assert len(results) == 1

    async def test_search_by_keywords(self, db, sample_article):
        """Test searching by keywords."""
        sample_article["keywords"] = ["artificial", "intelligence", "neural"]
        await db.add_article(sample_article)
        results = await db.search_articles("neural")
        assert len(results) == 1

    async def test_search_no_results(self, db, sample_article):
        """Test search with no matches."""
        await db.add_article(sample_article)
        results = await db.search_articles("nonexistent_term_xyz")
        assert len(results) == 0

    async def test_search_respects_limit(self, db, sample_article):
        """Test search limit parameter."""
        sample_article["summary"] = "unique keyword foobar"
        for i in range(10):
            sample_article["url"] = f"https://example.com/article/{i}"
            await db.add_article(sample_article)
        results = await db.search_articles("foobar", limit=3)
        assert len(results) == 3

    async def test_fts_stays_in_sync_on_update(self, db, sample_article):
        """Test that FTS index is updated when article is updated."""
        await db.add_article(sample_article)
        await db.update_article(sample_article["url"], {"title": "Quantum Computing"})
        results = await db.search_articles("Quantum")
        assert len(results) == 1

    async def test_fts_stays_in_sync_on_delete(self, db, sample_article):
        """Test that FTS index is updated when article is deleted."""
        sample_article["title"] = "Unique Delete Test Title"
        await db.add_article(sample_article)
        results = await db.search_articles("Unique Delete Test")
        assert len(results) == 1
        await db.delete_article(sample_article["url"])
        results = await db.search_articles("Unique Delete Test")
        assert len(results) == 0


class TestFeedFailures:
    """Tests for feed failure tracking."""

    async def test_record_feed_failure(self, db):
        """Test recording a feed failure."""
        await db.record_feed_failure("https://feed.example.com", "Connection timeout")
        failure = await db.get_feed_failure("https://feed.example.com")
        assert failure is not None
        assert failure["error"] == "Connection timeout"
        assert failure["retries"] == 0

    async def test_record_feed_failure_increments_retries(self, db):
        """Test that retries increment on subsequent failures."""
        url = "https://feed.example.com"
        await db.record_feed_failure(url, "Error 1")
        await db.record_feed_failure(url, "Error 2")
        failure = await db.get_feed_failure(url)
        assert failure["retries"] == 1
        assert failure["error"] == "Error 2"

    async def test_get_feed_failure_not_found(self, db):
        """Test getting a non-existent feed failure."""
        failure = await db.get_feed_failure("https://nonexistent.com")
        assert failure is None

    async def test_clear_feed_failure(self, db):
        """Test clearing a feed failure."""
        url = "https://feed.example.com"
        await db.record_feed_failure(url, "Error")
        cleared = await db.clear_feed_failure(url)
        assert cleared
        failure = await db.get_feed_failure(url)
        assert failure is None

    async def test_clear_feed_failure_not_found(self, db):
        """Test clearing a non-existent feed failure."""
        cleared = await db.clear_feed_failure("https://nonexistent.com")
        assert not cleared


class TestArticleFailures:
    """Tests for article failure tracking."""

    async def test_record_article_failure(self, db):
        """Test recording an article failure."""
        await db.record_article_failure("https://article.example.com", "404 Not Found")
        failure = await db.get_article_failure("https://article.example.com")
        assert failure is not None
        assert failure["error"] == "404 Not Found"

    async def test_record_article_failure_increments_retries(self, db):
        """Test that retries increment on subsequent failures."""
        url = "https://article.example.com"
        await db.record_article_failure(url, "Error 1")
        await db.record_article_failure(url, "Error 2")
        failure = await db.get_article_failure(url)
        assert failure["retries"] == 1

    async def test_clear_article_failure(self, db):
        """Test clearing an article failure."""
        url = "https://article.example.com"
        await db.record_article_failure(url, "Error")
        cleared = await db.clear_article_failure(url)
        assert cleared
        assert await db.get_article_failure(url) is None


class TestSummaryFailures:
    """Tests for summary failure tracking."""

    async def test_record_summary_failure(self, db):
        """Test recording a summary failure."""
        await db.record_summary_failure(
            "https://article.example.com",
            "Article Title",
            "/path/to/file.html",
            "LLM timeout",
        )
        failure = await db.get_summary_failure("https://article.example.com")
        assert failure is not None
        assert failure["title"] == "Article Title"
        assert failure["filepath"] == "/path/to/file.html"
        assert failure["error"] == "LLM timeout"

    async def test_record_summary_failure_overwrites(self, db):
        """Test that recording summary failure overwrites previous."""
        url = "https://article.example.com"
        await db.record_summary_failure(url, "Title 1", "/path1", "Error 1")
        await db.record_summary_failure(url, "Title 2", "/path2", "Error 2")
        failure = await db.get_summary_failure(url)
        assert failure["title"] == "Title 2"
        assert failure["error"] == "Error 2"


class TestFeedETags:
    """Tests for feed ETag caching."""

    async def test_set_feed_etag(self, db):
        """Test setting feed ETag."""
        await db.set_feed_etag(
            "https://feed.example.com",
            etag='"abc123"',
            last_modified="Mon, 15 Jan 2024 10:00:00 GMT",
        )
        etag_info = await db.get_feed_etag("https://feed.example.com")
        assert etag_info is not None
        assert etag_info["etag"] == '"abc123"'
        assert etag_info["last_modified"] == "Mon, 15 Jan 2024 10:00:00 GMT"
        assert etag_info["timestamp"] is not None

    async def test_set_feed_etag_overwrites(self, db):
        """Test that setting ETag overwrites previous."""
        url = "https://feed.example.com"
        await db.set_feed_etag(url, etag='"old"', last_modified="")
        await db.set_feed_etag(url, etag='"new"', last_modified="")
        etag_info = await db.get_feed_etag(url)
        assert etag_info["etag"] == '"new"'

    async def test_get_feed_etag_not_found(self, db):
        """Test getting a non-existent ETag."""
        etag_info = await db.get_feed_etag("https://nonexistent.com")
        assert etag_info is None


class TestStats:
    """Tests for database statistics."""

    async def test_get_stats_empty(self, db):
        """Test stats on empty database."""
        stats = await db.get_stats()
        assert stats["total_articles"] == 0
        assert stats["with_summary"] == 0
        assert stats["without_summary"] == 0
        assert stats["feed_failures"] == 0
        assert stats["article_failures"] == 0
        assert stats["summary_failures"] == 0

    async def test_get_stats_with_articles(self, db, sample_article):
        """Test stats with articles."""
        await db.add_article(sample_article)
        sample_article["url"] = "https://example.com/article/2"
        sample_article["summary"] = None
        await db.add_article(sample_article)
        stats = await db.get_stats()
        assert stats["total_articles"] == 2
        assert stats["with_summary"] == 1
        assert stats["without_summary"] == 1

    async def test_get_stats_with_failures(self, db, sample_article):
        """Test stats with failures."""
        await db.add_article(sample_article)
        await db.record_feed_failure("https://feed1.com", "Error")
        await db.record_feed_failure("https://feed2.com", "Error")
        await db.record_article_failure("https://article1.com", "Error")
        await db.record_summary_failure("https://article2.com", "Title", "/path", "Error")
        stats = await db.get_stats()
        assert stats["feed_failures"] == 2
        assert stats["article_failures"] == 1
        assert stats["summary_failures"] == 1

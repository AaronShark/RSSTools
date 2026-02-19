"""Tests for migration module."""

import json
import os
import tempfile

import pytest

from rsstools.database import Database
from rsstools.migrate import migrate, verify_migration


@pytest.fixture
def temp_migration_dir():
    """Create a temporary directory with sample migration data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        articles_dir = os.path.join(tmpdir, "articles", "TestFeed")
        os.makedirs(articles_dir, exist_ok=True)
        
        md_content = """---
title: "Test Article Title"
summary: "Test summary"
category: "Technology"
score_relevance: "8"
score_quality: "7"
score_timeliness: "9"
keywords: "[\\"python\\", \\"testing\\"]"
---

This is the body text of the article.
It has multiple lines.

More content here.
"""
        md_path = os.path.join(articles_dir, "2024-01-15_test-article_abc123.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        
        index_data = {
            "articles": {
                "https://example.com/article/1": {
                    "title": "Test Article Title",
                    "source_name": "TestFeed",
                    "feed_url": "https://example.com/feed.xml",
                    "published": "2024-01-15T10:00:00Z",
                    "downloaded": "2024-01-15T11:00:00Z",
                    "filepath": "articles/TestFeed/2024-01-15_test-article_abc123.md",
                    "content_source": "html",
                    "summary": "Test summary",
                    "category": "Technology",
                    "score_relevance": 8,
                    "score_quality": 7,
                    "score_timeliness": 9,
                    "keywords": ["python", "testing"],
                },
                "https://example.com/article/2": {
                    "title": "No File Article",
                    "source_name": "TestFeed",
                    "filepath": None,
                },
            },
            "feed_failures": {
                "https://failed-feed.com/rss": {
                    "error": "Connection timeout",
                    "timestamp": "2024-01-10T12:00:00Z",
                    "retries": 3,
                }
            },
            "article_failures": {
                "https://failed-article.com/1": {
                    "error": "404 Not Found",
                    "timestamp": "2024-01-10T12:00:00Z",
                    "retries": 1,
                }
            },
            "summary_failures": {
                "https://failed-summary.com/1": {
                    "title": "Failed Summary Article",
                    "filepath": "articles/Test/failed.md",
                    "error": "LLM timeout",
                }
            },
            "feed_etags": {
                "https://example.com/feed.xml": {
                    "etag": '"abc123"',
                    "last_modified": "Mon, 15 Jan 2024 10:00:00 GMT",
                    "timestamp": "2024-01-15T10:00:00Z",
                }
            },
        }
        
        index_path = os.path.join(tmpdir, "index.json")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f)
        
        yield tmpdir


class TestMigrate:
    """Tests for migration function."""

    async def test_migrate_creates_database(self, temp_migration_dir):
        """Test that migration creates the database file."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        result = await migrate(temp_migration_dir, db_path)
        
        assert "error" not in result
        assert os.path.exists(db_path)

    async def test_migrate_articles(self, temp_migration_dir):
        """Test that articles are migrated."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        result = await migrate(temp_migration_dir, db_path)
        
        assert result["articles_migrated"] == 2
        
        db = Database(db_path)
        await db.connect()
        
        article = await db.get_article("https://example.com/article/1")
        assert article is not None
        assert article["title"] == "Test Article Title"
        assert article["summary"] == "Test summary"
        assert "body text" in article["body"]
        
        article2 = await db.get_article("https://example.com/article/2")
        assert article2 is not None
        assert article2["title"] == "No File Article"
        assert article2["body"] is None
        
        await db.close()

    async def test_migrate_failures(self, temp_migration_dir):
        """Test that failures are migrated."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        result = await migrate(temp_migration_dir, db_path)
        
        assert result["feed_failures_migrated"] == 1
        assert result["article_failures_migrated"] == 1
        assert result["summary_failures_migrated"] == 1
        
        db = Database(db_path)
        await db.connect()
        
        feed_failure = await db.get_feed_failure("https://failed-feed.com/rss")
        assert feed_failure is not None
        assert feed_failure["error"] == "Connection timeout"
        
        article_failure = await db.get_article_failure("https://failed-article.com/1")
        assert article_failure is not None
        assert article_failure["error"] == "404 Not Found"
        
        summary_failure = await db.get_summary_failure("https://failed-summary.com/1")
        assert summary_failure is not None
        assert summary_failure["title"] == "Failed Summary Article"
        
        await db.close()

    async def test_migrate_etags(self, temp_migration_dir):
        """Test that feed ETags are migrated."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        result = await migrate(temp_migration_dir, db_path)
        
        assert result["feed_etags_migrated"] == 1
        
        db = Database(db_path)
        await db.connect()
        
        etag_info = await db.get_feed_etag("https://example.com/feed.xml")
        assert etag_info is not None
        assert etag_info["etag"] == '"abc123"'
        assert etag_info["last_modified"] == "Mon, 15 Jan 2024 10:00:00 GMT"
        
        await db.close()

    async def test_migrate_dry_run(self, temp_migration_dir):
        """Test dry run mode doesn't create database."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        result = await migrate(temp_migration_dir, db_path, dry_run=True)
        
        assert result["articles_migrated"] == 2
        assert result["feed_failures_migrated"] == 1
        assert not os.path.exists(db_path)

    async def test_migrate_missing_index(self, temp_migration_dir):
        """Test migration with missing index.json."""
        os.remove(os.path.join(temp_migration_dir, "index.json"))
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        result = await migrate(temp_migration_dir, db_path)
        
        assert "error" in result
        assert "not found" in result["error"]

    async def test_migrate_handles_missing_file(self, temp_migration_dir):
        """Test migration handles missing markdown files gracefully."""
        index_path = os.path.join(temp_migration_dir, "index.json")
        with open(index_path, encoding="utf-8") as f:
            index_data = json.load(f)
        
        index_data["articles"]["https://example.com/article/3"] = {
            "title": "Missing File Article",
            "source_name": "TestFeed",
            "filepath": "articles/TestFeed/nonexistent.md",
        }
        
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f)
        
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        result = await migrate(temp_migration_dir, db_path)
        
        assert len(result["errors"]) > 0
        assert any("not found" in e for e in result["errors"])

    async def test_migrate_idempotent(self, temp_migration_dir):
        """Test that migration can be run multiple times."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        
        result1 = await migrate(temp_migration_dir, db_path)
        assert result1["articles_migrated"] == 2
        assert result1["articles_skipped"] == 0
        
        result2 = await migrate(temp_migration_dir, db_path)
        assert result2["articles_migrated"] == 0
        assert result2["articles_skipped"] == 2
        
        db = Database(db_path)
        await db.connect()
        stats = await db.get_stats()
        assert stats["total_articles"] == 2
        await db.close()


class TestVerifyMigration:
    """Tests for verify_migration function."""

    async def test_verify_pass(self, temp_migration_dir):
        """Test verification passes for successful migration."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        await migrate(temp_migration_dir, db_path)
        
        result = await verify_migration(temp_migration_dir, db_path)
        
        assert result["status"] == "PASS"
        assert result["match"] is True
        assert result["missing_urls"] == []

    async def test_verify_fail_missing_index(self, temp_migration_dir):
        """Test verification fails with missing index.json."""
        os.remove(os.path.join(temp_migration_dir, "index.json"))
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        
        result = await verify_migration(temp_migration_dir, db_path)
        
        assert "error" in result

    async def test_verify_fail_missing_db(self, temp_migration_dir):
        """Test verification fails with missing database."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        
        result = await verify_migration(temp_migration_dir, db_path)
        
        assert "error" in result

    async def test_verify_fail_count_mismatch(self, temp_migration_dir):
        """Test verification fails when article count doesn't match."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        await migrate(temp_migration_dir, db_path)
        
        index_path = os.path.join(temp_migration_dir, "index.json")
        with open(index_path, encoding="utf-8") as f:
            index_data = json.load(f)
        index_data["articles"]["https://example.com/article/3"] = {
            "title": "Extra Article",
            "source_name": "TestFeed",
        }
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f)
        
        result = await verify_migration(temp_migration_dir, db_path)
        
        assert result["status"] == "FAIL"
        assert result["match"] is False

    async def test_verify_reports_missing_urls(self, temp_migration_dir):
        """Test verification reports missing URLs."""
        db_path = os.path.join(temp_migration_dir, "rsskb.db")
        
        db = Database(db_path)
        await db.connect()
        await db.add_article({
            "url": "https://example.com/different",
            "title": "Different Article",
            "source_name": "TestFeed",
        })
        await db.close()
        
        result = await verify_migration(temp_migration_dir, db_path)
        
        assert len(result["missing_urls"]) > 0

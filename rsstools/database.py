"""Async SQLite database backend with FTS5 full-text search."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from .logging_config import get_logger

logger = get_logger(__name__)


class Database:
    """Async SQLite database with FTS5 support for article storage."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect to database and create tables if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._create_schema()
        logger.info("database_connected", path=self.db_path)

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("database_closed")

    async def _create_schema(self) -> None:
        """Create all tables, indexes, and triggers."""
        await self._execute_script(SCHEMA_SQL)

    async def _execute_script(self, script: str) -> None:
        """Execute a SQL script with multiple statements."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.executescript(script)
        await self._conn.commit()

    async def _execute(
        self, query: str, params: tuple = ()
    ) -> aiosqlite.Cursor:
        """Execute a single query."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        return await self._conn.execute(query, params)

    async def begin_migration(self) -> None:
        """Begin a migration transaction."""
        await self._execute("BEGIN TRANSACTION")
        logger.info("migration_started")

    async def get_schema_version(self) -> int:
        """Get current schema version."""
        cursor = await self._execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def set_schema_version(self, version: int) -> None:
        """Set schema version after successful migration."""
        await self._execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,))
        await self._conn.commit()
        logger.info("schema_version_set", version=version)

    async def add_article(self, article: dict[str, Any]) -> int:
        """Add a new article. Returns the article ID."""
        keywords_json = json.dumps(article.get("keywords", [])) if article.get("keywords") else None
        cursor = await self._execute(
            """INSERT INTO articles (
                url, title, source_name, feed_url, published, downloaded,
                filepath, content_source, summary, body, category,
                score_relevance, score_quality, score_timeliness, keywords
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                article["url"],
                article["title"],
                article["source_name"],
                article.get("feed_url"),
                article.get("published"),
                article.get("downloaded"),
                article.get("filepath"),
                article.get("content_source"),
                article.get("summary"),
                article.get("body"),
                article.get("category"),
                article.get("score_relevance"),
                article.get("score_quality"),
                article.get("score_timeliness"),
                keywords_json,
            ),
        )
        await self._conn.commit()
        logger.debug("article_added", url=article["url"], id=cursor.lastrowid)
        return cursor.lastrowid

    async def get_article(self, url: str) -> Optional[dict[str, Any]]:
        """Get article by URL."""
        cursor = await self._execute("SELECT * FROM articles WHERE url = ?", (url,))
        row = await cursor.fetchone()
        return self._row_to_dict(row) if row else None

    async def update_article(self, url: str, updates: dict[str, Any]) -> bool:
        """Update article fields. Returns True if article was found and updated."""
        if not updates:
            return False
        set_clauses = []
        values = []
        for key, value in updates.items():
            if key == "keywords":
                set_clauses.append(f"{key} = ?")
                values.append(json.dumps(value) if value else None)
            elif key in (
                "url", "title", "source_name", "feed_url", "published",
                "downloaded", "filepath", "content_source", "summary", "body",
                "category", "score_relevance", "score_quality", "score_timeliness"
            ):
                set_clauses.append(f"{key} = ?")
                values.append(value)
        if not set_clauses:
            return False
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(url)
        cursor = await self._execute(
            f"UPDATE articles SET {', '.join(set_clauses)} WHERE url = ?",
            tuple(values),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def article_exists(self, url: str) -> bool:
        """Check if article exists by URL."""
        cursor = await self._execute("SELECT 1 FROM articles WHERE url = ?", (url,))
        row = await cursor.fetchone()
        return row is not None

    async def search_articles(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search articles using FTS5 full-text search."""
        cursor = await self._execute(
            """SELECT a.* FROM articles a
               JOIN articles_fts fts ON a.id = fts.rowid
               WHERE articles_fts MATCH ?
               ORDER BY a.published DESC
               LIMIT ?""",
            (query, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_all_articles(self, limit: int = 1000, offset: int = 0) -> list[dict[str, Any]]:
        """Get all articles with pagination."""
        cursor = await self._execute(
            "SELECT * FROM articles ORDER BY published DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def delete_article(self, url: str) -> bool:
        """Delete article by URL. Returns True if article was deleted."""
        cursor = await self._execute("DELETE FROM articles WHERE url = ?", (url,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def record_feed_failure(self, url: str, error: str) -> None:
        """Record a feed failure."""
        await self._execute(
            """INSERT INTO feed_failures (url, error, timestamp, retries)
               VALUES (?, ?, ?, 0)
               ON CONFLICT(url) DO UPDATE SET
                   error = excluded.error,
                   timestamp = excluded.timestamp,
                   retries = retries + 1""",
            (url, error, datetime.now(UTC).isoformat()),
        )
        await self._conn.commit()

    async def get_feed_failure(self, url: str) -> Optional[dict[str, Any]]:
        """Get feed failure info."""
        cursor = await self._execute("SELECT * FROM feed_failures WHERE url = ?", (url,))
        row = await cursor.fetchone()
        return self._row_to_dict(row) if row else None

    async def clear_feed_failure(self, url: str) -> bool:
        """Clear feed failure record."""
        cursor = await self._execute("DELETE FROM feed_failures WHERE url = ?", (url,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def record_article_failure(self, url: str, error: str) -> None:
        """Record an article download failure."""
        await self._execute(
            """INSERT INTO article_failures (url, error, timestamp, retries)
               VALUES (?, ?, ?, 0)
               ON CONFLICT(url) DO UPDATE SET
                   error = excluded.error,
                   timestamp = excluded.timestamp,
                   retries = retries + 1""",
            (url, error, datetime.now(UTC).isoformat()),
        )
        await self._conn.commit()

    async def get_article_failure(self, url: str) -> Optional[dict[str, Any]]:
        """Get article failure info."""
        cursor = await self._execute("SELECT * FROM article_failures WHERE url = ?", (url,))
        row = await cursor.fetchone()
        return self._row_to_dict(row) if row else None

    async def clear_article_failure(self, url: str) -> bool:
        """Clear article failure record."""
        cursor = await self._execute("DELETE FROM article_failures WHERE url = ?", (url,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def record_summary_failure(self, url: str, title: str, filepath: str, error: str) -> None:
        """Record a summary generation failure."""
        await self._execute(
            """INSERT OR REPLACE INTO summary_failures (url, title, filepath, error)
               VALUES (?, ?, ?, ?)""",
            (url, title, filepath, error),
        )
        await self._conn.commit()

    async def get_summary_failure(self, url: str) -> Optional[dict[str, Any]]:
        """Get summary failure info."""
        cursor = await self._execute("SELECT * FROM summary_failures WHERE url = ?", (url,))
        row = await cursor.fetchone()
        return self._row_to_dict(row) if row else None

    async def set_feed_etag(self, url: str, etag: str = "", last_modified: str = "") -> None:
        """Store feed ETag/Last-Modified for conditional requests."""
        await self._execute(
            """INSERT OR REPLACE INTO feed_etags (url, etag, last_modified, timestamp)
               VALUES (?, ?, ?, ?)""",
            (url, etag, last_modified, datetime.now(UTC).isoformat()),
        )
        await self._conn.commit()

    async def get_feed_etag(self, url: str) -> Optional[dict[str, Any]]:
        """Get stored feed ETag info."""
        cursor = await self._execute("SELECT * FROM feed_etags WHERE url = ?", (url,))
        row = await cursor.fetchone()
        return self._row_to_dict(row) if row else None

    async def get_stats(self) -> dict[str, int]:
        """Get database statistics."""
        stats = {}
        cursor = await self._execute("SELECT COUNT(*) FROM articles")
        row = await cursor.fetchone()
        stats["total_articles"] = row[0] if row else 0

        cursor = await self._execute("SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL")
        row = await cursor.fetchone()
        stats["with_summary"] = row[0] if row else 0

        stats["without_summary"] = stats["total_articles"] - stats["with_summary"]

        cursor = await self._execute("SELECT COUNT(*) FROM feed_failures")
        row = await cursor.fetchone()
        stats["feed_failures"] = row[0] if row else 0

        cursor = await self._execute("SELECT COUNT(*) FROM article_failures")
        row = await cursor.fetchone()
        stats["article_failures"] = row[0] if row else 0

        cursor = await self._execute("SELECT COUNT(*) FROM summary_failures")
        row = await cursor.fetchone()
        stats["summary_failures"] = row[0] if row else 0

        return stats

    def _row_to_dict(self, row: aiosqlite.Row) -> dict[str, Any]:
        """Convert a row to dict, parsing JSON fields."""
        result = dict(row)
        if result.get("keywords"):
            try:
                result["keywords"] = json.loads(result["keywords"])
            except json.JSONDecodeError:
                pass
        return result


SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- Articles table
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    source_name TEXT NOT NULL,
    feed_url TEXT,
    published DATETIME,
    downloaded DATETIME,
    filepath TEXT,
    content_source TEXT,
    summary TEXT,
    body TEXT,
    category TEXT,
    score_relevance INTEGER,
    score_quality INTEGER,
    score_timeliness INTEGER,
    keywords JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title, summary, body, keywords,
    content='articles',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, summary, body, keywords)
    VALUES (new.id, new.title, new.summary, new.body, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, summary, body, keywords)
    VALUES ('delete', old.id, old.title, old.summary, old.body, old.keywords);
END;

CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, summary, body, keywords)
    VALUES ('delete', old.id, old.title, old.summary, old.body, old.keywords);
    INSERT INTO articles_fts(rowid, title, summary, body, keywords)
    VALUES (new.id, new.title, new.summary, new.body, new.keywords);
END;

-- Feed failures
CREATE TABLE IF NOT EXISTS feed_failures (
    url TEXT PRIMARY KEY,
    error TEXT,
    timestamp DATETIME,
    retries INTEGER DEFAULT 0
);

-- Article failures
CREATE TABLE IF NOT EXISTS article_failures (
    url TEXT PRIMARY KEY,
    error TEXT,
    timestamp DATETIME,
    retries INTEGER DEFAULT 0
);

-- Summary failures
CREATE TABLE IF NOT EXISTS summary_failures (
    url TEXT PRIMARY KEY,
    title TEXT,
    filepath TEXT,
    error TEXT
);

-- Feed ETags
CREATE TABLE IF NOT EXISTS feed_etags (
    url TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    timestamp DATETIME
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_name);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
"""

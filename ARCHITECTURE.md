# RSSTools v3 Architecture

This document describes the technical architecture of RSSTools v3.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLI Layer (rsstools.py)                         │
│   Commands: download, summarize, stats, failed, config, migrate, health     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLI Implementation (cli.py)                        │
│   Orchestrates operations using Container for dependency management          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Dependency Injection (container.py)                  │
│   Manages lifecycle of: Database, Repositories, HTTPClient, LLMClient       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ ArticleRepository│      │  FeedRepository  │      │  CacheRepository │
│ - CRUD operations│      │ - Failure tracking│     │ - ETag caching  │
│ - FTS5 search    │      │ - Retry logic    │      │ - Timestamps    │
│ - Statistics     │      │                  │      │                  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
          │                           │                           │
          └───────────────────────────┼───────────────────────────┘
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Database Layer (database.py)                       │
│   Async SQLite with aiosqlite + FTS5 virtual tables + triggers              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Storage (rsstools.db + articles/)                    │
│   SQLite: articles, failures, etags | Files: markdown content               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Architecture

### Core Modules

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `rsstools.py` | CLI entry point | cli.py |
| `cli.py` | Command implementations | container.py, models.py |
| `container.py` | Dependency injection | database, repositories, llm, http_client |
| `models.py` | Pydantic config schemas | pydantic |
| `config.py` | Configuration loading | models.py, python-dotenv |

### Data Layer

| Module | Responsibility | Key Classes |
|--------|---------------|-------------|
| `database.py` | SQLite operations | `Database` |
| `repositories/article_repo.py` | Article CRUD + search | `ArticleRepository` |
| `repositories/feed_repo.py` | Failure tracking | `FeedRepository` |
| `repositories/cache_repo.py` | ETag management | `CacheRepository` |

### Service Layer

| Module | Responsibility | Key Classes |
|--------|---------------|-------------|
| `llm.py` | LLM API client | `LLMClient` |
| `downloader.py` | RSS download | `ArticleDownloader` |
| `http_client.py` | HTTP connection pool | `HTTPClient` |
| `cache.py` | LLM response cache | `LLMCache` |
| `content.py` | Content preprocessing | `ContentPreprocessor` |

### Infrastructure

| Module | Responsibility | Key Classes |
|--------|---------------|-------------|
| `circuit_breaker.py` | Resilience pattern | `CircuitBreaker`, `CircuitState` |
| `lru_cache.py` | In-memory caching | `LRUCache`, `SyncLRUCache` |
| `shutdown.py` | Graceful shutdown | `ShutdownManager` |
| `metrics.py` | Metrics collection | `Metrics` |
| `logging_config.py` | Structured logging | `setup_logging()` |
| `context.py` | Request context | `correlation_id` |
| `tokens.py` | Token counting | `TokenCounter` |
| `url_validator.py` | SSRF protection | `UrlValidator` |

### UI Layer

| Module | Responsibility | Key Classes |
|--------|---------------|-------------|
| `reader.py` | TUI application | `RSSReaderApp`, `ArticleWidget` |

### Utilities

| Module | Responsibility |
|--------|---------------|
| `utils.py` | YAML, OPML, front matter, content extraction |
| `migrate.py` | v2 to v3 migration |

## Database Schema

### Tables

```sql
-- Schema version tracking
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY
);

-- Main articles table
CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    source_name TEXT NOT NULL,
    feed_url TEXT,
    published DATETIME,
    downloaded DATETIME,
    filepath TEXT,
    content_source TEXT,
    body TEXT,
    summary TEXT,
    category TEXT,
    score_relevance INTEGER,
    score_quality INTEGER,
    score_timeliness INTEGER,
    keywords JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- FTS5 virtual table for search
CREATE VIRTUAL TABLE articles_fts USING fts5(
    title, summary, body, keywords,
    content='articles',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Feed failure tracking
CREATE TABLE feed_failures (
    url TEXT PRIMARY KEY,
    error TEXT,
    timestamp DATETIME,
    retries INTEGER DEFAULT 0
);

-- Article failure tracking
CREATE TABLE article_failures (
    url TEXT PRIMARY KEY,
    error TEXT,
    timestamp DATETIME,
    retries INTEGER DEFAULT 0
);

-- Summary failure tracking
CREATE TABLE summary_failures (
    url TEXT PRIMARY KEY,
    title TEXT,
    filepath TEXT,
    error TEXT
);

-- HTTP ETag caching
CREATE TABLE feed_etags (
    url TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    timestamp DATETIME
);
```

### Indexes

```sql
CREATE INDEX idx_articles_published ON articles(published);
CREATE INDEX idx_articles_source ON articles(source_name);
CREATE INDEX idx_articles_category ON articles(category);
```

### Triggers (FTS Sync)

```sql
-- Insert trigger
CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, summary, body, keywords)
    VALUES (new.id, new.title, new.summary, new.body, new.keywords);
END;

-- Delete trigger
CREATE TRIGGER articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, summary, body, keywords)
    VALUES ('delete', old.id, old.title, old.summary, old.body, old.keywords);
END;

-- Update trigger
CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, summary, body, keywords)
    VALUES ('delete', old.id, old.title, old.summary, old.body, old.keywords);
    INSERT INTO articles_fts(rowid, title, summary, body, keywords)
    VALUES (new.id, new.title, new.summary, new.body, new.keywords);
END;
```

## Data Flow

### Download Flow

```
1. OPML File → parse_opml() → List of feeds
2. For each feed (concurrent):
   a. Check ETag cache → conditional request
   b. Fetch RSS → FeedParser → entries
   c. For each entry (concurrent):
      - Check dedup via ArticleRepository.exists()
      - Download article HTML
      - Extract content (trafilatura/BeautifulSoup)
      - Sanitize HTML
      - Generate summary (LLMClient)
      - Save markdown file
      - Insert into database
3. Update failure records
```

### Summarize Flow

```
1. Query articles without summaries
2. Batch process (10 at a time):
   a. Read article files
   b. Preprocess content (ContentPreprocessor)
   c. Count tokens (TokenCounter)
   d. Truncate if needed
   e. Call LLM with circuit breaker protection
   f. Parse response
   g. Score and classify
   h. Update database
3. Cache results
```

### Search Flow

```
1. User enters query in TUI
2. ArticleRepository.search():
   a. Build FTS5 query
   b. Execute BM25 search
   c. Apply filters (category, source, date)
   d. Apply sort order
   e. Return paginated results
3. Display in Reader
```

## Key Patterns

### Dependency Injection

```python
# Container manages all dependencies
async with Container(config) as container:
    articles = await container.article_repo.search("python")
    await container.feed_repo.record_failure(url, error)
```

### Circuit Breaker

```python
# Protects LLM API calls
class CircuitBreaker:
    CLOSED → OPEN (after N failures)
    OPEN → HALF_OPEN (after timeout)
    HALF_OPEN → CLOSED (after success)
```

### Repository Pattern

```python
# Abstracts data access
class ArticleRepository:
    async def add(url, article) -> int
    async def get(url) -> Optional[dict]
    async def search(query, filters) -> list[dict]
    async def exists(url) -> bool
```

### Rate Limiting

```python
# Per-domain throttling
class DomainRateLimiter:
    async def acquire(domain: str)
    # Uses token bucket algorithm
```

## Configuration

### Pydantic Models

```python
class LLMConfig(BaseModel):
    api_key: str = ""
    host: str
    models: list[str]
    max_tokens: int
    temperature: float = Field(ge=0.0, le=2.0)
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0
    rate_limit_requests_per_minute: dict[str, int] = {}

class DownloadConfig(BaseModel):
    timeout: int
    concurrent_downloads: int = Field(ge=1, le=20)
    ssrf_protection_enabled: bool = True
    rate_limit_per_domain: dict[str, int] = {}

class Config(BaseModel):
    base_dir: str
    llm: LLMConfig
    download: DownloadConfig
    summarize: SummarizeConfig
```

### Environment Variables

| Variable | Config Path |
|----------|-------------|
| `RSSKB_BASE_DIR` | `base_dir` |
| `GLM_API_KEY` | `llm.api_key` |
| `GLM_HOST` | `llm.host` |
| `GLM_MODELS` | `llm.models` |
| `RSSKB_OPML_PATH` | `opml_path` |

## Error Handling

### Error Categories

1. **Network Errors**: Retry with exponential backoff
2. **API Errors**: Circuit breaker protection
3. **Parsing Errors**: Log and skip
4. **Database Errors**: Transaction rollback

### Logging

```python
# Structured logging with correlation IDs
logger.info("article_downloaded", url=url, source=source)
logger.error("llm_request_failed", model=model, error=str(e))
```

## Performance Considerations

### SQLite

- WAL mode for better concurrency
- Indexed queries for fast lookups
- FTS5 for sub-second search on 10K+ articles

### Memory

- Lazy loading in Container
- LRU cache for article bodies (100 articles)
- Streaming for large content

### Concurrency

- Semaphore-limited parallel downloads
- Connection pooling for HTTP
- Per-domain rate limiting

## Testing

### Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_cache.py        # LLMCache tests
├── test_config.py       # Configuration tests
├── test_content.py      # ContentPreprocessor tests
├── test_database.py     # Database operations
├── test_repositories.py # Repository tests
├── test_llm.py          # LLM client tests
├── test_circuit_breaker.py
├── test_http_client.py
├── test_shutdown.py
├── test_metrics.py
├── test_tokens.py
├── test_url_validator.py
└── test_utils.py
```

### Coverage Target

- Core modules: 80%+
- Overall: 70%+

## Security

### SSRF Protection

- Blocks private IP ranges
- Blocks localhost
- Only allows http/https schemes

### Content Sanitization

- Removes script tags
- Removes event handlers
- Removes dangerous hrefs

### Rate Limiting

- Prevents API abuse
- Per-domain throttling
- Per-model rate limits

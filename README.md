# RSSTools User Manual

## Introduction

RSSTools is a powerful RSS article management and knowledge base tool that integrates article downloading, AI summarization, and a TUI reader. It supports automatic article fetching from RSS sources, LLM-powered summarization, article classification and scoring, and provides a beautiful terminal interface for browsing and searching.

---

## Features

### 1. RSS Article Download
- **Multi-source Support**: Batch import RSS subscriptions from OPML files
- **Concurrent Downloading**: Support concurrent downloading of multiple RSS feeds and articles
- **Smart Deduplication**: Automatically skip already downloaded articles
- **Automatic Retry**: Support automatic retry for network errors
- **Conditional Requests**: Support ETag/Last-Modified conditional requests to avoid redundant downloads
- **Content Extraction**: Automatically extract article body content (supports Trafilatura and BeautifulSoup)

### 2. AI Summarization and Scoring
- **Batch Summarization**: Use LLM to batch generate article summaries (2-3 sentences)
- **Multi-model Fallback**: Support multiple LLM models with automatic fallback
- **Intelligent Scoring**: Rate articles on three dimensions:
  - **Relevance**: Value to tech professionals (1-10)
  - **Quality**: Depth and writing quality (1-10)
  - **Timeliness**: Current relevance (1-10)
- **Auto Classification**: Classify articles into 6 categories:
  - ai-ml (AI/ML)
  - security
  - engineering
  - tools
  - opinion
  - other
- **Keyword Extraction**: Extract 2-4 keywords
- **Result Caching**: Local cache of LLM results to avoid repeated API calls

### 3. TUI Reader
- **Beautiful Interface**: Terminal User Interface based on Textual with Nord theme
- **Full-Text Search**: Search across title, summary, keywords, and article body
  - Word match: `ai`
  - Multiple words (AND): `ai python`
  - Quoted phrases: `"machine learning"`
  - OR logic: `ai OR ml`
  - NOT logic: `ai -python`
  - **On-demand body loading**: Article content loaded only during search for efficiency
  - **Score-based sorting**: Results automatically sorted by relevance/quality/timeliness when searching
- **Date Filtering**: Filter articles by date range
- **Pagination**: Use arrow keys for selection, left/right keys for page navigation
- **Quick Open**: Press Enter to open article in browser
- **Theme Switching**: Support switching Textual built-in themes

### 4. Statistics and Management
- **Knowledge Base Statistics**: View total articles, summary count, failure records, etc.
- **Source Ranking**: View Top 10 article sources
- **Failure Report**: Generate OPML file for failed RSS feeds
- **Cache Cleanup**: Clean expired LLM cache files

---

## Technical Architecture

### Directory Structure

```
RSSTools/
├── rsstools/                 # Main package
│   ├── __init__.py          # Package exports
│   ├── config.py            # Configuration management
│   ├── cache.py             # LLM cache
│   ├── content.py           # Content preprocessing
│   ├── llm.py               # LLM client
│   ├── index.py             # Article index manager
│   ├── downloader.py        # RSS downloader
│   ├── reader.py            # TUI reader
│   ├── cli.py               # CLI command implementations
│   ├── utils.py             # Utility functions
│   └── rsstools.py          # CLI entry point
├── run.sh                   # Startup script
├── requirements.txt         # Dependencies
└── README.md                # User manual
```

### Core Modules

#### 1. Config (`config.py`)
- Default configuration definitions
- Load user config from `~/.rsstools/config.json`
- Environment variable override support
- Config merging logic

#### 2. LLM (`llm.py`)
- Multi-model fallback mechanism
- Request retry (exponential backoff)
- Local cache (based on SHA256)
- Serialized execution (avoid rate limiting)

#### 3. Cache (`cache.py`)
- File system cache
- Prompt hash-based keys
- Expiration time support
- Batch cleanup functionality

#### 4. Index (`index.py`)
- Article metadata management
- Deduplication check
- Failure records
- ETag management
- Statistics data

#### 5. Downloader (`downloader.py`)
- Async HTTP client
- Content extraction (Trafilatura/BeautifulSoup)
- Concurrency control (semaphore)
- Deduplication lock

#### 6. Reader (`reader.py`)
- Textual TUI framework
- Search and filtering
- Pagination navigation
- Nord theme

#### 7. Utils (`utils.py`)
- YAML escape/unescape
- OPML parsing
- Front matter handling
- Content extraction

### Data Flow

```
OPML File → FeedParser → RSS Entries
    ↓
IndexManager (Deduplication check)
    ↓
ArticleDownloader (Async download)
    ↓
Content Extractor (Body extraction)
    ↓
LLMClient (Summary + Scoring)
    ↓
Markdown File + Index.json
    ↓
TUI Reader (Browsing & Searching)
```

### Dependencies

- **aiohttp**: Async HTTP client
- **aiofiles**: Async file operations
- **feedparser**: RSS/Atom parsing
- **beautifulsoup4**: HTML parsing
- **trafilatura**: Content extraction (optional)
- **rich**: Terminal beautification
- **textual**: TUI framework
- **python-dateutil**: Date parsing

---

## Usage

### Installation

#### Method 1: Automatic Installation (Recommended)

```bash
# Clone or download the project
cd RSSTools

# Run directly, will automatically create virtual environment
./run.sh --help
```

The `run.sh` script will automatically:
1. Check if virtual environment exists
2. If not, create virtual environment
3. Install all dependencies
4. Activate virtual environment and execute command

#### Method 2: Manual Installation

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python -m rsstools.rsstools --help
```

### Configuration

#### Configuration File Location
Default config file: `~/.rsstools/config.json`

#### Default Configuration

```json
{
  "base_dir": "~/RSSKB",
  "opml_path": "~/RSSKB/subscriptions.opml",
  "llm": {
    "api_key": "your-api-key",
    "host": "https://api.z.ai/api/coding/paas/v4",
    "models": "glm-5,glm-4.7",
    "max_tokens": 2048,
    "temperature": 0.3,
    "max_content_chars": 10000,
    "request_delay": 0.5,
    "max_retries": 5,
    "timeout": 60,
    "system_prompt": "You are a helpful assistant that summarizes articles concisely.",
    "user_prompt": "Summarize this article in 2-3 sentences, in the same language as the article.\n\nTitle: {title}\n\n{content}"
  },
  "download": {
    "timeout": 15,
    "connect_timeout": 5,
    "max_retries": 3,
    "retry_delay": 2,
    "concurrent_downloads": 5,
    "concurrent_feeds": 3,
    "max_redirects": 5,
    "etag_max_age_days": 30,
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  },
  "summarize": {
    "save_every": 20
  }
}
```

#### Environment Variables

You can override configuration via environment variables:

```bash
export RSSKB_BASE_DIR="~/MyRSS"
export GLM_API_KEY="your-api-key"
export GLM_HOST="https://api.example.com/v4"
export GLM_MODELS="model1,model2"
export RSSKB_OPML_PATH="~/custom/subscriptions.opml"
```

### Command Reference

#### 1. Download Articles

```bash
# Download all new articles
./run.sh download

# Force re-download all articles (ignore deduplication)
./run.sh download --force
```

**Description**:
- Automatically read subscriptions from `opml_path`
- Support ETag/Last-Modified conditional requests
- Concurrent download of RSS feeds and articles
- Failed feeds will be retried after 24 hours
- Save to `articles/` directory after completion

#### 2. Generate Summaries

```bash
# Generate summaries for articles without summaries
./run.sh summarize

# Force re-summarize all articles
./run.sh summarize --force
```

**Description**:
- Use LLM to batch generate summaries (10 articles at a time)
- Automatically perform scoring and classification
- Save index every 20 articles processed
- Results cached in `.llm_cache/` directory

#### 3. View Statistics

```bash
./run.sh stats
```

**Output Example**:

```
          RSSKB Statistics
┌──────────────────┬───────────────┐
│ Total articles   │ 2299          │
│ With summary     │ 2295          │
│ Without summary  │ 4             │
│ Feed failures    │ 20            │
│ Article failures │ 67            │
│ Summary failures │ 4             │
│ Avg article size │ 12,452 bytes  │
│ Max article size │ 153,809 bytes │
│ Unique sources   │ 78            │
└──────────────────┴───────────────┘
                  Top 10 Sources
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Source                              ┃ Articles ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ Bert Hubert's writings              │      340 │
│ Paul Graham: Essays                 │      219 │
│ ...                                 │      ... │
└─────────────────────────────────────┴──────────┘
```

#### 4. Generate Failure Report

```bash
./run.sh failed
```

**Description**:
- Generate `failed_feeds.opml` file
- Include failed feeds and never-tried feeds
- Convenient for checking and fixing in RSS readers

#### 5. View Configuration

```bash
./run.sh config
```

**Description**:
- Display currently effective configuration
- Include default and user-customized configuration
- Display values overridden by environment variables

#### 6. Clean Cache

```bash
# Clean cache older than 30 days
./run.sh clean-cache

# Clean cache older than 7 days
./run.sh clean-cache --days 7

# Preview files to be deleted (without actually deleting)
./run.sh clean-cache --days 30 --dry-run
```

#### 7. TUI Reader

```bash
# Use default path (base_dir/index.json)
./run.sh reader

# Specify custom index file
./run.sh reader ~/custom/index.json
```

**TUI Interface Keyboard Shortcuts**:

| Key   | Function              |
|-------|-----------------------|
| `s`   | Open search box       |
| `d`   | Open date filter      |
| `c`   | Clear search filter   |
| `x`   | Clear date filter     |
| `r`   | Reset all filters    |
| `t`   | Switch theme         |
| `n` / `→` | Next page       |
| `p` / `←` | Previous page   |
| `↑` / `k` | Move up         |
| `↓` / `j` | Move down       |
| `Enter` | Open current article in browser |
| `q`   | Quit                  |
| `Esc`  | Close help palette/command palette |

**Article Display**:

Each article displays:
- Title with source and date
- URL
- **Category** (if available): One of ai-ml, security, engineering, tools, opinion, other
- **Scores** (if available): Relevance/Quality/Timeliness (1-10 each)
- **Keywords** (if available): 2-4 relevant keywords
- Summary

**Search Features**:

- `ai` - Search for articles containing "ai"
- `ai python` - Search for articles containing both "ai" and "python"
- `"machine learning"` - Search for phrase "machine learning"
- `ai OR ml` - Search for articles containing "ai" or "ml"
- `ai -python` - Search for articles containing "ai" but not "python"

**Search Scope**:

Searches across: title, summary, keywords, and article body (loaded on demand)

**Search Sorting**:

When searching, results are automatically sorted by article scores:
1. Relevance (highest first)
2. Quality (tie-breaker)
3. Timeliness (final tie-breaker)

**Date Filter**:

- Filter articles by date range
- Supports both start and end dates
- Optional defaults to min/max dates in database

---

## Workflow

### Typical Usage

1. **Prepare Subscription Sources**
   ```bash
   # Put your OPML file in the appropriate location
   cp my_feeds.opml ~/RSSKB/subscriptions.opml
   ```

2. **Download Articles**
   ```bash
   ./run.sh download
   ```

3. **Generate Summaries**
   ```bash
   ./run.sh summarize
   ```

4. **Browse Articles**
   ```bash
   ./run.sh reader
   ```

5. **Regular Updates**
   ```bash
   # Create a scheduled task (e.g., crontab)
   # Update daily at 3 AM
   0 3 * * * cd ~/RSSTools && ./run.sh download && ./run.sh summarize
   ```

---

## Advanced Usage

### Custom LLM Configuration

```json
{
  "llm": {
    "host": "https://your-api-endpoint.com/v1",
    "models": "gpt-4,gpt-3.5-turbo",
    "api_key": "your-key-here",
    "temperature": 0.7,
    "max_tokens": 4096,
    "system_prompt": "You are an expert technical writer. Summarize articles in Chinese.",
    "user_prompt": "Summarize this article in Chinese, highlighting key points.\n\nTitle: {title}\n\nContent: {content}"
  }
}
```

### Adjust Download Performance

```json
{
  "download": {
    "concurrent_downloads": 10,  // Increase concurrent downloads
    "concurrent_feeds": 5,        // Increase concurrent RSS feeds
    "timeout": 30,
    "max_retries": 5
  }
}
```

### Batch Import Articles

If you already have article Markdown files, you can manually add them using `IndexManager`:

```python
from rsstools import IndexManager

index = IndexManager("~/RSSKB")
index.add_article("https://example.com/article", {
    'title': 'My Article',
    'source_name': 'Blog',
    'published': '2024-01-01',
    'filepath': 'articles/blog/article.md',
    'summary': 'Article summary'
})
index.save()
```

---

## FAQ

### Q: How to switch LLM API?
A: Modify the `llm` configuration in `~/.rsstools/config.json`, or set environment variables:
```bash
export GLM_HOST="https://your-api.com/v1"
export GLM_API_KEY="your-key"
```

### Q: Download speed is slow?
A: Adjust concurrency configuration:
```json
{
  "download": {
    "concurrent_downloads": 10,
    "concurrent_feeds": 5
  }
}
```

### Q: Not satisfied with summary quality?
A: Customize prompts:
```json
{
  "llm": {
    "system_prompt": "You are a technical expert.",
    "user_prompt": "Summarize this article in Chinese, highlighting key points.\n\n{title}\n\n{content}"
  }
}
```

### Q: How to handle failed RSS feeds?
A: Run `./run.sh failed` to generate OPML, then check and fix source URLs in your RSS reader.

### Q: How to clean old articles?
A: Manually delete files in the `articles/` directory, then run `./run.sh stats` to view updated statistics.

### Q: Which OPML formats are supported?
A: Supports standard RSS/Atom OPML format, most RSS readers support exporting.

---

## Troubleshooting

### Problem: Virtual environment activation failed
**Solution**:
```bash
# Delete old environment
rm -rf venv

# Recreate
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Problem: LLM API call failed
**Solution**:
1. Check if API Key is correct
2. Check network connection
3. View error logs (console output)
4. Try switching to a different model

### Problem: Article content extraction failed
**Solution**:
1. Ensure `trafilatura` is installed
2. Some websites may have anti-crawling measures
3. Check the `download.log` file

### Problem: TUI shows garbled characters
**Solution**:
1. Ensure your terminal supports UTF-8
2. Switch terminal theme

---

## Performance Optimization

1. **Cache Optimization**: Regularly clean expired cache
   ```bash
   ./run.sh clean-cache --days 7
   ```

2. **Concurrency Tuning**: Adjust concurrency based on network conditions

3. **Model Selection**: Use faster models for summarization; complex scoring tasks can be processed separately

4. **Incremental Updates**: Avoid frequent use of the `--force` option

5. **TUI Reader Performance**: Efficient article browsing
   - **On-demand body loading**: Article content loaded only during search
   - **Fast startup**: Only metadata (title, summary, keywords) loaded at startup
   - **Low memory**: Suitable for collections of thousands of articles
   - **Quick search**: Pre-loaded fields (title, summary, keywords) provide instant matches
   - **Smart sorting**: Results automatically sorted by score during search

---

## License

This project is licensed under the MIT License.

---

## Contributing

Issues and Pull Requests are welcome!

---

## Changelog

### v2.0.0 (2026-02-18)
- Modular refactoring with clean architecture
- Integrated TUI reader with Nord theme
- Support for article scoring and classification
- Full-text search across title, summary, keywords, and body
- Score-based search result sorting
- On-demand article body loading for efficiency
- Enhanced TUI display with categories, scores, and keywords
- Optimized caching mechanism
- Improved error handling

**See detailed changelog**: [CHANGELOG.md](./CHANGELOG.md)

### v1.0.0
- Initial version
- Basic RSS download and summarization features

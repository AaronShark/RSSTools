# Scoring, Classification, and Keywords - Usage Guide

## Overview

RSSTools includes intelligent article analysis features that generate three types of metadata:

1. **Intelligent Scoring** - Three-dimensional quality assessment
2. **Auto Classification** - Automatic category assignment
3. **Keyword Extraction** - Relevant keyword identification

---

## Data Fields

### Intelligent Scoring

Articles are rated on three dimensions (1-10 scale):

| Field         | Description                              |
|---------------|-----------------------------------------|
| `score_relevance` | Value to tech professionals (1-10)  |
| `score_quality`   | Depth and writing quality (1-10)    |
| `score_timeliness` | Current relevance (1-10)            |

### Auto Classification

Articles are automatically classified into one of 6 categories:

| Category | Icon | Description                  |
|----------|-------|------------------------------|
| `ai-ml`    | 🤖    | AI and Machine Learning       |
| `security` | 🔒    | Security topics              |
| `engineering` | ⚙️   | Engineering and Development   |
| `tools`    | 🛠️    | Tools and Utilities          |
| `opinion`  | 💭    | Opinion pieces              |
| `other`    | 📄    | Other topics               |

### Keyword Extraction

Extract 2-4 relevant keywords for each article:

```json
{
  "keywords": ["machine learning", "Python", "data science"]
}
```

---

## Where Data is Generated

The data is generated in the **`summarize` command**:

```bash
./run.sh summarize
```

**Process flow**:
1. Download article content
2. Generate AI summary (2-3 sentences)
3. **Generate scores** (relevance, quality, timeliness)
4. **Determine category** (one of 6 categories)
5. **Extract keywords** (2-4 relevant terms)
6. Save all data to `index.json`

---

## Where Data is Used

### 1. Search Result Sorting

When you search in the TUI Reader, results are **automatically sorted by score**:

**Sorting priority**:
1. `score_relevance` (highest first)
2. `score_quality` (tie-breaker)
3. `score_timeliness` (final tie-breaker)

**Example**:

```bash
./run.sh reader
# Press 's' to search
# Enter: python

# Results are now sorted by score:
# 📊 Articles with high relevance scores appear first
# 📊 Within same relevance, higher quality scores come first
# 📊 Within same quality, higher timeliness scores come first
```

### 2. Search Scope Enhancement

Search now includes **keywords** in addition to title and summary:

**What's searched**:
- ✅ Article title
- ✅ Article summary
- ✅ **Keywords** (extracted by LLM)
- ✅ **Article body** (loaded on demand)

**Performance**:
- Body content is loaded **only when searching**, keeping memory usage low
- Keywords are pre-loaded from index.json for instant matching

---

## Technical Implementation

### Full-Text Search Architecture

The search system is designed for **memory efficiency** while supporting comprehensive search:

**Loading Strategy**:
```python
def _load_article_body(self, filepath: str) -> Optional[str]:
    """Load article body from file on demand"""
    # Only loaded during search, not at startup
    # Keeps memory usage low for large article collections
```

**Search Process**:
1. Build searchable text: title + summary + keywords (already in memory)
2. If no matches found in pre-loaded fields, load body from disk
3. Search across all fields with matching logic
4. Return matching articles

**Performance Characteristics**:
- Startup: Fast (only loads metadata from index.json)
- Search time: 10-50ms per article (disk I/O for body)
- Memory: Low (only one article body loaded at a time)

### Score-Based Sorting Algorithm

Articles are sorted using a **tuple-based comparison**:

```python
def _sort_articles_by_score(self, articles: List[Dict]) -> List[Dict]:
    return sorted(
        articles,
        key=lambda x: (
            x.get('score_relevance', 0) or 0,    # Primary sort
            x.get('score_quality', 0) or 0,       # Secondary sort
            x.get('score_timeliness', 0) or 0      # Tertiary sort
        ),
        reverse=True  # Descending order
    )
```

**Sorting Behavior**:
- Articles with no scores: Treated as (0, 0, 0), sorted to end
- Articles with partial scores: Missing scores default to 0
- All three scores required for optimal sorting position

### Search vs. No-Search Behavior

**With search query**:
```python
if self.search_query:
    filtered = [a for a in filtered if self._match_search(a, self.search_query)]
    filtered = self._sort_articles_by_score(filtered)  # Sort by score
```

**Without search query**:
```python
# Default behavior: sort by date (newest first)
self.articles = sorted(articles, key=lambda x: self._parse_date(x['published']), reverse=True)
```

**Date filter + search**:
- Date filter applied AFTER search matching
- Final results sorted by score, not date

---

## Where to View the Data

### 1. TUI Reader (Recommended)

**View in the terminal interface:**

```bash
./run.sh reader
```

Each article now displays:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
▶ 1. Article Title Here
  📅 Date: 2026-02-18 14:30  🌐 Source: Tech Blog
  🔗 URL: https://example.com/article
  🤖 Category: ai-ml
  📊 Scores: Relevance=8/10, Quality=7/10, Timeliness=9/10
  🏷️  Keywords: machine learning, AI, neural networks
  📝 Summary:
     This article discusses the latest advances in
     machine learning and their practical applications...
```

### 2. Raw Data in index.json

**Direct file access:**

```bash
cat ~/RSSKB/index.json | grep -A 20 "Article Title"
```

Example output:

```json
{
  "https://example.com/article": {
    "title": "Article Title",
    "published": "2026-02-18T14:30:00+00:00",
    "source_name": "Tech Blog",
    "summary": "Article summary text...",
    "category": "ai-ml",
    "score_relevance": 8,
    "score_quality": 7,
    "score_timeliness": 9,
    "keywords": ["machine learning", "AI", "neural networks"],
    "filepath": "articles/blog/article.md"
  }
}
```

### 3. Command Line Output

**During summarization process:**

```bash
./run.sh summarize
```

Console shows:

```
Done: 15, Remaining: 45, Failed: 0
    [green]OK[/green] Machine Learning Advances... [dim](ai-ml, 8/7/9)[/dim]
    [green]OK[/green] Python Best Practices... [dim](tools, 9/8/7)[/dim]
    [yellow]OK (no scores)[/yellow] Generic Article...
```

---

## Using the Data

### 1. Manual Filtering by Category

Use `jq` or Python to filter articles by category:

```bash
# Get all AI/ML articles
cat ~/RSSKB/index.json | jq '.articles | to_entries[] | select(.value.category == "ai-ml") | {title: .value.title, relevance: .value.score_relevance}'

# Get high-relevance articles (>= 7)
cat ~/RSSKB/index.json | jq '.articles | to_entries[] | select(.value.score_relevance >= 7) | .value.title'
```

### 2. Keyword Search

Search for articles with specific keywords:

```bash
# Find articles containing "machine learning"
cat ~/RSSKB/index.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
for url, info in d['articles'].items():
    if any('machine learning' in str(k).lower() for k in info.get('keywords', [])):
        print(f\"{info['title'][:60]}: {url}\")
"
```

### 3. Export to CSV

Export articles with scores to CSV for analysis:

```bash
cat ~/RSSKB/index.json | python3 -c "
import sys, json, csv
d = json.load(sys.stdin)
with open('articles_scores.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Title', 'Category', 'Relevance', 'Quality', 'Timeliness', 'Keywords'])
    for url, info in d['articles'].items():
        if info.get('category'):
            writer.writerow([
                info['title'][:50],
                info['category'],
                info.get('score_relevance', ''),
                info.get('score_quality', ''),
                info.get('score_timeliness', ''),
                ', '.join(info.get('keywords', []))
            ])
"
```

---

## Customization

### Modify Scoring Prompts

Edit `~/.rsstools/config.json`:

```json
{
  "llm": {
    "user_prompt": "Rate this article for software developers (1-10):\n- relevance: Business value\n- quality: Technical depth\n- timeliness: Current market relevance\n\nClassify into: startup, product, engineering, design, research, other\n\nExtract 3-5 keywords.\n\nTitle: {title}\n\nContent: {content}"
  }
}
```

### Custom Categories

Modify the `score_and_classify()` method in `rsstools/llm.py` to use your own category set.

---

## Troubleshooting

### No scores displayed in TUI?

**Cause**: Articles were summarized before scoring was implemented, or scoring failed.

**Solution**:

```bash
# Re-summarize with --force to regenerate scores
./run.sh summarize --force
```

### Scores showing "N/A"?

**Cause**: LLM API call failed during scoring phase.

**Solution**:

1. Check your API key and rate limits
2. Re-run summarize command
3. Check `~/RSSKB/.llm_cache/` for cached results

### Wrong categories assigned?

**Cause**: Category definitions in prompt don't match your content.

**Solution**:

Customize the classification prompt in `~/.rsstools/config.json`:

```json
{
  "llm": {
    "system_prompt": "You are an expert in technology classification."
  }
}
```

### Search is slow?

**Cause**: Searching many articles with body loading.

**Solution**:

Search performance depends on:
- Number of matching articles (body loaded for each)
- Article file size (larger = slower)
- Disk speed

**Optimizations**:
- Keywords and metadata are pre-loaded (instant search)
- Body loaded only when needed
- For better performance, search with specific terms first, then broader terms

### Search not finding articles?

**Cause**: Search terms only in body, and body loading failed.

**Solution**:

1. Check if article files exist:
   ```bash
   ls ~/RSSKB/articles/
   ```

2. Verify keywords were generated:
   ```bash
   cat ~/RSSKB/index.json | python3 -c "import sys, json; d=json.load(sys.stdin); print(len([a for a in d['articles'].values() if a.get('keywords')]))"
   ```

3. Re-run summarize if keywords missing:
   ```bash
   ./run.sh summarize --force
   ```

### Results not sorted by score?

**Cause**: No search query entered (results sorted by date by default).

**Solution**:

Search results are only sorted by score when you enter a search query. Without search, results are sorted by date (newest first).

**To sort by score without filtering**:
- Enter a broad search term like "article" or "content"
- This will match most articles and sort them by score

---

## Future Enhancements

Potential improvements for using this data:

1. ~~**Score sorting**~~ ✅ **Implemented** - Sort articles by relevance/quality/timeliness when searching
2. ~~**Keyword-based search**~~ ✅ **Implemented** - Search across title, summary, keywords, and body
3. **Category filtering in TUI** - Filter articles by category with keyboard shortcuts
4. **Statistics by category** - Show article count per category
5. **Score distribution** - Visual distribution of scores across articles
6. **Trending topics** - Most common keywords over time
7. **Advanced search filters** - Filter by score range, category, etc.

---

## Data Integrity

The scoring and classification data is stored in `index.json` alongside other article metadata:

```json
{
  "articles": {
    "https://example.com/article": {
      "title": "...",
      "summary": "...",
      "category": "ai-ml",
      "score_relevance": 8,
      "score_quality": 7,
      "score_timeliness": 9,
      "keywords": ["AI", "ML"],
      ...
    }
  }
}
```

**Backup recommendation**:

```bash
# Regularly backup index.json
cp ~/RSSKB/index.json ~/RSSKB/index.json.backup
```

---

## API Reference

### Article Data Structure

```python
{
    'url': str,                    # Article URL (key)
    'title': str,                  # Article title
    'published': str,              # ISO date string
    'source_name': str,            # RSS source name
    'summary': str,                # AI-generated summary
    'category': str,               # One of: ai-ml, security, engineering, tools, opinion, other
    'score_relevance': int,        # 1-10
    'score_quality': int,           # 1-10
    'score_timeliness': int,        # 1-10
    'keywords': List[str],         # 2-4 keywords
    'filepath': str,               # Relative path to .md file
    'content_source': str,          # 'page' or 'feed'
    'downloaded': str,             # ISO timestamp
    'feed_url': str               # RSS feed URL
}
```

---

## Summary

| Feature | Command to Generate | Where to View |
|----------|-------------------|----------------|
| **Scores** | `./run.sh summarize` | TUI Reader (📊 line), index.json |
| **Category** | `./run.sh summarize` | TUI Reader (🤖 line), index.json |
| **Keywords** | `./run.sh summarize` | TUI Reader (🏷️ line), index.json |

**Note**: These features require an LLM API key. Set via `~/.rsstools/config.json` or `GLM_API_KEY` environment variable.

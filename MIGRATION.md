# Migration Guide: v2 to v3

This guide explains how to migrate from RSSTools v2 (index.json) to v3 (SQLite).

## Overview

v3.0 replaces the JSON-based index with SQLite database for better performance, reliability, and search capabilities.

### What Changes

| Component | v2 | v3 |
|-----------|----|----|
| Article metadata | `index.json` | `rsstools.db` (SQLite) |
| Search | In-memory filtering | FTS5 full-text search |
| Reader data source | `index.json` path | `base_dir` |
| Storage format | JSON objects | SQL tables + FTS5 |

### What Stays the Same

- Article Markdown files in `articles/` directory
- LLM cache in `.llm_cache/` directory
- Configuration file `~/.rsstools/config.json`
- OPML subscription file

## Prerequisites

1. **Backup your data** (see below)
2. Ensure you have `index.json` in your base directory
3. Install v3 dependencies: `pip install aiosqlite`

## Backup Instructions

Before migrating, create a backup of your data:

```bash
# Create backup directory
BACKUP_DIR=~/RSSKB_backup_$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"

# Backup index.json
cp ~/RSSKB/index.json "$BACKUP_DIR/"

# Backup articles (optional but recommended)
cp -r ~/RSSKB/articles "$BACKUP_DIR/"

# Backup LLM cache (optional)
cp -r ~/RSSKB/.llm_cache "$BACKUP_DIR/"

# Backup configuration
cp ~/.rsstools/config.json "$BACKUP_DIR/"
```

## Migration Steps

### Step 1: Verify v2 Data

Check your current data:

```bash
# Check index.json exists and has articles
cat ~/RSSKB/index.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Articles: {len(d.get(\"articles\", {}))}')"
```

### Step 2: Dry Run (Recommended)

Preview what will be migrated without making changes:

```bash
cd RSSTools
./run.sh migrate --dry-run
```

Output example:
```
DRY RUN - no changes will be made

Migrating articles...
Articles migrated: 2299
Feed failures migrated: 20
Article failures migrated: 67
Summary failures migrated: 4
Feed ETags migrated: 45
Errors: 0
```

### Step 3: Run Migration

Execute the actual migration:

```bash
./run.sh migrate
```

This will:
1. Read `index.json` from your base directory
2. Create `rsstools.db` SQLite database
3. Migrate all articles, failures, and ETags
4. Show a summary of migrated items

### Step 4: Verify Migration

Verify the migration was successful:

```bash
./run.sh migrate --verify
```

Output example:
```
Verification Results
┌─────────────────┬───────┐
│ Index articles  │ 2299  │
│ DB articles     │ 2299  │
│ Match           │ True  │
│ Status          │ PASS  │
└─────────────────┴───────┘
```

### Step 5: Test the Reader

Verify the reader works with the new database:

```bash
./run.sh reader
```

The reader should load and display your articles.

## Post-Migration

### What to Keep

- **Keep**: `index.json` (as backup, can delete after verification)
- **Keep**: `articles/` directory (Markdown files)
- **Keep**: `.llm_cache/` directory

### What is Now Unused

- `index.json` - No longer used, kept for backup

### Database Location

The SQLite database is located at:
```
{base_dir}/rsstools.db
```

Default: `~/RSSKB/rsstools.db`

## Troubleshooting

### Error: index.json not found

**Symptom**: `Error: index.json not found at /path/to/index.json`

**Solution**: Ensure `base_dir` in your config points to the correct directory containing `index.json`:

```bash
# Check your config
./run.sh config | grep base_dir

# Or check directly
ls ~/RSSKB/index.json
```

### Error: Database locked

**Symptom**: `database is locked` error during migration

**Solution**: Ensure no other RSSTools processes are running:

```bash
# Kill any running instances
pkill -f rsstools

# Then retry migration
./run.sh migrate
```

### Error: Articles missing after migration

**Symptom**: Verification shows missing URLs

**Solution**: Check for corrupted entries in `index.json`:

```bash
# Check for articles with missing required fields
cat ~/RSSKB/index.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for url, meta in data.get('articles', {}).items():
    if not meta.get('title') or not meta.get('source_name'):
        print(f'Incomplete: {url}')
"
```

### Reader shows 0 articles

**Symptom**: Reader launches but shows no articles

**Solution**: 
1. Verify database exists: `ls ~/RSSKB/rsstools.db`
2. Verify database has articles: `./run.sh stats`
3. Check database integrity:
   ```bash
   sqlite3 ~/RSSKB/rsstools.db "SELECT COUNT(*) FROM articles;"
   ```

### Rollback to v2

If you need to rollback:

1. The original `index.json` is preserved
2. Simply use v2 code to read `index.json`
3. Delete `rsstools.db` if desired

```bash
# Remove v3 database
rm ~/RSSKB/rsstools.db

# Restore from backup if needed
cp ~/RSSKB_backup_YYYYMMDD/index.json ~/RSSKB/
```

## Migration Command Reference

```bash
# Preview migration (no changes)
./run.sh migrate --dry-run

# Run migration
./run.sh migrate

# Verify migration
./run.sh migrate --verify

# Direct module invocation
python -m rsstools.migrate ~/RSSKB --dry-run
python -m rsstools.migrate ~/RSSKB --verify
```

## Technical Details

### Data Migrated

| Source (index.json) | Destination (SQLite) |
|--------------------|---------------------|
| `articles` | `articles` table + `articles_fts` |
| `feed_failures` | `feed_failures` table |
| `article_failures` | `article_failures` table |
| `summary_failures` | `summary_failures` table |
| `feed_etags` | `feed_etags` table |

### FTS5 Search

The migration creates an FTS5 virtual table for full-text search:

```sql
CREATE VIRTUAL TABLE articles_fts USING fts5(
    title, summary, body, keywords,
    content='articles',
    tokenize='porter unicode61'
);
```

This enables:
- BM25-ranked search results
- Porter stemming for better matching
- Unicode support for international content

## Need Help?

1. Check the [ARCHITECTURE.md](./ARCHITECTURE.md) for technical details
2. Run `./run.sh health` to check system status
3. Check logs for errors during migration

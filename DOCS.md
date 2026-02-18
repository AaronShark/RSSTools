# RSSTools Documentation Index

## Overview

RSSTools is a comprehensive RSS article management and knowledge base tool with AI-powered summarization, intelligent scoring, and a beautiful TUI reader.

## Core Documentation

### 📖 [README.md](./README.md)
**User Manual and Getting Started Guide**

Complete guide for using RSSTools:
- Installation and setup
- Feature overview
- Command reference
- TUI Reader usage
- Advanced configuration
- Troubleshooting
- Performance optimization

**Best for**: New users, installation, basic usage

---

### 📊 [SCORING_GUIDE.md](./SCORING_GUIDE.md)
**Scoring, Classification, and Keywords - Usage Guide**

Detailed documentation of intelligent article analysis:
- Score dimensions (relevance, quality, timeliness)
- Auto classification (6 categories)
- Keyword extraction
- Where data is generated
- Where data is used (search, display)
- Manual data filtering and export
- API reference

**Best for**: Understanding AI analysis features, data usage

---

### 📝 [CHANGELOG.md](./CHANGELOG.md)
**Version History and Change Log**

Complete record of changes:
- New features
- Technical details
- Usage examples
- Performance improvements
- Backward compatibility notes

**Best for**: Tracking features, upgrading, understanding changes

---

## Quick Links

### Installation

1. **Automatic Setup** (Recommended)
   ```bash
   ./run.sh --help
   ```

2. **Manual Setup**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### Quick Start

1. **Download Articles**
   ```bash
   ./run.sh download
   ```

2. **Generate Summaries & Scores**
   ```bash
   ./run.sh summarize
   ```

3. **Browse with TUI**
   ```bash
   ./run.sh reader
   ```

### Key Features

| Feature | Documentation | Command |
|----------|----------------|----------|
| RSS Download | [README.md](./README.md#download-articles) | `./run.sh download` |
| AI Summarization | [README.md](./README.md#generate-summaries) | `./run.sh summarize` |
| TUI Reader | [README.md](./README.md#tui-reader) | `./run.sh reader` |
| Scoring & Classification | [SCORING_GUIDE.md](./SCORING_GUIDE.md) | Auto-generated |
| Search (Full-Text) | [README.md](./README.md#tui-reader) | Press `s` in TUI |
| Statistics | [README.md](./README.md#view-statistics) | `./run.sh stats` |

---

## Documentation by Topic

### Configuration

- **Setup**: [README.md - Installation](./README.md#installation)
- **Config File**: [README.md - Configuration](./README.md#configuration)
- **Environment Variables**: [README.md - Configuration](./README.md#configuration)
- **Custom LLM**: [README.md - Advanced Usage](./README.md#advanced-usage)

### Commands

- **Download**: [README.md - Download Articles](./README.md#download-articles)
- **Summarize**: [README.md - Generate Summaries](./README.md#generate-summaries)
- **Stats**: [README.md - View Statistics](./README.md#view-statistics)
- **Failed Feeds**: [README.md - Generate Failure Report](./README.md#generate-failure-report)
- **Clean Cache**: [README.md - Clean Cache](./README.md#clean-cache)
- **Reader**: [README.md - TUI Reader](./README.md#tui-reader)

### TUI Reader

- **Interface Overview**: [README.md - TUI Reader](./README.md#3-tui-reader)
- **Keyboard Shortcuts**: [README.md - TUI Reader](./README.md#tui-reader-1)
- **Search Syntax**: [README.md - TUI Reader](./README.md#tui-reader-1)
- **Score Display**: [SCORING_GUIDE.md - Where to View](./SCORING_GUIDE.md#1-tui-reader-recommended)

### AI Features

- **Scoring**: [SCORING_GUIDE.md - Data Fields](./SCORING_GUIDE.md#data-fields)
- **Classification**: [SCORING_GUIDE.md - Data Fields](./SCORING_GUIDE.md#data-fields)
- **Keywords**: [SCORING_GUIDE.md - Data Fields](./SCORING_GUIDE.md#data-fields)
- **Search Integration**: [SCORING_GUIDE.md - Where Data is Used](./SCORING_GUIDE.md#where-data-is-used)

### Performance

- **Optimization Tips**: [README.md - Performance](./README.md#performance-optimization)
- **Search Performance**: [CHANGELOG.md - Performance](./CHANGELOG.md#performance-considerations)
- **Technical Details**: [SCORING_GUIDE.md - Technical Implementation](./SCORING_GUIDE.md#technical-implementation)

---

## Architecture

### Project Structure

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
│   ├── cli.py               # CLI commands
│   └── utils.py             # Utilities
├── run.sh                   # Startup script
├── requirements.txt         # Dependencies
├── README.md               # User manual
├── SCORING_GUIDE.md       # Scoring guide
├── CHANGELOG.md            # Version history
└── DOCS.md                # This file
```

### Data Flow

1. **OPML** → RSS Feeds → Articles
2. **Articles** → LLM → Summaries + Scores + Keywords
3. **Articles + Scores** → index.json
4. **index.json** → TUI Reader → Search & Browse

---

## Getting Help

### Documentation

- 📖 **User Manual**: [README.md](./README.md)
- 📊 **Scoring Guide**: [SCORING_GUIDE.md](./SCORING_GUIDE.md)
- 📝 **Changelog**: [CHANGELOG.md](./CHANGELOG.md)

### Command Help

```bash
# Show all commands
./run.sh --help

# Show command-specific help
./run.sh download --help
./run.sh summarize --help
./run.sh reader --help
```

### Troubleshooting

- [FAQ](./README.md#faq)
- [Troubleshooting](./README.md#troubleshooting)
- [Scoring Issues](./SCORING_GUIDE.md#troubleshooting)

---

## Contributing

Contributions are welcome! Please see:
- [Contributing Guide](./README.md#contributing)
- [Changelog](./CHANGELOG.md) for recent changes
- [Issue Tracker](./README.md#contributing) for reporting bugs

---

## Version Information

**Current Version**: v2.0.0 (2026-02)
**Latest Release**: [See CHANGELOG.md](./CHANGELOG.md)

---

## License

This project is licensed under the MIT License.

---

## Quick Reference

### Common Tasks

| Task | Command | Documentation |
|------|----------|----------------|
| Initial setup | `./run.sh --help` | [Installation](./README.md#installation) |
| Download articles | `./run.sh download` | [Download](./README.md#download-articles) |
| Generate summaries | `./run.sh summarize` | [Summarize](./README.md#generate-summaries) |
| Browse articles | `./run.sh reader` | [Reader](./README.md#tui-reader) |
| View statistics | `./run.sh stats` | [Stats](./README.md#view-statistics) |
| Clean cache | `./run.sh clean-cache` | [Clean](./README.md#clean-cache) |

### Key Files

| File | Purpose | Documentation |
|------|---------|----------------|
| `~/.rsstools/config.json` | User configuration | [Configuration](./README.md#configuration) |
| `~/RSSKB/index.json` | Article index | [Data Structure](./SCORING_GUIDE.md#api-reference) |
| `~/RSSKB/articles/` | Article files | [File Structure](./README.md#technical-architecture) |

---

## Documentation Maintenance

This documentation is actively maintained and updated with each release.

**Last Updated**: 2026-02-18
**Documentation Version**: v2.0.0

For questions or issues, please refer to:
- [README.md - Troubleshooting](./README.md#troubleshooting)
- [SCORING_GUIDE.md - Troubleshooting](./SCORING_GUIDE.md#troubleshooting)
- [README.md - FAQ](./README.md#faq)

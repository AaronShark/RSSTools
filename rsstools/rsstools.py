#!/usr/bin/env python3
"""
RSSKB - RSS Knowledge Base Tool

Unified CLI for RSS article management:
  download   - Download articles from RSS feeds
  summarize  - Batch generate AI summaries
  failed     - Generate OPML for failed feeds
  stats      - Show knowledge base statistics
  config     - Show current configuration
  clean-cache- Clean old cached LLM results
  reader     - Launch TUI reader
  migrate    - Migrate data from index.json to SQLite
"""

import argparse
import asyncio
import os
import sys

from rsstools.cli import (
    cmd_clean_cache,
    cmd_config,
    cmd_download,
    cmd_failed,
    cmd_health,
    cmd_migrate,
    cmd_stats,
    cmd_summarize,
)
from rsstools.config import load_config
from rsstools.reader import run_reader


def main():
    parser = argparse.ArgumentParser(
        description="RSSKB - RSS Knowledge Base Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # download command
    dl_parser = subparsers.add_parser("download", help="Download articles from RSS feeds")
    dl_parser.add_argument(
        "-f", "--force", action="store_true", help="Force re-download all articles"
    )

    # summarize command
    sum_parser = subparsers.add_parser("summarize", help="Batch generate AI summaries")
    sum_parser.add_argument(
        "-f", "--force", action="store_true", help="Force re-summarize all articles"
    )

    # failed command
    subparsers.add_parser("failed", help="Generate OPML for failed feeds")

    # stats command
    subparsers.add_parser("stats", help="Show knowledge base statistics")

    # config command
    subparsers.add_parser("config", help="Show current configuration")

    # clean-cache command
    cc_parser = subparsers.add_parser("clean-cache", help="Clean old cached LLM results")
    cc_parser.add_argument("--days", type=int, default=30, help="Cache age in days (default: 30)")
    cc_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )

    # health command
    subparsers.add_parser("health", help="Check system health")

    # reader command
    subparsers.add_parser("reader", help="Launch TUI reader")

    # migrate command
    mig_parser = subparsers.add_parser("migrate", help="Migrate data from index.json to SQLite")
    mig_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing",
    )
    mig_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration integrity",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    cfg = load_config()

    if args.command == "download":
        asyncio.run(cmd_download(cfg, force=args.force))
    elif args.command == "summarize":
        asyncio.run(cmd_summarize(cfg, force=args.force))
    elif args.command == "failed":
        asyncio.run(cmd_failed(cfg))
    elif args.command == "stats":
        asyncio.run(cmd_stats(cfg))
    elif args.command == "config":
        cmd_config(cfg)
    elif args.command == "clean-cache":
        cmd_clean_cache(cfg, max_age_days=args.days, dry_run=args.dry_run)
    elif args.command == "health":
        healthy = asyncio.run(cmd_health(cfg))
        sys.exit(0 if healthy else 1)
    elif args.command == "reader":
        run_reader(cfg["base_dir"])
    elif args.command == "migrate":
        cmd_migrate(cfg, dry_run=args.dry_run, verify=args.verify)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

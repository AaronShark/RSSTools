"""Data migration tool: index.json + markdown files to SQLite."""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)
from rich.table import Table

from .database import Database
from .logging_config import get_logger
from .utils import extract_front_matter

console = Console()
logger = get_logger(__name__)


async def migrate(base_dir: str, db_path: str, dry_run: bool = False) -> dict[str, Any]:
    """
    Migrate data from index.json + markdown files to SQLite.
    
    Args:
        base_dir: Directory containing index.json and articles
        db_path: Path to SQLite database file
        dry_run: If True, show what would be migrated without writing
    
    Returns:
        Dict with migration stats: articles_migrated, failures_migrated, errors
    """
    index_path = os.path.join(base_dir, "index.json")
    
    if not os.path.exists(index_path):
        logger.error("migration_failed", reason="index_not_found", path=index_path)
        return {"error": f"index.json not found at {index_path}"}
    
    with open(index_path, encoding="utf-8") as f:
        index_data = json.load(f)
    
    articles = index_data.get("articles", {})
    feed_failures = index_data.get("feed_failures", {})
    article_failures = index_data.get("article_failures", {})
    summary_failures = index_data.get("summary_failures", {})
    feed_etags = index_data.get("feed_etags", {})
    
    stats = {
        "articles_migrated": 0,
        "articles_skipped": 0,
        "feed_failures_migrated": 0,
        "article_failures_migrated": 0,
        "summary_failures_migrated": 0,
        "feed_etags_migrated": 0,
        "errors": [],
    }
    
    if dry_run:
        console.print("[yellow]DRY RUN - no changes will be made[/yellow]\n")
        db = None
    else:
        db = Database(db_path)
        await db.connect()
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Migrating articles", total=len(articles))
            
            for url, meta in articles.items():
                try:
                    filepath = meta.get("filepath")
                    body = None
                    
                    if filepath:
                        full_path = os.path.join(base_dir, filepath)
                        if os.path.exists(full_path):
                            with open(full_path, encoding="utf-8") as f:
                                content = f.read()
                            fm, body_text = extract_front_matter(content)
                            body = body_text.strip() if body_text else None
                        else:
                            stats["errors"].append(f"File not found: {full_path}")
                    
                    article_data = {
                        "url": url,
                        "title": meta.get("title", "Unknown"),
                        "source_name": meta.get("source_name", "Unknown"),
                        "feed_url": meta.get("feed_url"),
                        "published": meta.get("published"),
                        "downloaded": meta.get("downloaded"),
                        "filepath": meta.get("filepath"),
                        "content_source": meta.get("content_source"),
                        "summary": meta.get("summary"),
                        "body": body,
                        "category": meta.get("category"),
                        "score_relevance": meta.get("score_relevance"),
                        "score_quality": meta.get("score_quality"),
                        "score_timeliness": meta.get("score_timeliness"),
                        "keywords": meta.get("keywords"),
                    }
                    
                    if dry_run:
                        stats["articles_migrated"] += 1
                    else:
                        existing = await db.get_article(url)
                        if existing:
                            await db.update_article(url, article_data)
                            stats["articles_skipped"] += 1
                        else:
                            await db.add_article(article_data)
                            stats["articles_migrated"] += 1
                    
                except Exception as e:
                    error_msg = f"Article {url}: {str(e)}"
                    stats["errors"].append(error_msg)
                    logger.error("migration_article_error", url=url, error=str(e))
                
                progress.advance(task_id)
        
        if not dry_run:
            console.print("\nMigrating failures and etags...")
            
            for url, info in feed_failures.items():
                try:
                    await db.record_feed_failure(url, info.get("error", "Unknown"))
                    stats["feed_failures_migrated"] += 1
                except Exception as e:
                    stats["errors"].append(f"Feed failure {url}: {str(e)}")
            
            for url, info in article_failures.items():
                try:
                    await db.record_article_failure(url, info.get("error", "Unknown"))
                    stats["article_failures_migrated"] += 1
                except Exception as e:
                    stats["errors"].append(f"Article failure {url}: {str(e)}")
            
            for url, info in summary_failures.items():
                try:
                    await db.record_summary_failure(
                        url,
                        info.get("title", ""),
                        info.get("filepath", ""),
                        info.get("error", "Unknown"),
                    )
                    stats["summary_failures_migrated"] += 1
                except Exception as e:
                    stats["errors"].append(f"Summary failure {url}: {str(e)}")
            
            for url, info in feed_etags.items():
                try:
                    await db.set_feed_etag(
                        url,
                        info.get("etag", ""),
                        info.get("last_modified", ""),
                    )
                    stats["feed_etags_migrated"] += 1
                except Exception as e:
                    stats["errors"].append(f"Feed etag {url}: {str(e)}")
        else:
            stats["feed_failures_migrated"] = len(feed_failures)
            stats["article_failures_migrated"] = len(article_failures)
            stats["summary_failures_migrated"] = len(summary_failures)
            stats["feed_etags_migrated"] = len(feed_etags)
        
        logger.info(
            "migration_complete",
            articles=stats["articles_migrated"],
            errors=len(stats["errors"]),
        )
        
        return stats
        
    finally:
        if db:
            await db.close()


async def verify_migration(base_dir: str, db_path: str) -> dict[str, Any]:
    """
    Verify migration integrity.
    
    Returns:
        Dict with verification results
    """
    index_path = os.path.join(base_dir, "index.json")
    
    if not os.path.exists(index_path):
        return {"error": f"index.json not found at {index_path}"}
    
    if not os.path.exists(db_path):
        return {"error": f"Database not found at {db_path}"}
    
    with open(index_path, encoding="utf-8") as f:
        index_data = json.load(f)
    
    articles = index_data.get("articles", {})
    
    db = Database(db_path)
    await db.connect()
    
    try:
        db_stats = await db.get_stats()
        
        verification = {
            "index_articles": len(articles),
            "db_articles": db_stats["total_articles"],
            "match": len(articles) == db_stats["total_articles"],
            "missing_urls": [],
            "extra_urls": [],
        }
        
        for url in articles:
            if not await db.article_exists(url):
                verification["missing_urls"].append(url)
        
        if verification["match"] and not verification["missing_urls"]:
            verification["status"] = "PASS"
        else:
            verification["status"] = "FAIL"
        
        return verification
        
    finally:
        await db.close()


def cmd_migrate(cfg: dict, dry_run: bool = False, verify: bool = False):
    """CLI command for migration."""
    base_dir = cfg["base_dir"]
    db_path = os.path.join(base_dir, "rsskb.db")
    
    if verify:
        console.print("[cyan]Verifying migration...[/cyan]\n")
        result = asyncio.run(verify_migration(base_dir, db_path))
        
        if "error" in result:
            console.print(f"[red]Error: {result['error']}[/red]")
            return
        
        table = Table(title="Verification Results", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Index articles", str(result["index_articles"]))
        table.add_row("DB articles", str(result["db_articles"]))
        table.add_row("Match", str(result["match"]))
        table.add_row("Status", result["status"])
        
        if result["missing_urls"]:
            console.print(f"\n[yellow]Missing URLs ({len(result['missing_urls'])}):[/yellow]")
            for url in result["missing_urls"][:10]:
                console.print(f"  - {url}")
            if len(result["missing_urls"]) > 10:
                console.print(f"  ... and {len(result['missing_urls']) - 10} more")
        
        console.print(table)
        return
    
    console.print(f"[cyan]Migrating from {base_dir} to {db_path}[/cyan]\n")
    
    result = asyncio.run(migrate(base_dir, db_path, dry_run=dry_run))
    
    if "error" in result:
        console.print(f"[red]Error: {result['error']}[/red]")
        return
    
    table = Table(title="Migration Summary", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Articles migrated", str(result["articles_migrated"]))
    table.add_row("Articles skipped (existing)", str(result["articles_skipped"]))
    table.add_row("Feed failures migrated", str(result["feed_failures_migrated"]))
    table.add_row("Article failures migrated", str(result["article_failures_migrated"]))
    table.add_row("Summary failures migrated", str(result["summary_failures_migrated"]))
    table.add_row("Feed ETags migrated", str(result["feed_etags_migrated"]))
    table.add_row("Errors", str(len(result["errors"])))
    
    console.print(table)
    
    if result["errors"]:
        console.print(f"\n[yellow]Errors ({len(result['errors'])}):[/yellow]")
        for err in result["errors"][:10]:
            console.print(f"  - {err}")
        if len(result["errors"]) > 10:
            console.print(f"  ... and {len(result['errors']) - 10} more")


def main():
    """CLI entry point for python -m rsstools.migrate."""
    parser = argparse.ArgumentParser(description="Migrate data from index.json to SQLite")
    parser.add_argument("base_dir", nargs="?", default=".", help="Base directory containing index.json")
    parser.add_argument("--db", default=None, help="Path to SQLite database (default: base_dir/rsskb.db)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without writing")
    parser.add_argument("--verify", action="store_true", help="Verify migration integrity")
    
    args = parser.parse_args()
    
    base_dir = os.path.abspath(args.base_dir)
    db_path = args.db or os.path.join(base_dir, "rsskb.db")
    
    if args.verify:
        console.print("[cyan]Verifying migration...[/cyan]\n")
        result = asyncio.run(verify_migration(base_dir, db_path))
        
        if "error" in result:
            console.print(f"[red]Error: {result['error']}[/red]")
            sys.exit(1)
        
        table = Table(title="Verification Results", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Index articles", str(result["index_articles"]))
        table.add_row("DB articles", str(result["db_articles"]))
        table.add_row("Match", str(result["match"]))
        table.add_row("Status", result["status"])
        console.print(table)
        
        if result["status"] == "FAIL":
            sys.exit(1)
        return
    
    console.print(f"[cyan]Migrating from {base_dir} to {db_path}[/cyan]\n")
    
    result = asyncio.run(migrate(base_dir, db_path, dry_run=args.dry_run))
    
    if "error" in result:
        console.print(f"[red]Error: {result['error']}[/red]")
        sys.exit(1)
    
    table = Table(title="Migration Summary", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Articles migrated", str(result["articles_migrated"]))
    table.add_row("Articles skipped (existing)", str(result["articles_skipped"]))
    table.add_row("Feed failures migrated", str(result["feed_failures_migrated"]))
    table.add_row("Article failures migrated", str(result["article_failures_migrated"]))
    table.add_row("Summary failures migrated", str(result["summary_failures_migrated"]))
    table.add_row("Feed ETags migrated", str(result["feed_etags_migrated"]))
    table.add_row("Errors", str(len(result["errors"])))
    console.print(table)
    
    if result["errors"]:
        console.print(f"\n[yellow]Errors ({len(result['errors'])}):[/yellow]")
        for err in result["errors"][:10]:
            console.print(f"  - {err}")


if __name__ == "__main__":
    main()

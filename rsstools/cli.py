"""CLI commands for RSSTools"""

import asyncio
import os
from html import escape as html_escape

import aiofiles
import aiohttp
import feedparser
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)
from rich.table import Table

from .cache import LLMCache
from .context import set_correlation_id
from .downloader import ArticleDownloader
from .index import IndexManager
from .llm import LLMClient
from .logging_config import get_logger
from .utils import extract_front_matter, parse_opml, rebuild_front_matter

console = Console()
logger = get_logger(__name__)


async def cmd_download(cfg: dict, force: bool = False):
    """Download articles from RSS feeds."""
    set_correlation_id()
    base_dir = cfg["base_dir"]
    opml_path = cfg["opml_path"]
    index = IndexManager(base_dir)
    cache = LLMCache(os.path.join(base_dir, ".llm_cache"))
    llm = LLMClient(cfg["llm"], cache)

    if not llm.enabled:
        logger.warning("llm_disabled", reason="api_key_not_set")
        console.print("[yellow]LLM api_key not set, summaries will be skipped[/yellow]")

    logger.info("download_started", feed_count=len(parse_opml(opml_path)))
    console.print(Panel.fit("RSSKB - Download Articles", style="bold blue"))
    feeds = parse_opml(opml_path)
    if not feeds:
        console.print("[red]No feeds found[/red]")
        return
    console.print(f"Found {len(feeds)} feeds")

    downloader = ArticleDownloader(cfg, index, llm, force=force)
    concurrent_feeds = cfg["download"]["concurrent_feeds"]
    etag_max_age = cfg["download"].get("etag_max_age_days", 30)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=10, force_close=True)
    ) as session:
        sem = asyncio.Semaphore(concurrent_feeds)

        async def process_feed(feed, idx):
            async with sem:
                tag = feed["title"][:25]
                console.print(f"\n[{idx}/{len(feeds)}] {feed['title']}")
                url = feed["url"]
                if not force and index.should_skip_feed(url, cfg["download"]["max_retries"]):
                    console.print(
                        f"  [{tag}] [yellow]Skipped (previously failed, retry after 24h)[/yellow]"
                    )
                    return
                try:
                    # Build conditional request headers from cached ETag/Last-Modified
                    etag_info = index.get_feed_etag(url, max_age_days=etag_max_age)
                    cond_headers = {}
                    if etag_info.get("etag"):
                        cond_headers["If-None-Match"] = etag_info["etag"]
                    if etag_info.get("last_modified"):
                        cond_headers["If-Modified-Since"] = etag_info["last_modified"]

                    feed_content, error, resp_headers = await downloader.download_with_retry(
                        session, url, extra_headers=cond_headers if cond_headers else None
                    )
                    if feed_content == "" and error is None:
                        # 304 Not Modified — feed unchanged
                        console.print(f"  [{tag}] [dim]Not modified (skipped)[/dim]")
                        return
                    if not feed_content:
                        logger.error("feed_fetch_failed", feed=tag, error=error)
                        console.print(f"  [{tag}] [red]Cannot fetch feed: {error}[/red]")
                        index.record_feed_failure(url, error or "Cannot fetch")
                        return
                    # Feed fetched successfully — clear any previous failure record
                    index.clear_feed_failure(url)
                    # Store ETag/Last-Modified for next run
                    if resp_headers.get("etag") or resp_headers.get("last_modified"):
                        index.set_feed_etag(
                            url, resp_headers.get("etag", ""), resp_headers.get("last_modified", "")
                        )
                    parsed = feedparser.parse(feed_content)
                    if not parsed.entries:
                        console.print(f"  [{tag}] [yellow]No entries[/yellow]")
                        return
                    entries = []
                    for entry in parsed.entries:
                        fc = ""
                        if entry.get("content"):
                            fc = entry["content"][0].get("value", "")
                        elif entry.get("summary"):
                            fc = entry["summary"]
                        entries.append(
                            {
                                "title": entry.get("title", "Unknown"),
                                "link": entry.get("link", ""),
                                "published": entry.get("published", entry.get("updated", "")),
                                "content": fc,
                            }
                        )
                    logger.info("feed_parsed", feed=tag, entry_count=len(entries))
                    console.print(f"  [{tag}] Found {len(entries)} entries", style="green")
                    await downloader.download_articles(session, entries, feed["title"], url)
                except Exception as e:
                    logger.error("feed_process_error", feed=tag, error=str(e))
                    console.print(f"  [{tag}] [red]Error: {e}[/red]")
                    index.record_feed_failure(url, str(e))

        tasks = [process_feed(f, i) for i, f in enumerate(feeds, 1)]
        await asyncio.gather(*tasks)

    index.flush()
    stats = index.get_stats()
    logger.info(
        "download_complete",
        downloaded=downloader.downloaded,
        failed=downloader.failed,
        total=stats["total_articles"],
    )
    console.print(
        Panel(
            f"[green]Download complete[/green]\n"
            f"  This run: {downloader.downloaded} downloaded, {downloader.failed} failed\n"
            f"  Total: {stats['total_articles']} articles, {stats['feed_failures']} feed failures",
            title="Summary",
            border_style="green",
        )
    )

    log_path = os.path.join(base_dir, "download.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(console.export_text())
    except Exception:
        pass


async def cmd_summarize(cfg: dict, force: bool = False):
    """Batch generate summaries for existing articles."""
    set_correlation_id()
    base_dir = cfg["base_dir"]
    index = IndexManager(base_dir)
    cache = LLMCache(os.path.join(base_dir, ".llm_cache"))
    llm = LLMClient(cfg["llm"], cache)

    if not llm.enabled:
        logger.error("summarize_failed", reason="llm_api_key_not_set")
        console.print("[red]LLM api_key not set (config llm.api_key or env GLM_API_KEY)[/red]")
        return

    articles = index.data.get("articles", {})
    if force:
        to_summarize = [
            {"url": url, **meta} for url, meta in articles.items() if "filepath" in meta
        ]
    else:
        to_summarize = [
            {"url": url, **meta}
            for url, meta in articles.items()
            if "summary" not in meta and "filepath" in meta
        ]
    total = len(articles)
    pending = len(to_summarize)
    logger.info("summarize_started", total=total, pending=pending)
    console.print(f"Total: {total}, already done: {total - pending}, to summarize: {pending}")

    if not to_summarize:
        console.print("[green]All articles already have summaries.[/green]")
        return

    counters = {"summarized": 0, "scored": 0, "failed": 0}
    save_every = cfg["summarize"]["save_every"]

    async with aiohttp.ClientSession() as session:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(f"Done: 0, Remaining: {pending}, Failed: 0", total=pending)

            for i in range(0, len(to_summarize), 10):
                batch = to_summarize[i : i + 10]

                batch_articles = []
                for article in batch:
                    filepath = os.path.join(base_dir, article["filepath"])
                    if not os.path.exists(filepath):
                        continue
                    try:
                        async with aiofiles.open(filepath, encoding="utf-8") as f:
                            text = await f.read()
                        fm, body = extract_front_matter(text)
                        if fm is not None:
                            batch_articles.append(
                                {
                                    "filepath": filepath,
                                    "url": article["url"],
                                    "title": article.get("title", ""),
                                    "body": body.strip(),
                                    "fm": fm,
                                }
                            )
                    except OSError:
                        pass

                if not batch_articles:
                    continue

                batch_summaries = await llm.summarize_batch(
                    session, [{"title": a["title"], "content": a["body"]} for a in batch_articles]
                )

                for article, result in zip(batch_articles, batch_summaries):
                    url = article["url"]
                    summary = result.get("summary")
                    error = result.get("error")

                    if summary:
                        article["fm"]["summary"] = summary
                        new_text = rebuild_front_matter(article["fm"], article["body"])
                        try:
                            async with aiofiles.open(
                                article["filepath"], "w", encoding="utf-8"
                            ) as f:
                                await f.write(new_text)
                        except OSError as e:
                            counters["failed"] += 1
                            progress.console.print(f"    [red]Write error: {e}[/red]")
                            progress.advance(task_id)
                            continue

                        index.data["articles"][url]["summary"] = summary
                        index._dirty = True
                        counters["summarized"] += 1

                        scores, score_error = await llm.score_and_classify(
                            session, article["title"], article["body"]
                        )
                        if scores:
                            index.update_article_scores(
                                url,
                                {
                                    "score_relevance": scores.get("relevance"),
                                    "score_quality": scores.get("quality"),
                                    "score_timeliness": scores.get("timeliness"),
                                    "category": scores.get("category"),
                                    "keywords": scores.get("keywords", []),
                                },
                            )
                            counters["scored"] += 1
                            progress.console.print(
                                f"    [green]OK[/green] {article['title'][:40]}... "
                                f"[dim]({scores.get('category')}, "
                                f"{scores.get('relevance', 0)}/{scores.get('quality', 0)}/{scores.get('timeliness', 0)})[/dim]"
                            )
                        else:
                            progress.console.print(
                                f"    [yellow]OK (no scores)[/yellow] {article['title'][:40]}..."
                            )

                        if counters["summarized"] % save_every == 0:
                            index.flush()
                    else:
                        counters["failed"] += 1
                        if error:
                            progress.console.print(
                                f"    [red]FAIL[/red] {article['title'][:40]}: {error}"
                            )
                        index.record_summary_failure(
                            url, article["title"], article["filepath"], error or "Unknown"
                        )

                    progress.advance(task_id)
                    done = counters["summarized"]
                    remaining = pending - done - counters["failed"]
                    progress.update(
                        task_id,
                        description=f"Done: {done}, Remaining: {remaining}, Failed: {counters['failed']}",
                    )

    index.flush()
    logger.info(
        "summarize_complete",
        summarized=counters["summarized"],
        scored=counters["scored"],
        failed=counters["failed"],
    )
    console.print(
        f"\n[green]Done![/green] Summarized: {counters['summarized']}, "
        f"Scored: {counters['scored']}, Failed: {counters['failed']}"
    )


def cmd_failed(cfg: dict):
    """Generate OPML for feeds with no successfully downloaded articles."""
    base_dir = cfg["base_dir"]
    opml_path = cfg["opml_path"]
    index = IndexManager(base_dir)
    output_path = os.path.join(base_dir, "failed_feeds.opml")

    all_feeds = parse_opml(opml_path)
    if not all_feeds:
        return
    console.print(f"Total feeds in OPML: {len(all_feeds)}")

    # Find feeds that have at least one downloaded article
    successful_urls = set()
    for meta in index.data.get("articles", {}).values():
        feed_url = meta.get("feed_url")
        if feed_url:
            successful_urls.add(feed_url)

    failed_feeds = []
    never_tried = []
    for f in all_feeds:
        if f["url"] not in successful_urls:
            failure_info = index.get_feed_failure_info(f["url"])
            if failure_info:
                failed_feeds.append({**f, "failure_info": failure_info})
            else:
                never_tried.append(f)

    console.print(f"Failed feeds: {len(failed_feeds)}")
    for f in failed_feeds:
        info = f.get("failure_info", {})
        console.print(f"  - [red]{f['title']}[/red]: {f['url']}")
        console.print(
            f"    Error: {info.get('error', 'Unknown')}, Retries: {info.get('retries', 0)}"
        )

    console.print(f"\nNever tried: {len(never_tried)}")
    for f in never_tried:
        console.print(f"  - [yellow]{f['title']}[/yellow]: {f['url']}")

    # Generate OPML
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="1.1">',
        "  <head><title>Failed and Never Tried Feeds</title></head>",
        "  <body>",
    ]
    if failed_feeds:
        lines.append("    <!-- Failed Feeds -->")
        for f in failed_feeds:
            t = html_escape(f["title"])
            x = html_escape(f["url"])
            h = html_escape(f.get("html_url", ""))
            lines.append(
                f'    <outline text="{t}" title="{t}" type="rss" xmlUrl="{x}" htmlUrl="{h}"/>'
            )
    if never_tried:
        lines.append("    <!-- Never Tried -->")
        for f in never_tried:
            t = html_escape(f["title"])
            x = html_escape(f["url"])
            h = html_escape(f.get("html_url", ""))
            lines.append(
                f'    <outline text="{t}" title="{t}" type="rss" xmlUrl="{x}" htmlUrl="{h}"/>'
            )
    lines.extend(["  </body>", "</opml>", ""])

    with open(output_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))
    console.print(f"\nOPML written to: {output_path}")


def cmd_stats(cfg: dict):
    """Show knowledge base statistics."""
    base_dir = cfg["base_dir"]
    index = IndexManager(base_dir)
    stats = index.get_stats()

    articles = index.data.get("articles", {})
    # Article length stats
    lengths = []
    for meta in articles.values():
        fp = os.path.join(base_dir, meta.get("filepath", ""))
        if os.path.exists(fp):
            lengths.append(os.path.getsize(fp))

    # Sources breakdown
    sources = {}
    for meta in articles.values():
        src = meta.get("source_name", "Unknown")
        sources[src] = sources.get(src, 0) + 1

    table = Table(title="RSSKB Statistics", show_header=False, border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total articles", str(stats["total_articles"]))
    table.add_row("With summary", str(stats["with_summary"]))
    table.add_row("Without summary", str(stats["without_summary"]))
    table.add_row("Feed failures", str(stats["feed_failures"]))
    table.add_row("Article failures", str(stats["article_failures"]))
    table.add_row("Summary failures", str(stats["summary_failures"]))
    if lengths:
        avg_len = sum(lengths) // len(lengths)
        table.add_row("Avg article size", f"{avg_len:,} bytes")
        table.add_row("Max article size", f"{max(lengths):,} bytes")
    table.add_row("Unique sources", str(len(sources)))
    console.print(table)

    # Top sources
    if sources:
        top = sorted(sources.items(), key=lambda x: -x[1])[:10]
        src_table = Table(title="Top 10 Sources", show_header=True, border_style="blue")
        src_table.add_column("Source", style="cyan")
        src_table.add_column("Articles", style="green", justify="right")
        for name, count in top:
            src_table.add_row(name[:40], str(count))
        console.print(src_table)


def cmd_config(cfg: dict):
    """Show current configuration."""
    import json

    console.print(Panel(json.dumps(cfg, indent=2, ensure_ascii=False), title="Current Config"))
    config_path = os.path.expanduser("~/.rsstools/config.json")
    console.print(f"\nConfig file: {config_path}")
    if not os.path.exists(config_path):
        console.print(
            "[dim]No config file found. Using defaults. "
            "Create ~/.rsstools/config.json to customize.[/dim]"
        )


def cmd_clean_cache(cfg: dict, max_age_days: int = 30, dry_run: bool = False):
    """Clean old cached LLM results."""
    base_dir = cfg["base_dir"]
    cache = LLMCache(os.path.join(base_dir, ".llm_cache"))
    console.print(f"Cleaning cache older than {max_age_days} days...")
    if dry_run:
        console.print("[yellow]Dry run — no files will be deleted[/yellow]")
    removed, size_freed = cache.clean(max_age_days, dry_run=dry_run)
    console.print(f"Removed {removed} cache files, freed {size_freed:,} bytes")

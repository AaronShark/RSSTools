"""Article downloader for RSS feeds"""

import asyncio
import hashlib
import os
import re
import time
from collections import defaultdict
from datetime import UTC
from urllib.parse import urlparse

import aiofiles
import aiohttp

from .logging_config import get_logger
from .metrics import metrics
from .repositories import ArticleRepository, FeedRepository
from .url_validator import SSRFError, UrlValidator
from .utils import extract_content, parse_date_prefix, safe_dirname, sanitize_html, yaml_escape

logger = get_logger(__name__)


class DomainRateLimiter:
    """Per-domain rate limiting for downloads."""

    def __init__(self, rate_limits: dict[str, int]):
        self.rate_limits = rate_limits
        self._last_request: dict[str, float] = defaultdict(float)
        self._lock = asyncio.Lock()

    async def acquire(self, domain: str) -> None:
        """Wait if necessary to comply with rate limit for domain.

        Args:
            domain: Domain name to rate limit
        """
        rate = self.rate_limits.get(domain)
        if not rate or rate <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            min_interval = 1.0 / rate
            elapsed = now - self._last_request[domain]
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_request[domain] = time.monotonic()


class ArticleDownloader:
    def __init__(
        self,
        cfg: dict,
        article_repo: ArticleRepository,
        feed_repo: FeedRepository,
        force: bool = False,
    ):
        self.cfg = cfg
        self.article_repo = article_repo
        self.feed_repo = feed_repo
        self.force = force
        self.articles_dir = os.path.join(cfg["base_dir"], "articles")
        os.makedirs(self.articles_dir, exist_ok=True)
        self.downloaded = 0
        self.failed = 0
        self.failures: list[dict] = []
        self._dedup_lock = asyncio.Lock()

        dl_cfg = cfg.get("download", {})
        self.rate_limiter = DomainRateLimiter(dl_cfg.get("rate_limit_per_domain", {}))
        self.url_validator = UrlValidator()
        self.ssr_protection_enabled = dl_cfg.get("ssrf_protection_enabled", True)
        self.content_sanitization_enabled = dl_cfg.get("content_sanitization_enabled", True)

    def record_feed_failure(self, title: str, url: str, error: str):
        self.failures.append({
            "type": "feed",
            "url": url,
            "title": title,
            "error": error,
        })

    async def download_with_retry(
        self, session: aiohttp.ClientSession, url: str, extra_headers: dict | None = None
    ) -> tuple[str | None, str | None, dict]:
        """Returns (content, error, resp_headers).
        resp_headers contains 'etag' and 'last_modified' from 200 responses.
        Returns ('', None, {}) for 304 Not Modified.
        """
        dl = self.cfg["download"]
        timeout = aiohttp.ClientTimeout(total=dl["timeout"], connect=dl["connect_timeout"])
        headers = {"User-Agent": dl["user_agent"]}
        if extra_headers:
            headers.update(extra_headers)
        last_error = None
        for attempt in range(dl["max_retries"]):
            try:
                async with session.get(
                    url, headers=headers, timeout=timeout, max_redirects=dl["max_redirects"]
                ) as resp:
                    if resp.status == 200:
                        raw = await resp.read()
                        rh = {
                            "etag": resp.headers.get("ETag", ""),
                            "last_modified": resp.headers.get("Last-Modified", ""),
                        }
                        return self._decode(raw, resp), None, rh
                    elif resp.status == 304:
                        return "", None, {}  # Not Modified
                    elif 400 <= resp.status < 500 and resp.status != 429:
                        return None, f"HTTP {resp.status}", {}
                    else:
                        last_error = f"HTTP {resp.status}"
            except TimeoutError:
                last_error = "Timeout"
            except aiohttp.ClientConnectorError as e:
                last_error = f"Connection: {e}"
            except aiohttp.TooManyRedirects:
                return None, "Too many redirects", {}
            except Exception as e:
                last_error = str(e)
            if attempt < dl["max_retries"] - 1:
                await asyncio.sleep(dl["retry_delay"] * (attempt + 1))
        return None, last_error, {}

    def _decode(self, content: bytes, resp) -> str:
        ct = resp.headers.get("Content-Type", "")
        m = re.search(r"charset=([^;\s]+)", ct, re.IGNORECASE)
        if m:
            try:
                return content.decode(m.group(1))
            except (UnicodeDecodeError, LookupError):
                pass
        for enc in ["utf-8", "iso-8859-1", "cp1252", "gbk", "gb2312", "big5"]:
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    async def download_articles(
        self, session: aiohttp.ClientSession, entries: list[dict], source_name: str, feed_url: str
    ):
        new_articles = []
        for entry in entries:
            url = (entry.get("link") or entry.get("id", "")).strip()
            if not url or not url.startswith(("http://", "https://")):
                continue
            if self.ssr_protection_enabled:
                try:
                    self.url_validator.validate(url)
                except SSRFError as e:
                    logger.warning("ssrf_blocked", url=url, reason=str(e))
                    continue
            if not self.force and await self.article_repo.exists(url):
                continue
            if not self.force and await self.feed_repo.should_skip_article(url):
                continue
            new_articles.append(
                {
                    "url": url,
                    "title": entry.get("title", "Unknown"),
                    "published": entry.get("published", ""),
                    "feed_url": feed_url,
                    "source_name": source_name,
                    "feed_content": entry.get("content", ""),
                }
            )
        if not new_articles:
            return
        tag = source_name[:25]
        logger.info("download_start", source=tag, article_count=len(new_articles))
        sem = asyncio.Semaphore(self.cfg["download"]["concurrent_downloads"])
        tasks = [self._download_one(session, a, sem) for a in new_articles]
        await asyncio.gather(*tasks)

    async def _download_one(self, session, article, sem):
        async with sem:
            url, title = article["url"], article["title"]
            source_name = article["source_name"]
            async with self._dedup_lock:
                if not self.force and await self.article_repo.exists(url):
                    return

            domain = urlparse(url).netloc
            await self.rate_limiter.acquire(domain)

            try:
                main_content, content_source = None, "page"
                content, error, _ = await self.download_with_retry(session, url)
                if content:
                    if self.content_sanitization_enabled:
                        content = sanitize_html(content)
                    main_content = extract_content(content, url)
                if not main_content and article.get("feed_content"):
                    from bs4 import BeautifulSoup

                    feed_content = article["feed_content"]
                    if self.content_sanitization_enabled:
                        feed_content = sanitize_html(feed_content)
                    soup = BeautifulSoup(feed_content, "html.parser")
                    if len(soup.get_text(strip=True)) > 50:
                        main_content = feed_content
                        content_source = "feed"
                if not main_content:
                    msg = error or "Cannot extract content"
                    self.failed += 1
                    self.failures.append({
                        "type": "article",
                        "url": url,
                        "title": title,
                        "source": source_name,
                        "error": msg,
                    })
                    await self.feed_repo.record_article_failure(url, msg)
                    return

                source_dir = os.path.join(self.articles_dir, safe_dirname(source_name))
                os.makedirs(source_dir, exist_ok=True)
                date_prefix = parse_date_prefix(article["published"])
                safe_title = re.sub(r"[-\s]+", "-", re.sub(r"[^\w\s-]", "", title).strip())
                url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
                filename = f"{date_prefix}_{safe_title[:50]}_{url_hash}.md"
                filepath = os.path.join(source_dir, filename)
                rel_path = os.path.relpath(filepath, self.cfg["base_dir"])

                from datetime import datetime

                now = datetime.now(UTC).isoformat()
                text = (
                    f"---\n"
                    f"title: {yaml_escape(title)}\n"
                    f"source: {yaml_escape(source_name)}\nfeed_url: {yaml_escape(article['feed_url'])}\n"
                    f"url: {yaml_escape(url)}\npublished: {yaml_escape(article['published'] or 'Unknown')}\n"
                    f"downloaded: {yaml_escape(now)}\ncontent_source: {yaml_escape(content_source)}\n"
                    f"---\n\n{main_content}\n"
                )
                try:
                    async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
                        await f.write(text)
                except OSError as e:
                    logger.error("write_failed", filepath=filepath, error=str(e))
                    self.failures.append({
                        "type": "article",
                        "url": url,
                        "title": title,
                        "source": source_name,
                        "error": f"Write error: {e}",
                    })
                    await self.feed_repo.record_article_failure(url, f"Write error: {e}")
                    self.failed += 1
                    return

                async with self._dedup_lock:
                    meta = {
                        "title": title,
                        "source_name": source_name,
                        "feed_url": article["feed_url"],
                        "published": article["published"],
                        "downloaded": now,
                        "filepath": rel_path,
                        "content_source": content_source,
                    }
                    await self.article_repo.add(url, meta)
                    await self.feed_repo.clear_article_failure(url)
                self.downloaded += 1
                metrics.record_download()
            except Exception as e:
                tag = source_name[:25]
                logger.error("download_failed", source=tag, url=url, error=str(e))
                await self.feed_repo.record_article_failure(url, str(e))
                self.failures.append({
                    "type": "article",
                    "url": url,
                    "title": title,
                    "source": source_name,
                    "error": str(e),
                })
                self.failed += 1

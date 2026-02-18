#!/usr/bin/env python3
"""
RSSKB - RSS Knowledge Base Tool

Unified CLI for RSS article management:
  download   - Download articles from RSS feeds
  summarize  - Batch generate AI summaries
  failed     - Generate OPML for failed feeds
  stats      - Show knowledge base statistics

FeedCraft-inspired features:
  - Content preprocessing (strip images/URLs before LLM)
  - Local file-based LLM result cache
  - Multi-model fallback
  - Configurable prompts via config file
  - Composable pipeline design
"""

import os
import re
import json
import copy
import asyncio
import hashlib
import argparse
import traceback
import warnings
import xml.etree.ElementTree as ET
from html import escape as html_escape
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import aiohttp
import aiofiles
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn,
)

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

console = Console()

# ==================== Default Config ====================

DEFAULT_CONFIG = {
    "base_dir": "~/RSSKB",
    "opml_path": "",  # default: {base_dir}/subscriptions.opml
    "llm": {
        "api_key": "04571e62bed046b8809423c19690f7da.Yvz4IaUKs3Vb9QLd",  # or set via GLM_API_KEY env var
        "host": "https://api.z.ai/api/coding/paas/v4",
        "models": "glm-5,glm-4.7",  # comma-separated for fallback
        "max_tokens": 2048,
        "temperature": 0.3,
        "max_content_chars": 10000,
        "request_delay": 0.5,
        "max_retries": 5,
        "timeout": 60,
        "system_prompt": "You are a helpful assistant that summarizes articles concisely.",
        "user_prompt": (
            "Summarize this article in 2-3 sentences, "
            "in the same language as the article.\n\nTitle: {title}\n\n{content}"
        ),
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
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    },
    "summarize": {
        "save_every": 20,
    },
}


def load_config() -> dict:
    """Load config from ~/.rsstools/config.json, merge with defaults."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    config_path = os.path.expanduser("~/.rsstools/config.json")
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_cfg = json.load(f)
        for section, values in user_cfg.items():
            if isinstance(values, dict) and section in cfg and isinstance(cfg[section], dict):
                cfg[section].update(values)
            else:
                cfg[section] = values
    # Env var overrides
    if os.environ.get("RSSKB_BASE_DIR"):
        cfg["base_dir"] = os.environ["RSSKB_BASE_DIR"]
    if os.environ.get("GLM_API_KEY"):
        cfg["llm"]["api_key"] = os.environ["GLM_API_KEY"]
    if os.environ.get("GLM_HOST"):
        cfg["llm"]["host"] = os.environ["GLM_HOST"]
    if os.environ.get("GLM_MODELS"):
        cfg["llm"]["models"] = os.environ["GLM_MODELS"]
    if os.environ.get("RSSKB_OPML_PATH"):
        cfg["opml_path"] = os.environ["RSSKB_OPML_PATH"]
    cfg["base_dir"] = os.path.expanduser(cfg["base_dir"])
    # Default opml_path to {base_dir}/subscriptions.opml if not set
    if not cfg["opml_path"]:
        cfg["opml_path"] = os.path.join(cfg["base_dir"], "subscriptions.opml")
    else:
        cfg["opml_path"] = os.path.expanduser(cfg["opml_path"])
    return cfg


# ==================== YAML Utilities ====================

def yaml_escape(value: str) -> str:
    """Escape string for YAML double-quoted value. Returns '"escaped"'."""
    if not value:
        return '""'
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\t', '\\t')
    return f'"{value}"'


def yaml_unescape(value: str) -> str:
    """Unescape YAML double-quoted value."""
    if not value:
        return ''
    value = value.replace('\\t', '\t')
    value = value.replace('\\r', '\r')
    value = value.replace('\\n', '\n')
    value = value.replace('\\"', '"')
    value = value.replace('\\\\', '\\')
    return value


# ==================== LLM Cache ====================

class LLMCache:
    """File-based cache for LLM results, keyed by prompt hash."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _key(self, model: str, system: str, user: str) -> str:
        h = hashlib.sha256(f"{model}|{system}|{user}".encode()).hexdigest()
        return h

    def get(self, model: str, system: str, user: str) -> Optional[str]:
        path = os.path.join(self.cache_dir, self._key(model, system, user))
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return None

    def put(self, model: str, system: str, user: str, result: str):
        path = os.path.join(self.cache_dir, self._key(model, system, user))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(result)

    def clean(self, max_age_days: int = 30, dry_run: bool = False) -> Tuple[int, int]:
        """Remove cache files older than max_age_days. Returns (files_removed, bytes_freed)."""
        if not os.path.exists(self.cache_dir):
            return 0, 0
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
        removed = 0
        size_freed = 0
        for f in os.listdir(self.cache_dir):
            path = os.path.join(self.cache_dir, f)
            if os.path.isfile(path):
                mtime = os.path.getmtime(path)
                if mtime < cutoff:
                    size_freed += os.path.getsize(path)
                    if not dry_run:
                        os.remove(path)
                    removed += 1
        return removed, size_freed


# ==================== Content Preprocessor ====================

class ContentPreprocessor:
    """Clean content before sending to LLM (FeedCraft-inspired)."""

    @staticmethod
    def process(text: str) -> str:
        # Strip markdown images: ![alt](url)
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
        # Strip HTML images
        text = re.sub(r'<img[^>]*>', '', text, flags=re.IGNORECASE)
        # Strip URLs but keep link text: [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Strip bare URLs
        text = re.sub(r'https?://\S+', '', text)
        # Strip remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Collapse whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()


# ==================== LLM Client ====================

class LLMClient:
    """Async LLM client with multi-model fallback, retry, caching, serial execution."""

    def __init__(self, cfg: dict, cache: LLMCache):
        self.host = cfg["host"]
        self.models = [m.strip() for m in cfg["models"].split(",")]
        self.max_tokens = cfg["max_tokens"]
        self.temperature = cfg["temperature"]
        self.max_content_chars = cfg["max_content_chars"]
        self.request_delay = cfg["request_delay"]
        self.max_retries = cfg["max_retries"]
        self.timeout = cfg["timeout"]
        self.system_prompt = cfg["system_prompt"]
        self.user_prompt_template = cfg["user_prompt"]
        self.cache = cache
        self.api_key = cfg.get("api_key", "")
        self._lock = asyncio.Lock()
        self.preprocessor = ContentPreprocessor()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def summarize(self, session: aiohttp.ClientSession,
                        title: str, content: str) -> Tuple[Optional[str], Optional[str]]:
        """Returns (summary, error). Serial via lock."""
        if not self.api_key:
            return None, "LLM api_key not set"
        async with self._lock:
            return await self._call_with_fallback(session, title, content)

    async def _call_with_fallback(self, session, title, content):
        cleaned = self.preprocessor.process(content)
        truncated = cleaned[:self.max_content_chars]
        user_msg = self.user_prompt_template.format(title=title, content=truncated)

        for model in self.models:
            # Check cache
            cached = self.cache.get(model, self.system_prompt, user_msg)
            if cached:
                return cached, None

            result, error = await self._call_api(session, model, user_msg)
            if result:
                self.cache.put(model, self.system_prompt, user_msg, result)
                await asyncio.sleep(self.request_delay)
                return result, None
            # If this model failed with 400 (content filter), skip all models
            if error and error == "Content filtered (400)":
                return None, error
            console.print(f"    [yellow]Model {model} failed: {error}, trying next...[/yellow]")

        await asyncio.sleep(self.request_delay)
        return None, error

    async def _call_api(self, session, model, user_msg):
        url = f"{self.host}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with session.post(url, headers=headers, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        usage = data.get("usage", {})
                        total_tok = usage.get("completion_tokens", 0)
                        reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
                        console.print(f"    [dim]tokens: reasoning={reasoning}, content={total_tok - reasoning}[/dim]")
                        result = data["choices"][0]["message"]["content"].strip()
                        if not result:
                            return None, f"Empty content (reasoning {reasoning}/{total_tok})"
                        return result, None
                    if resp.status == 400:
                        return None, "Content filtered (400)"
                    last_error = f"HTTP {resp.status}"
            except (asyncio.TimeoutError, aiohttp.ClientError, ConnectionError, OSError) as e:
                last_error = f"{type(e).__name__}: {e}"
            except Exception as e:
                return None, f"Unexpected: {e}"
            wait = min(2 ** attempt * 2, 60)
            console.print(f"    [yellow]{last_error}, retry in {wait}s ({attempt+1}/{self.max_retries})[/yellow]")
            await asyncio.sleep(wait)
        return None, f"Gave up after {self.max_retries} retries: {last_error}"

    async def score_and_classify(self, session: aiohttp.ClientSession,
                                   title: str, content: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Score and classify article. Returns (result_dict, error)."""
        if not self.api_key:
            return None, "LLM api_key not set"

        cleaned = self.preprocessor.process(content)
        truncated = cleaned[:self.max_content_chars]
        prompt = (
            f"Rate this article on 3 dimensions (1-10 scale):\n"
            f"- relevance: Value to tech professionals\n"
            f"- quality: Depth and writing quality\n"
            f"- timeliness: Current relevance\n\n"
            f"Classify into exactly one of these categories:\n"
            f"ai-ml (AI/ML), security, engineering, tools, opinion, other\n\n"
            f"Extract 2-4 keywords (single words or short phrases).\n\n"
            f"Article title: {title}\n\n"
            f"Article content:\n{truncated}\n\n"
            f"Return ONLY valid JSON (no markdown formatting):\n"
            f'{{"relevance": <1-10>, "quality": <1-10>, "timeliness": <1-10>, '
            f'"category": "<category>", "keywords": ["keyword1", "keyword2"]}}'
        )

        user_msg = prompt
        for model in self.models:
            cached = self.cache.get(model, self.system_prompt, user_msg)
            if cached:
                try:
                    return json.loads(cached), None
                except json.JSONDecodeError:
                    pass

            result, error = await self._call_api(session, model, user_msg)
            if result:
                try:
                    data = json.loads(result)
                    self.cache.put(model, self.system_prompt, user_msg, result)
                    await asyncio.sleep(self.request_delay)
                    return data, None
                except json.JSONDecodeError as e:
                    return None, f"Invalid JSON response: {e}"

            if error and error == "Content filtered (400)":
                return None, error
            console.print(f"    [yellow]Model {model} failed: {error}, trying next...[/yellow]")

        await asyncio.sleep(self.request_delay)
        return None, error

    async def summarize_batch(self, session: aiohttp.ClientSession,
                               articles: List[Dict]) -> List[Dict]:
        """Summarize multiple articles in one API call.
        Args:
            articles: List of {'title': str, 'content': str}
        Returns:
            List of {'summary': str, 'error': Optional[str]}
        """
        if not articles:
            return []
        if not self.api_key:
            return [{'summary': None, 'error': 'LLM api_key not set'}] * len(articles)

        batch_size = 10
        all_results = []

        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            articles_text = "\n\n---\n\n".join([
                f"Index {idx}: {a['title']}\n\n{self.preprocessor.process(a['content'][:2000])}"
                for idx, a in enumerate(batch)
            ])

            prompt = (
                f"Summarize each article in 2-3 sentences, in the same language as the article.\n"
                f"Return ONLY valid JSON (no markdown formatting):\n"
                f'{{"results": [{{"index": 0, "summary": "..."}}, {{"index": 1, "summary": "..."}}]}}\n\n'
                f"Articles:\n{articles_text}"
            )

            batch_results = await self._process_batch(session, prompt, len(batch))
            all_results.extend(batch_results)

            await asyncio.sleep(self.request_delay)

        return all_results

    async def _process_batch(self, session: aiohttp.ClientSession,
                               prompt: str, batch_size: int) -> List[Dict]:
        """Process batch with fallback to individual calls."""
        for model in self.models:
            cached = self.cache.get(model, self.system_prompt, prompt)
            if cached:
                try:
                    data = json.loads(cached)
                    return data.get('results', [])
                except json.JSONDecodeError:
                    pass

            result, error = await self._call_api(session, model, prompt)
            if result:
                try:
                    data = json.loads(result)
                    self.cache.put(model, self.system_prompt, prompt, result)
                    results = data.get('results', [])
                    if len(results) == batch_size:
                        return [{'summary': r.get('summary'), 'error': None} for r in results]
                except json.JSONDecodeError:
                    console.print("    [yellow]Batch JSON parse failed, trying next model[/yellow]")

            if error and error == "Content filtered (400)":
                break
            console.print(f"    [yellow]Batch failed with {model}: {error}, trying fallback[/yellow]")

        await asyncio.sleep(self.request_delay)
        return [{'summary': None, 'error': 'Batch processing failed'}] * batch_size


# ==================== Index Manager ====================

class IndexManager:
    """Unified index: metadata, dedup, failure records in index.json."""

    def __init__(self, base_dir: str):
        self.index_path = os.path.join(base_dir, "index.json")
        self.data = self._load()
        self._dirty = False

    def _load(self) -> Dict:
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for key in ('articles', 'feed_failures', 'article_failures', 'summary_failures', 'feed_etags'):
                    data.setdefault(key, {})
                return data
            except Exception as e:
                console.print(f"  [yellow]Warning: failed to load index: {e}[/yellow]")
        return {'articles': {}, 'feed_failures': {}, 'article_failures': {}, 'summary_failures': {}, 'feed_etags': {}}

    def save(self):
        if not self._dirty:
            return
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        self._dirty = False

    def flush(self):
        self.save()

    def is_downloaded(self, url: str) -> bool:
        return url in self.data['articles']

    def add_article(self, url: str, meta: Dict):
        self.data['articles'][url] = meta
        self._dirty = True

    def update_article_scores(self, url: str, scores: Dict):
        """Update article with scoring and classification data."""
        if url in self.data['articles']:
            self.data['articles'][url].update(scores)
            self._dirty = True

    def is_feed_failed(self, url: str) -> bool:
        return url in self.data['feed_failures']

    def get_feed_failure_info(self, url: str) -> Optional[Dict]:
        return self.data['feed_failures'].get(url)

    def should_skip_feed(self, url: str, max_retries: int, retry_after_hours: int = 24) -> bool:
        """Check if feed should be skipped. Expired failures get a fresh chance."""
        info = self.data['feed_failures'].get(url)
        if not info:
            return False
        if info.get('retries', 0) < max_retries:
            return False
        # Time-based expiry: retry after N hours even if max retries reached
        ts = _parse_date_flexible(info.get('timestamp', ''))
        if ts:
            ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            if age_hours >= retry_after_hours:
                # Delete the entire record for a clean slate
                del self.data['feed_failures'][url]
                self._dirty = True
                return False
        return True

    def should_skip_article(self, url: str, max_retries: int = 3) -> bool:
        """Check if article should be skipped after too many failures."""
        info = self.data['article_failures'].get(url)
        if not info:
            return False
        return info.get('retries', 0) >= max_retries

    def record_feed_failure(self, url: str, error: str):
        failures = self.data['feed_failures']
        now = datetime.now(timezone.utc).isoformat()
        if url not in failures:
            failures[url] = {'error': error, 'timestamp': now, 'retries': 0}
        else:
            failures[url].update({'error': error, 'retries': failures[url]['retries'] + 1, 'timestamp': now})
        self._dirty = True

    def clear_feed_failure(self, url: str):
        if url in self.data['feed_failures']:
            del self.data['feed_failures'][url]
            self._dirty = True

    def record_article_failure(self, url: str, error: str):
        failures = self.data['article_failures']
        now = datetime.now(timezone.utc).isoformat()
        if url not in failures:
            failures[url] = {'error': error, 'timestamp': now, 'retries': 0}
        else:
            failures[url].update({'error': error, 'retries': failures[url]['retries'] + 1, 'timestamp': now})
        self._dirty = True

    def clear_article_failure(self, url: str):
        if url in self.data['article_failures']:
            del self.data['article_failures'][url]
            self._dirty = True

    def record_summary_failure(self, url: str, title: str, filepath: str, error: str):
        self.data['summary_failures'][url] = {
            'title': title, 'filepath': filepath, 'error': error,
        }
        self._dirty = True

    def get_feed_etag(self, url: str, max_age_days: int = 30) -> Dict:
        """Get cached ETag for feed, with expiry check."""
        info = self.data['feed_etags'].get(url, {})
        if not info:
            return {}
        ts = _parse_date_flexible(info.get('timestamp', ''))
        if ts:
            ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
            if age_days > max_age_days:
                return {}
        return info

    def set_feed_etag(self, url: str, etag: str = '', last_modified: str = ''):
        self.data['feed_etags'][url] = {
            k: v for k, v in {
                'etag': etag, 'last_modified': last_modified,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }.items() if v
        }
        self._dirty = True

    def get_stats(self) -> Dict:
        articles = self.data['articles']
        with_summary = sum(1 for m in articles.values() if 'summary' in m)
        return {
            'total_articles': len(articles),
            'with_summary': with_summary,
            'without_summary': len(articles) - with_summary,
            'feed_failures': len(self.data['feed_failures']),
            'article_failures': len(self.data['article_failures']),
            'summary_failures': len(self.data['summary_failures']),
        }


# ==================== Utilities ====================

def safe_dirname(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name).strip()
    name = re.sub(r'[\s]+', '-', name)
    return name[:80] or 'unknown'


def parse_date_prefix(published: str) -> str:
    if published:
        try:
            dt = date_parser.parse(published)
            return dt.strftime('%Y-%m-%d')
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def parse_opml(opml_path: str) -> List[Dict]:
    if not os.path.exists(opml_path):
        console.print(f"  [red]OPML file not found: {opml_path}[/red]")
        return []
    try:
        tree = ET.parse(opml_path)
        body = tree.getroot().find('.//body')
        if body is None:
            body = tree.getroot()
        feeds = []
        for outline in body.findall('.//outline'):
            url = outline.get('xmlUrl') or outline.get('htmlUrl')
            title = outline.get('text') or outline.get('title', 'Unknown')
            if url:
                feeds.append({
                    'title': title, 'url': url,
                    'html_url': outline.get('htmlUrl', ''),
                })
        return feeds
    except Exception as e:
        console.print(f"  [red]Failed to parse OPML: {e}[/red]")
        return []


def extract_front_matter(text: str) -> Tuple[Optional[Dict], str]:
    """Parse YAML front matter. Handles both quoted and unquoted values."""
    m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if not m:
        return None, text
    fm_text = m.group(1)
    body = text[m.end():]
    meta = {}
    for line in fm_text.split('\n'):
        kv = re.match(r'^(\w[\w_]*)\s*:\s*(.*)', line)
        if kv:
            val = kv.group(2)
            # If value is double-quoted, strip quotes and unescape
            if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
                val = yaml_unescape(val[1:-1])
            meta[kv.group(1)] = val
    return meta, body


def rebuild_front_matter(meta: Dict, body: str) -> str:
    """Rebuild front matter with properly escaped values."""
    lines = [f"{k}: {yaml_escape(v)}" for k, v in meta.items()]
    return "---\n" + "\n".join(lines) + "\n---\n" + body


# ==================== Article Downloader ====================

class ArticleDownloader:

    def __init__(self, cfg: dict, index: IndexManager, llm: Optional[LLMClient] = None, force: bool = False):
        self.cfg = cfg
        self.index = index
        self.llm = llm
        self.force = force
        self.articles_dir = os.path.join(cfg["base_dir"], "articles")
        os.makedirs(self.articles_dir, exist_ok=True)
        self.downloaded = 0
        self.failed = 0
        self._dedup_lock = asyncio.Lock()

    async def download_with_retry(self, session: aiohttp.ClientSession,
                                  url: str, extra_headers: Dict = None
                                  ) -> Tuple[Optional[str], Optional[str], Dict]:
        """Returns (content, error, resp_headers).
        resp_headers contains 'etag' and 'last_modified' from 200 responses.
        Returns ('', None, {}) for 304 Not Modified.
        """
        dl = self.cfg["download"]
        timeout = aiohttp.ClientTimeout(total=dl["timeout"], connect=dl["connect_timeout"])
        headers = {'User-Agent': dl["user_agent"]}
        if extra_headers:
            headers.update(extra_headers)
        last_error = None
        for attempt in range(dl["max_retries"]):
            try:
                async with session.get(url, headers=headers, timeout=timeout,
                                       max_redirects=dl["max_redirects"]) as resp:
                    if resp.status == 200:
                        raw = await resp.read()
                        rh = {
                            'etag': resp.headers.get('ETag', ''),
                            'last_modified': resp.headers.get('Last-Modified', ''),
                        }
                        return self._decode(raw, resp), None, rh
                    elif resp.status == 304:
                        return '', None, {}  # Not Modified
                    elif 400 <= resp.status < 500 and resp.status != 429:
                        return None, f"HTTP {resp.status}", {}
                    else:
                        last_error = f"HTTP {resp.status}"
            except asyncio.TimeoutError:
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
        ct = resp.headers.get('Content-Type', '')
        m = re.search(r'charset=([^;\s]+)', ct, re.IGNORECASE)
        if m:
            try:
                return content.decode(m.group(1))
            except (UnicodeDecodeError, LookupError):
                pass
        for enc in ['utf-8', 'iso-8859-1', 'cp1252', 'gbk', 'gb2312', 'big5']:
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode('utf-8', errors='replace')

    def extract_content(self, html: str, url: str) -> Optional[str]:
        if HAS_TRAFILATURA:
            text = trafilatura.extract(html, url=url, include_comments=False,
                                       output_format='markdown', include_links=True,
                                       include_images=True, include_tables=True)
            if text and len(text) > 100:
                return text
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe']):
            tag.decompose()
        for sel in ['article', '[role="main"]', '.content', '#content',
                    '.post', '.entry', '.article-body', '.post-content',
                    'main', '.main-content', '#main']:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 100:
                return str(el)
        body = soup.find('body')
        if body and body.get_text(strip=True):
            return str(body)
        return None

    async def download_articles(self, session: aiohttp.ClientSession,
                                entries: List[Dict], source_name: str, feed_url: str):
        new_articles = []
        for entry in entries:
            url = (entry.get('link') or entry.get('id', '')).strip()
            if not url or not url.startswith(('http://', 'https://')):
                continue
            if not self.force and self.index.is_downloaded(url):
                continue
            if not self.force and self.index.should_skip_article(url):
                continue
            new_articles.append({
                'url': url, 'title': entry.get('title', 'Unknown'),
                'published': entry.get('published', ''), 'feed_url': feed_url,
                'source_name': source_name, 'feed_content': entry.get('content', ''),
            })
        if not new_articles:
            return
        tag = source_name[:25]
        console.print(f"  [{tag}] {len(new_articles)} new articles to download")
        sem = asyncio.Semaphore(self.cfg["download"]["concurrent_downloads"])
        tasks = [self._download_one(session, a, sem) for a in new_articles]
        await asyncio.gather(*tasks)
        self.index.flush()

    async def _download_one(self, session, article, sem):
        async with sem:
            url, title = article['url'], article['title']
            source_name = article['source_name']
            async with self._dedup_lock:
                if not self.force and self.index.is_downloaded(url):
                    return
            try:
                main_content, content_source = None, 'page'
                content, error, _ = await self.download_with_retry(session, url)
                if content:
                    main_content = self.extract_content(content, url)
                if not main_content and article.get('feed_content'):
                    soup = BeautifulSoup(article['feed_content'], 'html.parser')
                    if len(soup.get_text(strip=True)) > 50:
                        main_content = article['feed_content']
                        content_source = 'feed'
                if not main_content:
                    msg = error or "Cannot extract content"
                    self.failed += 1
                    self.index.record_article_failure(url, msg)
                    return

                source_dir = os.path.join(self.articles_dir, safe_dirname(source_name))
                os.makedirs(source_dir, exist_ok=True)
                date_prefix = parse_date_prefix(article['published'])
                safe_title = re.sub(r'[-\s]+', '-', re.sub(r'[^\w\s-]', '', title).strip())
                url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
                filename = f"{date_prefix}_{safe_title[:50]}_{url_hash}.md"
                filepath = os.path.join(source_dir, filename)
                rel_path = os.path.relpath(filepath, self.cfg["base_dir"])

                summary = None
                if self.llm and self.llm.enabled:
                    summary, _ = await self.llm.summarize(session, title, main_content)

                now = datetime.now(timezone.utc).isoformat()
                summary_line = ""
                if summary:
                    summary_line = f"summary: {yaml_escape(summary)}\n"
                text = (
                    f"---\n"
                    f"title: {yaml_escape(title)}\n"
                    f"source: {yaml_escape(source_name)}\nfeed_url: {yaml_escape(article['feed_url'])}\n"
                    f"url: {yaml_escape(url)}\npublished: {yaml_escape(article['published'] or 'Unknown')}\n"
                    f"downloaded: {yaml_escape(now)}\ncontent_source: {yaml_escape(content_source)}\n"
                    f"{summary_line}---\n\n{main_content}\n"
                )
                try:
                    async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                        await f.write(text)
                except IOError as e:
                    console.print(f"    [red]Failed to write file: {e}[/red]")
                    self.index.record_article_failure(url, f"Write error: {e}")
                    self.failed += 1
                    return

                async with self._dedup_lock:
                    meta = {
                        'title': title, 'source_name': source_name,
                        'feed_url': article['feed_url'], 'published': article['published'],
                        'downloaded': now, 'filepath': rel_path,
                        'content_source': content_source,
                    }
                    if summary:
                        meta['summary'] = summary
                    self.index.add_article(url, meta)
                    self.index.clear_article_failure(url)
                self.downloaded += 1
            except Exception as e:
                tag = source_name[:25]
                console.print(f"    [{tag}] [red]Failed: {e}[/red]")
                self.index.record_article_failure(url, str(e))
                self.failed += 1


# ==================== Commands ====================

async def cmd_download(cfg: dict, force: bool = False):
    """Download articles from RSS feeds."""
    base_dir = cfg["base_dir"]
    opml_path = cfg["opml_path"]
    index = IndexManager(base_dir)
    cache = LLMCache(os.path.join(base_dir, ".llm_cache"))
    llm = LLMClient(cfg["llm"], cache)

    if not llm.enabled:
        console.print("[yellow]LLM api_key not set, summaries will be skipped[/yellow]")

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
                tag = feed['title'][:25]
                console.print(f"\n[{idx}/{len(feeds)}] {feed['title']}")
                url = feed['url']
                if not force and index.should_skip_feed(url, cfg["download"]["max_retries"]):
                    console.print(f"  [{tag}] [yellow]Skipped (previously failed, retry after 24h)[/yellow]")
                    return
                try:
                    # Build conditional request headers from cached ETag/Last-Modified
                    etag_info = index.get_feed_etag(url, max_age_days=etag_max_age)
                    cond_headers = {}
                    if etag_info.get('etag'):
                        cond_headers['If-None-Match'] = etag_info['etag']
                    if etag_info.get('last_modified'):
                        cond_headers['If-Modified-Since'] = etag_info['last_modified']

                    feed_content, error, resp_headers = await downloader.download_with_retry(
                        session, url, extra_headers=cond_headers or None
                    )
                    if feed_content == '' and error is None:
                        # 304 Not Modified — feed unchanged
                        console.print(f"  [{tag}] [dim]Not modified (skipped)[/dim]")
                        return
                    if not feed_content:
                        console.print(f"  [{tag}] [red]Cannot fetch feed: {error}[/red]")
                        index.record_feed_failure(url, error or "Cannot fetch")
                        return
                    # Feed fetched successfully — clear any previous failure record
                    index.clear_feed_failure(url)
                    # Store ETag/Last-Modified for next run
                    if resp_headers.get('etag') or resp_headers.get('last_modified'):
                        index.set_feed_etag(url, resp_headers.get('etag', ''), resp_headers.get('last_modified', ''))
                    parsed = feedparser.parse(feed_content)
                    if not parsed.entries:
                        console.print(f"  [{tag}] [yellow]No entries[/yellow]")
                        return
                    entries = []
                    for entry in parsed.entries:
                        fc = ''
                        if entry.get('content'):
                            fc = entry['content'][0].get('value', '')
                        elif entry.get('summary'):
                            fc = entry['summary']
                        entries.append({
                            'title': entry.get('title', 'Unknown'),
                            'link': entry.get('link', ''),
                            'published': entry.get('published', entry.get('updated', '')),
                            'content': fc,
                        })
                    console.print(f"  [{tag}] Found {len(entries)} entries", style="green")
                    await downloader.download_articles(session, entries, feed['title'], url)
                except Exception as e:
                    console.print(f"  [{tag}] [red]Error: {e}[/red]")
                    index.record_feed_failure(url, str(e))

        tasks = [process_feed(f, i) for i, f in enumerate(feeds, 1)]
        await asyncio.gather(*tasks)

    index.flush()
    stats = index.get_stats()
    console.print(Panel(
        f"[green]Download complete[/green]\n"
        f"  This run: {downloader.downloaded} downloaded, {downloader.failed} failed\n"
        f"  Total: {stats['total_articles']} articles, {stats['feed_failures']} feed failures",
        title="Summary", border_style="green",
    ))

    log_path = os.path.join(base_dir, "download.log")
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(console.export_text())
    except Exception:
        pass


async def cmd_summarize(cfg: dict, force: bool = False):
    """Batch generate summaries for existing articles."""
    base_dir = cfg["base_dir"]
    index = IndexManager(base_dir)
    cache = LLMCache(os.path.join(base_dir, ".llm_cache"))
    llm = LLMClient(cfg["llm"], cache)

    if not llm.enabled:
        console.print("[red]LLM api_key not set (config llm.api_key or env GLM_API_KEY)[/red]")
        return

    articles = index.data.get('articles', {})
    if force:
        to_summarize = [
            {'url': url, **meta}
            for url, meta in articles.items()
            if 'filepath' in meta
        ]
    else:
        to_summarize = [
            {'url': url, **meta}
            for url, meta in articles.items()
            if 'summary' not in meta and 'filepath' in meta
        ]
    total = len(articles)
    pending = len(to_summarize)
    console.print(f"Total: {total}, already done: {total - pending}, to summarize: {pending}")

    if not to_summarize:
        console.print("[green]All articles already have summaries.[/green]")
        return

    counters = {'summarized': 0, 'scored': 0, 'failed': 0}
    save_every = cfg["summarize"]["save_every"]

    async with aiohttp.ClientSession() as session:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(
                f"Done: 0, Remaining: {pending}, Failed: 0", total=pending)

            for i in range(0, len(to_summarize), 10):
                batch = to_summarize[i:i + 10]

                batch_articles = []
                for article in batch:
                    filepath = os.path.join(base_dir, article['filepath'])
                    if not os.path.exists(filepath):
                        continue
                    try:
                        async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                            text = await f.read()
                        fm, body = extract_front_matter(text)
                        if fm is not None:
                            batch_articles.append({
                                'filepath': filepath,
                                'url': article['url'],
                                'title': article.get('title', ''),
                                'body': body.strip(),
                                'fm': fm
                            })
                    except IOError:
                        pass

                if not batch_articles:
                    continue

                batch_summaries = await llm.summarize_batch(
                    session,
                    [{'title': a['title'], 'content': a['body']} for a in batch_articles]
                )

                for article, result in zip(batch_articles, batch_summaries):
                    url = article['url']
                    summary = result.get('summary')
                    error = result.get('error')

                    if summary:
                        article['fm']['summary'] = summary
                        new_text = rebuild_front_matter(article['fm'], article['body'])
                        try:
                            async with aiofiles.open(article['filepath'], 'w', encoding='utf-8') as f:
                                await f.write(new_text)
                        except IOError as e:
                            counters['failed'] += 1
                            progress.console.print(f"    [red]Write error: {e}[/red]")
                            progress.advance(task_id)
                            continue

                        index.data['articles'][url]['summary'] = summary
                        index._dirty = True
                        counters['summarized'] += 1

                        scores, score_error = await llm.score_and_classify(
                            session, article['title'], article['body']
                        )
                        if scores:
                            index.update_article_scores(url, {
                                'score_relevance': scores.get('relevance'),
                                'score_quality': scores.get('quality'),
                                'score_timeliness': scores.get('timeliness'),
                                'category': scores.get('category'),
                                'keywords': scores.get('keywords', [])
                            })
                            counters['scored'] += 1
                            progress.console.print(
                                f"    [green]OK[/green] {article['title'][:40]}... "
                                f"[dim]({scores.get('category')}, "
                                f"{scores.get('relevance', 0)}/{scores.get('quality', 0)}/{scores.get('timeliness', 0)})[/dim]"
                            )
                        else:
                            progress.console.print(
                                f"    [yellow]OK (no scores)[/yellow] {article['title'][:40]}..."
                            )

                        if counters['summarized'] % save_every == 0:
                            index.flush()
                    else:
                        counters['failed'] += 1
                        if error:
                            progress.console.print(
                                f"    [red]FAIL[/red] {article['title'][:40]}: {error}"
                            )
                        index.record_summary_failure(
                            url, article['title'], article['filepath'], error or 'Unknown'
                        )

                    progress.advance(task_id)
                    done = counters['summarized']
                    remaining = pending - done - counters['failed']
                    progress.update(task_id,
                        description=f"Done: {done}, Remaining: {remaining}, Failed: {counters['failed']}")

    index.flush()
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
    for meta in index.data.get('articles', {}).values():
        feed_url = meta.get('feed_url')
        if feed_url:
            successful_urls.add(feed_url)

    failed_feeds = []
    never_tried = []
    for f in all_feeds:
        if f['url'] not in successful_urls:
            failure_info = index.get_feed_failure_info(f['url'])
            if failure_info:
                failed_feeds.append({**f, 'failure_info': failure_info})
            else:
                never_tried.append(f)

    console.print(f"Failed feeds: {len(failed_feeds)}")
    for f in failed_feeds:
        info = f.get('failure_info', {})
        console.print(f"  - [red]{f['title']}[/red]: {f['url']}")
        console.print(f"    Error: {info.get('error', 'Unknown')}, Retries: {info.get('retries', 0)}")

    console.print(f"\nNever tried: {len(never_tried)}")
    for f in never_tried:
        console.print(f"  - [yellow]{f['title']}[/yellow]: {f['url']}")

    # Generate OPML
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="1.1">',
        '  <head><title>Failed and Never Tried Feeds</title></head>',
        '  <body>',
    ]
    if failed_feeds:
        lines.append('    <!-- Failed Feeds -->')
        for f in failed_feeds:
            t = html_escape(f['title'])
            x = html_escape(f['url'])
            h = html_escape(f.get('html_url', ''))
            lines.append(f'    <outline text="{t}" title="{t}" type="rss" xmlUrl="{x}" htmlUrl="{h}"/>')
    if never_tried:
        lines.append('    <!-- Never Tried -->')
        for f in never_tried:
            t = html_escape(f['title'])
            x = html_escape(f['url'])
            h = html_escape(f.get('html_url', ''))
            lines.append(f'    <outline text="{t}" title="{t}" type="rss" xmlUrl="{x}" htmlUrl="{h}"/>')
    lines.extend(['  </body>', '</opml>', ''])

    with open(output_path, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(lines))
    console.print(f"\nOPML written to: {output_path}")


def cmd_stats(cfg: dict):
    """Show knowledge base statistics."""
    base_dir = cfg["base_dir"]
    index = IndexManager(base_dir)
    stats = index.get_stats()

    articles = index.data.get('articles', {})
    # Article length stats
    articles_dir = os.path.join(base_dir, "articles")
    lengths = []
    for meta in articles.values():
        fp = os.path.join(base_dir, meta.get('filepath', ''))
        if os.path.exists(fp):
            lengths.append(os.path.getsize(fp))

    # Sources breakdown
    sources = {}
    for meta in articles.values():
        src = meta.get('source_name', 'Unknown')
        sources[src] = sources.get(src, 0) + 1

    table = Table(title="RSSKB Statistics", show_header=False, border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total articles", str(stats['total_articles']))
    table.add_row("With summary", str(stats['with_summary']))
    table.add_row("Without summary", str(stats['without_summary']))
    table.add_row("Feed failures", str(stats['feed_failures']))
    table.add_row("Article failures", str(stats['article_failures']))
    table.add_row("Summary failures", str(stats['summary_failures']))
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
    console.print(Panel(json.dumps(cfg, indent=2, ensure_ascii=False), title="Current Config"))
    config_path = os.path.expanduser("~/.rsstools/config.json")
    console.print(f"\nConfig file: {config_path}")
    if not os.path.exists(config_path):
        console.print("[dim]No config file found. Using defaults. "
                      "Create ~/.rsstools/config.json to customize.[/dim]")


def cmd_clean_cache(cfg: dict, max_age_days: int = 30, dry_run: bool = False):
    """Clean old cached LLM results."""
    base_dir = cfg["base_dir"]
    cache = LLMCache(os.path.join(base_dir, ".llm_cache"))
    console.print(f"Cleaning cache older than {max_age_days} days...")
    if dry_run:
        console.print("[yellow]Dry run — no files will be deleted[/yellow]")
    removed, size_freed = cache.clean(max_age_days=max_age_days, dry_run=dry_run)
    if removed > 0:
        action = "Would remove" if dry_run else "Removed"
        console.print(f"[green]{action}: {removed} files, {size_freed / 1024:.1f} KB freed[/green]")
    else:
        console.print("[green]No cache files to clean[/green]")


def _generate_mermaid_pie_chart(category_counts: Dict[str, int]) -> str:
    """Generate Mermaid pie chart for category distribution."""
    total = sum(category_counts.values())
    lines = ['```mermaid', 'pie showData', '  title Category Distribution']
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        percentage = (count / total) * 100
        lines.append(f'  "{cat}": {percentage:.1f}')
    lines.extend(['```', ''])
    return '\n'.join(lines)


def _generate_mermaid_bar_chart(keyword_counts: Dict[str, int], top_n: int = 10) -> str:
    """Generate Mermaid horizontal bar chart for keyword frequency."""
    top_keywords = sorted(keyword_counts.items(), key=lambda x: -x[1])[:top_n]
    if not top_keywords:
        return ''
    max_count = max(keyword_counts.values())
    lines = ['```mermaid', 'xychart-beta', '  horizontal', '  title "Top Keywords"']
    labels = [f'"{kw}"' for kw, _ in top_keywords]
    values = [str(count) for _, count in top_keywords]
    lines.append('  x-axis [' + ', '.join(labels) + ']')
    lines.append('  y-axis "Frequency" 0 --> ' + str(max_count))
    lines.append('  bar [' + ', '.join(values) + ']')
    lines.extend(['```', ''])
    return '\n'.join(lines)


async def cmd_digest(cfg: dict, hours: int = 48, top_n: int = 15,
                     lang: str = 'zh', output: Optional[str] = None, min_score: int = 5):
    """Generate daily digest report."""
    base_dir = cfg["base_dir"]
    index = IndexManager(base_dir)
    cache = LLMCache(os.path.join(base_dir, ".llm_cache"))
    llm = LLMClient(cfg["llm"], cache)

    console.print(f"[bold blue]Generating digest: last {hours} hours, top {top_n} articles[/bold blue]")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    recent_articles = []
    for url, meta in index.data.get('articles', {}).items():
        published = _parse_date_flexible(meta.get('published', ''))
        if published:
            pub = published if published.tzinfo else published.replace(tzinfo=timezone.utc)
            if pub >= cutoff:
                relevance = meta.get('score_relevance', 0)
                if relevance >= min_score:
                    recent_articles.append({
                        'url': url,
                        'title': meta.get('title', ''),
                        'summary': meta.get('summary', ''),
                        'source': meta.get('source_name', ''),
                        'published': meta.get('published', ''),
                        'score_relevance': meta.get('score_relevance', 0),
                        'score_quality': meta.get('score_quality', 0),
                        'score_timeliness': meta.get('score_timeliness', 0),
                        'category': meta.get('category', 'other'),
                        'keywords': meta.get('keywords', []),
                        'total_score': relevance + meta.get('score_quality', 0) + meta.get('score_timeliness', 0)
                    })

    if not recent_articles:
        console.print("[yellow]No articles found in the specified time window.[/yellow]")
        return

    recent_articles.sort(key=lambda x: x['total_score'], reverse=True)
    top_articles = recent_articles[:top_n]

    category_counts = {}
    keyword_counts = {}
    for article in recent_articles:
        cat = article['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1
        for kw in article['keywords']:
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

    trends = ""
    if llm.enabled and len(top_articles) >= 5:
        console.print("  Generating trend analysis...")
        articles_text = "\n\n".join([
            f"- {a['title']} (category: {a['category']}, score: {a['total_score']})"
            for a in top_articles[:10]
        ])
        prompt = (
            f"From these top technical articles, identify 2-3 major trends.\n\n"
            f"Articles:\n{articles_text}\n\n"
            f"Return 3-5 bullet points, each 1-2 sentences."
        )
        result, _ = await llm._call_with_fallback(
            await aiohttp.ClientSession().__aenter__(), "", prompt
        )
        if result:
            trends = result

    date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if not output:
        output = os.path.join(base_dir, f"digest-{date_str}.md")

    report_lines = [
        f"# Tech Digest - {date_str}",
        "",
        f"## 📝 Today's Highlights",
        "",
    ]

    if trends:
        report_lines.extend([trends.strip(), ""])

    report_lines.extend([
        f"## 🏆 Today's Top {len(top_articles)} Articles",
        "",
    ])

    for i, article in enumerate(top_articles, 1):
        score_badge = f"⭐ {article['total_score']}/30"
        cat_emoji = {
            'ai-ml': '🤖', 'security': '🔒', 'engineering': '⚙️',
            'tools': '🛠', 'opinion': '💡', 'other': '📝'
        }.get(article['category'], '📄')

        report_lines.extend([
            f"### {i}. {cat_emoji} {article['title']}",
            "",
            f"**Score**: {article['score_relevance']}/10 relevance, "
            f"{article['score_quality']}/10 quality, "
            f"{article['score_timeliness']}/10 timeliness {score_badge}",
            "",
            f"**Category**: {article['category']} | **Source**: {article['source']}",
            "",
        ])

        if article['keywords']:
            kw_str = ', '.join(article['keywords'])
            report_lines.append(f"**Keywords**: {kw_str}")
            report_lines.append("")

        if article['summary']:
            report_lines.extend([article['summary'], ""])

        report_lines.append(f"🔗 [Read full article]({article['url']})")
        report_lines.append("")

    report_lines.extend([
        "## 📊 Statistics",
        "",
        f"- **Total articles analyzed**: {len(recent_articles)}",
        f"- **Time window**: Last {hours} hours",
        f"- **Categories covered**: {len(category_counts)}",
        "",
        _generate_mermaid_pie_chart(category_counts),
    ])

    keyword_chart = _generate_mermaid_bar_chart(keyword_counts, top_n=10)
    if keyword_chart:
        report_lines.extend([
            "## 🔑 Top Keywords",
            "",
            keyword_chart,
        ])

    report_lines.extend([
        "---",
        "",
        f"*Generated by RSSKB on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        ""
    ])

    with open(output, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))

    console.print(Panel(
        f"[green]Digest generated successfully![/green]\n\n"
        f"  Articles: {len(top_articles)} (top {top_n} from {len(recent_articles)})\n"
        f"  Output: {output}\n"
        f"  Time window: Last {hours} hours",
        title="Digest Complete",
        border_style="green",
    ))


# ==================== Search / Filter ====================

def _parse_date_flexible(s: str) -> Optional[datetime]:
    """Parse dates in ISO or RFC 2822 format."""
    if not s or s == 'Unknown':
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return date_parser.parse(s)
    except Exception:
        return None


def _detect_lang(text: str) -> str:
    """Simple language detection heuristic based on character ranges."""
    if not text:
        return 'unknown'
    sample = text[:2000]
    total = len(sample)
    if total == 0:
        return 'unknown'
    cjk = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff')
    jp = sum(1 for c in sample if '\u3040' <= c <= '\u30ff')
    ko = sum(1 for c in sample if '\uac00' <= c <= '\ud7af')
    if jp / total > 0.05:
        return 'ja'
    if ko / total > 0.05:
        return 'ko'
    if cjk / total > 0.05:
        return 'zh'
    return 'en'


def cmd_search(cfg: dict, args):
    """Search and filter articles."""
    base_dir = cfg["base_dir"]
    index = IndexManager(base_dir)
    articles = index.data.get('articles', {})

    if not articles:
        console.print("[yellow]No articles in index.[/yellow]")
        return

    # Parse date filters once
    date_from = _parse_date_flexible(args.date_from) if args.date_from else None
    date_to = _parse_date_flexible(args.date_to) if args.date_to else None
    date_after = _parse_date_flexible(args.after) if args.after else None

    results = []
    need_file_read = bool(args.keyword or args.lang or args.min_size or args.max_size)

    for url, meta in articles.items():
        # --- Fast filters (index metadata only) ---

        # Title filter
        if args.title and args.title.lower() not in meta.get('title', '').lower():
            continue

        # Source filter
        if args.source and args.source.lower() not in meta.get('source_name', '').lower():
            continue

        # Content source filter
        if args.content_source and meta.get('content_source') != args.content_source:
            continue

        # Summary presence filter
        if args.has_summary and 'summary' not in meta:
            continue
        if args.no_summary and 'summary' in meta:
            continue

        # Topic filter (title + summary)
        if args.topic:
            haystack = (meta.get('title', '') + ' ' + meta.get('summary', '')).lower()
            if args.topic.lower() not in haystack:
                continue

        # Category filter
        if args.category:
            if meta.get('category') != args.category:
                continue

        # Minimum score filter
        if args.min_score:
            total = (meta.get('score_relevance', 0) +
                    meta.get('score_quality', 0) +
                    meta.get('score_timeliness', 0))
            if total < args.min_score:
                continue

        # Published date range
        if date_from or date_to:
            pub = _parse_date_flexible(meta.get('published', ''))
            if pub is None:
                continue
            # Make naive for comparison if needed
            if date_from:
                df = date_from if date_from.tzinfo else date_from.replace(tzinfo=timezone.utc)
                pf = pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
                if pf < df:
                    continue
            if date_to:
                dt = date_to if date_to.tzinfo else date_to.replace(tzinfo=timezone.utc)
                pt = pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
                if pt > dt:
                    continue

        # Downloaded date filter
        if date_after:
            dl = _parse_date_flexible(meta.get('downloaded', ''))
            if dl is None:
                continue
            da = date_after if date_after.tzinfo else date_after.replace(tzinfo=timezone.utc)
            dd = dl if dl.tzinfo else dl.replace(tzinfo=timezone.utc)
            if dd < da:
                continue

        # --- Slow filters (need file access) ---
        filepath = os.path.join(base_dir, meta.get('filepath', ''))
        file_content = None

        if need_file_read:
            if not os.path.exists(filepath):
                continue

            # Size filters
            fsize = os.path.getsize(filepath)
            if args.min_size and fsize < args.min_size:
                continue
            if args.max_size and fsize > args.max_size:
                continue

            # Read file for keyword / lang
            if args.keyword or args.lang:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                except Exception:
                    continue

                # Keyword filter (full-text + metadata keywords)
                if args.keyword:
                    kw_lower = args.keyword.lower()
                    meta_keywords = [k.lower() for k in meta.get('keywords', [])]
                    found_in_meta = any(kw_lower in k for k in meta_keywords)
                    if not found_in_meta and kw_lower not in file_content.lower():
                        continue

                # Language filter
                if args.lang:
                    # Strip front matter for detection
                    _, body = extract_front_matter(file_content)
                    detected = _detect_lang(body)
                    if detected != args.lang:
                        continue

        # Passed all filters
        entry = {'url': url, **meta}
        if need_file_read:
            entry['_size'] = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        results.append(entry)

    # Sort
    sort_key = args.sort or 'published'
    reverse = not args.reverse  # default: newest first
    if sort_key == 'size':
        results.sort(key=lambda x: x.get('_size', 0), reverse=reverse)
    elif sort_key == 'title':
        results.sort(key=lambda x: x.get('title', '').lower(), reverse=not reverse)
    else:
        results.sort(key=lambda x: x.get(sort_key, '') or '', reverse=reverse)

    # Limit
    limit = args.limit or 50
    total_matches = len(results)
    results = results[:limit]

    # Output
    if args.json:
        # Clean internal keys
        for r in results:
            r.pop('_size', None)
        console.print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    console.print(f"\n[bold]Found {total_matches} articles[/bold]"
                  + (f" (showing top {limit})" if total_matches > limit else ""))

    if not results:
        return

    table = Table(show_header=True, header_style="bold cyan", border_style="blue",
                  expand=True, show_lines=True)
    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Published", width=10, no_wrap=True)
    table.add_column("Cat", max_width=10, no_wrap=True)
    table.add_column("Score", max_width=8, no_wrap=True)
    table.add_column("Source", max_width=18)
    table.add_column("Title", ratio=2)
    table.add_column("Summary", ratio=3)

    for i, r in enumerate(results, 1):
        pub_raw = r.get('published', '')
        pub_dt = _parse_date_flexible(pub_raw)
        pub = pub_dt.strftime('%Y-%m-%d') if pub_dt else pub_raw[:10]
        cat = r.get('category', '')[:6]
        total_score = (r.get('score_relevance', 0) +
                      r.get('score_quality', 0) +
                      r.get('score_timeliness', 0))
        score = str(total_score) if total_score > 0 else '—'
        src = r.get('source_name', '')
        if len(src) > 18:
            src = src[:15] + '...'
        title = r.get('title', '')
        if len(title) > 60:
            title = title[:57] + '...'
        summary = r.get('summary', '')
        if len(summary) > 80:
            summary = summary[:77] + '...'
        table.add_row(str(i), pub, cat, score, src, title, summary or '[dim]—[/dim]')

    console.print(table)


# ==================== CLI Entry Point ====================

def main():
    parser = argparse.ArgumentParser(
        prog='rsstools',
        description='RSSKB - RSS Knowledge Base Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  rsstools download                          Download articles from all RSS feeds
  rsstools download --force                  Re-download all articles
  rsstools summarize                         Generate AI summaries with batch processing + scoring
  rsstools summarize --force                 Re-generate all summaries with scoring
  rsstools digest                            Generate daily digest (last 48h, top 15)
  rsstools digest --hours 72 --top-n 20      Custom digest parameters
  rsstools digest --min-score 7             Only high-quality articles
  rsstools search -t "Rust"                  Search articles by title
  rsstools search --category ai-ml          Filter by category
  rsstools search -s "Paul Graham" --limit 10
  rsstools search --from 2025-06-01 --to 2025-12-31
  rsstools search -k "WebAssembly" --lang en Full-text search, English only
  rsstools search --topic "security" --json  Search title+summary, output JSON
  rsstools search --no-summary --sort downloaded
  rsstools failed                            Generate OPML for failed feeds
  rsstools stats                             Show knowledge base statistics
  rsstools config                            Show current configuration
  rsstools clean-cache                       Clean cache older than 30 days
  rsstools clean-cache --dry-run --max-age 7 Preview cleanup

environment variables:
  GLM_API_KEY       Override llm.api_key from config file
  GLM_HOST          Override LLM API host
  GLM_MODELS        Override model list (comma-separated for fallback)
  RSSKB_BASE_DIR    Override base directory (default: ~/RSSKB)
  RSSKB_OPML_PATH   Override subscriptions.opml path

config file:
  ~/.rsstools/config.json    Override any default setting (see 'rsstools config')
""",
    )
    sub = parser.add_subparsers(dest='command', help='Available commands')

    sp_download = sub.add_parser('download',
        help='Download articles from RSS feeds',
        description='Parse subscriptions.opml and download new articles. '
                    'Supports concurrent feed/article downloads, content extraction '
                    'via trafilatura, and optional AI summarization during download.')
    sp_download.add_argument('--force', action='store_true',
                             help='Re-download even if article already exists')
    sp_summarize = sub.add_parser('summarize',
        help='Batch generate AI summaries for articles',
        description='Generate AI summaries for all articles that don\'t have one yet. '
                    'Resumable — skips articles that already have summaries. '
                    'Requires llm.api_key in config or GLM_API_KEY env var.')
    sp_summarize.add_argument('--force', action='store_true',
                              help='Re-summarize even if summary exists')
    sub.add_parser('failed',
        help='Generate OPML for feeds with no downloaded articles',
        description='Cross-reference subscriptions.opml with index.json to find feeds '
                    'that have zero successfully downloaded articles, and output them '
                    'as failed_feeds.opml for re-import or debugging. '
                    'Distinguishes between failed feeds and never-tried feeds.')
    sub.add_parser('stats',
        help='Show knowledge base statistics',
        description='Display article counts, summary coverage, failure stats, '
                    'file size distribution, and top sources.')
    sub.add_parser('config',
        help='Show current configuration',
        description='Display the merged configuration (defaults + config file + env vars).')
    sp_clean = sub.add_parser('clean-cache',
        help='Clean old LLM cache files',
        description='Remove cached LLM results older than specified days.')
    sp_clean.add_argument('--max-age', type=int, default=30,
                          help='Maximum age in days (default: 30)')
    sp_clean.add_argument('--dry-run', action='store_true',
                          help='Show what would be deleted without actually deleting')

    sp = sub.add_parser('search',
        help='Search and filter articles',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Search and filter articles by multiple dimensions.',
        epilog="""filter examples:
  rsstools search -t "package manager"           Title keyword
  rsstools search -s "Keygen" --has-summary      Source + must have summary
  rsstools search --from 2026-01-01 --limit 20   Date range
  rsstools search -k "async" --lang en            Full-text + language
  rsstools search --topic "security" --json       Topic search, JSON output
  rsstools search --no-summary --sort size        Missing summaries, by size
  rsstools search --min-size 50000                Large articles only
""")
    sp.add_argument('-t', '--title', help='Search in article title')
    sp.add_argument('-s', '--source', help='Filter by source name (substring match)')
    sp.add_argument('-k', '--keyword', help='Full-text search in article content')
    sp.add_argument('--topic', help='Search in title + summary combined')
    sp.add_argument('--from', dest='date_from', help='Published after date (e.g. 2025-06-01)')
    sp.add_argument('--to', dest='date_to', help='Published before date (e.g. 2025-12-31)')
    sp.add_argument('--after', help='Downloaded after date')
    sp.add_argument('--has-summary', action='store_true', help='Only articles with summary')
    sp.add_argument('--no-summary', action='store_true', help='Only articles without summary')
    sp.add_argument('--content-source', choices=['page', 'feed'], help='Filter by content source')
    sp.add_argument('--min-size', type=int, help='Minimum file size in bytes')
    sp.add_argument('--max-size', type=int, help='Maximum file size in bytes')
    sp.add_argument('--lang', choices=['zh', 'en', 'ja', 'ko'], help='Filter by detected language')
    sp.add_argument('--category', choices=['ai-ml', 'security', 'engineering', 'tools', 'opinion', 'other'],
                    help='Filter by article category')
    sp.add_argument('--keyword', help='Full-text search in article content or keywords')
    sp.add_argument('--min-score', type=int, help='Minimum total score (1-30)')
    sp.add_argument('--limit', type=int, default=50, help='Max results (default: 50)')
    sp.add_argument('--sort', choices=['published', 'downloaded', 'title', 'size'],
                    default='published', help='Sort field (default: published)')
    sp.add_argument('--reverse', action='store_true', help='Reverse sort (oldest first)')
    sp.add_argument('--json', action='store_true', help='Output as JSON')

    sp_digest = sub.add_parser('digest',
        help='Generate daily digest report',
        description='Generate a curated daily digest from recent articles with AI scoring, '
                    'summaries, and trend analysis. Outputs a Markdown report with visualizations.')
    sp_digest.add_argument('--hours', type=int, default=48,
                           help='Time window in hours (default: 48)')
    sp_digest.add_argument('--top-n', type=int, default=15,
                           help='Number of top articles (default: 15)')
    sp_digest.add_argument('--lang', choices=['zh', 'en'], default='zh',
                           help='Summary language (default: zh)')
    sp_digest.add_argument('--output', help='Output file path (default: digest-YYYYMMDD.md)')
    sp_digest.add_argument('--min-score', type=int, default=5,
                           help='Minimum relevance score (1-10, default: 5)')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cfg = load_config()
    os.makedirs(cfg["base_dir"], exist_ok=True)

    if args.command == 'download':
        asyncio.run(cmd_download(cfg, force=args.force))
    elif args.command == 'summarize':
        asyncio.run(cmd_summarize(cfg, force=args.force))
    elif args.command == 'failed':
        cmd_failed(cfg)
    elif args.command == 'stats':
        cmd_stats(cfg)
    elif args.command == 'config':
        cmd_config(cfg)
    elif args.command == 'clean-cache':
        cmd_clean_cache(cfg, max_age_days=args.max_age, dry_run=args.dry_run)
    elif args.command == 'search':
        cmd_search(cfg, args)
    elif args.command == 'digest':
        asyncio.run(cmd_digest(cfg, hours=args.hours, top_n=args.top_n,
                              lang=args.lang, output=args.output, min_score=args.min_score))


if __name__ == '__main__':
    main()

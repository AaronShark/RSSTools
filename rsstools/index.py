"""Index management for articles"""

import os
import json
from datetime import datetime, timezone
from typing import Dict

from .utils import _parse_date_flexible


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
                from rich.console import Console
                Console().print(f"  [yellow]Warning: failed to load index: {e}[/yellow]")
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

    def get_feed_failure_info(self, url: str):
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

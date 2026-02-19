"""Utility functions for RSSTools"""

import os
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

try:
    import trafilatura

    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

from bs4 import BeautifulSoup


def yaml_escape(value: str) -> str:
    """Escape string for YAML double-quoted value. Returns '"escaped"'."""
    if not value:
        return '""'
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    value = value.replace("\t", "\\t")
    return f'"{value}"'


def yaml_unescape(value: str) -> str:
    """Unescape YAML double-quoted value."""
    if not value:
        return ""
    value = value.replace("\\t", "\t")
    value = value.replace("\\r", "\r")
    value = value.replace("\\n", "\n")
    value = value.replace('\\"', '"')
    value = value.replace("\\\\", "\\")
    return value


def _parse_date_flexible(date_str: str) -> datetime | None:
    """Parse date string with multiple format support."""
    if not date_str:
        return None
    try:
        from dateutil import parser

        dt = parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return None


def safe_dirname(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "", name).strip()
    name = re.sub(r"[\s]+", "-", name)
    return name[:80] or "unknown"


def parse_date_prefix(published: str) -> str:
    if published:
        try:
            from dateutil import parser

            dt = parser.parse(published)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return datetime.now(UTC).strftime("%Y-%m-%d")


def parse_opml(opml_path: str) -> list[dict]:
    if not os.path.exists(opml_path):
        from rich.console import Console

        Console().print(f"  [red]OPML file not found: {opml_path}[/red]")
        return []
    try:
        tree = ET.parse(opml_path)
        body = tree.getroot().find(".//body")
        if body is None:
            body = tree.getroot()
        feeds = []
        for outline in body.findall(".//outline"):
            url = outline.get("xmlUrl") or outline.get("htmlUrl")
            title = outline.get("text") or outline.get("title", "Unknown")
            if url:
                feeds.append(
                    {
                        "title": title,
                        "url": url,
                        "html_url": outline.get("htmlUrl", ""),
                    }
                )
        return feeds
    except Exception as e:
        from rich.console import Console

        Console().print(f"  [red]Failed to parse OPML: {e}[/red]")
        return []


def extract_front_matter(text: str) -> tuple[dict | None, str]:
    """Parse YAML front matter. Handles both quoted and unquoted values."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return None, text
    fm_text = m.group(1)
    body = text[m.end() :]
    meta = {}
    for line in fm_text.split("\n"):
        kv = re.match(r"^(\w[\w_]*)\s*:\s*(.*)", line)
        if kv:
            val = kv.group(2)
            # If value is double-quoted, strip quotes and unescape
            if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
                val = yaml_unescape(val[1:-1])
            meta[kv.group(1)] = val
    return meta, body


def rebuild_front_matter(meta: dict, body: str) -> str:
    """Rebuild front matter with properly escaped values."""
    lines = [f"{k}: {yaml_escape(v)}" for k, v in meta.items()]
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def extract_content(html: str, url: str) -> str | None:
    """Extract article content from HTML using trafilatura or BeautifulSoup."""
    if HAS_TRAFILATURA:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            output_format="markdown",
            include_links=True,
            include_images=True,
            include_tables=True,
        )
        if text and len(text) > 100:
            return text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
        tag.decompose()
    for sel in [
        "article",
        '[role="main"]',
        ".content",
        "#content",
        ".post",
        ".entry",
        ".article-body",
        ".post-content",
        "main",
        ".main-content",
        "#main",
    ]:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 100:
            return str(el)
    body = soup.find("body")
    if body and body.get_text(strip=True):
        return str(body)
    return None

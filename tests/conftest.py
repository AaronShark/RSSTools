"""Shared fixtures for RSSTools tests."""

import os
import tempfile

import pytest


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_dir():
    """Create a temporary directory for general file tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_opml(temp_dir):
    """Create a sample OPML file for testing."""
    opml_content = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>Test Feeds</title>
  </head>
  <body>
    <outline text="Tech" title="Tech">
      <outline text="Example Feed" title="Example Feed" xmlUrl="https://example.com/feed.xml" htmlUrl="https://example.com"/>
    </outline>
    <outline text="News" title="News" xmlUrl="https://news.example.com/rss"/>
  </body>
</opml>
"""
    opml_path = os.path.join(temp_dir, "feeds.opml")
    with open(opml_path, "w", encoding="utf-8") as f:
        f.write(opml_content)
    yield opml_path


@pytest.fixture
def sample_html():
    """Sample HTML content for content extraction tests."""
    return """
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
  <nav>Navigation</nav>
  <article>
    <h1>Article Title</h1>
    <p>This is a paragraph with <a href="https://example.com">a link</a>.</p>
    <p>Another paragraph here.</p>
    <img src="image.jpg" alt="An image">
  </article>
  <footer>Footer content</footer>
</body>
</html>
"""


@pytest.fixture
def sample_markdown():
    """Sample Markdown content for preprocessing tests."""
    return """# Title

This is [a link](https://example.com) and ![an image](https://example.com/img.png).

More text with a bare URL: https://bare-url.com

<div>Some HTML</div>
<img src="html-image.jpg">


Multiple   spaces   here.
"""

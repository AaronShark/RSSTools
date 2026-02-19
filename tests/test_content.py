"""Tests for rsstools/content.py."""

import pytest

from rsstools.content import ContentPreprocessor


@pytest.fixture
def preprocessor():
    return ContentPreprocessor()


class TestContentPreprocessor:
    """Tests for ContentPreprocessor.process()."""

    def test_process_strips_markdown_images(self, preprocessor):
        text = "Here is an image: ![alt text](https://example.com/img.png) and text."
        result = preprocessor.process(text)
        assert "![alt text]" not in result
        assert "alt text" in result
        assert "https://example.com/img.png" not in result

    def test_process_strips_html_images(self, preprocessor):
        text = "Text <img src='image.jpg' alt='pic'> more text"
        result = preprocessor.process(text)
        assert "<img" not in result
        assert "src=" not in result

    def test_process_strips_markdown_links_keeps_text(self, preprocessor):
        text = "Check out [this link](https://example.com) for more info"
        result = preprocessor.process(text)
        assert "this link" in result
        assert "[this link]" not in result
        assert "(https://example.com)" not in result

    def test_process_strips_bare_urls(self, preprocessor):
        text = "Visit https://example.com for more info"
        result = preprocessor.process(text)
        assert "https://example.com" not in result
        assert "Visit" in result
        assert "for more info" in result

    def test_process_strips_html_tags(self, preprocessor):
        text = "<div><p>Hello</p><span>World</span></div>"
        result = preprocessor.process(text)
        assert "<div>" not in result
        assert "<p>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_process_collapses_multiple_newlines(self, preprocessor):
        text = "Line 1\n\n\n\n\nLine 2"
        result = preprocessor.process(text)
        assert "\n\n\n" not in result
        assert "Line 1\n\nLine 2" in result

    def test_process_collapses_multiple_spaces(self, preprocessor):
        text = "Word1     Word2     Word3"
        result = preprocessor.process(text)
        assert "     " not in result
        assert "Word1 Word2 Word3" in result

    def test_process_strips_leading_trailing_whitespace(self, preprocessor):
        text = "   Content here   "
        result = preprocessor.process(text)
        assert result == "Content here"

    def test_process_empty_string(self, preprocessor):
        result = preprocessor.process("")
        assert result == ""

    def test_process_whitespace_only(self, preprocessor):
        result = preprocessor.process("   \n\n   ")
        assert result == ""

    def test_process_complex_content(self, preprocessor, sample_markdown):
        result = preprocessor.process(sample_markdown)
        assert "https://" not in result
        assert "![" not in result
        assert "<div>" not in result
        assert "<img" not in result

    def test_process_preserves_plain_text(self, preprocessor):
        text = "Just plain text with no formatting."
        result = preprocessor.process(text)
        assert result == text

    def test_process_handles_unicode(self, preprocessor):
        text = "Unicode: \u4e2d\u6587 \U0001f600 emoji"
        result = preprocessor.process(text)
        assert "\u4e2d\u6587" in result
        assert "\U0001f600" in result

    def test_process_nested_markdown(self, preprocessor):
        text = "![outer ![inner](url)](outer-url)"
        result = preprocessor.process(text)
        assert "![" not in result
        assert "(url)" not in result

    def test_process_http_urls(self, preprocessor):
        text = "http://example.com and https://secure.com"
        result = preprocessor.process(text)
        assert "http://example.com" not in result
        assert "https://secure.com" not in result

    def test_process_case_insensitive_html_images(self, preprocessor):
        text = "<IMG SRC='image.jpg'> <Img src='other.jpg'>"
        result = preprocessor.process(text)
        assert "<IMG" not in result.upper()
        assert "<Img" not in result

    def test_process_and_count(self, preprocessor):
        text = "Hello world"
        result, count = preprocessor.process_and_count(text)
        assert result == "Hello world"
        assert count > 0

    def test_truncate_to_tokens(self, preprocessor):
        text = "Hello world " * 1000
        truncated, count = preprocessor.truncate_to_tokens(text, 10)
        assert count <= 10

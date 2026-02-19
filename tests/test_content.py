"""Tests for rsstools/content.py."""

from rsstools.content import ContentPreprocessor


class TestContentPreprocessor:
    """Tests for ContentPreprocessor.process()."""

    def test_process_strips_markdown_images(self):
        text = "Here is an image: ![alt text](https://example.com/img.png) and text."
        result = ContentPreprocessor.process(text)
        assert "![alt text]" not in result
        assert "alt text" in result
        assert "https://example.com/img.png" not in result

    def test_process_strips_html_images(self):
        text = "Text <img src='image.jpg' alt='pic'> more text"
        result = ContentPreprocessor.process(text)
        assert "<img" not in result
        assert "src=" not in result

    def test_process_strips_markdown_links_keeps_text(self):
        text = "Check out [this link](https://example.com) for more info"
        result = ContentPreprocessor.process(text)
        assert "this link" in result
        assert "[this link]" not in result
        assert "(https://example.com)" not in result

    def test_process_strips_bare_urls(self):
        text = "Visit https://example.com for more info"
        result = ContentPreprocessor.process(text)
        assert "https://example.com" not in result
        assert "Visit" in result
        assert "for more info" in result

    def test_process_strips_html_tags(self):
        text = "<div><p>Hello</p><span>World</span></div>"
        result = ContentPreprocessor.process(text)
        assert "<div>" not in result
        assert "<p>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_process_collapses_multiple_newlines(self):
        text = "Line 1\n\n\n\n\nLine 2"
        result = ContentPreprocessor.process(text)
        assert "\n\n\n" not in result
        assert "Line 1\n\nLine 2" in result

    def test_process_collapses_multiple_spaces(self):
        text = "Word1     Word2     Word3"
        result = ContentPreprocessor.process(text)
        assert "     " not in result
        assert "Word1 Word2 Word3" in result

    def test_process_strips_leading_trailing_whitespace(self):
        text = "   Content here   "
        result = ContentPreprocessor.process(text)
        assert result == "Content here"

    def test_process_empty_string(self):
        result = ContentPreprocessor.process("")
        assert result == ""

    def test_process_whitespace_only(self):
        result = ContentPreprocessor.process("   \n\n   ")
        assert result == ""

    def test_process_complex_content(self, sample_markdown):
        result = ContentPreprocessor.process(sample_markdown)
        assert "https://" not in result
        assert "![" not in result
        assert "<div>" not in result
        assert "<img" not in result

    def test_process_preserves_plain_text(self):
        text = "Just plain text with no formatting."
        result = ContentPreprocessor.process(text)
        assert result == text

    def test_process_handles_unicode(self):
        text = "Unicode: \u4e2d\u6587 \U0001f600 emoji"
        result = ContentPreprocessor.process(text)
        assert "\u4e2d\u6587" in result
        assert "\U0001f600" in result

    def test_process_nested_markdown(self):
        text = "![outer ![inner](url)](outer-url)"
        result = ContentPreprocessor.process(text)
        assert "![" not in result
        assert "(url)" not in result

    def test_process_http_urls(self):
        text = "http://example.com and https://secure.com"
        result = ContentPreprocessor.process(text)
        assert "http://example.com" not in result
        assert "https://secure.com" not in result

    def test_process_case_insensitive_html_images(self):
        text = "<IMG SRC='image.jpg'> <Img src='other.jpg'>"
        result = ContentPreprocessor.process(text)
        assert "<IMG" not in result.upper()
        assert "<Img" not in result

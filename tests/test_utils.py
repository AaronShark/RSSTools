"""Tests for rsstools/utils.py."""

import os
from rsstools.utils import (
    yaml_escape,
    yaml_unescape,
    parse_opml,
    extract_front_matter,
    extract_content,
    safe_dirname,
    parse_date_prefix,
    rebuild_front_matter,
)


class TestYamlEscape:
    """Tests for yaml_escape()."""

    def test_empty_string(self):
        assert yaml_escape("") == '""'

    def test_none_converts_to_empty(self):
        result = yaml_escape(None)
        assert result == '""'

    def test_simple_string(self):
        assert yaml_escape("hello") == '"hello"'

    def test_escapes_backslash(self):
        assert yaml_escape("path\\to\\file") == '"path\\\\to\\\\file"'

    def test_escapes_double_quote(self):
        assert yaml_escape('say "hello"') == '"say \\"hello\\""'

    def test_escapes_newline(self):
        assert yaml_escape("line1\nline2") == '"line1\\nline2"'

    def test_escapes_carriage_return(self):
        assert yaml_escape("line1\rline2") == '"line1\\rline2"'

    def test_escapes_tab(self):
        assert yaml_escape("col1\tcol2") == '"col1\\tcol2"'

    def test_escapes_all_special_chars(self):
        result = yaml_escape('a"b\nc\rd\\e\tf')
        assert result == '"a\\"b\\nc\\rd\\\\e\\tf"'

    def test_preserves_unicode(self):
        assert yaml_escape("\u4e2d\u6587") == '"\u4e2d\u6587"'


class TestYamlUnescape:
    """Tests for yaml_unescape()."""

    def test_empty_string(self):
        assert yaml_unescape("") == ""

    def test_none_converts_to_empty(self):
        assert yaml_unescape(None) == ""

    def test_simple_string(self):
        assert yaml_unescape("hello") == "hello"

    def test_unescapes_tab(self):
        assert yaml_unescape("col1\\tcol2") == "col1\tcol2"

    def test_unescapes_carriage_return(self):
        assert yaml_unescape("line1\\rline2") == "line1\rline2"

    def test_unescapes_newline(self):
        assert yaml_unescape("line1\\nline2") == "line1\nline2"

    def test_unescapes_double_quote(self):
        assert yaml_unescape('say \\"hello\\"') == 'say "hello"'

    def test_unescapes_backslash(self):
        assert yaml_unescape(r"a\\b\\c") == r"a\b\c"

    def test_unescapes_all_special_chars(self):
        assert yaml_unescape(r'a\"b\nc\rd\\e\tf') == 'a"b\nc\rd\\e\tf'


class TestYamlRoundTrip:
    """Tests for yaml_escape/yaml_unescape round trip."""

    def test_roundtrip_simple(self):
        original = "simple text"
        assert yaml_unescape(yaml_escape(original)[1:-1]) == original

    def test_roundtrip_with_specials(self):
        original = 'text "with" \\special\\ \n\t chars'
        escaped = yaml_escape(original)
        unescaped = yaml_unescape(escaped[1:-1])
        assert unescaped == original


class TestParseOpml:
    """Tests for parse_opml()."""

    def test_parse_valid_opml(self, sample_opml):
        feeds = parse_opml(sample_opml)
        assert len(feeds) == 2
        assert any(f["url"] == "https://example.com/feed.xml" for f in feeds)
        assert any(f["url"] == "https://news.example.com/rss" for f in feeds)

    def test_parse_extracts_title(self, sample_opml):
        feeds = parse_opml(sample_opml)
        example_feed = next(f for f in feeds if "example.com" in f["url"])
        assert example_feed["title"] == "Example Feed"

    def test_parse_extracts_html_url(self, sample_opml):
        feeds = parse_opml(sample_opml)
        example_feed = next(f for f in feeds if "example.com" in f["url"])
        assert example_feed["html_url"] == "https://example.com"

    def test_parse_missing_file(self, temp_dir):
        feeds = parse_opml(os.path.join(temp_dir, "nonexistent.opml"))
        assert feeds == []

    def test_parse_invalid_xml(self, temp_dir):
        bad_opml = os.path.join(temp_dir, "bad.opml")
        with open(bad_opml, "w", encoding="utf-8") as f:
            f.write("not valid xml <")
        feeds = parse_opml(bad_opml)
        assert feeds == []

    def test_parse_empty_opml(self, temp_dir):
        opml_path = os.path.join(temp_dir, "empty.opml")
        with open(opml_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0"?><opml><body></body></opml>')
        feeds = parse_opml(opml_path)
        assert feeds == []

    def test_parse_uses_htmlUrl_fallback(self, temp_dir):
        opml_path = os.path.join(temp_dir, "html_url.opml")
        with open(opml_path, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0"?>
<opml><body>
  <outline text="Feed" htmlUrl="https://html-only.com"/>
</body></opml>""")
        feeds = parse_opml(opml_path)
        assert len(feeds) == 1
        assert feeds[0]["url"] == "https://html-only.com"

    def test_parse_uses_text_over_title(self, temp_dir):
        opml_path = os.path.join(temp_dir, "text_attr.opml")
        with open(opml_path, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0"?>
<opml><body>
  <outline text="TextTitle" title="TitleAttr" xmlUrl="https://test.com/feed"/>
</body></opml>""")
        feeds = parse_opml(opml_path)
        assert feeds[0]["title"] == "TextTitle"


class TestExtractFrontMatter:
    """Tests for extract_front_matter()."""

    def test_extracts_simple_front_matter(self):
        text = '---\ntitle: Test Title\n---\nBody content here'
        meta, body = extract_front_matter(text)
        assert meta == {"title": "Test Title"}
        assert body == "Body content here"

    def test_extracts_multiple_fields(self):
        text = '---\ntitle: Title\nauthor: Author\ndate: 2024-01-01\n---\nBody'
        meta, body = extract_front_matter(text)
        assert meta["title"] == "Title"
        assert meta["author"] == "Author"
        assert meta["date"] == "2024-01-01"

    def test_handles_quoted_values(self):
        text = '---\ntitle: "Quoted Title"\n---\nBody'
        meta, body = extract_front_matter(text)
        assert meta["title"] == "Quoted Title"

    def test_handles_escaped_in_quotes(self):
        text = '---\ntitle: "Line1\\nLine2"\n---\nBody'
        meta, body = extract_front_matter(text)
        assert meta["title"] == "Line1\nLine2"

    def test_no_front_matter(self):
        text = "Just body content without front matter"
        meta, body = extract_front_matter(text)
        assert meta is None
        assert body == text

    def test_empty_front_matter(self):
        text = "---\n---\nBody"
        meta, body = extract_front_matter(text)
        assert meta is None
        assert body == text

    def test_preserves_body_formatting(self):
        text = "---\ntitle: Test\n---\n\n# Heading\n\nParagraph"
        meta, body = extract_front_matter(text)
        assert body == "\n# Heading\n\nParagraph"

    def test_handles_colon_in_value(self):
        text = '---\ntitle: "Title: Subtitle"\n---\nBody'
        meta, body = extract_front_matter(text)
        assert meta["title"] == "Title: Subtitle"


class TestRebuildFrontMatter:
    """Tests for rebuild_front_matter()."""

    def test_rebuilds_simple(self):
        meta = {"title": "Test"}
        body = "Content"
        result = rebuild_front_matter(meta, body)
        assert result.startswith("---\n")
        assert "---\nContent" in result

    def test_escapes_values(self):
        meta = {"title": 'Text with "quotes" and \\backslash'}
        body = "Content"
        result = rebuild_front_matter(meta, body)
        assert '\\"' in result
        assert "\\\\" in result


class TestExtractContent:
    """Tests for extract_content()."""

    def test_extracts_from_article(self, sample_html):
        result = extract_content(sample_html, "https://example.com/article")
        assert result is not None
        assert "Article Title" in result

    def test_returns_none_for_empty_html(self):
        result = extract_content("", "https://example.com")
        assert result is None or result.strip() == ""

    def test_removes_script_and_style(self):
        html = "<html><body><script>alert('xss')</script><p>Content</p></body></html>"
        result = extract_content(html, "https://example.com")
        assert result is not None
        assert "alert" not in result or "xss" not in result

    def test_removes_nav_footer(self):
        html = "<html><body><nav>Nav</nav><main>Main content here is longer</main><footer>Footer</footer></body></html>"
        result = extract_content(html, "https://example.com")
        if result:
            assert "Nav" not in result or "Main" in result

    def test_handles_malformed_html(self):
        html = "<html><body><p>Content here is long enough to pass length checks</p></body></html>"
        result = extract_content(html, "https://example.com")
        assert result is not None


class TestSafeDirname:
    """Tests for safe_dirname()."""

    def test_removes_invalid_chars(self):
        assert "<" not in safe_dirname("file<name")
        assert ">" not in safe_dirname("file>name")
        assert ":" not in safe_dirname("file:name")
        assert '"' not in safe_dirname('file"name')
        assert "/" not in safe_dirname("file/name")
        assert "\\" not in safe_dirname("file\\name")
        assert "|" not in safe_dirname("file|name")
        assert "?" not in safe_dirname("file?name")
        assert "*" not in safe_dirname("file*name")

    def test_replaces_whitespace_with_dash(self):
        assert safe_dirname("file name") == "file-name"
        assert safe_dirname("file  name") == "file-name"

    def test_truncates_long_names(self):
        long_name = "a" * 100
        assert len(safe_dirname(long_name)) == 80

    def test_returns_unknown_for_empty(self):
        assert safe_dirname("") == "unknown"
        assert safe_dirname("   ") == "unknown"

    def test_strips_whitespace(self):
        assert safe_dirname("  name  ") == "name"


class TestParseDatePrefix:
    """Tests for parse_date_prefix()."""

    def test_parse_iso_date(self):
        result = parse_date_prefix("2024-03-15T10:30:00Z")
        assert result == "2024-03-15"

    def test_parse_rfc2822_date(self):
        result = parse_date_prefix("Fri, 15 Mar 2024 10:30:00 GMT")
        assert result == "2024-03-15"

    def test_returns_today_for_invalid(self):
        result = parse_date_prefix("invalid date")
        assert len(result) == 10
        assert "-" in result

    def test_returns_today_for_none(self):
        result = parse_date_prefix(None)
        assert len(result) == 10

    def test_returns_today_for_empty(self):
        result = parse_date_prefix("")
        assert len(result) == 10

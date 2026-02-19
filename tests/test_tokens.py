"""Tests for rsstools/tokens.py."""

import pytest

from rsstools.tokens import TokenCounter


@pytest.fixture
def counter():
    return TokenCounter()


class TestTokenCounter:
    """Tests for TokenCounter."""

    def test_count_simple_text(self, counter):
        text = "Hello world"
        count = counter.count(text)
        assert count > 0
        assert count < 10

    def test_count_empty_string(self, counter):
        assert counter.count("") == 0

    def test_count_none_string(self, counter):
        assert counter.count(None) == 0

    def test_count_unicode(self, counter):
        text = "Chinese: 中文字符"
        count = counter.count(text)
        assert count > 0

    def test_count_long_text(self, counter):
        text = "word " * 1000
        count = counter.count(text)
        assert count > 500

    def test_truncate_no_truncation_needed(self, counter):
        text = "Hello world"
        result = counter.truncate(text, 100)
        assert result == text

    def test_truncate_truncation_needed(self, counter):
        text = "Hello world " * 100
        result = counter.truncate(text, 5)
        count = counter.count(result)
        assert count <= 5

    def test_truncate_empty_string(self, counter):
        assert counter.truncate("", 10) == ""

    def test_truncate_preserves_start(self, counter):
        text = "The quick brown fox jumps over the lazy dog"
        result = counter.truncate(text, 5)
        assert result.startswith("The")

    def test_chunk_no_chunking_needed(self, counter):
        text = "Short text"
        chunks = counter.chunk(text, 100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_multiple_chunks(self, counter):
        text = "word " * 100
        chunks = counter.chunk(text, 20)
        assert len(chunks) > 1
        for chunk in chunks:
            assert counter.count(chunk) <= 20

    def test_chunk_with_overlap(self, counter):
        text = "word " * 100
        chunks = counter.chunk(text, 20, overlap=5)
        assert len(chunks) > 1

    def test_chunk_empty_string(self, counter):
        assert counter.chunk("", 10) == []

    def test_count_messages_single(self, counter):
        messages = [{"role": "user", "content": "Hello"}]
        count = counter.count_messages(messages)
        assert count > 0

    def test_count_messages_multiple(self, counter):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi there"},
        ]
        count = counter.count_messages(messages)
        assert count > 0

    def test_count_messages_empty(self, counter):
        assert counter.count_messages([]) == 2

    def test_different_models(self):
        counter_gpt4 = TokenCounter("gpt-4")
        counter_gpt35 = TokenCounter("gpt-3.5-turbo")
        text = "Hello world"
        count4 = counter_gpt4.count(text)
        count35 = counter_gpt35.count(text)
        assert count4 == count35

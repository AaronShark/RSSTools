"""Content preprocessing for LLM"""

import re

from .tokens import TokenCounter


class ContentPreprocessor:
    """Clean content before sending to LLM (FeedCraft-inspired)."""

    def __init__(self, token_model: str = "gpt-4"):
        self.token_counter = TokenCounter(token_model)

    def process(self, text: str) -> str:
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"<img[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def process_and_count(self, text: str) -> tuple[str, int]:
        cleaned = self.process(text)
        token_count = self.token_counter.count(cleaned)
        return cleaned, token_count

    def truncate_to_tokens(self, text: str, max_tokens: int) -> tuple[str, int]:
        cleaned = self.process(text)
        truncated = self.token_counter.truncate(cleaned, max_tokens)
        return truncated, self.token_counter.count(truncated)

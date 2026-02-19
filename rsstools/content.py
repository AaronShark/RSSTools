"""Content preprocessing for LLM"""

import re


class ContentPreprocessor:
    """Clean content before sending to LLM (FeedCraft-inspired)."""

    @staticmethod
    def process(text: str) -> str:
        # Strip markdown images: ![alt](url)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        # Strip HTML images
        text = re.sub(r"<img[^>]*>", "", text, flags=re.IGNORECASE)
        # Strip URLs but keep link text: [text](url) -> text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Strip bare URLs
        text = re.sub(r"https?://\S+", "", text)
        # Strip remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

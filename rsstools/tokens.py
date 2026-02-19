"""Token counting and management using tiktoken."""

import tiktoken


class TokenCounter:
    """Count and manage tokens for LLM APIs."""

    def __init__(self, model: str = "gpt-4"):
        self.model = model
        self.encoding = tiktoken.encoding_for_model(model)

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def truncate(self, text: str, max_tokens: int) -> str:
        if not text:
            return ""
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.encoding.decode(tokens[:max_tokens])

    def chunk(self, text: str, chunk_size: int, overlap: int = 0) -> list[str]:
        if not text:
            return []
        tokens = self.encoding.encode(text)
        if len(tokens) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(tokens):
            end = start + chunk_size
            chunk_tokens = tokens[start:end]
            chunks.append(self.encoding.decode(chunk_tokens))
            start = end - overlap if overlap > 0 else end
            if start < 0:
                start = 0
        return chunks

    def count_messages(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += self.count(msg.get("role", ""))
            total += self.count(msg.get("content", ""))
            total += 4
        total += 2
        return total

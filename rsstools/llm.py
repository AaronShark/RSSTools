"""LLM client for summarization and scoring"""

import asyncio
import json

import aiohttp

from .cache import LLMCache
from .circuit_breaker import CircuitBreaker, CircuitState
from .content import ContentPreprocessor
from .logging_config import get_logger
from .lru_cache import AsyncSlidingWindowRateLimiter

logger = get_logger(__name__)


class LLMClient:
    """Async LLM client with multi-model fallback, retry, caching, serial execution."""

    def __init__(self, cfg: dict, cache: LLMCache):
        self.host = cfg["host"]
        self.models = [m.strip() for m in cfg["models"].split(",")]
        self.max_tokens = cfg["max_tokens"]
        self.temperature = cfg["temperature"]
        self.max_content_chars = cfg["max_content_chars"]
        self.request_delay = cfg["request_delay"]
        self.max_retries = cfg["max_retries"]
        self.timeout = cfg["timeout"]
        self.system_prompt = cfg["system_prompt"]
        self.user_prompt_template = cfg["user_prompt"]
        self.cache = cache
        self.api_key = cfg.get("api_key", "")
        self._lock = asyncio.Lock()
        self.preprocessor = ContentPreprocessor()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._rate_limiters: dict[str, AsyncSlidingWindowRateLimiter] = {}
        self.use_content_only_cache_key = cfg.get("use_content_only_cache_key", False)
        cb_failure_threshold = cfg.get("circuit_breaker_failure_threshold", 5)
        cb_recovery_timeout = cfg.get("circuit_breaker_recovery_timeout", 60.0)
        rate_limits = cfg.get("rate_limit_requests_per_minute", {})
        default_rate_limit = rate_limits.get("default", 60)
        for model in self.models:
            self._circuit_breakers[model] = CircuitBreaker(
                failure_threshold=cb_failure_threshold,
                recovery_timeout=cb_recovery_timeout,
            )
            rpm = rate_limits.get(model, default_rate_limit)
            self._rate_limiters[model] = AsyncSlidingWindowRateLimiter(
                max_requests=rpm, window_seconds=60
            )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _get_cache_key(self, model: str, system: str, user: str) -> str:
        """Generate cache key based on configuration."""
        if self.use_content_only_cache_key:
            import hashlib
            return hashlib.sha256(user.encode()).hexdigest()
        import hashlib
        return hashlib.sha256(f"{model}|{system}|{user}".encode()).hexdigest()

    async def summarize(
        self, session: aiohttp.ClientSession, title: str, content: str
    ) -> tuple[str | None, str | None]:
        """Returns (summary, error). Serial via lock."""
        if not self.api_key:
            return None, "LLM api_key not set"
        async with self._lock:
            return await self._call_with_fallback(session, title, content)

    async def _call_with_fallback(self, session, title, content):
        cleaned = self.preprocessor.process(content)
        truncated = cleaned[: self.max_content_chars]
        user_msg = self.user_prompt_template.format(title=title, content=truncated)
        last_error = None

        for model in self.models:
            cb = self._circuit_breakers.get(model)
            if cb and not await cb.can_execute():
                logger.warning(
                    "circuit_breaker_open",
                    model=model,
                    state=cb.state.value,
                    action="skipping_model",
                )
                continue

            rate_limiter = self._rate_limiters.get(model)
            if rate_limiter:
                wait_time = await rate_limiter.wait_time()
                if wait_time > 0:
                    logger.debug(
                        "rate_limit_wait",
                        model=model,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                if not await rate_limiter.allow_request():
                    logger.warning(
                        "rate_limit_exceeded",
                        model=model,
                        action="skipping_model",
                    )
                    continue

            cache_key = self._get_cache_key(model, self.system_prompt, user_msg)
            cached = self.cache.get_by_key(cache_key)
            if cached:
                return cached, None

            result, error = await self._call_api(session, model, user_msg)
            if result:
                if cb:
                    await cb.record_success()
                self.cache.put_by_key(cache_key, result)
                await asyncio.sleep(self.request_delay)
                return result, None
            if cb:
                prev_state = cb.state
                await cb.record_failure()
                if prev_state != cb.state:
                    logger.info(
                        "circuit_breaker_state_change",
                        model=model,
                        from_state=prev_state.value,
                        to_state=cb.state.value,
                    )
            if error and error == "Content filtered (400)":
                return None, error
            last_error = error
            logger.warning("model_failed", model=model, error=error, action="trying_next")

        await asyncio.sleep(self.request_delay)
        return None, last_error

    async def _call_api(self, session, model, user_msg):
        url = f"{self.host}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        usage = data.get("usage", {})
                        total_tok = usage.get("completion_tokens", 0)
                        reasoning = usage.get("completion_tokens_details", {}).get(
                            "reasoning_tokens", 0
                        )
                        logger.debug(
                            "tokens_used",
                            reasoning_tokens=reasoning,
                            content_tokens=total_tok - reasoning,
                        )
                        result = data["choices"][0]["message"]["content"].strip()
                        if not result:
                            return None, f"Empty content (reasoning {reasoning}/{total_tok})"
                        return result, None
                    if resp.status == 400:
                        return None, "Content filtered (400)"
                    last_error = f"HTTP {resp.status}"
            except (TimeoutError, aiohttp.ClientError, ConnectionError, OSError) as e:
                last_error = f"{type(e).__name__}: {e}"
            except Exception as e:
                return None, f"Unexpected: {e}"
            wait = min(2**attempt * 2, 60)
            logger.warning(
                "api_retry",
                error=last_error,
                wait_seconds=wait,
                attempt=attempt + 1,
                max_retries=self.max_retries,
            )
            await asyncio.sleep(wait)
        return None, f"Gave up after {self.max_retries} retries: {last_error}"

    async def score_and_classify(
        self, session: aiohttp.ClientSession, title: str, content: str
    ) -> tuple[dict | None, str | None]:
        """Score and classify article. Returns (result_dict, error)."""
        if not self.api_key:
            return None, "LLM api_key not set"

        cleaned = self.preprocessor.process(content)
        truncated = cleaned[: self.max_content_chars]
        prompt = (
            f"Rate this article on 3 dimensions (1-10 scale):\n"
            f"- relevance: Value to tech professionals\n"
            f"- quality: Depth and writing quality\n"
            f"- timeliness: Current relevance\n\n"
            f"Classify into exactly one of these categories:\n"
            f"ai-ml (AI/ML), security, engineering, tools, opinion, other\n\n"
            f"Extract 2-4 keywords (single words or short phrases).\n\n"
            f"Article title: {title}\n\n"
            f"Article content:\n{truncated}\n\n"
            f"Return ONLY valid JSON (no markdown formatting):\n"
            f'{{"relevance": <1-10>, "quality": <1-10>, "timeliness": <1-10>, '
            f'"category": "<category>", "keywords": ["keyword1", "keyword2"]}}'
        )

        user_msg = prompt
        last_error = None
        for model in self.models:
            cb = self._circuit_breakers.get(model)
            if cb and not await cb.can_execute():
                logger.warning(
                    "circuit_breaker_open",
                    model=model,
                    state=cb.state.value,
                    action="skipping_model",
                )
                continue

            rate_limiter = self._rate_limiters.get(model)
            if rate_limiter:
                wait_time = await rate_limiter.wait_time()
                if wait_time > 0:
                    logger.debug(
                        "rate_limit_wait",
                        model=model,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                if not await rate_limiter.allow_request():
                    logger.warning(
                        "rate_limit_exceeded",
                        model=model,
                        action="skipping_model",
                    )
                    continue

            cache_key = self._get_cache_key(model, self.system_prompt, user_msg)
            cached = self.cache.get_by_key(cache_key)
            if cached:
                try:
                    return json.loads(cached), None
                except json.JSONDecodeError:
                    pass

            result, error = await self._call_api(session, model, user_msg)
            if result:
                if cb:
                    await cb.record_success()
                try:
                    data = json.loads(result)
                    self.cache.put_by_key(cache_key, result)
                    await asyncio.sleep(self.request_delay)
                    return data, None
                except json.JSONDecodeError as e:
                    return None, f"Invalid JSON response: {e}"

            if cb:
                prev_state = cb.state
                await cb.record_failure()
                if prev_state != cb.state:
                    logger.info(
                        "circuit_breaker_state_change",
                        model=model,
                        from_state=prev_state.value,
                        to_state=cb.state.value,
                    )
            if error and error == "Content filtered (400)":
                return None, error
            last_error = error
            logger.warning("score_model_failed", model=model, error=error, action="trying_next")

        await asyncio.sleep(self.request_delay)
        return None, last_error

    async def summarize_batch(
        self, session: aiohttp.ClientSession, articles: list[dict]
    ) -> list[dict]:
        """Summarize multiple articles in one API call.
        Args:
            articles: List of {'title': str, 'content': str}
        Returns:
            List of {'summary': str, 'error': Optional[str]}
        """
        if not articles:
            return []
        if not self.api_key:
            return [{"summary": None, "error": "LLM api_key not set"}] * len(articles)

        batch_size = 10
        all_results = []

        for i in range(0, len(articles), batch_size):
            batch = articles[i : i + batch_size]
            articles_text = "\n\n---\n\n".join(
                [
                    f"Index {idx}: {a['title']}\n\n{self.preprocessor.process(a['content'][:2000])}"
                    for idx, a in enumerate(batch)
                ]
            )

            prompt = (
                f"Summarize each article in 2-3 sentences, in the same language as the article.\n"
                f"Return ONLY valid JSON (no markdown formatting):\n"
                f'{{"results": [{{"index": 0, "summary": "..."}}, {{"index": 1, "summary": "..."}}]}}\n\n'
                f"Articles:\n{articles_text}"
            )

            batch_results = await self._process_batch(session, prompt, len(batch))
            all_results.extend(batch_results)

            await asyncio.sleep(self.request_delay)

        return all_results

    async def _process_batch(
        self, session: aiohttp.ClientSession, prompt: str, batch_size: int
    ) -> list[dict]:
        """Process batch with fallback to individual calls."""
        for model in self.models:
            rate_limiter = self._rate_limiters.get(model)
            if rate_limiter:
                wait_time = await rate_limiter.wait_time()
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                if not await rate_limiter.allow_request():
                    continue

            cache_key = self._get_cache_key(model, self.system_prompt, prompt)
            cached = self.cache.get_by_key(cache_key)
            if cached:
                try:
                    data = json.loads(cached)
                    return data.get("results", [])
                except json.JSONDecodeError:
                    pass

            result, error = await self._call_api(session, model, prompt)
            if result:
                try:
                    data = json.loads(result)
                    self.cache.put_by_key(cache_key, result)
                    results = data.get("results", [])
                    if len(results) == batch_size:
                        return [{"summary": r.get("summary"), "error": None} for r in results]
                except json.JSONDecodeError:
                    logger.warning("batch_json_parse_failed", action="trying_next_model")

            if error and error == "Content filtered (400)":
                break
            logger.warning("batch_failed", model=model, error=error, action="trying_fallback")

        await asyncio.sleep(self.request_delay)
        return [{"summary": None, "error": "Batch processing failed"}] * batch_size

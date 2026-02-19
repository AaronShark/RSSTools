"""Tests for URL validator SSRF protection."""

import pytest

from rsstools.url_validator import SSRFError, UrlValidator, validate_url


class TestUrlValidator:
    def test_valid_http_url(self):
        validator = UrlValidator()
        url = "http://example.com/path"
        assert validator.validate(url) == url

    def test_valid_https_url(self):
        validator = UrlValidator()
        url = "https://example.com/path"
        assert validator.validate(url) == url

    def test_block_file_scheme(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="not allowed"):
            validator.validate("file:///etc/passwd")

    def test_block_ftp_scheme(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="not allowed"):
            validator.validate("ftp://example.com/file")

    def test_block_javascript_scheme(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="not allowed"):
            validator.validate("javascript:alert(1)")

    def test_block_data_scheme(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="not allowed"):
            validator.validate("data:text/html,<script>alert(1)</script>")

    def test_block_localhost(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="blocked"):
            validator.validate("http://localhost/admin")

    def test_block_127_0_0_1(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="blocked"):
            validator.validate("http://127.0.0.1/admin")

    def test_block_127_any(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="blocked"):
            validator.validate("http://127.0.0.5/admin")

    def test_block_10_x_private(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="blocked"):
            validator.validate("http://10.0.0.1/internal")

    def test_block_172_16_private(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="blocked"):
            validator.validate("http://172.16.0.1/internal")

    def test_block_192_168_private(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="blocked"):
            validator.validate("http://192.168.1.1/internal")

    def test_block_169_254_link_local(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="blocked"):
            validator.validate("http://169.254.1.1/internal")

    def test_block_ipv6_loopback(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="blocked"):
            validator.validate("http://[::1]/admin")

    def test_empty_url(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="empty"):
            validator.validate("")

    def test_none_url(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError):
            validator.validate(None)

    def test_url_without_hostname(self):
        validator = UrlValidator()
        with pytest.raises(SSRFError, match="no hostname"):
            validator.validate("http:///path")

    def test_custom_allowed_schemes(self):
        validator = UrlValidator(allowed_schemes=["http", "https", "ftp"])
        assert validator.validate("ftp://example.com/file") == "ftp://example.com/file"

    def test_is_safe_returns_true_for_valid(self):
        validator = UrlValidator()
        assert validator.is_safe("https://example.com") is True

    def test_is_safe_returns_false_for_blocked(self):
        validator = UrlValidator()
        assert validator.is_safe("http://localhost") is False

    def test_public_ip_allowed(self):
        validator = UrlValidator()
        url = "http://8.8.8.8/dns"
        assert validator.validate(url) == url

    def test_valid_url_with_port(self):
        validator = UrlValidator()
        url = "https://example.com:8080/path"
        assert validator.validate(url) == url

    def test_valid_url_with_query(self):
        validator = UrlValidator()
        url = "https://example.com/path?query=value"
        assert validator.validate(url) == url

    def test_convenience_function(self):
        assert validate_url("https://example.com") == "https://example.com"


class TestDomainRateLimiter:
    def test_rate_limiter_init(self):
        from rsstools.downloader import DomainRateLimiter

        limiter = DomainRateLimiter({"example.com": 10})
        assert limiter.rate_limits == {"example.com": 10}

    @pytest.mark.asyncio
    async def test_rate_limiter_no_limit(self):
        from rsstools.downloader import DomainRateLimiter

        limiter = DomainRateLimiter({})
        await limiter.acquire("example.com")

    @pytest.mark.asyncio
    async def test_rate_limiter_zero_limit(self):
        from rsstools.downloader import DomainRateLimiter

        limiter = DomainRateLimiter({"example.com": 0})
        await limiter.acquire("example.com")

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_delay(self):
        import time

        from rsstools.downloader import DomainRateLimiter

        limiter = DomainRateLimiter({"example.com": 10})

        start = time.monotonic()
        await limiter.acquire("example.com")
        await limiter.acquire("example.com")
        elapsed = time.monotonic() - start

        assert elapsed >= 0.1

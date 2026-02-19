"""URL validation for SSRF protection."""

import ipaddress
import re
from urllib.parse import urlparse


class SSRFError(Exception):
    """Raised when URL is blocked due to SSRF protection."""
    pass


class UrlValidator:
    """Validate URLs to prevent Server-Side Request Forgery."""

    BLOCKED_SCHEMES = frozenset(["file", "ftp", "gopher", "data", "javascript", "vbscript"])
    ALLOWED_SCHEMES = frozenset(["http", "https"])

    PRIVATE_IP_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    def __init__(self, allowed_schemes: list[str] | None = None):
        self.allowed_schemes = frozenset(allowed_schemes) if allowed_schemes else self.ALLOWED_SCHEMES

    def validate(self, url: str) -> str:
        """Validate URL and return it if safe.

        Args:
            url: URL to validate

        Returns:
            The validated URL

        Raises:
            SSRFError: If URL is blocked
        """
        if not url or not isinstance(url, str):
            raise SSRFError("Invalid URL: empty or not a string")

        url = url.strip()

        try:
            parsed = urlparse(url)
        except Exception as e:
            raise SSRFError(f"Invalid URL format: {e}") from e

        scheme = parsed.scheme.lower()
        if scheme not in self.allowed_schemes:
            raise SSRFError(f"URL scheme '{scheme}' is not allowed")

        hostname = parsed.hostname
        if not hostname:
            raise SSRFError("URL has no hostname")

        self._validate_hostname(hostname)
        return url

    def _validate_hostname(self, hostname: str) -> None:
        """Validate hostname is not a blocked IP or resolves to one."""
        hostname_lower = hostname.lower()

        if hostname_lower in ("localhost", "localhost.localdomain"):
            raise SSRFError("localhost is blocked")

        if self._is_blocked_ip_literal(hostname):
            raise SSRFError(f"IP address {hostname} is in blocked range")

        ipv4_pattern = r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
        match = re.match(ipv4_pattern, hostname)
        if match:
            octets = [int(g) for g in match.groups()]
            if all(0 <= o <= 255 for o in octets):
                ip_str = ".".join(str(o) for o in octets)
                if self._is_ip_in_blocked_range(ip_str):
                    raise SSRFError(f"IP address {ip_str} is in blocked range")

    def _is_blocked_ip_literal(self, hostname: str) -> bool:
        """Check if hostname is an IP literal in blocked range."""
        try:
            if hostname.startswith("[") and hostname.endswith("]"):
                hostname = hostname[1:-1]
            ip = ipaddress.ip_address(hostname)
            return self._is_ip_blocked(ip)
        except ValueError:
            return False

    def _is_ip_in_blocked_range(self, ip_str: str) -> bool:
        """Check if IP string is in a blocked range."""
        try:
            ip = ipaddress.ip_address(ip_str)
            return self._is_ip_blocked(ip)
        except ValueError:
            return False

    def _is_ip_blocked(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        """Check if IP object is in any blocked range."""
        for network in self.PRIVATE_IP_RANGES:
            if ip in network:
                return True
        return False

    def is_safe(self, url: str) -> bool:
        """Check if URL is safe without raising exception.

        Args:
            url: URL to check

        Returns:
            True if URL is safe, False otherwise
        """
        try:
            self.validate(url)
            return True
        except SSRFError:
            return False


def validate_url(url: str) -> str:
    """Convenience function to validate a URL.

    Args:
        url: URL to validate

    Returns:
        Validated URL

    Raises:
        SSRFError: If URL is blocked
    """
    validator = UrlValidator()
    return validator.validate(url)

"""Tests for browser connector stealth features."""

from erasure_executor.connectors.browser import (
    BrokerRateLimiter,
    BrowserConnector,
    RobotsTxtBlocked,
    RobotsTxtChecker,
    get_rate_limiter,
)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def test_rate_limiter_allows_within_limit():
    limiter = BrokerRateLimiter(max_per_hour=5)
    for _ in range(5):
        assert limiter.acquire("spokeo") is True


def test_rate_limiter_blocks_over_limit():
    limiter = BrokerRateLimiter(max_per_hour=3)
    for _ in range(3):
        assert limiter.acquire("spokeo") is True
    assert limiter.acquire("spokeo") is False


def test_rate_limiter_separate_keys():
    limiter = BrokerRateLimiter(max_per_hour=2)
    assert limiter.acquire("spokeo") is True
    assert limiter.acquire("spokeo") is True
    assert limiter.acquire("spokeo") is False
    # Different broker key should still work
    assert limiter.acquire("beenverified") is True


def test_rate_limiter_disabled():
    limiter = BrokerRateLimiter(max_per_hour=0)
    for _ in range(100):
        assert limiter.acquire("any") is True


def test_get_rate_limiter_singleton():
    # Just ensure it returns a BrokerRateLimiter
    limiter = get_rate_limiter(50)
    assert isinstance(limiter, BrokerRateLimiter)


# ---------------------------------------------------------------------------
# BrowserConnector config
# ---------------------------------------------------------------------------

def test_browser_connector_default_config():
    bc = BrowserConnector()
    assert bc._headless is True
    assert bc._stealth is True
    assert bc._proxy_url is None
    assert bc._min_delay_s == 1.0
    assert bc._max_delay_s == 3.0
    assert bc._check_robots_txt is True


def test_browser_connector_custom_config():
    bc = BrowserConnector(
        headless=False,
        stealth=False,
        proxy_url="http://proxy.example.com:8080",
        proxy_username="user",
        proxy_password="pass",
        min_delay_ms=500,
        max_delay_ms=2000,
        check_robots_txt=False,
    )
    assert bc._headless is False
    assert bc._stealth is False
    assert bc._proxy_url == "http://proxy.example.com:8080"
    assert bc._proxy_username == "user"
    assert bc._proxy_password == "pass"
    assert bc._min_delay_s == 0.5
    assert bc._max_delay_s == 2.0
    assert bc._check_robots_txt is False


def test_browser_connector_human_delay():
    bc = BrowserConnector(min_delay_ms=1000, max_delay_ms=2000)
    delay = bc._human_delay(1.0)
    assert 1.0 <= delay <= 2.0

    delay_half = bc._human_delay(0.5)
    assert 0.5 <= delay_half <= 1.0


# ---------------------------------------------------------------------------
# robots.txt checker
# ---------------------------------------------------------------------------

def test_robots_checker_fail_open():
    """When robots.txt can't be fetched, should allow access."""
    checker = RobotsTxtChecker()
    # This domain won't resolve, so _fetch returns None, is_allowed returns True
    assert checker.is_allowed("http://nonexistent-domain-12345.test/page") is True

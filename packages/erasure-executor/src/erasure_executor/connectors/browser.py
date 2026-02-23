from __future__ import annotations

import asyncio
import logging
import random
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1680, "height": 1050},
]


@dataclass
class BrowserResult:
    url: str
    status: int
    html: str
    screenshot_path: str | None
    extracted: dict | None


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class BrokerRateLimiter:
    """Token bucket rate limiter keyed by broker domain."""

    def __init__(self, max_per_hour: int = 30):
        self._max_per_hour = max_per_hour
        self._lock = threading.Lock()
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def acquire(self, broker_key: str) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        if self._max_per_hour <= 0:
            return True
        now = time.monotonic()
        window = 3600.0
        with self._lock:
            ts_list = self._timestamps[broker_key]
            # Prune old entries
            self._timestamps[broker_key] = [t for t in ts_list if now - t < window]
            if len(self._timestamps[broker_key]) >= self._max_per_hour:
                return False
            self._timestamps[broker_key].append(now)
            return True

    def wait(self, broker_key: str, timeout: float = 120.0) -> bool:
        """Block until a slot is available or timeout. Returns True if acquired."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.acquire(broker_key):
                return True
            time.sleep(1.0)
        return False


# Global rate limiter (configured at module level, updated on first use)
_rate_limiter: BrokerRateLimiter | None = None


def get_rate_limiter(max_per_hour: int = 30) -> BrokerRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = BrokerRateLimiter(max_per_hour)
    return _rate_limiter


# ---------------------------------------------------------------------------
# robots.txt checker
# ---------------------------------------------------------------------------

class RobotsTxtChecker:
    """Caches robots.txt per domain and checks if a URL is allowed."""

    def __init__(self):
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def is_allowed(self, url: str, user_agent: str = "*") -> bool:
        """Check if the URL is allowed by robots.txt. Returns True on failure (fail open)."""
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        with self._lock:
            if origin not in self._parsers:
                self._parsers[origin] = self._fetch(origin)

            parser = self._parsers[origin]
            if parser is None:
                return True  # Could not fetch — fail open
            return parser.can_fetch(user_agent, url)

    @staticmethod
    def _fetch(origin: str) -> RobotFileParser | None:
        robots_url = f"{origin}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
            return parser
        except Exception:
            logger.debug("robots_txt.fetch_failed origin=%s", origin)
            return None


_robots_checker = RobotsTxtChecker()


# ---------------------------------------------------------------------------
# Browser connector
# ---------------------------------------------------------------------------

class BrowserConnector:
    """Playwright-based browser for JS-heavy broker sites."""

    def __init__(
        self,
        headless: bool = True,
        stealth: bool = True,
        proxy_url: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
        min_delay_ms: int = 1000,
        max_delay_ms: int = 3000,
        check_robots_txt: bool = True,
    ):
        self._headless = headless
        self._stealth = stealth
        self._proxy_url = proxy_url
        self._proxy_username = proxy_username
        self._proxy_password = proxy_password
        self._min_delay_s = min_delay_ms / 1000.0
        self._max_delay_s = max_delay_ms / 1000.0
        self._check_robots_txt = check_robots_txt
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()

            launch_kwargs: dict[str, Any] = {"headless": self._headless}
            if self._proxy_url:
                proxy: dict[str, str] = {"server": self._proxy_url}
                if self._proxy_username:
                    proxy["username"] = self._proxy_username
                if self._proxy_password:
                    proxy["password"] = self._proxy_password
                launch_kwargs["proxy"] = proxy

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        return self._browser

    async def _new_page(self):
        browser = await self._ensure_browser()
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport=random.choice(VIEWPORTS),
            locale="en-US",
        )
        page = await context.new_page()

        if self._stealth:
            # Inject basic stealth: override navigator.webdriver
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = {runtime: {}};
            """)

        return page

    def _human_delay(self, factor: float = 1.0) -> float:
        """Return a human-like delay in seconds."""
        return random.uniform(self._min_delay_s * factor, self._max_delay_s * factor)

    async def navigate(self, url: str, wait_for: str | None = None, timeout_ms: int = 15000):
        """Navigate to a URL and optionally wait for a selector."""
        if self._check_robots_txt and not _robots_checker.is_allowed(url):
            logger.warning("browser.robots_blocked url=%s", url)
            raise RobotsTxtBlocked(f"robots.txt disallows access: {url}")

        page = await self._new_page()
        response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        status = response.status if response else 0

        if wait_for:
            try:
                await page.wait_for_selector(wait_for, timeout=timeout_ms)
            except Exception:
                logger.warning("browser.wait_for_timeout selector=%s url=%s", wait_for, url)

        await asyncio.sleep(self._human_delay())
        return page, status

    async def extract(self, page, selectors: dict[str, str]) -> dict[str, list[str]]:
        """Extract data from page using CSS selectors."""
        results: dict[str, list[str]] = {}
        for key, selector in selectors.items():
            if " @" in selector:
                css, attr = selector.rsplit(" @", 1)
                elements = await page.query_selector_all(css)
                results[key] = [
                    (await el.get_attribute(attr.strip())) or "" for el in elements
                ]
            else:
                elements = await page.query_selector_all(selector)
                results[key] = [
                    (await el.text_content()) or "" for el in elements
                ]
        return results

    async def fill_form(self, page, fields: list[dict[str, str]]) -> None:
        """Fill form fields with human-like delays."""
        for field_item in fields:
            selector = field_item["selector"]
            value = field_item["value"]
            await page.click(selector)
            await asyncio.sleep(self._human_delay(0.3))
            await page.fill(selector, value)
            await asyncio.sleep(self._human_delay(0.5))

    async def click_and_wait(
        self, page, selector: str, wait_for: str | None = None, timeout_ms: int = 15000
    ) -> None:
        """Click an element and optionally wait for a result."""
        await page.click(selector)
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)
        await asyncio.sleep(self._human_delay())

    async def screenshot(self, page, path: str) -> str:
        """Take a full-page screenshot."""
        await page.screenshot(path=path, full_page=True)
        return path

    async def get_html(self, page) -> str:
        """Get the page HTML content."""
        return await page.content()

    async def close(self) -> None:
        """Clean up browser resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


class RobotsTxtBlocked(Exception):
    """Raised when robots.txt disallows access to a URL."""


def run_browser_task(coro):
    """Helper to run an async browser task from sync code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)

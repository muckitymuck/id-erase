from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any

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


class BrowserConnector:
    """Playwright-based browser for JS-heavy broker sites."""

    def __init__(self, headless: bool = True, stealth: bool = True):
        self._headless = headless
        self._stealth = stealth
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
        return self._browser

    async def _new_page(self):
        browser = await self._ensure_browser()
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport=random.choice(VIEWPORTS),
            locale="en-US",
        )
        page = await context.new_page()
        return page

    async def navigate(self, url: str, wait_for: str | None = None, timeout_ms: int = 15000):
        """Navigate to a URL and optionally wait for a selector."""
        page = await self._new_page()
        response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        status = response.status if response else 0

        if wait_for:
            try:
                await page.wait_for_selector(wait_for, timeout=timeout_ms)
            except Exception:
                logger.warning("browser.wait_for_timeout selector=%s url=%s", wait_for, url)

        # Human-like delay
        await asyncio.sleep(random.uniform(1.0, 3.0))
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
        for field in fields:
            selector = field["selector"]
            value = field["value"]
            await page.click(selector)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await page.fill(selector, value)
            await asyncio.sleep(random.uniform(0.5, 1.5))

    async def click_and_wait(
        self, page, selector: str, wait_for: str | None = None, timeout_ms: int = 15000
    ) -> None:
        """Click an element and optionally wait for a result."""
        await page.click(selector)
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)
        await asyncio.sleep(random.uniform(1.0, 3.0))

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

"""Playwright browser lifecycle helpers."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from src.config import Settings
from src.utils import BrowserAutomationError

logger = logging.getLogger(__name__)


try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Error as PlaywrightError,
        Page,
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )
except ImportError:  # pragma: no cover - exercised only before dependencies are installed
    Browser = BrowserContext = Page = Any  # type: ignore[assignment]
    PlaywrightError = RuntimeError  # type: ignore[assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]


class BrowserSession:
    """Async context manager that opens and closes a Chromium page."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright: Any | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> Page:
        if async_playwright is None:
            raise BrowserAutomationError(
                "Playwright is not installed. Run `pip install -r requirements.txt` "
                "and `python -m playwright install chromium`."
            )

        try:
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=self.settings.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            self.context = await self.browser.new_context(
                accept_downloads=True,
                viewport={"width": 1440, "height": 1000},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
            )
            self.context.set_default_timeout(self.settings.playwright_timeout)
            await self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.settings.playwright_timeout)
            return self.page
        except PlaywrightError as exc:
            await self.__aexit__(type(exc), exc, exc.__traceback__)
            raise BrowserAutomationError(f"Could not start Chromium: {exc}") from exc

    async def __aexit__(self, *_exc_info: object) -> None:
        with suppress(Exception):
            if self.context:
                await self.context.close()
        with suppress(Exception):
            if self.browser:
                await self.browser.close()
        with suppress(Exception):
            if self._playwright:
                await self._playwright.stop()
        logger.debug("Browser session closed")

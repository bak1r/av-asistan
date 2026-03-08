"""Playwright tabanli browser automation manager (stub)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrowserManager:
    """Playwright singleton — lifecycle yonetimi.

    Not: Bu bir stub implementasyondur. Playwright kurduktan sonra
    gercek browser otomasyonu eklenecek. Su an sadece arayuz tanimli.
    """

    _instance: BrowserManager | None = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None
        self._running = False

    @classmethod
    async def get_instance(cls) -> BrowserManager:
        """Singleton erisimi."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def launch(self, headless: bool = True) -> None:
        """Playwright browser baslat."""
        if self._running:
            return

        try:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(headless=headless)
            self._context = await self._browser.new_context(
                locale="tr-TR",
                timezone_id="Europe/Istanbul",
            )
            self._page = await self._context.new_page()
            self._running = True
            logger.info("Browser launched (headless=%s)", headless)
        except ImportError:
            logger.warning("Playwright not installed. Browser features disabled.")
            raise
        except Exception as e:
            logger.error("Browser launch failed: %s", e)
            raise

    async def navigate(self, url: str) -> dict[str, Any]:
        """Sayfaya git."""
        self._ensure_running()
        response = await self._page.goto(url, wait_until="domcontentloaded")
        return {
            "url": self._page.url,
            "title": await self._page.title(),
            "status": response.status if response else None,
        }

    async def click(self, selector: str) -> dict[str, Any]:
        """Elemente tikla."""
        self._ensure_running()
        await self._page.click(selector, timeout=5000)
        return {"action": "click", "selector": selector, "success": True}

    async def type_text(self, selector: str, text: str) -> dict[str, Any]:
        """Elemente yaz."""
        self._ensure_running()
        await self._page.fill(selector, text)
        return {"action": "type", "selector": selector, "success": True}

    async def screenshot(self) -> bytes:
        """Ekran goruntusu al (PNG bytes)."""
        self._ensure_running()
        return await self._page.screenshot(type="png")

    async def get_text(self, selector: str = "body") -> str:
        """Element icerigini al."""
        self._ensure_running()
        element = await self._page.query_selector(selector)
        if element:
            return await element.inner_text()
        return ""

    async def close(self) -> None:
        """Browser kapat."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
            self._page = None
            self._running = False
            logger.info("Browser closed")

    def _ensure_running(self):
        if not self._running or not self._page:
            raise RuntimeError("Browser not running. Call launch() first.")

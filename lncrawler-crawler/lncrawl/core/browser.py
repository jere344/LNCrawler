"""Playwright-backed browser backend.

The async Playwright API is driven from a dedicated event-loop thread so that
`Browser` can be used synchronously from any crawler thread (including the
ThreadPoolExecutor workers). Playwright objects are only ever touched inside
that one thread, which is what the sync/async API requires.
"""

import asyncio
import enum
import logging
import threading
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class By(enum.Enum):
    ID = "id"
    XPATH = "xpath"
    LINK_TEXT = "link text"
    PARTIAL_LINK_TEXT = "partial link text"
    NAME = "name"
    TAG_NAME = "tag name"
    CLASS_NAME = "class name"
    CSS_SELECTOR = "css selector"


class Browser:
    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30,
        user_agent: Optional[str] = None,
        soup_maker: Any = None,
    ) -> None:
        self.headless = headless
        self.timeout = timeout
        self.user_agent = user_agent
        self.soup_maker = soup_maker
        self.active = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        # Raw Playwright cookie list (name/value/domain/path/...) last seen.
        # Harvested by BasicBrowserTemplate during fallbacks so the native
        # curl_cffi session can reuse the challenge/JS cookies.
        self.cookies_snapshot: List[Dict[str, Any]] = []

    # -- lifecycle ----------------------------------------------------- #

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            # Release the loop's selector/self-pipe fds; otherwise a long-lived
            # worker leaks descriptors on every browser-backed job.
            self._loop.close()

    def _call(self, coro, timeout: Optional[float] = None):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result((timeout or self.timeout) + 30)

    async def _ensure(self) -> None:
        if self._page is not None:
            return
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(user_agent=self.user_agent)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout * 1000)

    async def _close(self) -> None:
        # Close each resource in its own try: a failure in one must not skip
        # the others, or Chromium is left running with refs nulled below.
        try:
            if self._context:
                await self._context.close()
        except Exception:
            logger.debug("Error closing browser context", exc_info=True)
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            logger.debug("Error closing browser", exc_info=True)
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            logger.debug("Error stopping playwright", exc_info=True)
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None

    def close(self) -> None:
        self.active = False
        try:
            if self._pw or self._page:
                self._call(self._close())
        except Exception:
            logger.debug("Error closing browser", exc_info=True)
        finally:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> "Browser":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _restore_cookies(self) -> None:
        pass

    # -- navigation ---------------------------------------------------- #

    async def _visit(self, url: str, wait_until: str) -> None:
        await self._ensure()
        await self._page.goto(url, wait_until=wait_until)
        try:
            self.cookies_snapshot = await self._context.cookies()
        except Exception:
            pass

    def visit(self, url: str, wait_until: str = "domcontentloaded"):
        self._call(self._visit(url, wait_until))
        return self

    async def _content(self) -> str:
        await self._ensure()
        # Snapshot cookies on every read: a challenge page sets its clearance
        # cookie before the real content is returned, and we want it captured
        # even when the caller only reads html()/soup.
        try:
            self.cookies_snapshot = await self._context.cookies()
        except Exception:
            pass
        return await self._page.content()

    def html(self) -> str:
        return self._call(self._content())

    @property
    def soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.html(), features="lxml")

    @property
    def current_url(self) -> str:
        async def _url():
            await self._ensure()
            return self._page.url

        try:
            return self._call(_url())
        except Exception:
            return ""

    async def _wait_for(self, selector: str) -> None:
        await self._ensure()
        try:
            await self._page.wait_for_selector(selector)
        except Exception:
            logger.debug("Timed out waiting for %s", selector)

    def wait(self, selector: str, by=None, timeout: Optional[float] = None) -> None:
        if by in (None, By.CSS_SELECTOR):
            self._call(self._wait_for(selector))

import logging
from abc import abstractmethod
from typing import Generator, List, Optional

from ...core.browser import Browser, By  # noqa: F401  (By re-exported for sources)
from ...core.crawler import Crawler
from ...core.exeptions import FallbackToBrowser, ScraperErrorGroup
from ...models import Chapter
from ...models.search_result import SearchResult

logger = logging.getLogger(__name__)


class BasicBrowserTemplate(Crawler):
    """Attempts to crawl using the native request backend first, then the browser."""

    can_use_browser = True
    headless = True

    def __init__(
        self,
        headless: bool = True,
        timeout: Optional[int] = 120,
        workers: Optional[int] = None,
        parser: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.headless = headless
        super().__init__(workers=workers, parser=parser)

    @property
    def using_browser(self) -> bool:
        return getattr(self, "_browser", None) is not None and self._browser.active

    def __del__(self) -> None:
        try:
            self.close_browser()
        except Exception:
            pass
        super().__del__()

    @property
    def browser(self) -> "Browser":
        """A Playwright based browser."""
        self.init_browser()
        return self._browser

    def init_browser(self) -> None:
        if not self.can_use_browser:
            raise RuntimeError("Browser usage is disabled for this source")
        if self.using_browser:
            return
        # A single shared page cannot be driven by several threads at once.
        self._max_workers = self.workers
        self.init_executor(1)
        self._browser = Browser(
            headless=self.headless,
            timeout=self.timeout,
            user_agent=self.user_agent,
            soup_maker=self,
        )
        self._visit = self._browser.visit
        self._browser.visit = self.visit

    def visit(self, url: str) -> None:
        self._visit(url)
        self._browser._restore_cookies()
        self._harvest_browser_cookies()
        self.last_soup_url = self._browser.current_url or url

    def _harvest_browser_cookies(self) -> None:
        """Copy cookies the browser just earned into the native session.

        A site that serves a JS/Cloudflare challenge to curl_cffi (but loads in
        the browser) drops a clearance cookie during that page load. Once the
        browser has it, the native curl_cffi session can reuse it and fetch the
        remaining chapters itself — the browser is then only paid for one page.
        """
        browser = getattr(self, "_browser", None)
        if browser is None:
            return
        for cookie in getattr(browser, "cookies_snapshot", []) or []:
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            try:
                self.scraper.cookies.set(
                    name,
                    value,
                    domain=cookie.get("domain"),
                    path=cookie.get("path") or "/",
                )
            except Exception:
                try:
                    self.scraper.cookies.set(name, value)
                except Exception:
                    logger.debug("Failed to harvest cookie %s", name, exc_info=True)

    def close_browser(self) -> None:
        browser = getattr(self, "_browser", None)
        if browser is None:
            return
        browser.close()
        self._browser = None
        self.init_executor(getattr(self, "_max_workers", None))

    # -- entrypoints --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        try:
            return list(self.search_novel_in_soup(query))
        except ScraperErrorGroup as e:
            logger.debug("Failed search novel in soup: %s", e)
            self.init_browser()
            return list(self.search_novel_in_browser(query))
        finally:
            self.close_browser()

    def read_novel_info(self) -> None:
        try:
            self.read_novel_info_in_soup()
        except ScraperErrorGroup as e:
            logger.debug("Failed read_novel_info in soup: %s", e)
            self.init_browser()
            self.volumes.clear()
            self.chapters.clear()
            self.read_novel_info_in_browser()
        finally:
            self.close_browser()

    def download_chapters(
        self,
        chapters: List[Chapter],
        fail_fast: bool = False,
    ) -> Generator[Chapter, None, None]:
        # Native backend first: it can batch chapters in parallel, but keep the
        # number of in-flight futures bounded so large novels do not pin every
        # completed body in memory.
        from collections import deque

        window = max(self.workers, 1) * 2
        queue: deque = deque()

        def _collect(chapter, future) -> Chapter:
            result = None
            try:
                result = future.result()
            except Exception as e:
                if isinstance(e, KeyboardInterrupt):
                    raise
                logger.warning("%s: %s", type(e).__name__, e)
            chapter.body = result or ""
            chapter.images = {}
            if result:
                self.extract_chapter_images(chapter)
            chapter.success = bool(result)
            return chapter

        for chapter in chapters:
            queue.append(
                (chapter, self.executor.submit(self.download_chapter_body_in_soup, chapter))
            )
            if len(queue) >= window:
                yield _collect(*queue.popleft())
        while queue:
            yield _collect(*queue.popleft())

        # Fall back to the browser for the chapters the native backend missed.
        remaining = [ch for ch in chapters if not ch.get("success")]
        try:
            for chapter in remaining:
                chapter.body = ""
                chapter.images = {}
                try:
                    chapter.body = self.download_chapter_body(chapter)
                    self.extract_chapter_images(chapter)
                    chapter.success = True
                except Exception as e:
                    logger.error("Failed to get chapter body: %s", e)
                    if isinstance(e, KeyboardInterrupt):
                        break
                    if fail_fast:
                        raise
                finally:
                    yield chapter
        finally:
            self.close_browser()

    def download_chapter_body(self, chapter: Chapter) -> str:
        try:
            return self.download_chapter_body_in_soup(chapter)
        except ScraperErrorGroup as e:
            logger.debug("Failed chapter body in soup: %s", e)
            self.init_browser()
            return self.download_chapter_body_in_browser(chapter)

    def close(self) -> None:
        self.close_browser()
        super().close()

    # -- defaults ------------------------------------------------------ #

    def search_novel_in_soup(self, query: str) -> Generator[SearchResult, None, None]:
        raise FallbackToBrowser()

    def search_novel_in_browser(
        self, query: str
    ) -> Generator[SearchResult, None, None]:
        yield from ()

    def read_novel_info_in_soup(self) -> None:
        raise FallbackToBrowser()

    @abstractmethod
    def read_novel_info_in_browser(self) -> None:
        raise NotImplementedError()

    def download_chapter_body_in_soup(self, chapter: Chapter) -> str:
        raise FallbackToBrowser()

    @abstractmethod
    def download_chapter_body_in_browser(self, chapter: Chapter) -> str:
        raise NotImplementedError()

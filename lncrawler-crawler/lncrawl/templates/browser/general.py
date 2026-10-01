import logging
from typing import Generator, Union

from bs4 import BeautifulSoup, Tag

from ...models import Chapter, Volume
from ..soup.general import GeneralSoupTemplate, meta_description
from .basic import BasicBrowserTemplate

logger = logging.getLogger(__name__)


class GeneralBrowserTemplate(BasicBrowserTemplate, GeneralSoupTemplate):
    """Attempts to crawl using the native request backend first, then the browser."""

    def read_novel_info_in_soup(self) -> None:
        # Identical to GeneralSoupTemplate.read_novel_info: a title-parse failure
        # raises within ScraperErrorGroup, which BasicBrowserTemplate catches and
        # retries in the browser. No need to duplicate the parser here.
        GeneralSoupTemplate.read_novel_info(self)

    def visit_novel_page_in_browser(self) -> BeautifulSoup:
        """Open the Novel URL in the browser"""
        self.visit(self.novel_url)
        return self.browser.soup

    def read_novel_info_in_browser(self) -> None:
        self.visit_novel_page_in_browser()

        self.novel_title = self.parse_title_in_browser()

        try:
            self.novel_cover = self.parse_cover_in_browser()
        except Exception as e:
            logger.warning("Failed to parse novel cover | %s", e)

        try:
            authors = set(list(self.parse_authors_in_browser()))
            self.novel_author = ", ".join(authors)
        except Exception as e:
            logger.warning("Failed to parse novel authors | %s", e)

        try:
            tags = set(list(self.parse_genres_in_browser()))
            self.novel_tags = ", ".join(tags)
        except Exception as e:
            logger.warning("Failed to parse novel tags | %s", e)

        try:
            self.novel_synopsis = self.parse_summary_in_browser() or meta_description(
                self.browser.soup
            )
        except Exception as e:
            logger.warning("Failed to parse novel synopsis | %s", e)
            self.novel_synopsis = meta_description(self.browser.soup)

        for item in self.parse_chapter_list_in_browser():
            if isinstance(item, Chapter):
                self.chapters.append(item)
            elif isinstance(item, Volume):
                self.volumes.append(item)

    def parse_title_in_browser(self) -> str:
        return self.parse_title(self.browser.soup)

    def parse_cover_in_browser(self) -> str:
        return self.parse_cover(self.browser.soup)

    def parse_authors_in_browser(self) -> Generator[str, None, None]:
        yield from self.parse_authors(self.browser.soup)

    def parse_genres_in_browser(self) -> Generator[str, None, None]:
        yield from self.parse_genres(self.browser.soup)

    def parse_summary_in_browser(self) -> str:
        return self.parse_summary(self.browser.soup)

    def parse_chapter_list_in_browser(
        self,
    ) -> Generator[Union[Chapter, Volume], None, None]:
        return self.parse_chapter_list(self.browser.soup)

    def download_chapter_body_in_soup(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = self.select_chapter_body(soup)
        return self.parse_chapter_body(body)

    def download_chapter_body_in_browser(self, chapter: Chapter) -> str:
        self.visit_chapter_page_in_browser(chapter)
        body = self.select_chapter_body_in_browser()
        return self.parse_chapter_body(body)

    def visit_chapter_page_in_browser(self, chapter: Chapter) -> None:
        self.visit(chapter.url)

    def select_chapter_body_in_browser(self) -> Tag:
        return self.select_chapter_body(self.browser.soup)

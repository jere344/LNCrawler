import logging
from abc import abstractmethod
from typing import Generator, Union

from bs4 import BeautifulSoup, Tag

from ...core.crawler import Crawler
from ...core.exeptions import LNException
from ...models import Chapter, Volume

logger = logging.getLogger(__name__)


def meta_description(soup: BeautifulSoup) -> str:
    """Best-effort synopsis from standard meta tags (template-wide fallback)."""
    for selector in (
        'meta[property="og:description"]',
        'meta[name="description"]',
        'meta[property="twitter:description"]',
    ):
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


class GeneralSoupTemplate(Crawler):
    def read_novel_info(self) -> None:
        soup = self.get_novel_soup()

        try:
            self.novel_title = self.parse_title(soup)
        except Exception as e:
            raise LNException("Failed to parse novel title", e)

        try:
            self.novel_cover = self.parse_cover(soup)
        except Exception as e:
            logger.warning("Failed to parse novel cover | %s", e)

        try:
            authors = set(list(self.parse_authors(soup)))
            self.novel_author = ", ".join(authors)
        except Exception as e:
            logger.warning("Failed to parse novel authors | %s", e)

        try:
            tags = set(list(self.parse_genres(soup)))
            self.novel_tags = ", ".join(tags)
        except Exception as e:
            logger.warning("Failed to parse novel tags | %s", e)

        try:
            self.novel_synopsis = self.parse_summary(soup) or meta_description(soup)
        except Exception as e:
            logger.warning("Failed to parse novel synopsis | %s", e)
            self.novel_synopsis = meta_description(soup)

        for item in self.parse_chapter_list(soup):
            if isinstance(item, Chapter):
                self.chapters.append(item)
            elif isinstance(item, Volume):
                self.volumes.append(item)

    def get_novel_soup(self) -> BeautifulSoup:
        return self.get_soup(self.novel_url)

    @abstractmethod
    def parse_title(self, soup: BeautifulSoup) -> str:
        """Parse and return the novel title"""
        raise NotImplementedError()

    @abstractmethod
    def parse_cover(self, soup: BeautifulSoup) -> str:
        """Parse and return the novel cover image"""
        raise NotImplementedError()

    def parse_authors(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        """Parse and return the novel authors"""
        return []

    def parse_genres(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        """Parse and return the novel categories"""
        return []

    def parse_summary(self, soup: BeautifulSoup) -> str:
        """Parse and return the novel summary or synopsis"""
        return ""

    @abstractmethod
    def parse_chapter_list(
        self, soup: BeautifulSoup
    ) -> Generator[Union[Chapter, Volume], None, None]:
        """Parse and set the volumes and chapters"""
        raise NotImplementedError()

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = self.select_chapter_body(soup)
        return self.parse_chapter_body(body)

    @abstractmethod
    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        """Select the tag containing the chapter text"""
        raise NotImplementedError()

    def parse_chapter_body(self, tag: Tag) -> str:
        """Extract the clean HTML content from the tag containing the chapter text"""
        return self.cleaner.extract_contents(tag)

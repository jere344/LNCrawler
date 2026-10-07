# -*- coding: utf-8 -*-
"""foxaholic.com — large danmei/BL translation aggregator (Madara theme).

The site currently serves a hard Cloudflare Turnstile challenge to this host
(HTTP 403 ``Just a moment...``) on every path, and neither the native
curl_cffi backend nor a headless Chromium can clear it, so the source is
disabled. The parser below follows the Madara theme the site uses so it can be
re-enabled once the challenge is lifted.
"""

import logging
from typing import Generator, Optional

from bs4 import BeautifulSoup, Tag

from lncrawl.models import NovelStatus
from lncrawl.templates.madara import MadaraTemplate

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "canceled": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


class FoxaholicCrawler(MadaraTemplate):
    base_url = [
        "https://foxaholic.com/",
        "https://www.foxaholic.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Cloudflare Turnstile blocks every request (HTTP 403 'Just a moment...') "
        "for this host; neither native curl_cffi nor a headless browser clears it."
    )

    def initialize(self) -> None:
        super().initialize()
        self.cleaner.bad_css.update(
            {
                ".ad",
                ".ads",
                ".code-block",
                ".wp-manga-nav",
                ".nav-links",
                ".chapter-nav",
            }
        )

    def _summary_item(self, soup: BeautifulSoup, label: str) -> str:
        """Value of the Madara ``<div class="post-content_item">`` labeled ``label``."""
        wanted = label.lower()
        for item in soup.select(".post-content_item"):
            heading = item.select_one(".summary-heading")
            content = item.select_one(".summary-content")
            if not (heading and content):
                continue
            if heading.get_text(" ", strip=True).rstrip(":").strip().lower() == wanted:
                return content.get_text(" ", strip=True)
        return ""

    def parse_authors(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        for a in soup.select('.author-content a[href*="novel-author"]'):
            name = a.get_text(" ", strip=True)
            if name:
                yield name

    def parse_summary(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".description-summary .summary__content") or soup.select_one(
            ".description-summary"
        )
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def parse_genres(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        yield from super().parse_genres(soup)

        alternative = self._summary_item(soup, "Alternative")
        if alternative:
            self.alternative_titles = [
                name.strip() for name in alternative.split(",") if name.strip()
            ]

        translator = self._summary_item(soup, "Translator")
        if translator:
            self.translators = [name.strip() for name in translator.split(",") if name.strip()]

        status = self._summary_item(soup, "Status")
        if status:
            self.status = _STATUSES.get(status.lower(), NovelStatus.unknown)

        publisher = self._summary_item(soup, "Publisher")
        if publisher:
            self.english_publisher = publisher

    def select_chapter_body(self, soup: BeautifulSoup) -> Optional[Tag]:
        return (
            soup.select_one(".entry-content_wrap")
            or soup.select_one(".reading-content")
            or soup.select_one(".text-left")
        )

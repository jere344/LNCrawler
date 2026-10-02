import logging
from bs4 import BeautifulSoup, Tag
from lncrawl.templates.madara import MadaraTemplate

logger = logging.getLogger(__name__)


class SonicMTLCrawler(MadaraTemplate):
    has_mtl = True
    base_url = [
        "https://sonicmtl.com",
        "https://www.sonicmtl.com/",
    ]

    def initialize(self):
        super().initialize()
        self.cleaner.bad_css.update(
            {
                ".ad",
                ".c-ads",
                ".custom-code",
                ".body-top-ads",
                ".before-content-ad",
                ".autors-widget",
            }
        )

    def parse_authors(self, soup: BeautifulSoup):
        for a in soup.select(".author-content a"):
            name = a.get_text(" ", strip=True)
            if name:
                yield name

    def parse_genres(self, soup: BeautifulSoup):
        yield from super().parse_genres(soup)
        for item in soup.select(".post-content_item"):
            heading = item.select_one(".summary-heading")
            content = item.select_one(".summary-content")
            if not (heading and content):
                continue
            if heading.get_text(strip=True) == "Alternative":
                self.alternative_titles = [
                    name.strip()
                    for name in content.get_text(" ", strip=True).split(",")
                    if name.strip()
                ]

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        return soup.select_one(".reading-content .text-left")

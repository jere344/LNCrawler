import logging
from bs4 import BeautifulSoup, Tag
from lncrawl.models import SearchResult
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

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = (
                f"{self.home_url}?m_orderby=views"
                if page == 1
                else f"{self.home_url}page/{page}/?m_orderby=views"
            )
            soup = self.get_soup(url)
            items = soup.select(".page-item-detail .post-title h3 a[href]")
            if not items:
                break
            for a in items:
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
        return results[offset : offset + limit]

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

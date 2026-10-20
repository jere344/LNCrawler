# -*- coding: utf-8 -*-
import logging

from bs4 import BeautifulSoup, Tag

from lncrawl.models import SearchResult
from lncrawl.templates.madara import MadaraTemplate

logger = logging.getLogger(__name__)
search_url = "https://meionovels.com/wp-admin/admin-ajax.php"


class MeionovelCrawler(MadaraTemplate):
    base_url = ["https://meionovel.id/", "https://meionovels.com/"]

    is_disabled = True
    disable_reason = (
        "Cloudflare managed challenge (cf-mitigated: challenge) blocks this "
        "host; fails in curl_cffi and headless Playwright. Needs a residential "
        "proxy."
    )

    def initialize(self):
        super().initialize()
        self.home_url = "https://meionovels.com/"

    def search_novel(self, query):
        data = self.submit_form(
            search_url,
            {
                "action": "wp-manga-search-manga",
                "title": query,
            },
        ).json()

        results = []
        for novel in data["data"]:
            titleSoup = self.make_soup(novel["title"])
            results.append(
                {
                    "title": titleSoup.body.text.title(),
                    "url": self.absolute_url(novel["url"]),
                }
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = "https://meionovels.com/novel/?m_orderby=views"
            if page > 1:
                url = f"https://meionovels.com/novel/page/{page}/?m_orderby=views"
            soup = self.get_soup(url)
            items = soup.select(".page-item-detail")
            if not items:
                break
            for item in items:
                a = item.select_one(".post-title h3 a")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def parse_authors(self, soup: BeautifulSoup):
        yield from filter(None, super().parse_authors(soup))

    def parse_cover(self, soup: BeautifulSoup) -> str:
        return self.absolute_url(soup.select_one(".summary_image img")["src"])

    def parse_genres(self, soup: BeautifulSoup):
        for a in soup.select(".genres-content a"):
            yield a.text.strip()

    def parse_summary(self, soup: BeautifulSoup):
        tag = soup.select_one(".summary__content")
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def select_chapter_tags(self, soup: BeautifulSoup):
        response = self.submit_form(self.novel_url.strip("/") + "/ajax/chapters")
        soup = self.make_soup(response)
        yield from reversed(soup.select(".wp-manga-chapter a"))

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        contents = soup.select_one("div.text-left")

        for img in contents.findAll("img"):
            if img.has_attr("data-lazy-src"):
                src_url = img["data-lazy-src"]
                parent = img.parent
                img.extract()
                new_tag = soup.new_tag("img", src=src_url)
                parent.append(new_tag)

        if contents.h3:
            contents.h3.extract()

        for codeblock in contents.findAll("div", {"class": "code-block"}):
            codeblock.extract()

        return contents

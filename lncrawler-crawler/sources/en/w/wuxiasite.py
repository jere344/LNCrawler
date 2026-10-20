# -*- coding: utf-8 -*-
import logging

from bs4 import BeautifulSoup
from bs4.element import Tag

from lncrawl.models import SearchResult
from lncrawl.templates.madara import MadaraTemplate

logger = logging.getLogger(__name__)
search_url = "https://wuxiaworld.site/?s=%s&post_type=wp-manga"


class WuxiaSiteCrawler(MadaraTemplate):
    base_url = "https://wuxiaworld.site/"

    def search_novel(self, query):
        query = query.lower().replace(' ', '+')
        soup = self.get_soup(search_url % query)

        results = []
        for tab in soup.select('.c-tabs-item__content'):
            a = tab.select_one('.post-title h3 a')
            latest = tab.select_one('.latest-chap .chapter a').text
            votes = tab.select_one('.rating .total_votes').text
            results.append({
                'title': a.text.strip(),
                'url': self.absolute_url(a['href']),
                'info': '%s | Rating: %s' % (latest, votes),
            })
        # end for

        return results
    # end def

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = self.home_url if page == 1 else "%spage/%d/" % (self.home_url, page)
            soup = self.get_soup(url, params={"m_orderby": "views"})
            items = soup.select(".page-item-detail")
            if not items:
                break
            for tab in items:
                a = tab.select_one(".post-title h3 a")
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

    def parse_title(self, soup: BeautifulSoup) -> str:
        possible_title = soup.select_one(".post-title")
        assert isinstance(possible_title, Tag)
        possible_title = possible_title.select_one("h1, h2, h3")
        assert isinstance(possible_title, Tag)
        return " ".join(
            [str(x) for x in possible_title.contents if not isinstance(x, Tag)]
        ).strip()

    def parse_authors(self, soup: BeautifulSoup):
        authors = soup.select(".author-content a")
        if len(authors) == 2:
            yield authors[0].text + " (" + authors[1].text + ")"
        elif len(authors) == 1:
            yield authors[0].text

    def parse_genres(self, soup: BeautifulSoup):
        for a in soup.select(".genres-content a"):
            yield a.text.strip()

    def parse_summary(self, soup: BeautifulSoup):
        tag = soup.select_one(".summary__content")
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        content = soup.select_one(".text-left")
        if not isinstance(content, Tag):
            content = soup.select_one(".cha-words")
        if not isinstance(content, Tag):
            content = soup.select_one(".reading-content")
        return content

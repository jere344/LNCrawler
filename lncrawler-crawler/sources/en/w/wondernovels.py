# -*- coding: utf-8 -*-
import logging
import re

from bs4 import BeautifulSoup, Tag

from lncrawl.models import SearchResult
from lncrawl.templates.madara import MadaraTemplate

logger = logging.getLogger(__name__)
search_url = "https://wondernovels.com/?s=%s&post_type=wp-manga"


class WonderNovels(MadaraTemplate):
    base_url = "https://wondernovels.com/"

    def search_novel(self, query):
        query = query.lower().replace(" ", "+")
        soup = self.get_soup(search_url % query)

        results = []
        for tab in soup.select(".c-tabs-item__content"):
            a = tab.select_one(".post-title h3 a")
            if not a:
                continue
            latest = tab.select_one(".latest-chap .chapter a")
            votes = tab.select_one(".rating .total_votes")
            results.append(
                {
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                    "info": " | ".join(
                        x.text.strip() for x in (latest, votes) if x
                    ),
                }
            )

        return results

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = self.home_url if page == 1 else "%spage/%d/" % (self.home_url, page)
            try:
                soup = self.get_soup(url, params={"m_orderby": "views"})
            except Exception:
                break
            items = soup.select(".page-item-detail")
            if not items:
                break
            for tab in items:
                a = tab.select_one(".post-title h3 a")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.text.strip(),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def parse_authors(self, soup: BeautifulSoup):
        names = [
            a.text.strip()
            for a in soup.select('.author-content a[href*="translator"]')
        ]
        if names:
            yield " ".join(names)
            return
        author = soup.select_one('.post-content_item h5:-soup-contains("Author")')
        if author:
            content = author.find_next_sibling()
            if content:
                yield content.get_text(strip=True)
        else:
            match = re.search(
                r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"',
                str(soup),
            )
            if match:
                yield match.group(1)

    def parse_genres(self, soup: BeautifulSoup):
        yield from (
            a.get_text(strip=True)
            for a in soup.select(".genres-content a[rel='tag']")
            if a.get_text(strip=True)
        )
        self.tags = [
            a.get_text(strip=True)
            for a in soup.select(".tags-content a[rel='tag']")
            if a.get_text(strip=True)
        ]
        for node in soup.select(".post-content_item"):
            heading = node.select_one(".summary-heading h5")
            content = node.select_one(".summary-content")
            if not heading or not content:
                continue
            if "alternative" in heading.get_text(strip=True).lower():
                self.alternative_titles = [
                    part.strip()
                    for part in re.split(r"\n|,", content.get_text(" ", strip=True))
                    if part.strip()
                ]
                break

    def parse_summary(self, soup: BeautifulSoup):
        tag = soup.select_one(".summary__content")
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select(".reading-content p")
        return "".join([str(p) for p in contents])

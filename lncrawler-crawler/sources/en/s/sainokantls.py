# -*- coding: utf-8 -*-
"""SainoKanTLS (sainokantls.com) - English light/web novel translations.

A custom Laravel site, not a common CMS.  Chapter text is not in the DOM as
text: the body is split into empty ``<span class="cdh-chunk">`` elements whose
``data-content`` holds a base64 fragment of the real text, interleaved with
lorem-ipsum decoy tags (``[aria-hidden="true"]``).  The body is rebuilt by
decoding every chunk in order and dropping the decoys.
"""

import base64
import logging
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class SainoKanTLSCrawler(Crawler):
    base_url = ["https://sainokantls.com/", "https://www.sainokantls.com/"]
    language = "en"

    def _parse_cards(self, soup):
        results = []
        seen = set()
        for a in soup.select("main .grid a[href*='/novel/']"):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            title = a.select_one("h3")
            if not title:
                continue
            seen.add(url)
            author = a.select_one("p")
            results.append(
                SearchResult(
                    title=title.get_text(strip=True),
                    url=url,
                    info=author.get_text(strip=True) if author else None,
                )
            )
        return results

    def search_novel(self, query):
        soup = self.get_soup(f"{self.base_url[0]}/novels?search={quote_plus(query)}")
        return self._parse_cards(soup)

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.base_url[0]}/novels?page={page}")
            cards = self._parse_cards(soup)
            if not cards:
                break
            results.extend(cards)
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.find("h1")
        if title:
            self.novel_title = title.get_text(strip=True)

        cover = soup.select_one("img[src*='/storage/covers/']")
        if cover:
            self.novel_cover = self.absolute_url(cover["src"])

        author_icon = soup.select_one("i.fa-user")
        if author_icon:
            span = author_icon.find_next_sibling("span")
            if span:
                self.novel_author = span.get_text(strip=True)

        for heading in soup.find_all("h3"):
            if heading.get_text(strip=True).lower() == "synopsis":
                para = heading.find_next_sibling("p")
                if para:
                    self.novel_synopsis = para.get_text(" ", strip=True)
                break

        self.novel_tags = [
            a.get_text(strip=True) for a in soup.select("a[href*='category=']")
        ]

        chapters_heading = next(
            (h for h in soup.find_all("h2") if h.get_text(strip=True) == "Chapters"),
            None,
        )
        card = chapters_heading.find_parent("div", class_="rounded-lg") if chapters_heading else None
        for a in (card.select("a[href]") if card else []):
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": a.get_text(" ", strip=True),
                    "url": self.absolute_url(a["href"]),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("#chapter-content")
        if contents is None:
            return ""

        for decoy in contents.select("[aria-hidden='true']"):
            decoy.decompose()

        for chunk in contents.select(".cdh-chunk"):
            try:
                text = base64.b64decode(chunk.get("data-content") or "").decode("utf-8")
            except Exception:
                text = ""
            chunk.replace_with(text)

        return self.cleaner.extract_contents(contents)

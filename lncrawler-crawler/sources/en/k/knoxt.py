# -*- coding: utf-8 -*-
"""KnoxT - Novel and Translations (knoxt.space).

WordPress site on the MangaStream theme. Search, novel pages and chapter
lists use the template defaults. Novels are listed at /series/ (20 per page).
Chapters are newest-first in .eplister. Translators' human-edited chapters are
hosted here; the site's recruitment page says it accepts "edited MTL or
translations" and rejects pure MTL, so MTL is not flagged per novel.
"""
import logging

from lncrawl.models import NovelStatus, SearchResult
from lncrawl.templates.mangastream import MangaStreamTemplate

logger = logging.getLogger(__name__)


class KnoxT(MangaStreamTemplate):
    has_mtl = False
    has_manga = False
    base_url = ["https://knoxt.space/"]

    def parse_search_item(self, tag):
        # The title link in search results holds only an image, so take the
        # title from the link attribute or the headline.
        a = tag.select_one("h2 a[href]") or tag.select_one("a.tip[href]")
        title = (a.get("title") or a.get_text()).strip()
        return SearchResult(title=title, url=self.absolute_url(a["href"]))

    def get_novel_soup(self):
        # Keep the novel page soup so read_novel_info can read the status from it.
        self._novel_soup = super().get_novel_soup()
        return self._novel_soup

    def read_novel_info(self):
        super().read_novel_info()
        soup = getattr(self, "_novel_soup", None)
        if soup is None:
            return
        # The status is a "Status: Ongoing" span in the .spe details block.
        for span in soup.select(".spe span"):
            text = span.get_text(" ", strip=True)
            if not text.lower().startswith("status:"):
                continue
            value = text.split(":", 1)[1].strip().lower()
            if "ongoing" in value:
                self.status = NovelStatus.ongoing
            elif "completed" in value:
                self.status = NovelStatus.completed
            elif "hiatus" in value:
                self.status = NovelStatus.hiatus
            break

    def browse_novels(self, offset=0, limit=50):
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 200:
            soup = self.get_soup(f"{self.home_url}series/?page={page}")
            items = soup.select(".listupd article")
            if not items:
                break
            fresh = 0
            for item in items:
                a = item.select_one("a.tip[href]")
                if not a:
                    continue
                title = (a.get("title") or a.get_text()).strip()
                if not title:
                    continue
                url = self.absolute_url(a["href"])
                if url in seen:
                    continue
                seen.add(url)
                results.append(SearchResult(title=title, url=url))
                fresh += 1
            # The site may repeat the last page; stop once a page adds nothing new.
            if fresh == 0:
                break
            page += 1
        return results[offset : offset + limit]

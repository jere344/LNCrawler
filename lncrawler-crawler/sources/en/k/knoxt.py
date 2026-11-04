# -*- coding: utf-8 -*-
"""KnoxT - Novel and Translations (knoxt.space).

WordPress site on the MangaStream theme. Search, novel pages and chapter
lists use the template defaults. Novels are listed at /series/ (20 per page).
Chapters are newest-first in .eplister. Translators' human-edited chapters are
hosted here; the site's recruitment page says it accepts "edited MTL or
translations" and rejects pure MTL, so MTL is not flagged per novel.
"""
import copy
import logging

from bs4 import BeautifulSoup, Tag

from lncrawl.core import body_migrations
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume
from lncrawl.templates.mangastream import MangaStreamTemplate

logger = logging.getLogger(__name__)

# In-page ad slot the site puts into every chapter body.
_AD_IMAGE = "In-pageMediumRectangle"


class KnoxT(MangaStreamTemplate):
    has_mtl = False
    has_manga = False
    version = 2
    body_migrations = {2: "_migrate_v2"}
    base_url = ["https://knoxt.space/"]

    def initialize(self) -> None:
        super().initialize()
        self.cleaner.bad_css.update({f'img[src*="{_AD_IMAGE}"]'})

    def parse_summary(self, soup: BeautifulSoup) -> str:
        # The blurb is the paragraphs after the "Synopsis:" label, up to the
        # "~~~" separator; the lines after it are site notes, not synopsis.
        content = soup.select_one(".entry-content")
        if not isinstance(content, Tag):
            return ""
        wrapper = soup.new_tag("div")
        for p in content.find_all("p", recursive=False):
            text = p.get_text(" ", strip=True)
            if text.startswith("~~~"):
                break
            if text and text.lower() != "synopsis:":
                wrapper.append(copy.copy(p))
        return self.cleaner.extract_contents(wrapper)

    def _migrate_v2(self, body, chapter):
        # Stored images are renamed images/<md5>.jpg: the URL is in the chapter's map.
        images = chapter.get("images") or {}

        def is_ad(src):
            return _AD_IMAGE in images.get(src.removeprefix("images/"), src)

        soup = body_migrations.parse(body)
        ads = [img for img in soup.find_all("img") if is_ad(img.get("src", ""))]
        if not ads:
            return body
        for img in ads:
            img.decompose()
        # A block the ad left with no text and no image is gone too.
        for tag in list(soup.find_all(recursive=False)):
            if not body_migrations.block_text(tag) and not tag.find("img"):
                tag.decompose()
        return str(soup)

    def parse_chapter_item(self, tag: Tag, id: int, vol: Volume) -> Chapter:
        chapter = super().parse_chapter_item(tag, id, vol)
        # Site titles read "<novel title> chapter N"; keep only the chapter part.
        name = (self.novel_title or "").strip()
        title = chapter.title or ""
        if name and title[: len(name)].lower() == name.lower():
            rest = title[len(name) :].lstrip(" -–:|")
            if rest:
                chapter.title = rest[0].upper() + rest[1:]
        return chapter

    def parse_search_item(self, tag):
        # The title link in search results holds only an image, so take the
        # title from the link attribute or the headline.
        a = tag.select_one("h2 a[href]") or tag.select_one("a.tip[href]")
        title = (a.get("title") or a.get_text()).strip()
        return SearchResult(
            title=title,
            url=self.absolute_url(a["href"]),
            cover=self.image_url(tag.select_one("img")),
        )

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

# -*- coding: utf-8 -*-
import json
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_PAGE_COUNTER_RE = re.compile(r"\d+ / \d+")
_SCROLL_IMG_RE = re.compile(r"scroll-up-down")

_STATUSES = {
    "連載中": NovelStatus.ongoing,
    "完結": NovelStatus.completed,
    "完結済み": NovelStatus.completed,
    "休載中": NovelStatus.hiatus,
}


class AlphapolisCrawler(Crawler):
    base_url = "https://www.alphapolis.co.jp/"
    language = "ja"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        tag = soup.select_one("#app-cover-data")
        data = json.loads(tag.string)
        content = data["content"]
        self.novel_title = content["title"].strip()

        author = (content.get("user") or {}).get("name")
        if author:
            self.novel_author = author.strip()

        if content.get("coverImageUrl"):
            self.novel_cover = self.absolute_url(content["coverImageUrl"])

        synopsis = soup.select_one(".p-content-info__abstract")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        # Genre and serialization status are badges in the sidebar ("ファンタジー 連載中 長編").
        genres = []
        status = NovelStatus.unknown
        for badge in soup.select(".p-sidebar-content-info__summary .c-attribute-tag"):
            text = badge.get_text(" ", strip=True)
            if "c-attribute-tag--novel" in (badge.get("class") or []):
                genres.append(text)
            elif text in _STATUSES:
                status = _STATUSES[text]
        self.genres = list(dict.fromkeys(genres))
        self.novel_tags = list(self.genres)
        self.status = status

        for group in data.get("chapterEpisodes", []):
            for episode in group.get("episodes", []):
                if not episode.get("isPublic", True):
                    continue
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=(episode.get("mainTitle") or "").strip(),
                        url=self.absolute_url(episode["url"]),
                    )
                )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("#novelBody") or soup.select_one(".js-novel-body")
        if body is None:
            # The outer .p-novel-episode__body also holds the scroll buttons and the page counter.
            body = soup.select_one(".p-novel-episode__body")
            if body is None:
                return ""
            for junk in body.select(
                ".c-scroll-up-down, .p-novel-episode__page-count, .p-novel-episode__episode-title"
            ):
                junk.decompose()
        return self.cleaner.extract_contents(body)

    def search_novel(self, query: str):
        soup = self.get_soup(
            "https://www.alphapolis.co.jp/search?query=" + quote_plus(query)
        )
        results = []
        for card in soup.select("div.section.novels.content-block")[:10]:
            a = card.select_one("h2.title a")
            if not a:
                continue
            author = card.select_one(".author a")
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                    info=author.get_text(" ", strip=True) if author else "",
                )
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup("https://www.alphapolis.co.jp/novel/ranking/hot")
        results = []
        for card in soup.select("section.c-content"):
            a = card.select_one("h2.c-content__title a")
            if not a:
                continue
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def _migrate_v2(self, body, chapter):
        # v1 bodies came from the whole episode box: scroll buttons, page counter, title.
        title = " ".join((chapter.get("title") or "").split())
        images = chapter.get("images") or {}

        def is_scroll_img(img):
            # Stored src is images/<md5>.jpg: the original URL is in chapter["images"].
            src = img.get("src") or ""
            original = images.get(src.rsplit("/", 1)[-1], "")
            return _SCROLL_IMG_RE.search(src) or _SCROLL_IMG_RE.search(original)

        def drop(text, tag):
            if _PAGE_COUNTER_RE.fullmatch(text) or (title and text == title):
                return True
            # Only an image-only block is the button; a story line keeps its place.
            imgs = [tag] if tag.name == "img" else tag.find_all("img")
            return not text and any(is_scroll_img(img) for img in imgs)

        return body_migrations.drop_blocks(body, drop)

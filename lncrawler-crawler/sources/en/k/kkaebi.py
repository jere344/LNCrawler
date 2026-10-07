# -*- coding: utf-8 -*-
"""Kkaebi (kkaebi.io) — officially licensed English translations of Korean novels.

Madara/WooCommerce site with a coin store (``wp-manga-chapter-coin``). Novel
pages are ``/novel/<slug>/`` and the chapter list is loaded from:

    POST /wp-admin/admin-ajax.php  action=hbl_manga_load_chapters
         page=<n> manga_id=<post id> manga_slug=<slug>

Free chapters carry the ``free-chap`` class and a real chapter URL; paid ones
are ``premium`` with ``href="#"`` and a coin lock, so only free chapters are
collected (they are the only ones with a readable body).
"""

import logging
import re
from typing import List

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, Volume

logger = logging.getLogger(__name__)

_AJAX_URL = "https://kkaebi.io/wp-admin/admin-ajax.php"

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


class KkaebiCrawler(Crawler):
    base_url = "https://kkaebi.io/"
    language = "en"

    def _slug(self) -> str:
        match = re.search(r"/novel/([^/?#]+)", self.novel_url)
        return match.group(1) if match else ""

    def _list_chapters(self, manga_id: str, slug: str) -> None:
        seen = set()
        page = 1
        while page <= 200:
            response = self.submit_form(
                _AJAX_URL,
                data={
                    "action": "hbl_manga_load_chapters",
                    "page": page,
                    "manga_id": manga_id,
                    "manga_slug": slug,
                },
            )
            soup = self.make_soup(response.text)
            rows = soup.select("li.wp-manga-chapter")
            if not rows:
                break

            fresh = 0
            for row in rows:
                classes = row.get("class") or []
                link = row.select_one("a.chapter-link[href]")
                href = (link.get("href") or "") if isinstance(link, Tag) else ""
                if "free-chap" not in classes or not href or href == "#" or href in seen:
                    continue
                seen.add(href)
                title_node = row.select_one(".chapter-link span span")
                title = (
                    title_node.get_text(" ", strip=True)
                    if isinstance(title_node, Tag)
                    else f"Chapter {len(seen)}"
                )
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=re.sub(r"\s*\u200b?\s*$", "", title),
                        url=self.absolute_url(href),
                        volume=1,
                    )
                )
                fresh += 1

            if fresh == 0:
                break
            page += 1

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.hbl-novel-single-title")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(" ", strip=True)

        original = soup.select_one(
            ".hbl-novel-single-meta.is-original-name .hbl-novel-single-meta-value"
        )
        if isinstance(original, Tag) and original.get_text(strip=True):
            self.alternative_titles = [original.get_text(" ", strip=True)]

        author = soup.select_one('.hbl-novel-single-meta a[href*="/novel-author/"]')
        if isinstance(author, Tag):
            self.novel_author = author.get_text(" ", strip=True)

        status = soup.select_one(".hbl-novel-single-meta .status")
        if isinstance(status, Tag):
            self.status = _STATUSES.get(status.get_text(strip=True).lower(), NovelStatus.unknown)

        genres = [
            span.get_text(" ", strip=True)
            for span in soup.select(".hbl-novel-genre span")
            if span.get_text(strip=True)
        ]
        self.genres = genres

        tags: List[str] = []
        for tag in soup.select(".tags-list a.tag-item"):
            text = tag.get_text(strip=True).lstrip("#").strip()
            if text and text not in tags:
                tags.append(text)
        self.r18 = bool(soup.select_one(".adult-content")) or any(
            re.fullmatch(r"R-?18", t, re.I) for t in tags
        )
        if self.r18 and not any(re.fullmatch(r"R-?18", t, re.I) for t in tags):
            tags.append("R-18")
        self.tags = tags
        self.novel_tags = list(dict.fromkeys(genres + tags))

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = cover["content"]

        summary = soup.select_one(".hbl-novel-summary .hbl-summary-content.active")
        if not isinstance(summary, Tag):
            summary = soup.select_one(".hbl-novel-summary .summary__content")
        if isinstance(summary, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(summary)

        manga_id = soup.select_one("input.rating-post-id")
        manga_id = manga_id.get("value") if isinstance(manga_id, Tag) else None
        slug = self._slug()
        if not (manga_id and slug):
            raise ValueError(f"Cannot determine chapter list config for {self.novel_url!r}")

        self.volumes.append(Volume(id=1, title="Volume 1"))
        self._list_chapters(manga_id, slug)
        logger.info("Found %d free chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.reading-content")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)

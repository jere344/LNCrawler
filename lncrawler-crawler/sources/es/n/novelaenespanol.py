# -*- coding: utf-8 -*-
"""novelaenespanol.com — large Spanish novel/light-novel aggregator.

Plain WordPress + the "ranobe-novels" theme. Novel pages expose every useful
field natively (title, author, status, cover, synopsis, genres), and the full
table of contents is returned by the theme's ``chapters-query.php`` AJAX
endpoint. Chapter text lives in the standard ``.entry-content`` block.

No bot wall: the site serves anonymous requests fine, so this is a native
curl_cffi source.
"""

import json
import logging
import re
from typing import List
from urllib.parse import urlparse

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

CHAPTERS_API = (
    "https://novelaenespanol.com/wp-content/themes/ranobe-novels"
    "/template-parts/category/chapters-query.php"
)
ALL_NOVELS_URL = "https://novelaenespanol.com/todas-las-novelas/"
SEARCH_URL = "https://novelaenespanol.com/search/"

_STATUSES = {
    "terminado": NovelStatus.completed,
    "completado": NovelStatus.completed,
    "completa": NovelStatus.completed,
    "en curso": NovelStatus.ongoing,
    "emitiendose": NovelStatus.ongoing,
    "pausado": NovelStatus.hiatus,
    "en pausa": NovelStatus.hiatus,
}


class NovelaEnEspanolCrawler(Crawler):
    base_url = "https://novelaenespanol.com/"
    language = "es"

    # -- metadata helpers ---------------------------------------------- #

    @staticmethod
    def _status_from(text: str) -> NovelStatus:
        text = (text or "").strip().lower()
        for needle, value in _STATUSES.items():
            if needle in text:
                return value
        return NovelStatus.unknown

    @staticmethod
    def _strip_label(text: str, label: str) -> str:
        text = (text or "").strip()
        return re.sub(rf"^{label}\s*:?\s*", "", text, flags=re.IGNORECASE).strip()

    def _canonical_url(self, url: str) -> str:
        """Normalize a novel URL to the detail page ``/novela-ligera/<post>/``.

        The catalog links to ``/<post>/novela-ligera/<title>/``, which is the
        reader page, not the novel page; the first path segment is the post slug.
        """
        parts = [p for p in urlparse(url or "").path.split("/") if p]
        if "novela-ligera" not in parts:
            return self.absolute_url(url)
        index = parts.index("novela-ligera")
        slug = parts[index - 1] if index > 0 else (
            parts[index + 1] if index + 1 < len(parts) else ""
        )
        if not slug:
            return self.absolute_url(url)
        return self.absolute_url(f"/novela-ligera/{slug}/")

    def _parse_catalog(self) -> List[dict]:
        """The search page embeds the whole catalog as JS; reuse it."""
        soup = self.get_soup(SEARCH_URL)
        script = next(
            (
                s.string
                for s in soup.find_all("script")
                if s.string and "let cat = [" in s.string
            ),
            None,
        )
        if not script:
            return []
        match = re.search(r"let cat = (\[.*?\]);", script, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip().lower()
        results = []
        for item in self._parse_catalog():
            title = (item.get("cat_title") or "").strip()
            haystack = " ".join(
                str(item.get(key) or "")
                for key in ("cat_title", "excerpt", "author")
            ).lower()
            if query and query not in haystack:
                continue
            url = item.get("cat_link") or ""
            if not title or not url:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=self._canonical_url(url),
                    info=" | ".join(
                        part
                        for part in (
                            item.get("author") or "",
                            f"{item.get('chapters')} capítulos"
                            if item.get("chapters")
                            else "",
                        )
                        if part
                    ),
                )
            )
            if len(results) >= 10:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{ALL_NOVELS_URL}page/{page}/")
            cards = soup.select("article.most-liked-card")
            if not cards:
                break
            for card in cards:
                link = card.select_one(".most-liked-card-title a[href]")
                if not isinstance(link, Tag):
                    continue
                results.append(
                    SearchResult(
                        title=link.get_text(" ", strip=True),
                        url=self.absolute_url(link["href"]),
                    )
                )
            page += 1
            if page > 50:
                break
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        card = soup.select_one(".js-bookcard") or soup

        title = card.select_one(".category-title a") or card.select_one(
            "[itemprop='name']"
        )
        assert isinstance(title, Tag), "No novel title"
        self.novel_title = title.get_text(" ", strip=True)

        cover = card.select_one("img.category-img") or card.select_one(
            "img[itemprop='image']"
        )
        if isinstance(cover, Tag) and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])

        author = card.select_one(".cat-author")
        if isinstance(author, Tag):
            self.novel_author = self._strip_label(author.get_text(" ", strip=True), "Autor")

        status = card.select_one(".cat-status")
        if isinstance(status, Tag):
            self.status = self._status_from(status.get_text(" ", strip=True))

        synopsis = card.select_one(".category-exerpt") or card.select_one(
            ".description"
        )
        if isinstance(synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        genres = [
            a.get_text(" ", strip=True)
            for a in card.select(".post_tags a")
            if a.get_text(strip=True)
        ]
        self.genres = genres
        self.novel_tags = list(genres)

        data = soup.select_one(".js-cat-data")
        if not isinstance(data, Tag):
            return
        cat_id = data.get("data-category")
        slug = data.get("data-slug")
        if not cat_id or not slug:
            return

        chapters = self.submit_form_json(
            CHAPTERS_API,
            data={"cat_id": cat_id, "limit": 100000, "offset": 0, "query": ""},
        )
        chapters = chapters or []
        chapters.reverse()
        for index, item in enumerate(chapters, start=1):
            post_name = item.get("post_name")
            if not post_name:
                continue
            self.chapters.append(
                Chapter(
                    id=index,
                    title=(item.get("post_title") or f"Capítulo {index}").strip(),
                    url=self.absolute_url(f"/{slug}/novela-ligera/{post_name}/"),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".entry-content")
        assert isinstance(body, Tag), "No chapter body"
        return self.cleaner.extract_contents(body)

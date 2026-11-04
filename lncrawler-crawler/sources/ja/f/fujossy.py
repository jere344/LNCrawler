# -*- coding: utf-8 -*-
import logging
import re

from bs4 import Comment, NavigableString, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

# Template covers the site offers in place of an uploaded image: generic
# backgrounds stored under the book's own path, so matched by file name.
_DEFAULT_COVER_RE = re.compile(
    r"/(bluesky|skyblue|purple|red|pink|stars|couple_love)\.png$", re.IGNORECASE
)


class FujossyCrawler(Crawler):
    base_url = "https://fujossy.jp/"
    has_mtl = False
    is_adult = True
    version = 2

    def search_novel(self, query):
        soup = self.get_soup("https://fujossy.jp/books/search", params={"q": query})
        results = []
        for a in soup.select("a[href*='/books/']"):
            href = a.get("href", "")
            if not href.split("/")[-1].isdigit():
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            card = a.find_parent(class_="book__related-tile")
            image = card.select_one("img") if card else None
            cover = image.get("data-echo") if image else None
            cover = self.absolute_url(cover) or None
            if cover and _DEFAULT_COVER_RE.search(cover):
                cover = None
            results.append(
                {
                    "title": title,
                    "url": self.absolute_url(href),
                    "cover": cover,
                }
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit:
            data = self.get_json(
                "https://fujossy.jp/api/books/ranking.json",
                params={
                    "kind": "daily",
                    "page": page,
                    "per": 100,
                    "book_data": "true",
                },
            )
            books = data.get("books", [])
            if not books:
                break
            added = 0
            for book in books:
                url = f"https://fujossy.jp/books/{book['id']}"
                if url in seen:
                    continue
                seen.add(url)
                results.append(
                    SearchResult(title=(book.get("title") or "").strip(), url=url)
                )
                added += 1
            if not added:
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one('meta[property="og:title"]')
        if title:
            self.novel_title = title.get("content", "").split(" | ")[0].strip()

        cover = soup.select_one('meta[property="og:image"]')
        if cover and not _DEFAULT_COVER_RE.search(cover.get("content", "")):
            self.novel_cover = cover.get("content")

        synopsis = soup.select_one('meta[property="og:description"]')
        if synopsis:
            blurb, tags = self._split_description(synopsis.get("content", ""))
            self.novel_synopsis = blurb
            self.tags = tags

        author = soup.select_one(".book-side-author__name")
        if author:
            self.novel_author = author.get_text(strip=True)

        self.volumes.append({"id": 1, "title": "Volume 1"})
        seen = set()
        for a in soup.select("a[href*='/stories/']"):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "volume": 1,
                    "title": title,
                    "url": url,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one(".story__body")
        if isinstance(body, Tag):
            # Lines are separated by bare newlines, not <br>: make them breaks.
            for text in body.find_all(string=True):
                if "\n" not in text or not isinstance(text, NavigableString):
                    continue
                if isinstance(text, Comment) or text.find_parent(["script", "style"]):
                    continue
                parts = []
                for index, piece in enumerate(text.split("\n")):
                    if index:
                        parts.append(soup.new_tag("br"))
                    parts.append(NavigableString(piece))
                text.replace_with(*parts)
            return self.cleaner.extract_contents(body)
        return ""

    def _split_description(self, description):
        # og:description is "<synopsis> <tag>・<tag>  無料BL小説です".
        description = (description or "").strip()
        match = re.search(
            r"(?:^|\s)([^\s・]+(?:・[^\s・]+)*)\s*無料BL小説です", description
        )
        if not match:
            return description, []
        tags = [t.strip() for t in match.group(1).split("・") if t.strip()]
        return description[: match.start()].strip(), tags

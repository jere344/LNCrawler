# -*- coding: utf-8 -*-
import html
import logging
import re

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}

# Scan running heads ("Kampfer – Volume 4") copied into the chapter text from
# the printed book.
_SCAN_LINE_RE = re.compile(r"^.{1,80}\s[–-]\sVolume\s\d+(?:\.\d+)?$")

# Page numbers copied from the printed book. Only dropped as the first or last
# paragraph of a chapter, so dialogue such as "7" or "1984" is kept.
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")

# Labelled lines of the series description that are not part of the blurb.
_META_LINE_RE = re.compile(
    r"^(?:Author|Illustrator|Status|Type|Genres?|Tags?)\s*:", re.IGNORECASE
)


def _drop_scan_noise(root) -> None:
    paragraphs = root.select("p")
    for index, p in enumerate(paragraphs):
        text = p.get_text(" ", strip=True)
        is_edge = index in (0, len(paragraphs) - 1)
        if _SCAN_LINE_RE.match(text) or (is_edge and _PAGE_NUMBER_RE.match(text)):
            p.decompose()


def _synopsis_html(text: str) -> str:
    blurb = re.split(r"\bTags\s*:", text, maxsplit=1)[0]
    if re.search(r"\bSynopsis\s*:", blurb):
        blurb = re.split(r"\bSynopsis\s*:", blurb, maxsplit=1)[1]
    lines = [
        line.strip()
        for line in blurb.split("\n")
        if line.strip() and not _META_LINE_RE.match(line.strip())
    ]
    if lines and re.match(r"^The Synopsis is\s*:?$", lines[0], re.IGNORECASE):
        lines = lines[1:]
    return "".join(f"<p>{html.escape(line, quote=False)}</p>" for line in lines)


class AsianHobbyistCrawler(Crawler):
    base_url = ["https://www.asianhobbyist.com/"]
    language = "en"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def search_novel(self, query):
        soup = self.get_soup(self.home_url, params={"s": query})
        results = []
        seen = set()
        for a in soup.select('a[href*="/series/"]'):
            href = a.get("href", "")
            if not re.match(r"^https?://[^/]+/series/[^/]+/?$", href):
                continue
            url = self.absolute_url(href)
            title = a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            card = a.find_parent(class_="vote-novel") or a.find_parent("li")
            cover = self.image_url(card.select_one("img") if card else None)
            results.append({"title": title, "url": url, "cover": cover})
        return results[:20]

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.absolute_url("/ranking/"))
        results = []
        seen = set()
        for a in soup.select("a[href*='/series/']"):
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".entry-title") or soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        cover = soup.select_one(".thumb img") or soup.select_one(".background img")
        if cover:
            self.novel_cover = self.absolute_url(
                cover.get("data-src") or cover.get("src")
            )
        logger.info("Novel cover: %s", self.novel_cover)

        description = soup.select_one(".description")
        if description:
            text = description.get_text("\n", strip=True)

            author = re.search(r"\bAuthor\s*:\s*([^\n]+)", text)
            if author:
                self.novel_author = author.group(1).strip()

            edition = re.search(
                r"\bType\s*:\s*([^\n]*?)[ \t]*(?:Genres\s*:|$)", text, re.M
            )
            if edition and edition.group(1).strip():
                self.novel_edition = edition.group(1).strip()

            status = re.search(r"\bStatus\s*:\s*([^\n]+)", text)
            if status:
                self.status = _STATUSES.get(
                    status.group(1).strip().lower(), NovelStatus.unknown
                )

            self.novel_synopsis = _synopsis_html(text)

            genres = re.search(
                r"\bGenres\s*:\s*([^\n]*?)[ \t]*(?:\bSynopsis\s*:|$)", text, re.M
            )
            if genres:
                self.genres = [
                    tag.strip() for tag in genres.group(1).split(",") if tag.strip()
                ]
            tags = re.search(r"\bTags\s*:\s*([^\n]+)", text)
            if tags:
                self.novel_tags = [
                    tag.strip() for tag in tags.group(1).split(",") if tag.strip()
                ]
        logger.info("Novel author: %s", self.novel_author)

        # The chapter table lists every chapter, even when a chapter URL does
        # not share the series slug.
        links = soup.select(".tableBody a[href]")
        if not links:
            slug = self.novel_url.rstrip("/").split("/")[-1]
            pattern = re.compile(r"^https?://[^/]+/{0}/[^/]+/?$".format(re.escape(slug)))
            links = [a for a in soup.select("a[href]") if pattern.match(a.get("href", ""))]

        chapters = {}
        for a in links:
            href = a.get("href", "")
            title = a.get_text(" ", strip=True)
            if not title or title.lower().startswith("read "):
                continue
            chapters[self.absolute_url(href)] = title

        for index, url in enumerate(chapters):
            self.chapters.append(
                {"id": index + 1, "title": chapters[url], "url": url}
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".entry-content") or soup.select_one("article")
        if contents is not None:
            _drop_scan_noise(contents)
        return self.cleaner.extract_contents(contents)

    def _migrate_v2(self, body, chapter):
        soup = body_migrations.parse(body)
        # The cleaner drops empty paragraphs, so a stored end may not be the page's end.
        ends = soup.select("p")[:1] + soup.select("p")[-1:]
        if any(_PAGE_NUMBER_RE.match(p.get_text(" ", strip=True)) for p in ends):
            return None
        _drop_scan_noise(soup)
        return str(soup)

# -*- coding: utf-8 -*-
import json
import logging
import re
from urllib.parse import urljoin

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_DATA_MARKER = "window.__DATA__ = "
_TRANSLATION_STATUS = {
    "active": NovelStatus.ongoing,
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "frozen": NovelStatus.hiatus,
    "hiatus": NovelStatus.hiatus,
}


def _toc_data(soup) -> dict:
    # Chapter lists are rendered by Vue from an inline JSON blob.
    for script in soup.find_all("script"):
        text = script.string or ""
        start = text.find(_DATA_MARKER)
        if start >= 0:
            try:
                data, _ = json.JSONDecoder().raw_decode(text, start + len(_DATA_MARKER))
            except ValueError:
                return {}
            return data
    return {}


class RanobesComCrawler(Crawler):
    base_url = "https://ranobes.com/"
    language = "ru"

    def initialize(self):
        # A chapter list is one request per 25 chapters; the site answers 429.
        self.init_executor(ratelimit=1)

    def search_novel(self, query):
        soup = self.submit_form_for_soup(
            self.home_url,
            data={"do": "search", "subaction": "search", "story": query},
            headers={"Referer": self.home_url},
        )
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^https?://ranobes\.com/ranobe/\d+", href) or href in seen:
                continue
            seen.add(href)
            card = a.find_parent("article") or a.find_parent(class_="story_line") or a
            figure = card.select_one(".cover")
            match = re.search(r"url\((.*?)\)", str(figure.get("style") or "")) if figure else None
            cover = self.absolute_url(match.group(1).strip("'\"")) if match else None
            results.append({"title": a.get_text(strip=True), "url": href, "cover": cover})
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}popular.html")
        results = []
        for a in soup.select(".poplist-items article.popshort h2.title a[href]"):
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        desc = soup.select_one('meta[property="og:title"]')
        if desc:
            self.novel_title = desc.get("content", "").strip()
        if not self.novel_title:
            h1 = soup.select_one("h1")
            self.novel_title = h1.get_text(strip=True) if h1 else ""
        logger.info("Novel title: %s", self.novel_title)

        authors = [a.get_text(strip=True) for a in soup.select('a[href*="/authors/"]')]
        if authors:
            self.novel_author = ", ".join(authors)
        logger.info("Novel author: %s", self.novel_author)

        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            self.novel_cover = cover.get("content", "")
        logger.info("Novel cover: %s", self.novel_cover)

        synopsis = soup.select_one('meta[property="og:description"]')
        if synopsis:
            self.novel_synopsis = synopsis.get("content", "")
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        # Translation status ("Перевод: Активен"), else the original one.
        status_link = soup.select_one(
            '.r-fullstory-spec a[href*="/tags/status-trs/"]'
        ) or soup.select_one('.r-fullstory-spec a[href*="/tags/status-end/"]')
        self.status = NovelStatus.unknown
        if status_link is not None:
            key = status_link.get("href", "").rstrip("/").split("/")[-1].lower()
            self.status = _TRANSLATION_STATUS.get(key, NovelStatus.unknown)

        genres = [
            a.get_text(strip=True)
            for a in soup.select("#mc-fs-genre .links a")
            if a.get_text(strip=True)
        ]
        if genres:
            self.novel_tags = genres

        subtitle = soup.select_one(".title .subtitle")
        if subtitle:
            self.alternative_titles = [
                t.strip()
                for t in re.split(r"[•]+", subtitle.get_text(strip=True))
                if t.strip()
            ]

        toc_url = None
        for a in soup.select("a[href]"):
            href = urljoin(self.novel_url, a.get("href", ""))
            if re.match(r"^https?://ranobes\.com/chapters/[^/]+/$", href):
                toc_url = href
                break
        if not toc_url:
            return

        seen = set()
        entries = []
        page = 1
        pages_count = 1
        while page <= min(pages_count, 300):
            url = toc_url if page == 1 else "%spage/%d/" % (toc_url, page)
            data = _toc_data(self.get_soup(url))
            pages_count = int(data.get("pages_count") or 1)
            items = data.get("chapters") or []
            if not items:
                break
            added = 0
            for item in items:
                href = urljoin(self.home_url, item.get("link") or "")
                if not href or href in seen:
                    continue
                seen.add(href)
                entries.append(((item.get("title") or "").strip(), href))
                added += 1
            if not added:
                break
            page += 1

        for title, href in reversed(entries):
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": title,
                    "url": href,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        title = soup.select_one("h1")
        if title:
            chapter["title"] = title.get_text(strip=True)
        contents = soup.select_one("article .text") or soup.select_one(".text")
        self.cleaner.clean_contents(contents)
        return str(contents)

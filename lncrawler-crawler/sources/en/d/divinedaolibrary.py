# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}


class DivineDaoLibraryCrawler(Crawler):
    base_url = "https://www.divinedaolibrary.com/"

    def search_novel(self, query):
        soup = self.get_soup(self.absolute_url("/?s=" + quote_plus(query)))
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^https?://www\.divinedaolibrary\.com/story/[^/]+/$", href):
                continue
            if href in seen:
                continue
            seen.add(href)
            card = a.find_parent("li", class_="card")
            cover = self.image_url(card.select_one("img") if card else None)
            results.append({"title": a.get_text(strip=True), "url": href, "cover": cover})
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.absolute_url("/novels/"))
        results = []
        seen = set()
        for a in soup.select("a[href*='/story/']"):
            url = self.absolute_url(a["href"]).split("#")[0]
            if url in seen or url.count("/") != 4:
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def _parse_summary(self, summary):
        # The summary holds "Author:", "Raws:", "Other Names" and "Description"
        # blocks in that order. The "by" link under the title is the uploader
        # account (the translator team), not the author.
        if summary is None:
            return
        alt_titles = []
        paragraphs = []
        section = ""
        for el in summary.find_all(recursive=False):
            if el.name == "h3":
                label, _, value = el.get_text(" ", strip=True).partition(":")
                section = label.strip().lower()
                value = value.strip()
                if section == "author" and value:
                    self.novel_author = value
                elif section == "raws" and value:
                    alt_titles.append(value)
            elif section == "other names":
                alt_titles.extend(el.get_text(" ", strip=True).split(","))
                section = ""
            elif section == "description" and el.name == "p":
                text = el.get_text(" ", strip=True)
                if text:
                    paragraphs.append(text)
        self.alternative_titles = [t.strip() for t in dict.fromkeys(alt_titles) if t.strip()]
        self.novel_synopsis = "\n".join(paragraphs)

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        self._parse_summary(soup.select_one("section.story__summary"))
        logger.info("Novel author: %s", self.novel_author)

        status = soup.select_one("span.story__status")
        if status:
            self.status = _STATUSES.get(status.get_text(strip=True).lower(), NovelStatus.unknown)

        cover = soup.select_one("img.story__thumbnail-image")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src"))
        logger.info("Novel cover: %s", self.novel_cover)

        self.genres = [
            tag.get_text(strip=True)
            for tag in soup.select(".story__taxonomies .tag-pill")
            if tag.get_text(strip=True)
        ]
        self.tags = [
            tag.get_text(strip=True)
            for tag in soup.select(".story__tags-and-warnings .tag-pill")
            if tag.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)
        logger.info("Novel tags: %s", self.tags)

        if not self.novel_synopsis:
            desc = soup.select_one('meta[property="og:description"]')
            if desc:
                self.novel_synopsis = desc.get("content", "")
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        # Chapters are listed in volume groups; the last group, "unassigned",
        # holds the chapters the site has not put in a volume.
        volume_id = 0
        for group in soup.select("section.story__chapters div.chapter-group"):
            links = group.select("ol.chapter-group__list a[href]")
            if not links:
                continue
            vol = None
            if group.get("id") != "chapter-group-unassigned":
                volume_id += 1
                vol = volume_id
                name = group.select_one("button.chapter-group__name span")
                title = name.get_text(" ", strip=True) if name else ""
                title = re.sub(
                    r"\s*\((?:complete|completed|ongoing|hiatus)\)$", "", title, flags=re.I
                )
                self.volumes.append(Volume(id=vol, title=title or f"Volume {vol}"))
            for a in links:
                chapter = {
                    "id": len(self.chapters) + 1,
                    "title": a.get_text(strip=True),
                    "url": a["href"],
                }
                if vol is not None:
                    chapter["volume"] = vol
                self.chapters.append(chapter)

        if not self.chapters:
            for a in soup.select("section.story__chapters a[href]"):
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": a.get_text(strip=True),
                        "url": a["href"],
                    }
                )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".chapter__content") or soup.select_one("article.chapter__article")
        self.cleaner.clean_contents(contents)
        return str(contents)

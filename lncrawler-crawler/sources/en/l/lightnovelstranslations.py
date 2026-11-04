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
    "hiatus": NovelStatus.hiatus,
}

# Upper bound on volumes read from one novel page (one request each, when not loaded).
_MAX_VOLUMES = 200


class LightNovelsTranslationsCrawler(Crawler):
    is_disabled = True
    disable_reason = "Most chapters are VIP-locked; about 70 percent locked on sampled novels"
    base_url = "https://lightnovelstranslations.com/"

    def initialize(self):
        self.init_executor(ratelimit=1)

    def search_novel(self, query):
        soup = self.get_soup(self.absolute_url("/?s=" + quote_plus(query)))
        roots = []
        seen = set()
        for a in soup.select("a[href]"):
            match = re.match(
                r"^(https?://lightnovelstranslations\.com/novel/[^/]+/)", a["href"]
            )
            if not match:
                continue
            root = match.group(1)
            if root in seen:
                continue
            seen.add(root)
            roots.append(root)
        results = []
        for root in roots[:8]:
            title = root.rstrip("/").split("/")[-1].replace("-", " ").title()
            try:
                title = self.get_soup(root).title.get_text(strip=True)
            except Exception:
                pass
            results.append({"title": title, "url": root})
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit:
            if page == 1:
                url = f"{self.home_url}read/"
            else:
                url = f"{self.home_url}read/page/{page}/"
            soup = self.get_soup(url)
            found = False
            for a in soup.select('a[href*="/novel/"]'):
                href = a["href"].split("?")[0]
                match = re.match(
                    r"^https?://lightnovelstranslations\.com/novel/([^/]+)/?$", href
                )
                if not match:
                    continue
                title = a.text.strip()
                if not title or match.group(1) in seen:
                    continue
                seen.add(match.group(1))
                found = True
                results.append(SearchResult(title=title, url=href))
            if not found:
                break
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def _volume_items(self, section):
        """Chapter items of one volume section.

        The novel page renders only the first volume's chapters. Any other
        volume is loaded on its own URL (one request per volume) and the
        matching section is read from that response.
        """
        items = section.select("li.chapter-item")
        if items:
            return items
        heading = section.select_one("a.lnt-volume-link")
        if not heading or not heading.get("href"):
            return []
        count = heading.select_one("span")
        if count and re.match(r"\s*0\b", count.get_text()):
            return []

        volume_id = section.get("data-volume")
        soup = self.get_soup(self.absolute_url(heading["href"]))
        for loaded in soup.select("section.lnt-volume"):
            if loaded.get("data-volume") == volume_id:
                break
        else:
            logger.warning("Volume %s is missing from its own page", volume_id)
            return []

        items = loaded.select("li.chapter-item")
        page = loaded.select_one(".lnt-chapter-page")
        total = page.get("data-total") if page else None
        if total and total.isdigit() and len(items) < int(total):
            logger.warning(
                "Volume %s shows %d of %s chapters", volume_id, len(items), total
            )
        return items

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        # Chapters come only from the table of contents: the page's other
        # links (reading button, sidebars) would add wrong titles or extras.
        locked = 0
        seen = set()
        sections = soup.select("#lnt-chapter-list section.lnt-volume")
        if not sections:
            logger.warning("No volume sections found in the chapter list")
        if len(sections) > _MAX_VOLUMES:
            logger.warning("Only the first %d volumes are read", _MAX_VOLUMES)
            sections = sections[:_MAX_VOLUMES]
        for section in sections:
            heading = section.select_one("a.lnt-volume-link")
            volume_title = (
                "".join(heading.find_all(string=True, recursive=False)).strip()
                if heading
                else ""
            )
            volume_id = len(self.volumes) + 1
            before = len(self.chapters)
            for item in self._volume_items(section):
                # "lock" marks VIP early-access chapters: the page only holds
                # a truncated teaser for them.
                if "lock" in (item.get("class") or []):
                    locked += 1
                    continue
                link = item.select_one("a[href]")
                if not link:
                    continue
                url = self.absolute_url(link["href"])
                if url in seen:
                    continue
                seen.add(url)
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": link.get_text(strip=True),
                        "url": url,
                        "volume": volume_id,
                    }
                )
            if len(self.chapters) > before:
                self.volumes.append(Volume(id=volume_id, title=volume_title))
        logger.info("Skipped %d VIP early-access chapters", locked)

        if soup.title:
            self.novel_title = soup.title.get_text(strip=True).split(" | ")[0].strip()
        logger.info("Novel title: %s", self.novel_title)

        self.novel_tags = [
            span.get_text(" ", strip=True)
            for span in soup.select(".novel_tags_item span")
            if span.get_text(" ", strip=True)
        ]
        logger.info("Novel tags: %s", self.novel_tags)

        for li in soup.select(".novel_detail_info li"):
            label = li.select_one("span")
            if not label:
                continue
            key = label.get_text(strip=True).lower()
            value = li.get_text(" ", strip=True).split(":", 1)[-1].strip()
            if not value:
                continue
            if key.startswith("author"):
                self.novel_author = value
            elif key.startswith("translator"):
                self.translators = [value]
            elif key.startswith("raw") and not value.startswith("http"):
                self.original_publisher = value
        logger.info("Novel author: %s", self.novel_author)

        status = soup.select_one(".novel_status")
        if status:
            self.status = _STATUSES.get(
                status.get_text(strip=True).lower(), NovelStatus.unknown
            )

        # A placeholder image (the site's "No Image" banner) is not a cover.
        cover = soup.select_one(".novel-image img")
        if cover and "lnt-current-placeholder" not in (cover.get("class") or []):
            self.novel_cover = self.absolute_url(
                cover.get("data-src") or cover.get("src")
            )
        logger.info("Novel cover: %s", self.novel_cover)

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = (
            soup.select_one(".text_story")
            or soup.select_one(".actual-read-page")
            or soup.select_one(".chapter-page")
        )
        self.cleaner.clean_contents(contents)
        return str(contents)

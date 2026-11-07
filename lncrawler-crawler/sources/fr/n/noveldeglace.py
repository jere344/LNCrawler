# -*- coding: utf-8 -*-
"""noveldeglace.com — French fan translations (WordPress, "tempera" theme).

Novels are the "roman" custom post type, served at ``/roman/<slug>/``. That page
carries the title, author, cover, volumes and the chapter list. The WordPress
category with the same slug holds posts from other novels too, so it is not
used for the novel data. The public ``/wp-json/wp/v2`` API is still used for
search and browse, which work because category slugs equal roman slugs.

Each post's API ``link`` points to an announcement note, not to the chapter
text. The chapter text is served at ``/chapitre/<slug>/``, so that URL is used
as the chapter URL and as the body source.
"""

import logging
import re
from html import unescape
from typing import Dict, List
from urllib.parse import quote_plus, unquote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

TOME_RE = re.compile(r"Tome\s*(\d+)", re.IGNORECASE)
# Meta categories ("Publication", "Special"...) that are not novels.
META_CATEGORIES = {"publication", "special", "test", "annonce"}


def _is_meta_category(cat: dict) -> bool:
    name = unescape(cat.get("name") or "").strip().lower()
    slug = (cat.get("slug") or "").strip().lower()
    return name in META_CATEGORIES or slug in META_CATEGORIES


class NoveldeglaceCrawler(Crawler):
    base_url = "https://noveldeglace.com/"
    language = "fr"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    # -- helpers ------------------------------------------------------- #

    def _novel_url(self, slug: str) -> str:
        return f"{self.home_url}roman/{slug}/"

    def _fetch_categories(self, ids: List[int]) -> Dict[int, dict]:
        if not ids:
            return {}
        data = self.get_json(
            f"{self.home_url}wp-json/wp/v2/categories"
            f"?include={','.join(str(i) for i in ids)}"
            "&per_page=100&_fields=id,name,slug,count"
        )
        return {c["id"]: c for c in data}

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        posts = self.get_json(
            f"{self.home_url}wp-json/wp/v2/posts"
            f"?search={quote_plus(query)}&per_page=20&_fields=id,title,categories"
        )
        cat_ids = sorted({c for p in posts for c in p.get("categories", [])})
        cats = self._fetch_categories(cat_ids)

        results: List[SearchResult] = []
        seen = set()
        for post in posts:
            candidates = [
                cats[c]
                for c in post.get("categories", [])
                if c in cats and cats[c].get("count", 0) > 0
            ]
            if not candidates:
                continue
            # Meta categories ("Publication", "Special"...) hold 1-2 posts;
            # the novel category holds the most.
            best = max(candidates, key=lambda c: c.get("count", 0))
            if best["id"] in seen:
                continue
            seen.add(best["id"])
            results.append(
                SearchResult(
                    title=unescape(best["name"]).strip(),
                    url=self._novel_url(best["slug"]),
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            resp = self.get_response(
                f"{self.home_url}wp-json/wp/v2/categories"
                f"?per_page=100&page={page}&_fields=id,name,slug,count"
            )
            cats = resp.json()
            for c in cats:
                if c.get("count", 0) <= 0 or _is_meta_category(c):
                    continue
                results.append(
                    SearchResult(
                        title=unescape(c["name"]).strip(),
                        url=self._novel_url(c["slug"]),
                    )
                )
            total_pages = int(resp.headers.get("X-WP-TotalPages") or 1)
            if not cats or page >= total_pages:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel --------------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = unquote(urlparse(self.novel_url).path.rstrip("/").split("/")[-1])
        soup = self.get_soup(f"{self.home_url}roman/{slug}/")

        title = soup.select_one("h1.entry-title")
        if title is None:
            raise LNException(f"No novel page found for slug '{slug}'")
        self.novel_title = unescape(title.get_text()).strip()

        self.novel_author = ""
        for line in soup.select("div.line_roman"):
            label = line.find("strong")
            if label is not None and label.get_text(strip=True).startswith("Auteur"):
                text = line.get_text(" ", strip=True)
                self.novel_author = text[len(label.get_text(" ", strip=True)) :].strip()
                break

        og_image = soup.find("meta", property="og:image")
        if og_image is not None and og_image.get("content"):
            self.novel_cover = self.absolute_url(og_image["content"])

        volume_ids = set()
        for heading in soup.select("h4.title-roman-single"):
            volume_id = None
            volume_link = heading.find("a", href=True)
            tome = (
                re.search(r"tome-(\d+)", volume_link["href"])
                if volume_link is not None
                else None
            ) or TOME_RE.search(heading.get_text(" ", strip=True))
            if tome is not None:
                volume_id = int(tome.group(1))
            if volume_id is not None and volume_id not in volume_ids:
                volume_ids.add(volume_id)
                self.volumes.append(Volume(id=volume_id, title=f"Tome {volume_id}"))

            # Only the list directly after this heading belongs to its volume.
            chapter_list = heading.find_next_sibling()
            if chapter_list is None or chapter_list.name != "ul":
                continue
            for item in chapter_list.select("li.chpt"):
                link = item.find("a", href=True)
                if link is None:
                    continue
                chapter_title = unescape(link.get_text()).strip()
                entries = [(chapter_title, link["href"])]
                # Multi-part chapters link each part as its own chapter page.
                for part in item.select("span.partie-chapitre a[href]"):
                    part_title = part.get_text(strip=True)
                    entries.append((f"{chapter_title} – {part_title}", part["href"]))
                for entry_title, href in entries:
                    self.chapters.append(
                        Chapter(
                            id=len(self.chapters) + 1,
                            title=entry_title,
                            url=self.absolute_url(href),
                            volume=volume_id,
                        )
                    )

        if not self.chapters:
            logger.warning("No chapters found for %s", self.novel_url)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.entry-content-chapitre")
        if body is None:
            return ""

        # Only ul elements inside share/related/nav widgets are dropped; real
        # list content in the chapter text is kept.
        # div.index is the "Table des matières" box of multi-part chapters.
        for bad in body.select(
            "script, style, button, form, input, label, footer, svg, "
            "[class*=jscolor], [class*=mistape], div.index, "
            "[class*=share] ul, [class*=related] ul, nav ul"
        ):
            bad.extract()

        # Text-colour picker widget; only drop wrappers that hold no paragraph.
        for div in body.find_all("div"):
            if div.find("p") is None and "setTextColor" in str(div):
                div.extract()

        return self.cleaner.extract_contents(body)

    def _migrate_v2(self, body, chapter):
        # The box is removed by class (div.index), which the stored body no longer has.
        if "Table des mati" in body:
            return None
        return body

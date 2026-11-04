# -*- coding: utf-8 -*-

import logging
import re
import unicodedata
from typing import List
from urllib.parse import quote_plus, urlencode

from bs4 import Tag

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

# Site watermarks: the site name written with lookalike letters (Cyrillic,
# mathematical styled letters) between matching decorations, e.g.
# "❀ Novelight ❀ (Don't copy, read here)", plus a "stolen" sentence.
_WATERMARK_DECOS = "◆◇❀❁✿❖✦✪✧★☆~♦✩✫#➤/°•◈⊛"
_WATERMARK_LOOKALIKES = str.maketrans(
    {
        "а": "a",
        "с": "c",
        "е": "e",
        "г": "g",
        "һ": "h",
        "і": "i",
        "ı": "i",
        "ι": "i",
        "т": "t",
        "ј": "j",
        "о": "o",
        "р": "p",
        "ѕ": "s",
        "у": "y",
        "х": "x",
    }
)
# Group 1: leading spaces; 2/3/4: opening decorations, name, closing decorations
# (1-3 characters each, not necessarily the same); 5-7: «», {} and [] names;
# 8: "(...)" suffix; 9: trailing spaces. The lookbehind makes a run of spaces
# start only once, so the leading \s* never backtracks over the same run twice.
WATERMARK_RE = re.compile(
    rf"((?<!\s)\s*)(?:([{_WATERMARK_DECOS}]{{1,3}})([^<>{_WATERMARK_DECOS}]{{3,40}}?)"
    rf"([{_WATERMARK_DECOS}]{{1,3}})"
    r"|«([^<>«»]{3,40}?)»|\{([^<>{}]{3,40}?)\}|\[([^<>\[\]]{3,40}?)\])"
    r"(\s*\([^()<>]{0,80}\))?(\s*)"
)
STOLEN_RE = re.compile(
    r"\s*(?i:If you are reading this translation anywhere other than"
    r" Novelight\.net or SilkRoadTL, it has been stolen\.)"
)


def _strip_watermark(match: re.Match) -> str:
    name = next(g for g in match.groups()[2:7] if g is not None)
    name = unicodedata.normalize("NFKC", name)
    # NFKC turns "Ⅰ" into "I". A capital "I" can stand for a lowercase "l" (a
    # lookalike) or be a real "i" (all-caps "NOVELIGHT"): accept either reading.
    readings = {name.lower(), name.replace("I", "l").lower()}
    if not any(
        re.sub(r"[^a-z]", "", r.translate(_WATERMARK_LOOKALIKES)) == "novelight"
        for r in readings
    ):
        return match.group(0)
    spaced = match.group(1) or match.group(9)
    return " " if spaced else ""


class NoveLightCrawler(Crawler):
    base_url = "https://novelight.net/"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self) -> None:
        self.cleaner.bad_css.update(["div.advertisment"])

    def search_novel(self, query) -> List[SearchResult]:
        soup = self.get_soup(
            f"{self.home_url}catalog/?search={quote_plus(query.lower())}"
        )

        return [
            SearchResult(
                title=a.text.strip(),
                url=self.absolute_url(a["href"]),
                cover=self.image_url(a.select_one(".poster img")),
            )
            for a in soup.select(".manga-grid-list a.item")
            if isinstance(a, Tag)
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(
                f"{self.home_url}catalog/?ordering=popularity&page={page}"
            )
            items = soup.select(".manga-grid-list a.item[href]")
            if not items:
                break
            for a in items:
                title = a.select_one(".title") or a
                results.append(
                    SearchResult(
                        title=title.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title_tag = soup.select_one("header.header-manga h1")
        if not isinstance(title_tag, Tag):
            raise LNException("No title found")
        self.novel_title = title_tag.get_text().strip()
        logger.info("Novel title: %s", self.novel_title)

        novel_cover = soup.select_one("div.second-information div.poster img")
        if isinstance(novel_cover, Tag):
            self.novel_cover = self.absolute_url(novel_cover["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        novel_synopsis = soup.select_one("div#information section.text-info")
        if isinstance(novel_synopsis, Tag):
            # first line is a "「 ✦ Read <title> Novel ✦ 」" site banner
            for p in novel_synopsis.select("p"):
                if re.match(r"^[「\s✦]*Read .+ Novel\s*✦", p.get_text(strip=True)):
                    p.decompose()
            self.novel_synopsis = self.cleaner.extract_contents(novel_synopsis)

        novel_tags = soup.select(
            "div#information section.tags a[href^='/catalog/?tags=']"
        )
        for tag in novel_tags:
            self.novel_tags.append(tag.get_text().strip())
        # "R-18" is a content rating, not a tag
        self.is_adult = any(t.upper() == "R-18" for t in self.novel_tags)
        self.novel_tags = [t for t in self.novel_tags if t.upper() != "R-18"]

        for item in soup.select(".mini-info .item"):
            header = item.select_one(".sub-header")
            if not header:
                continue
            label = header.get_text(strip=True).lower()
            info = item.select_one(".info")
            value = info.get_text(" ", strip=True).lower() if info else ""
            if label == "genres":
                self.genres = [
                    a.get_text(strip=True) for a in item.select(".info a")
                ]
            elif label == "alternative":
                self.alternative_titles = [
                    d.get_text(strip=True)
                    for d in item.select(".info div")
                    if d.get_text(strip=True)
                ]
            elif label == "status":
                if "completed" in value:
                    self.status = NovelStatus.completed
                elif "hiatus" in value or "on hold" in value:
                    self.status = NovelStatus.hiatus
                elif "releasing" in value or "ongoing" in value:
                    self.status = NovelStatus.ongoing
            elif label == "type" and info:
                edition = info.get_text(" ", strip=True)
                if edition.lower() in ("web novel", "light novel"):
                    self.novel_edition = edition

        novel_author = soup.select_one(".mini-info a[href^='/character/'] div.info")
        if isinstance(novel_author, Tag) and novel_author.get_text():
            self.novel_author = novel_author.get_text().strip()
        logger.info("Novel author: %s", self.novel_author)

        page_scripts = soup.select("body > script:not([src])")
        scripts_joined = "\n".join(str(s) for s in page_scripts)
        book_id = re.search(r'.*const BOOK_ID = "(\d+)".*', scripts_joined).group(1)
        if not book_id:
            raise LNException("Could not extract book_id from novel page")
        logger.debug("book_id: %s", book_id)
        # this is different token than the 'csrftoken' in cookies
        csrfmiddlewaretoken = re.search(
            r'.*window.CSRF_TOKEN = "(\w+)".*', scripts_joined
        ).group(1)
        if not csrfmiddlewaretoken:
            raise LNException("Could not extract csrfmiddlewaretoken from novel page")

        headers = {
            "Accept": "*/*",
            "Referer": self.novel_url,
            "x-requested-with": "XMLHttpRequest",
        }
        chapters_lists = soup.select("select#select-pagination-chapter > option")
        encountered_paid_chapter = False
        for page in reversed(chapters_lists):
            if encountered_paid_chapter:
                break
            params = {
                "csrfmiddlewaretoken": csrfmiddlewaretoken,
                "book_id": book_id,
                "page": page["value"],
            }
            chapters_response = self.get_json(
                f"{self.home_url}book/ajax/chapter-pagination?{urlencode(params)}",
                headers=headers,
            )
            chapters_soup = self.make_soup(chapters_response["html"])
            for a in reversed(chapters_soup.select("a[href^='/book/chapter/']")):
                if a.select_one(".chapter-info .cost"):
                    encountered_paid_chapter = True
                    break
                else:
                    self.chapters.append(
                        Chapter(
                            id=len(self.chapters) + 1,
                            title=a.select_one(".title").text.strip(),
                            url=self.absolute_url(a["href"]),
                        )
                    )
        if encountered_paid_chapter:
            logger.warning(
                "WARNING: Paid chapters are not supported and will be skipped."
            )

    def download_chapter_body(self, chapter: Chapter):
        url = chapter.url.replace("/book/chapter/", "/book/ajax/read-chapter/")
        data = self.get_json(
            url,
            headers={
                "Referer": chapter.url,
                "x-requested-with": "XMLHttpRequest",
            },
        )
        content = WATERMARK_RE.sub(_strip_watermark, data["content"])
        content = STOLEN_RE.sub("", content)
        content = re.sub(r"<div>\s*</div>", "", content)
        soup = self.make_soup(content)
        contents = soup.select_one(".chapter-text")
        self.cleaner.clean_contents(contents)

        return str(contents)

    def _migrate_v2(self, body, chapter):
        body = body_migrations.sub_text(body, WATERMARK_RE, _strip_watermark, drop_empty=False)
        body = body_migrations.sub_text(body, STOLEN_RE, "", drop_empty=False)
        return re.sub(r"<div>\s*</div>", "", body)

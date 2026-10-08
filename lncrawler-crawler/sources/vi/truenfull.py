# -*- coding: utf-8 -*-
import logging
from typing import List, Optional
from urllib.parse import quote_plus, urlencode

from bs4.element import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)


class TruenFull(Crawler):
    has_mtl = True
    # truyenfull.io is intentionally omitted: its TLS chain is broken and it
    # only serves a JS redirect, so it cannot be crawled directly.
    base_url = [
        "https://truyenfull.live/",
        "https://truyenfull.vn/",
        "https://truyenfull.vision/",
    ]

    @staticmethod
    def __select_value(tag: Tag, css: str, attr: Optional[str] = None):
        possible_item = tag.select_one(css)
        if not isinstance(possible_item, Tag):
            return ""
        if attr:
            return (getattr(possible_item, "attrs") or {}).get(attr)
        else:
            return (getattr(possible_item, "text") or "").strip()

    def search_novel(self, query):
        soup = self.get_soup(f"{self.home_url}tim-kiem/?tukhoa={quote_plus(query)}")

        results = []
        for div in soup.select(".list-truyen .row"):
            a = div.select_one("h3.truyen-title a")
            if not isinstance(a, Tag):
                continue

            author = self.__select_value(div, ".author")
            info = [x for x in [author] if x]

            results.append(
                {
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                    "info": " | ".join(info),
                }
            )

        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = f"{self.home_url}danh-sach/truyen-hot/"
            if page > 1:
                url = f"{self.home_url}danh-sach/truyen-hot/trang-{page}/"
            soup = self.get_soup(url)
            items = soup.select(".list-truyen .row")
            if not items:
                break
            for item in items:
                a = item.select_one(".truyen-title a")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("h3.title, h1.title")
        assert isinstance(possible_title, Tag)
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        self.novel_cover = self.__select_value(
            soup, ".book-thumb img, .books .book img", "src"
        )
        logger.info("Novel cover: %s", self.novel_cover)

        authors = soup.select('.info a[itemprop="author"]')
        self.novel_author = ", ".join([x.text for x in authors if isinstance(x, Tag)])
        logger.info("Novel author: %s", self.novel_author)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select('.info a[itemprop="genre"]')
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)

        synopsis_tag = soup.select_one(".desc-text") or soup.select_one("div.desc")
        if synopsis_tag:
            self.novel_synopsis = synopsis_tag.get_text("\n", strip=True)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        info_rows = self.__parse_info_rows(soup)
        if "tên khác" in info_rows or "tên gọi khác" in info_rows:
            value = info_rows.get("tên khác") or info_rows.get("tên gọi khác")
            self.alternative_titles = [
                x.strip() for x in value.split(",") if x.strip()
            ]
        if "nguồn" in info_rows:
            self.translators = [
                x.strip() for x in info_rows["nguồn"].split(",") if x.strip()
            ]
        status = (info_rows.get("trạng thái") or "").lower()
        if "full" in status or "hoàn thành" in status:
            self.status = NovelStatus.completed
        elif "đang ra" in status or "đang cập nhật" in status:
            self.status = NovelStatus.ongoing
        elif "tạm dừng" in status:
            self.status = NovelStatus.hiatus
        logger.info(
            "Status: %s | Alt titles: %s | Translators: %s",
            getattr(self, "status", None),
            getattr(self, "alternative_titles", None),
            getattr(self, "translators", None),
        )

        self.parse_truyenfull_chapters(soup)

    @staticmethod
    def __parse_info_rows(soup: Tag):
        """Map each ``.info`` row label to its value text (label stripped)."""
        rows = {}
        info = soup.select_one(".info")
        if not isinstance(info, Tag):
            return rows
        for div in info.find_all("div", recursive=False):
            h3 = div.find("h3")
            if not isinstance(h3, Tag):
                continue
            label = h3.get_text(strip=True).rstrip(":").lower()
            value = div.get_text(",", strip=True)
            raw = h3.get_text(strip=True)
            if value.startswith(raw):
                value = value[len(raw):]
            rows[label] = value.lstrip(": ,").strip()
        return rows

    def parse_truyenfull_chapters(self, soup: Tag):
        truyen_id = self.__select_value(soup, "input#truyen-id", "value")
        total_page = self.__select_value(soup, "input#total-page", "value")
        truyen_ascii = self.__select_value(soup, "input#truyen-ascii", "value")
        assert truyen_id, "No truen novel id found"
        total_page = int(str(total_page))
        logger.info("Total page count: %d", total_page)

        calls = []
        for page in range(total_page):
            params = urlencode(
                {
                    "type": "list_chapter",
                    "tid": int(truyen_id),
                    "tascii": truyen_ascii,
                    "tname": self.novel_title,
                    "page": page + 1,
                    "totalp": total_page,
                }
            )
            url = f"{self.home_url}ajax.php?" + params
            logger.info("Getting chapters: %s", url)
            calls.append((self.get_json, url))

        for data in self.resolve_bounded(calls):
            soup = self.make_soup(data["chap_list"])
            self.parse_all_links(soup.select(".list-chapter a"))

    def parse_all_links(self, links: List[Tag]):
        for a in links:
            chap_id = 1 + len(self.chapters)
            vol_id = 1 + len(self.chapters) // 100
            if len(self.chapters) % 100 == 0:
                self.volumes.append({"id": vol_id})
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "title": a["title"],
                    "url": self.absolute_url(a["href"]),
                }
            )

    def initialize(self) -> None:
        self.init_executor(ratelimit=2)
        self.cleaner.bad_css = set(
            [
                ".ads-content",
                ".ads-inpage-container",
                ".ads-responsive",
                ".ads-pc",
                ".ads-chapter-box",
                ".incontent-ad",
                ".ads-network",
                ".ads-desktop",
                ".ads-mobile",
                ".ads-holder",
                ".ads-taboola",
                ".ads-middle",
                ".adsbygoogle",
            ]
        )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("#chapter-c, .chapter-c")
        return self.cleaner.extract_contents(contents)

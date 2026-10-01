# -*- coding: utf-8 -*-
import logging
import re

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

SEARCH_URL = "https://novelpia.com/proc/novel"
EPISODE_URL = "https://novelpia.com/proc/episode_list"
VIEWER_URL = "https://novelpia.com/proc/viewer_data/%s"

EP_TITLE_NOISE = re.compile(r"^(?:무료|유료|대여|소장)\s*")


class NovelpiaCrawler(Crawler):
    base_url = "https://novelpia.com/"
    has_mtl = False

    def search_novel(self, query):
        data = {
            "cmd": "novel_search",
            "page": 1,
            "rows": 30,
            "search_type": "all",
            "search_val": query,
            "novel_type": "",
            "start_count_book": "",
            "end_count_book": "",
            "novel_age": "",
            "start_days": "",
            "sort_col": "last_viewdate",
            "novel_genre": "",
            "block_out": 0,
            "block_stop": 0,
            "is_contest": 0,
            "is_complete": "",
            "is_challenge": 0,
            "list_display": "list",
        }
        payload = self.get_json(
            SEARCH_URL,
            headers={"X-Requested-With": "XMLHttpRequest"},
            params=data,
        )
        results = []
        for item in payload.get("list", []) or []:
            novel_no = item.get("novel_no")
            if not novel_no:
                continue
            results.append(
                {
                    "title": (item.get("novel_name") or "").strip(),
                    "url": f"https://novelpia.com/novel/{novel_no}",
                    "info": item.get("writer_nick") or "",
                }
            )
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one('meta[property="og:title"]')
        if title:
            self.novel_title = re.sub(
                r"^.*세상!\s*-\s*", "", title.get("content", "")
            ).strip()
        assert self.novel_title, "No novel title"

        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            self.novel_cover = cover.get("content")

        author = soup.select_one("a.writer-name")
        if author:
            self.novel_author = author.get_text(strip=True)

        synopsis = soup.select_one('meta[property="og:description"]')
        if synopsis:
            self.novel_synopsis = synopsis.get("content", "").strip()

        tag = soup.select_one(".writer-tag")
        if tag:
            self.novel_tags = [t for t in tag.get_text(" ", strip=True).split("#") if t]

        match = re.search(r"/novel/(\d+)", self.novel_url)
        assert match, "No novel id in url"
        novel_no = match.group(1)

        first = self._episode_page(novel_no, 0)
        max_page = re.search(r"max_page\s*=\s*['\"](\d+)['\"]", str(first))
        pages = int(max_page.group(1)) if max_page else 1

        self.volumes.append({"id": 0})
        for page in range(pages):
            page_soup = first if page == 0 else self._episode_page(novel_no, page)
            for row in page_soup.select("tr[data-episode-no]"):
                ep_no = row.get("data-episode-no")
                b = row.select_one("b")
                if not ep_no or not b:
                    continue
                chapter_id = len(self.chapters) + 1
                self.chapters.append(
                    {
                        "id": chapter_id,
                        "volume": 0,
                        "title": EP_TITLE_NOISE.sub("", b.get_text(" ", strip=True)).strip(),
                        "url": f"https://novelpia.com/viewer/{ep_no}",
                    }
                )

    def _episode_page(self, novel_no: str, page: int) -> BeautifulSoup:
        response = self.post_response(
            EPISODE_URL,
            data={"novel_no": novel_no, "sort": "", "page": page},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        return self.make_soup(response)

    def download_chapter_body(self, chapter):
        match = re.search(r"/viewer/(\d+)", chapter["url"])
        assert match, "No episode id in url"
        data = self.get_json(
            VIEWER_URL % match.group(1),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        parts = []
        for item in data.get("s", []) or []:
            text = item.get("text") or ""
            if "cover-wrapper" in text:
                continue
            parts.append(text)
        html = "\n".join(parts)
        soup = self.make_soup(html)
        body = soup.find("body")
        if not isinstance(body, Tag):
            return html
        return self.cleaner.extract_contents(body)

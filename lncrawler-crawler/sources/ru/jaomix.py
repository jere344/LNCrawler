# -*- coding: utf-8 -*-
import json
import logging
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)
ajax_url = "https://jaomix.ru/wp-admin/admin-ajax.php"
MAX_TOC_PAGES = 300
MAX_EMPTY_TOC_PAGES = 3


class JaomixCrawler(Crawler):
    base_url = [
        "https://jaomix.ru/",
    ]

    language = "ru"

    def initialize(self):
        self.init_executor(ratelimit=1)

    def search_novel(self, query):
        soup = self.get_soup(f"{self.base_url[0]}?searchrn={quote_plus(query)}")
        return [
            {
                "title": a["title"],
                "url": self.absolute_url(a["href"]),
                "cover": self.image_url(a.select_one("img")),
            }
            for a in soup.select(".img-home a[title][href]")
        ][:10]

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}?sortby=count&gpage={page}")
            items = soup.select(".img-home a[title][href]")
            if not items:
                break
            for a in items:
                results.append(
                    SearchResult(title=a["title"], url=self.absolute_url(a["href"]))
                )
            page += 1
            if page > 500:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one(".desc-book h1")
        if possible_title:
            self.novel_title = possible_title.get_text()

        logger.info("Novel title: %s", self.novel_title)

        for p in soup.select("#info-book p"):
            text = p.text.strip()
            if "Автор" in text:
                author = text.partition(":")[2].strip()
                if author.startswith("["):
                    # Some pages store the author as a JSON list: ["Name"].
                    try:
                        author = ", ".join(str(x) for x in json.loads(author))
                    except ValueError:
                        pass
                self.novel_author = author
            elif "Жанр" in text:
                self.genres = [
                    g.strip()
                    for g in text.partition(":")[2].split(",")
                    if g.strip()
                ]
            elif "Статус" in text:
                status = text.partition(":")[2].strip().lower()
                if "продолж" in status:
                    self.status = NovelStatus.ongoing
                elif "заверш" in status:
                    self.status = NovelStatus.completed
                elif "приостанов" in status:
                    self.status = NovelStatus.hiatus
            elif "Название" in text:
                self.alternative_titles = [text.partition(":")[2].strip()]

        logger.info("Novel author: %s", self.novel_author)
        logger.info("Novel genres: %s", self.genres)

        possible_synopsis = soup.select_one("div#desc-tab")
        if possible_synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(possible_synopsis)

        logger.info("Novel synopsis: %s", self.novel_synopsis)

        img_src = soup.select_one("div.img-book img")

        if img_src:
            self.novel_cover = self.absolute_url(img_src["src"])

        for url, title in reversed(self._collect_chapters(soup)):
            chap_id = 1 + len(self.chapters)

            self.chapters.append(
                {
                    "id": chap_id,
                    "title": title,
                    "url": url,
                }
            )

    def _collect_chapters(self, soup):
        """Return (url, title) pairs of the whole TOC, newest first.

        The novel page only shows the newest block of 50 chapters. The TOC
        select lists one block per option value; each block is fetched with
        admin-ajax, which needs the novel page as Referer.
        """
        pages = [
            o["value"].strip()
            for o in soup.select("select.sel-toc option[value]")
            if o["value"].strip() not in ("", "0")
        ]
        if not pages:
            pages = None  # no TOC select: the novel page itself is the list
        elif len(pages) > MAX_TOC_PAGES:
            logger.warning("TOC has %d blocks, reading only %d", len(pages), MAX_TOC_PAGES)
            pages = pages[:MAX_TOC_PAGES]

        blocks = pages or [None]
        found = []
        seen = set()
        empty_streak = 0
        for index, page in enumerate(blocks):
            if page is None:
                page_soup = soup
            else:
                page_soup = self.post_soup(
                    ajax_url,
                    data={"action": "loadpagenavchapstt", "page": page},
                    headers={
                        "Referer": self.novel_url,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
            new = 0
            for url, title in self._chapter_links(page_soup):
                if url in seen:
                    continue
                seen.add(url)
                found.append((url, title))
                new += 1
            if new:
                empty_streak = 0
                continue
            empty_streak += 1
            if empty_streak >= MAX_EMPTY_TOC_PAGES:
                remaining = len(blocks) - index - 1
                if remaining:
                    logger.warning(
                        "Stopped reading TOC after %d empty blocks, %d blocks left unread",
                        empty_streak,
                        remaining,
                    )
                break
        return found

    def _chapter_links(self, soup):
        return [
            (self.absolute_url(a["href"]), a.text.strip())
            for a in soup.select(".flex-dow-txt a[href]")
        ]

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".entry-content .entry") or soup.select_one(".entry")
        return self.cleaner.extract_contents(contents)

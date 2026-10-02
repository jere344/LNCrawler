# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)
search_url = "https://noveltoon.mobi/en/search?word=%s&source=&lock="


class NovelsRockCrawler(Crawler):
    base_url = "https://noveltoon.mobi/"

    def initialize(self) -> None:
        self.cleaner.bad_text_regex.update(
            [
                r"Don't forget to leave a like and subscribe to this new novel.",
                r"Feel free to comment your thoughts below.",
                r"——————————————————.*",
                r"Don't forget to leave like sub to this new novel.",
                r"Feel free to comment below.",
            ]
        )

    def search_novel(self, query):
        query = quote_plus(query.lower())
        soup = self.get_soup(search_url % query)

        results = []
        for item in soup.select(".novel-result .recommend-item")[:10]:
            a = item.select_one("a[href]")
            if not a:
                continue
            title = item.select_one(".recommend-comics-title")
            info = item.select_one(".comics-type")
            results.append(
                SearchResult(
                    url=self.absolute_url(a["href"]),
                    title=title.text.strip() if title else a.get_text(strip=True),
                    info=info.text.strip() if info else "",
                )
            )

        return results

    def read_novel_info(self):
        self.novel_url = re.sub(
            r"/detail/(\d+)(/\w+)?",
            lambda m: "/detail/%s/episodes" % m.group(1),
            self.novel_url,
        )

        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one(".detail-top .detail-title")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_image = soup.select_one(".detail-top .detail-top-right img")
        if possible_image:
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        try:
            self.novel_author = soup.select_one(
                ".detail-top .detail-author"
            ).text.strip()
        except Exception as e:
            logger.debug("Failed to get novel author. %s", e)
        logger.info("Novel author: %s", self.novel_author)

        for a in soup.select("a.episodes-info-a-item"):
            chap_id = len(self.chapters) + 1
            vol_id = chap_id // 100 + 1
            if chap_id % 100 == 1:
                self.volumes.append({"id": vol_id})
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "url": self.absolute_url(a["href"]),
                    "title": a.select_one(".episode-item-title").text.strip(),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".watch-chapter-content")
        if contents is None:
            return ""
        # Chat-style layout: each line is a `.content_text` node; join them into
        # paragraphs and drop the avatars/author labels.
        body = soup.new_tag("div")
        for node in contents.select(".content_text"):
            p = soup.new_tag("p")
            p.string = node.get_text(strip=True)
            body.append(p)
        return self.cleaner.extract_contents(body)

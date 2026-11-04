# -*- coding: utf-8 -*-
import html
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)
search_url = "https://noveltoon.mobi/en/search?word=%s&source=&lock="


class NovelsRockCrawler(Crawler):
    is_disabled = True
    disable_reason = "Chapter bodies are no longer served to anonymous readers and chapters are truncated from episode 6"
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
                    cover=self.image_url(item.select_one(".comics-image img")),
                )
            )

        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(
                f"https://noveltoon.mobi/en/genre/2/0/0?page={page}"
            )
            items = soup.select("a.genre-item-box")
            if not items:
                break
            for item in items:
                title = item.select_one(".genre-item-title")
                if not title or not item.get("href"):
                    continue
                results.append(
                    SearchResult(
                        title=title.get_text(strip=True),
                        url=self.absolute_url(item["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

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
            self.novel_author = re.sub(
                r"^Author Name:\s*",
                "",
                soup.select_one(".detail-top .detail-author").text.strip(),
            )
        except Exception as e:
            logger.debug("Failed to get novel author. %s", e)
        logger.info("Novel author: %s", self.novel_author)

        # Synopsis: one <p> with <br> breaks; the last line is the publisher's
        # boilerplate shared by every novel.
        desc = soup.select_one(".detail-top-left .detail-desc-info")
        if desc:
            lines = [line.strip() for line in desc.get_text("\n").split("\n")]
            self.novel_synopsis = "".join(
                f"<p>{html.escape(line, quote=False)}</p>"
                for line in lines
                if line and not re.search(r"got authorization from", line)
            )

        # Tags list also carries the status ("Completed") as its last item.
        tags = []
        for span in soup.select(".detail-tags .detail-tag-item span"):
            text = span.get_text(strip=True)
            if text.lower() in ("ongoing", "completed"):
                self.status = (
                    NovelStatus.completed
                    if text.lower() == "completed"
                    else NovelStatus.ongoing
                )
            elif text and text not in tags:
                tags.append(text)
        self.novel_tags = tags

        # The page lists every episode twice (ascending and reverse lists).
        seen_urls = set()
        for a in soup.select("a.episodes-info-a-item"):
            url = self.absolute_url(a["href"])
            if url in seen_urls:
                continue
            seen_urls.add(url)
            chap_id = len(self.chapters) + 1
            self.chapters.append(
                {
                    "id": chap_id,
                    "url": url,
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

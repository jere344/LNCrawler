# -*- coding: utf-8 -*-
import logging
import re
from bs4 import Tag
from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class sixnineshu(Crawler):
    base_url = [
        "https://www.69shuba.com/",
        "https://www.69shu.com/",
        "https://www.69xinshu.com/",
        "https://www.69shu.pro/",
        "https://www.69shuba.pro/",
    ]

    def initialize(self):
        # the default lxml parser cannot handle the huge gbk encoded sites (fails after 4.3k chapters)
        self.init_parser("html.parser")
        self.init_executor(ratelimit=20)

    def search_novel(self, query):
        # The real search.php endpoint is gated by a Cloudflare Turnstile
        # challenge that curl_cffi cannot solve. `/all.html` is the complete
        # novel index (unchallenged) so filter it locally instead.
        soup = self.get_soup(self.base_url[0] + "all.html", encoding="gbk")

        query = query.lower()
        results = []
        seen = set()
        for a in soup.select("a[href*='/book/']"):
            title = a.text.strip()
            href = a["href"]
            if not title or href in seen:
                continue
            if query not in title.lower():
                continue
            seen.add(href)
            results.append(
                SearchResult(
                    title=title,
                    url=self.absolute_url(href),
                    info="Latest: %s" % title,
                )
            )
            if len(results) >= 10:
                break

        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}novels/hot", encoding="gbk")
        results = []
        for a in soup.select("div.newnav h3 a[href]"):
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url, encoding="gbk")

        possible_title = soup.select_one("div.booknav2 h1")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_image = soup.select_one("div.bookimg2 img")
        if isinstance(possible_image, Tag):
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        possible_author = soup.select_one('.booknav2 p a[href*="author"]')
        if isinstance(possible_author, Tag):
            self.novel_author = possible_author.text.strip()
        logger.info("Novel Author: %s", self.novel_author)

        # tags are in a script tag and js add them to the page
        match = re.search(r"tags:\s*'([^']+)'", str(soup))
        if match:
            tags = match.group(1)
            self.novel_tags = [tag.strip() for tag in tags.split("|") if tag.strip()]
        possible_tags = soup.select('.booknav2 p a[href*="/class/"]')
        for tag in possible_tags:
            self.novel_tags.append(tag.text.strip())

        logger.info("Novel Tags: %s", self.novel_tags)

        possible_synopsis = soup.select_one("div.navtxt")
        if isinstance(possible_synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(possible_synopsis)
        logger.info("Novel Synopsis: %s", self.novel_synopsis)

        # Only one category per novel on this website
        possible_tag = soup.select_one('.booknav2 p a[href*="top"]')
        if isinstance(possible_tag, Tag):
            self.novel_tags = [possible_tag.text.strip()]
        logger.info("Novel Tag: %s", self.novel_tags)

        # https://www.69shuba.com/txt/A43616.htm -> https://www.69shuba.com/A43616/
        soup = self.get_soup(
            self.novel_url.replace("/txt/", "/").replace(".htm", "/"), encoding="gbk"
        )

        volumes = set([])
        for li in soup.select("div#catalog ul li"):
            a = li.select_one("a")
            assert isinstance(a, Tag)
            ch_id = len(self.chapters) + 1
            vol_id = 1 + len(self.chapters) // 100
            volumes.add(vol_id)
            self.chapters.append(
                {
                    "id": ch_id,
                    "volume": vol_id,
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter.url, encoding="gbk")

        contents = soup.select_one("div.txtnav")
        contents.select_one("h1").decompose()
        contents.select_one("div.txtinfo").decompose()
        contents.select_one("div#txtright").decompose()

        return self.cleaner.extract_contents(contents)

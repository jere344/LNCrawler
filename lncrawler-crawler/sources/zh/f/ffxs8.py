# -*- coding: utf-8 -*-
import logging
import re

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class FanFanXiaoShuoCrawler(Crawler):
    base_url = "https://ffxs8.com/"
    language = "zh"

    def search_novel(self, query):
        soup = self.submit_form_for_soup(
            self.absolute_url("/e/search/index.php"),
            data={
                "keyboard": query.encode("gb2312", "ignore"),
                "show": "title",
                "classid": "0",
            },
            headers={"Referer": self.home_url},
            encoding="gb18030",
        )
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or href in seen:
                continue
            if not re.match(r"^/[a-z0-9]+/\d+\.html$", href):
                continue
            seen.add(href)
            results.append({"title": title, "url": self.absolute_url(href)})
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url, encoding="gb18030")

        h1 = soup.select_one("h1")
        self.novel_title = re.sub(r"[（(].*?[)）]\s*$", "", h1.get_text(strip=True)).strip()
        logger.info("Novel title: %s", self.novel_title)

        author = re.search(r"作者[:：]?\s*([^_|，,]+)", soup.title.get_text(strip=True))
        if author:
            self.novel_author = author.group(1).strip()
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one(".descInfo")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        categories = [
            a.get_text(strip=True)
            for a in soup.select(".sNav a")
            if re.match(r"^/[a-z0-9]+/$", a.get("href", ""))
        ]
        if categories:
            self.novel_tags = categories

        for a in soup.select("a[href]"):
            href = a["href"]
            if not re.search(r"/\d+-\d+-\d+\.html$", href):
                continue
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": a.get_text(strip=True),
                    "url": self.absolute_url(href),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"], encoding="gb18030")
        contents = soup.select_one(".content") or soup.select_one("#content")
        self.cleaner.clean_contents(contents)
        return str(contents)

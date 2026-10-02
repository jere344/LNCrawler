# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class LightNovelsTranslationsCrawler(Crawler):
    base_url = "https://lightnovelstranslations.com/"

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

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        prefix = self.novel_url.rstrip("/") + "/"
        seen = set()
        for a in soup.select("a[href]"):
            href = a["href"]
            if not href.startswith(prefix) or href == prefix or "?" in href:
                continue
            if href.endswith("/#respond") or href in seen:
                continue
            seen.add(href)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": a.get_text(strip=True),
                    "url": href,
                }
            )

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
            if label and label.get_text(strip=True).startswith("Author"):
                self.novel_author = li.get_text(" ", strip=True).split(":", 1)[-1].strip()
                break
        logger.info("Novel author: %s", self.novel_author)

        cover = soup.select_one(".novel-image img")
        if cover:
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

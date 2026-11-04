# -*- coding: utf-8 -*-
import logging
from html import escape

from bs4.element import Tag
from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class TigerTranslations(Crawler):
    base_url = "https://tigertranslations.org/"

    # there's certain text within the .entry-content which can be removed
    removable_texts = ["Page 1", "Page 2", "Next Chapter", "Previous Chapter"]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        content = soup.select_one("div.entry-content")

        entry_title = soup.select_one("h1.entry-title")
        assert isinstance(entry_title, Tag)  # this must be here, is part of normal site structure/framework
        self.novel_title = entry_title.text
        self.novel_author = "TigerTranslations"

        if isinstance(content, Tag):
            for line in content.text.splitlines():
                if "author:" in line.lower():
                    self.novel_author = line[line.find(':') + 1:].strip()
                    self.translators = ["TigerTranslations"]
                    break  # no need to continue after finding author
            self.novel_synopsis = self._synopsis(content)
            first = content.find("p")
            if first:
                titles = []
                for bit in first.strings:
                    text = str(bit).strip()
                    if text and text != self.novel_title and text not in titles:
                        titles.append(text)
                self.alternative_titles = titles

        logger.info("Novel title: %s", self.novel_title)
        logger.info("Novel author: %s", self.novel_author)

        if isinstance(content, Tag):
            for img in content.select("img"):
                src = img.get("src")
                if src:
                    self.novel_cover = self.absolute_url(src)
                    break

        logger.info("Novel cover: %s", self.novel_cover)

        if not isinstance(content, Tag):
            return

        links = [a for a in content.select("a") if a.text.strip().lower().startswith("chapter")]
        for i, a in enumerate(links):
            url = self.absolute_url(a["href"])
            # Some posts are listed twice, or with a wrong number on the first
            # entry: keep the last entry for that post, its title is the right one.
            if any(self.absolute_url(b["href"]) == url for b in links[i + 1 :]):
                continue
            chap_id = 1 + len(self.chapters)
            self.chapters.append(
                Chapter(
                    id=chap_id,
                    url=url,
                    title=a.text,
                ),
            )

    @staticmethod
    def _synopsis(content: Tag) -> str:
        # The blurb sits between the "Author:" line and the chapter links.
        paragraphs = []
        after_author = False
        for p in content.find_all("p", recursive=False):
            text = p.get_text(" ", strip=True)
            if not after_author:
                after_author = text.lower().startswith("author:")
                continue
            if text.lower().startswith("chapter"):
                break
            if text:
                paragraphs.append("<p>%s</p>" % escape(text))
        return "".join(paragraphs)

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter.url)
        contents_html = soup.select_one("div.entry-content")
        contents_str = self.cleaner.extract_contents(contents_html)

        # remove annoyances (such as "Page 2")
        for text in self.removable_texts:
            contents_str = contents_str.replace(text, '')
            contents_str = contents_str.replace(text.upper(), '')
            contents_str = contents_str.replace(text.lower(), '')

        return contents_str

    def search_novel(self, query: str):
        soup = self.get_soup(f"{self.home_url}?s={query}")
        results = []
        seen = set()

        # WP search mixes chapter posts and novel overview pages; a novel page is
        # the only one whose .entry-content links to chapters.
        for a in soup.select(".entry-title a"):
            url = a.get("href", "")
            if not url or url in seen:
                continue
            seen.add(url)

            page = self.get_soup(url)
            content = page.select_one("div.entry-content")
            if not isinstance(content, Tag):
                continue
            if not any(
                x.text.strip().lower().startswith("chapter")
                for x in content.select("a")
            ):
                continue

            results.append(
                SearchResult(
                    title=a.text,
                    url=url,
                    cover=self.image_url(content.select_one("img")),
                )
            )

        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}novels/")
        results = []
        for a in soup.select("#primary-menu > li > a[href]"):
            title = a.get_text(strip=True)
            if not title or "donation" in title.lower():
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

# -*- coding: utf-8 -*-

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from lncrawl.core import body_migrations
from lncrawl.models import Chapter, NovelStatus, SearchResult
from lncrawl.templates.browser.chapter_only import ChapterOnlyBrowserTemplate

logger = logging.getLogger(__name__)

# Chapter footer nav line, not part of the text.
_NAV_RE = r"^\s*Previous Chapter \u2207 Table of Content \u2207 Next Chapter\s*$"


def _strip_nav(body: str) -> str:
    return body_migrations.drop_matching(body, _NAV_RE)


class SnowyCodexCrawler(ChapterOnlyBrowserTemplate):
    base_url = "https://snowycodex.com/"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            {
                ".wpulike",
                ".sharedaddy",
                ".wpulike-default",
                '[style="text-align:center;"]',
            }
        )
        self.cleaner.bad_tag_text_pairs.update(
            {
                "p": r"[\u4E00-\u9FFF]+",
            }
        )

    def search_novel(self, query):
        soup = self.get_soup(f"{self.base_url[0]}/novels/")
        query = query.lower()
        results = []
        for a in soup.select("a[href]"):
            title = a.text.strip()
            path = urlparse(a["href"]).path
            if not title or path.count("/") != 3 or not path.startswith("/novels/"):
                continue
            if path == "/novels/oneshots/":
                continue
            if query in title.lower():
                results.append(
                    {"title": title, "url": self.absolute_url(a["href"])}
                )
        return results[:10]

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}novels/")
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            title = a.text.strip()
            path = urlparse(a["href"]).path
            if not title or path.count("/") != 3 or not path.startswith("/novels/"):
                continue
            if path == "/novels/oneshots/":
                # Collection page for one-shot stories, not a novel of its own.
                continue
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def parse_chapter_body(self, tag: Tag) -> str:
        return _strip_nav(super().parse_chapter_body(tag))

    def _migrate_v2(self, body, chapter):
        return _strip_nav(body)

    def get_novel_soup(self):
        # Keep the novel page soup so read_novel_info can read the status from it.
        self._novel_soup = super().get_novel_soup()
        return self._novel_soup

    def read_novel_info(self):
        super().read_novel_info()
        soup = getattr(self, "_novel_soup", None)
        if soup is None:
            return
        # The status is inside the "Status: 197 Chapters + 4 Extras (Complete)" line.
        content = soup.select_one(".entry-content")
        label = content.find("strong", string=re.compile(r"^\s*Status:")) if content else None
        if not isinstance(label, Tag) or not isinstance(label.parent, Tag):
            return
        value = label.parent.get_text(" ", strip=True).split(":", 1)[-1].lower()
        if "ongoing" in value:
            self.status = NovelStatus.ongoing
        elif "complete" in value:
            self.status = NovelStatus.completed
        elif "hiatus" in value:
            self.status = NovelStatus.hiatus

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".entry-content h2")
        assert isinstance(tag, Tag)
        return tag.text.strip()

    def parse_summary(self, soup: BeautifulSoup) -> str:
        # The blurb is the paragraphs after "Summary:" up to the next "Label:" line.
        label = soup.find(
            "strong", string=re.compile(r"^\s*Summary:")
        )
        if not isinstance(label, Tag) or not isinstance(label.parent, Tag):
            return ""
        paragraphs = []
        inline = " ".join(
            node.get_text(" ", strip=True) if isinstance(node, Tag) else str(node).strip()
            for node in label.next_siblings
        ).strip()
        if inline:
            paragraphs.append(inline)
        for sibling in label.parent.find_next_siblings("p"):
            children = [
                c for c in sibling.contents
                if not (isinstance(c, NavigableString) and not c.strip())
            ]
            first = children[0] if children else None
            if (
                isinstance(first, Tag)
                and first.name == "strong"
                and first.get_text(strip=True).endswith(":")
            ):
                break
            text = sibling.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)

    def parse_cover(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".entry-content img")
        assert isinstance(tag, Tag)
        if tag.has_attr("data-src"):
            return self.absolute_url(tag["data-src"])
        elif tag.has_attr("src"):
            return self.absolute_url(tag["src"])

    def parse_authors(self, soup: BeautifulSoup):
        tag = soup.find("strong", string="Author:")
        assert isinstance(tag, Tag)
        yield tag.next_sibling.text.strip()

    def parse_genres(self, soup: BeautifulSoup):
        tag = soup.find("strong", string=re.compile(r"^Tags"))
        if not isinstance(tag, Tag) or not isinstance(tag.parent, Tag):
            return
        value = tag.parent.get_text(" ", strip=True).split(":", 1)[-1]
        for part in re.split(r"[,;]+", value):
            if part.strip():
                yield part.strip()

    def select_chapter_tags(self, soup: BeautifulSoup):
        yield from soup.select(".entry-content a[href*='/chapter']")

    def parse_chapter_item(self, tag: Tag, id: int) -> Chapter:
        return Chapter(
            id=id,
            title=tag.text.strip(),
            url=self.absolute_url(tag["href"]),
        )

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        return soup.select_one(".entry-content")

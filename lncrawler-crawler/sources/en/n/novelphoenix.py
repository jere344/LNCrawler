# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

# Watermark paragraphs injected mid-chapter. The wording is randomised and often
# omits the site name, so match the recurring themes instead of exact sentences.
# Only short, standalone blocks are tested (see download_chapter_body), and every
# alternative needs a watermark-only combination of words, never one common word.
_WATERMARK_RE = re.compile(
    r"novel\s*phoenix"
    # "...on Amazon ... stolen / report / without the author's consent"
    r"|\bamazon\b.{0,120}\b(report|stolen|consent|unlawful\w*|theft|purloined|lifted|obtained|taken|violation)\b"
    r"|\b(report|stolen|consent|unlawful\w*|theft|purloined|lifted|obtained|taken|violation)\b.{0,120}\bamazon\b"
    # "stolen / unauthorized ... author's consent / report the violation"
    r"|\b(stolen|theft|purloined|unlawful\w*|unauthori[sz]ed|pirate site)\b.{0,100}\b(author|report|violation|sightings?|content|story|tale|narrative|novel|book)\b"
    r"|without the author'?s (consent|approval|permission)"
    r"|\breport (the|any) (violation|sightings?|appearances?|instances?)\b"
    # "support the author ... original site / official source / reading it there"
    r"|\b(support|supports)\b.{0,60}\b(author|authors|creativity)\b.{0,80}\b(there|original|official|visiting|finding|seeking|reading)\b"
    r"|\bsupport (the )?(original )?(creators?|authors?)\b.{0,3}$"
    r"|\b(pirated|pirate)\b.{0,60}\b(copy|site|version)\b"
    r"|\b(official|preferred) (release|platform)\b.{0,60}\b(support|author|novel)\b"
    r"|\b(original|official|genuine|true) (site|source|version|home|story|platform)\b.{0,80}\b(novel|story|tale|narrative|book|author|support)\b"
    r"|\b(novel|story|tale|narrative|book)\b.{0,60}\b(hosted|published|found|available|is from|true home|originates)\b.{0,40}\b(another|different|elsewhere|original|official|other)\b",
    re.I,
)


class NovelPhoenixCrawler(Crawler):
    base_url = ["https://novelphoenix.com/"]
    language = "en"
    # v2: drop the injected watermark paragraphs.
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            {
                ".free-support-top",
                ".free-support-bottom",
                ".chapter-nav",
            }
        )

    def search_novel(self, query):
        soup = self.get_soup(
            "{0}search?keyword={1}".format(self.home_url, quote_plus(query))
        )
        results = []
        seen = set()
        for a in soup.select("li.novel-item a[href*='/novel/']"):
            href = a.get("href", "")
            if "/chapter" in href:
                continue
            url = self.absolute_url(href)
            title = a.get("title") or a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            cover = self.image_url(a.select_one(".novel-cover img"))
            results.append({"title": title, "url": url, "cover": cover})
        return results[:20]

    def browse_novels(self, offset: int = 0, limit: int = 50):
        soup = self.get_soup(f"{self.home_url}ranking")
        results = []
        for item in soup.select("li.novel-item"):
            a = item.select_one(".title a") or item.select_one("h2 a")
            if not a:
                continue
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".novel-title") or soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        cover = soup.select_one(".cover img") or soup.select_one(".novel-cover img")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src") or cover.get("data-src"))
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one(".author")
        if author:
            self.novel_author = re.sub(
                r"^\s*Author\s*:\s*", "", author.get_text(strip=True)
            )
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one(".summary .content") or soup.select_one(".summary")
        if synopsis:
            for heading in synopsis.select("h1, h2, h3, h4, h5, h6"):
                heading.extract()
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select(".categories a.property-item[href*='/genre-']")
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)

        slug = self.novel_url.rstrip("/")
        if slug.endswith("/chapters"):
            slug = slug[: -len("/chapters")]
        first = self.get_soup(slug + "/chapters")

        last_page = 1
        for a in first.select('a[href*="chapters?page="]'):
            match = re.search(r"page=(\d+)", a.get("href", ""))
            if match:
                last_page = max(last_page, int(match.group(1)))

        found = {}
        for page in range(1, last_page + 1):
            page_soup = first if page == 1 else self.get_soup(
                "{0}/chapters?page={1}".format(slug, page)
            )
            for a in page_soup.select("#chapter-list-page a[href*='/chapter-']"):
                match = re.search(r"/chapter-(\d+)", a.get("href", ""))
                if not match:
                    continue
                number = int(match.group(1))
                label = a.select_one(".chapter-title")
                found[number] = (
                    (label or a).get_text(" ", strip=True) or "Chapter %d" % number,
                    self.absolute_url(a["href"]),
                )

        for index, number in enumerate(sorted(found)):
            title, url = found[number]
            self.chapters.append(
                {"id": index + 1, "title": title, "url": url}
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("#content")
        if contents:
            for node in contents.find_all(["p", "div"]):
                text = node.get_text(" ", strip=True)
                if len(text) < 160 and _WATERMARK_RE.search(text):
                    node.extract()
        return self.cleaner.extract_contents(contents)

    def _migrate_v2(self, body, chapter):
        return body_migrations.drop_matching(body, _WATERMARK_RE, max_length=159)

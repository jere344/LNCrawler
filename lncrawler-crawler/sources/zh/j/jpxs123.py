# -*- coding: utf-8 -*-
"""精品小说网 (jpxs123.cc / jpxs123.top) — Chinese original web novels, static HTML, GBK.

- Chapter URLs: /<category>/<book_id>/<n>.html, whole table of contents on the book page.
- Search: POST /e/search/indexsearch.php with GBK-encoded keyword (redirects to a result page).
- Browse: ranking pages /hot/ and /hot/index_N.html (20 per page).
- Chapter bodies are in div.read_chapterDetail; the site injects remote-eval ad scripts
  (hbs.js) and an obfuscated eval loader on 404 pages, so scripts and ad blocks are stripped.
"""
import html
import logging
import re

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

ENCODING = "gb18030"
MAX_BROWSE_PAGES = 50


class JpXs123Crawler(Crawler):
    base_url = ["https://jpxs123.cc/", "https://jpxs123.top/"]
    language = "zh"

    def search_novel(self, query):
        soup = self.submit_form_for_soup(
            self.absolute_url("/e/search/indexsearch.php"),
            data={
                "keyboard": query.encode("gb18030", "ignore"),
                "show": "title",
                "classid": "0",
            },
            headers={"Referer": self.home_url},
            encoding=ENCODING,
        )
        results = []
        seen = set()
        for h3 in soup.select(".bk_right h3"):
            a = h3.select_one("a[href]")
            if not a:
                continue
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            container = h3.parent
            labels = container.select("label.size, label.date") if container else []
            info = " | ".join(l.get_text(strip=True) for l in labels) or None
            results.append(
                SearchResult(title=a.get_text(strip=True), url=url, info=info)
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= MAX_BROWSE_PAGES:
            path = "/hot/" if page == 1 else f"/hot/index_{page}.html"
            soup = self.get_soup(self.absolute_url(path), encoding=ENCODING)
            items = soup.select(".books .bk")
            if not items:
                break
            added = 0
            for item in items:
                a = item.select_one("a[href]")
                title_tag = item.select_one(".infos h3")
                if not a or not title_tag:
                    continue
                url = self.absolute_url(a["href"])
                if url in seen:
                    continue
                seen.add(url)
                added += 1
                results.append(
                    SearchResult(
                        title=title_tag.get_text(strip=True),
                        url=url,
                    )
                )
            if added == 0:
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url, encoding=ENCODING)

        h1 = soup.select_one(".infos h1")
        if not h1:
            raise ValueError(f"Novel title not found: {self.novel_url}")
        raw_title = h1.get_text(strip=True)
        if "全本" in raw_title:
            self.status = NovelStatus.completed
        self.novel_title = re.sub(r"\s*[（(](全本|连载|完结)[)）]\s*$", "", raw_title).strip()
        logger.info("Novel title: %s", self.novel_title)

        author_link = soup.select_one(".date span a")
        if author_link:
            self.novel_author = author_link.get_text(strip=True)
        logger.info("Novel author: %s", self.novel_author)

        cover = soup.select_one(".book_info .pic img")
        if cover and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])

        tags = []
        crumbs = soup.select(".readTop a[href]")
        if len(crumbs) >= 2:
            tags.append(crumbs[1].get_text(strip=True))

        intro = soup.select_one(".book_info .infos > p")
        if intro:
            lines = [
                line.strip()
                for line in intro.get_text("\n", strip=True).split("\n")
                if line.strip()
            ]
            synopsis_lines = []
            in_synopsis = False
            for line in lines:
                if line.startswith("别名："):
                    alias = line[len("别名："):].strip()
                    if alias:
                        self.alternative_titles.append(alias)
                elif line.startswith("标签："):
                    for tag in re.split(r"[,，]", line[len("标签："):]):
                        tag = tag.strip()
                        if tag:
                            tags.append(tag)
                elif line.startswith("简介："):
                    in_synopsis = True
                    text = line[len("简介："):].strip()
                    if text:
                        synopsis_lines.append(text)
                elif in_synopsis:
                    synopsis_lines.append(line)
            self.novel_synopsis = "".join(
                f"<p>{html.escape(s)}</p>" for s in synopsis_lines
            )

        seen_tags = set()
        self.novel_tags = []
        for tag in tags:
            if tag not in seen_tags:
                seen_tags.add(tag)
                self.novel_tags.append(tag)

        book_id = re.search(r"/(\d+)\.html$", self.novel_url)
        if not book_id:
            raise ValueError(f"Unexpected novel URL: {self.novel_url}")
        chapter_re = re.compile(rf"^/[a-z]+/{book_id.group(1)}/\d+\.html$")

        seen_urls = set()
        for a in soup.select(".book_list a[href]"):
            href = a["href"]
            if not chapter_re.match(href):
                continue
            url = self.absolute_url(href)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get_text(strip=True),
                    url=url,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"], encoding=ENCODING)
        contents = soup.select_one(".read_chapterDetail")
        if contents is None:
            logger.warning("Chapter body not found: %s", chapter["url"])
            return ""
        for junk in contents.select(
            "script, noscript, iframe, ins, style, .ad, .ads, .adbox, [class*='adv']"
        ):
            junk.decompose()
        return self.cleaner.extract_contents(contents)

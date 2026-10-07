# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

API = "https://baka-tsuki.org/project/api.php"

_NAMESPACES = {
    "file", "template", "user", "help", "category", "talk", "special",
    "mediawiki", "module", "forum", "widget", "project",
}
_SKIP_WORDS = (
    "full text", "novel illustration", "illustration", "registration",
    "download", "update", "project staff", "translator", "editor",
    "timeline", "synopsis", "overview", "wiki", "wikipedia", "more information",
    "guideline", "sandbox", "cc-by", "copyright",
)


class BakaTsukiCrawler(Crawler):
    base_url = "https://baka-tsuki.org/"
    language = "en"

    def search_novel(self, query):
        data = self.get_json(
            f"{API}?action=query&list=search&srnamespace=0&srlimit=20"
            f"&format=json&srsearch={query.replace(' ', '%20')}"
        )
        results = []
        for item in data.get("query", {}).get("search", []):
            title = item["title"]
            if ":" in title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=self._page_url(title),
                    info=f"Page id: {item['pageid']}",
                )
            )
        return results[:10]

    def browse_novels(self, offset=0, limit=50):
        data = self.get_json(
            f"{API}?action=query&list=querypage&qppage=Mostlinked"
            f"&qplimit=500&format=json"
        )
        results = []
        for item in data.get("query", {}).get("querypage", {}).get("results", []):
            title = item.get("title", "")
            if item.get("ns") != 0 or ":" in title:
                continue
            if any(w in title.lower() for w in _SKIP_WORDS):
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=self._page_url(title.replace(" ", "_")),
                )
            )
        return results[offset : offset + limit]

    def _page_url(self, page_title: str) -> str:
        title = quote(page_title.replace(" ", "_"), safe="/:")
        return "https://baka-tsuki.org/project/index.php?title=" + title

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        self.novel_title = soup.select_one("h1.firstHeading").get_text(strip=True)

        content = soup.select_one(".mw-parser-output")
        text = content.get_text(" ", strip=True)
        author = re.search(r"Author:\s*([^\n]+?)(?:\s{2,}|Illustrator:|Genres|$)", text)
        if author:
            self.novel_author = author.group(1).strip()[:120]

        og_image = soup.select_one('meta[property="og:image"]')
        if og_image and og_image.get("content"):
            self.novel_cover = self.absolute_url(og_image["content"])
        else:
            img = content.select_one("figure.mw-halign-right img, .infobox img, figure img")
            if img and img.get("src"):
                self.novel_cover = self.absolute_url(img["src"])

        first_paras = []
        for p in content.select("p"):
            line = p.get_text(" ", strip=True)
            if not line or line.startswith("This project has been updated"):
                continue
            first_paras.append(line)
            if len(first_paras) >= 2:
                break
        self.novel_synopsis = " ".join(first_paras)[:2000]

        page_title = parse_qs(urlparse(self.novel_url).query).get("title", [""])[0]
        seen = set()
        for a in content.find_all("a", href=True):
            href = a["href"]
            if "title=" not in href or "action=" in href:
                continue
            target = unquote(parse_qs(urlparse(href).query).get("title", [""])[0])
            if not target:
                continue
            ns = target.split(":", 1)[0].lower()
            if ns in _NAMESPACES:
                continue
            label = a.get_text(strip=True)
            low = (target + " " + label).lower()
            if any(w in low for w in _SKIP_WORDS):
                continue
            url = self._page_url(target)
            if url in seen or target == page_title:
                continue
            seen.add(url)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": label or target.split(":", 1)[-1].replace("_", " "),
                    "url": url,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one(".mw-parser-output")
        for tag in body.select(".mw-editsection, .noprint, .toc, sup.reference, .reference"):
            tag.decompose()
        if soup.select_one("h2 .mw-headline"):
            for h in body.select("h2, h3"):
                if "Translator" in h.get_text() and "Note" in h.get_text():
                    node = h
                    while node:
                        nxt = node.find_next_sibling()
                        node.decompose()
                        node = nxt
                    break
        self.cleaner.clean_contents(body)
        return str(body)

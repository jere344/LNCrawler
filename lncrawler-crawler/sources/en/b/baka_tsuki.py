# -*- coding: utf-8 -*-
import logging
import re
from collections import Counter
from urllib.parse import parse_qs, quote, unquote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult, Volume

logger = logging.getLogger(__name__)

API = "https://baka-tsuki.org/project/api.php"
_WRITTEN_BY = re.compile(r"written by\s+(.+?)\s*(?:\s+and\s+|[(.,;]|$)", re.I)
_VOLUME_NOTE = re.compile(r"\s*\((?=[^()]*(?:full text|epub|pdf))[^()]*\)\s*$", re.I)
_NOTE_SECTIONS = (
    "translation", "project staff", "updates", "series overview", "terminolog",
    "awards", "alternative languages", "story synopsis", "recruitment", "feedback",
)

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
    version = 2

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
        self.novel_edition = "Light Novel"
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

        if not getattr(self, "novel_author", None):
            by = _WRITTEN_BY.search(" ".join(first_paras))
            if by:
                self.novel_author = by.group(1).strip()[:120]

        self._read_volumes(content)

    def _link_target(self, a):
        """Page title behind a wiki link, or None for external, redlink and namespace links."""
        href = a.get("href") or ""
        if "title=" not in href or "action=" in href:
            return None
        target = unquote(parse_qs(urlparse(href).query).get("title", [""])[0]).strip()
        ns, sep, _ = target.partition(":")
        if not sep or ns.lower() in _NAMESPACES:
            return None
        return target

    def _project_links(self, links, project_ns):
        """(label, url) of links to pages under the project's own prefix, minus galleries."""
        picked = []
        for a in links:
            target = self._link_target(a)
            if not target or target.split(":", 1)[0] != project_ns:
                continue
            label = " ".join(a.get_text(" ", strip=True).split())
            low = (target + " " + label).lower()
            if any(w in low for w in _SKIP_WORDS):
                continue
            label = label or target.split(":", 1)[-1].replace("_", " ")
            picked.append((label, self._page_url(target)))
        return picked

    def _read_volumes(self, content):
        # Each h3 is a volume; its chapter links sit in the sibling blocks before the next heading.
        # h3s under project notes (translation guidelines, staff, updates) are not volumes.
        sections = []
        for heading in content.find_all("h3"):
            parent_h2 = heading.find_previous("h2")
            h2_text = parent_h2.get_text(" ", strip=True).lower() if parent_h2 else ""
            if h2_text.startswith(_NOTE_SECTIONS):
                continue
            nodes = []
            node = heading.find_next_sibling()
            while node is not None and node.name not in ("h2", "h3"):
                nodes.append(node)
                node = node.find_next_sibling()
            sections.append((heading, nodes))

        counts = Counter()
        for a in content.find_all("a", href=True):
            target = self._link_target(a)
            if target:
                counts[target.split(":", 1)[0]] += 1
        if not counts:
            return
        project_ns = counts.most_common(1)[0][0]

        volumes = []
        seen = set()
        for heading, nodes in sections:
            links = [a for node in nodes for a in node.find_all("a", href=True)]
            chapters = []
            for label, url in self._project_links(links, project_ns):
                if url in seen:
                    continue
                seen.add(url)
                chapters.append((label, url))
            if not chapters:
                continue
            title = " ".join(heading.get_text(" ", strip=True).split())
            title = _VOLUME_NOTE.sub("", title).strip()
            imgs = [img for node in nodes for img in node.select("figure img")]
            cover = self.image_url(imgs[0], self.novel_url) if imgs else None
            volumes.append((title, cover, chapters))

        if not volumes:
            # No volume headings: keep the project's pages as one flat list.
            all_links = content.find_all("a", href=True)
            for label, url in self._project_links(all_links, project_ns):
                if url not in seen:
                    seen.add(url)
                    self.chapters.append(
                        {"id": len(self.chapters) + 1, "title": label, "url": url}
                    )
            return

        for title, cover, chapters in volumes:
            vol_id = len(self.volumes) + 1
            self.volumes.append(Volume(id=vol_id, title=title, cover_url=cover))
            for label, url in chapters:
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": label,
                        "url": url,
                        "volume": vol_id,
                    }
                )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one(".mw-parser-output")
        if body is None:
            return ""
        for tag in body.select(
            ".mw-editsection, .noprint, .toc, sup.reference, .reference, table#navbar"
        ):
            tag.decompose()
        for table in body.select("table"):
            links = [a.get_text(strip=True) for a in table.find_all("a")]
            if links[:1] == ["Prev"] and links[-1:] == ["Next"]:
                table.decompose()
        for p in body.select("p"):
            if not p.get_text(strip=True) and not p.find("img"):
                p.decompose()
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

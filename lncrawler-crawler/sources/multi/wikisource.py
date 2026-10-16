# -*- coding: utf-8 -*-
"""Generic Wikimedia Wikisource crawler (MediaWiki API).

Public-domain texts from the language Wikisource editions. A "work" is a wiki
page; its chapters are usually subpages (``Work/Chapter 1``) listed on the work
page, otherwise the single page is one chapter. Everything is read through the
stable ``/w/api.php`` endpoints, so no HTML scraping is needed for the TOC.

``GadyaKoshCrawler`` (sources/hi/gadyakosh.py) subclasses this module's
``WikisourceCrawler`` for a different MediaWiki farm that names chapters
``Chapter / Work / Author`` instead of using subpages.

Language resolution: the framework only auto-assigns a class-level ``language``
from the ``sources/<xx>/`` directory, and ``sources/multi/`` has no 2-letter
code, so a multi-edition crawler must set ``self.language`` per novel. The
instance attribute is what ``save_metadata`` reads (``crawler.language``), so
setting it in ``read_novel_info()`` works; the host subdomain is mapped here.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlencode, urlparse

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

# Host subdomain -> language; also the explicit base_url list so the lazy host
# index maps each edition to this file without importing every source.
WIKISOURCE_LANGS = [
    "ml", "mr", "te", "kn", "gu", "or", "as", "pa", "ta", "bn", "hi", "ur", "fa", "ne",
]

# ``|key = value`` within a template call, stopping at the next template
# parameter. Only spaces/tabs may follow ``=`` before the value, otherwise an
# empty parameter would swallow the next line.
_PARAM_RE = re.compile(r"\|\s*([^=\n|]+?)[ \t]*=[ \t]*(.*?)[ \t]*(?=\n\s*[|}]|$)", re.S)
_HTML_RE = re.compile(r"<[^>]+>")


class WikisourceCrawler(Crawler):
    base_url = [
        "https://ml.wikisource.org/",
        "https://mr.wikisource.org/",
        "https://te.wikisource.org/",
        "https://kn.wikisource.org/",
        "https://gu.wikisource.org/",
        "https://or.wikisource.org/",
        "https://as.wikisource.org/",
        "https://pa.wikisource.org/",
        "https://ta.wikisource.org/",
        "https://bn.wikisource.org/",
        "https://hi.wikisource.org/",
        "https://ur.wikisource.org/",
        "https://fa.wikisource.org/",
        "https://ne.wikisource.org/",
        # Multilingual hub (also carries the Sinhala texts).
        "https://wikisource.org/",
    ]

    api_path = "w/api.php"
    article_path = "wiki/"

    # Template parameters carrying the same meaning across editions. Matching
    # is exact (case-insensitive), so an edition whose template uses a key not
    # listed here simply leaves that field empty rather than picking a wrong one.
    FIELD_ALIASES: Dict[str, List[str]] = {
        "title": ["title", "नाम", "శీర్షిక", "ശീർഷകം", "শিরোনাম", "શીર્ષક",
                  "ଶୀର୍ଷକ", "தலைப்பு", "शीर्षक", "عنوان", "سرخی"],
        "author": ["author", "रचनाकार", "लेखक", "రచయిత", "രചയിതാവ്", "লেখক",
                   "લેખક", "ଲେଖକ", "ஆசிரியர்", "مصنف"],
        "translator": ["translator", "अनुवाद", "अनुवादक", "అనువాదం", "অনুবাদ",
                       "ترجمہ"],
        "publisher": ["publisher", "प्रकाशक", "প্রকাশক", "પ્રકાશક",
                      "ప్రచురణకర్త", "ناشر"],
        "genre": ["genre"],
        "year": ["year", "वर्ष", "సంవత్సరం", "বছর", "વર્ષ", "سال"],
        "image": ["image", "चित्र", "চিত্র", "ચિત્ર", "ଚିତ୍ର", "تصویر"],
        "notes": ["notes", "विविध", "विवरण", "వివరములు", "টীকা", "نوٹ"],
    }

    # Stripped before reading the work page's chapter links, so navigation
    # templates and the duplicate sidebar TOC cannot reorder the chapters.
    _toc_bad_css = [
        ".headertemplate", ".header_notes", ".toccolours",
        ".mw-editsection", ".noprint", ".catlinks",
    ]
    # Stripped from a chapter body before extraction.
    body_bad_css = [
        ".headertemplate", ".header_notes", ".toccolours", ".mw-editsection",
        ".noprint", ".catlinks", ".ws-noexport", "sup.reference", "table.navbox",
    ]

    def initialize(self) -> None:
        # MediaWiki starts throttling after ~13 rapid API calls; one request
        # per 0.5s keeps a TOC read well under the limit.
        self.init_executor(ratelimit=2)

    # -- url / language helpers --------------------------------------- #

    def _detect_language(self) -> str:
        host = (self.origin.hostname or "").lower()
        if host.endswith(".wikisource.org"):
            return host.split(".")[0]
        if host in ("wikisource.org", "www.wikisource.org"):
            return "si"
        return ""

    def _site(self) -> str:
        return "{0.scheme}://{0.netloc}/".format(self.origin)

    def _api(self, params: Dict[str, str]) -> dict:
        query = dict(params)
        query["format"] = "json"
        url = self._site() + self.api_path + "?" + urlencode(query)
        return self.get_json(url)

    def _page_url(self, title: str) -> str:
        slug = quote(title.strip().replace(" ", "_"), safe="/_")
        return self._site() + self.article_path + slug

    def _title_from_url(self, url: str) -> str:
        # Strip the site root ("/" or e.g. "/gk/") and then the article prefix
        # ("wiki/" or "") so the same code serves every MediaWiki layout.
        path = unquote(urlparse(url).path)
        site_path = urlparse(self._site()).path or "/"
        if path.startswith(site_path):
            path = path[len(site_path):]
        if self.article_path and path.startswith(self.article_path):
            path = path[len(self.article_path):]
        return path.replace("_", " ").strip("/")

    # -- template / wikitext helpers ---------------------------------- #

    @staticmethod
    def _parse_params(wikitext: str) -> Dict[str, str]:
        return {
            match.group(1).strip(): match.group(2).strip()
            for match in _PARAM_RE.finditer(wikitext or "")
        }

    @staticmethod
    def _plain(text: str) -> str:
        text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text or "")
        text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
        text = re.sub(r"\{\{[^}]*\}\}", "", text)
        text = re.sub(r"'{2,}", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _field(self, params: Dict[str, str], field: str) -> str:
        aliases = {a.lower() for a in self.FIELD_ALIASES.get(field, [])}
        for key, value in params.items():
            if key.lower() in aliases:
                text = self._plain(value)
                if text and text != "--":
                    return text
        return ""

    # -- chapter discovery hooks -------------------------------------- #

    def _is_chapter(self, title: str, page: str) -> bool:
        return title.startswith(page + "/")

    def _chapter_entries(self, page: str, soup: Tag) -> List[Tuple[str, str]]:
        """Ordered ``(title, label)`` chapter links from the work page."""
        body = soup.select_one(".mw-parser-output") or soup
        for selector in self._toc_bad_css:
            for tag in body.select(selector):
                tag.decompose()

        found: Dict[str, str] = {}
        for anchor in body.select("a[title]"):
            if "index.php" in (anchor.get("href") or ""):
                continue  # red link / edit link
            title = (anchor.get("title") or "").strip().replace("_", " ")
            if not title or ":" in title or title == page:
                continue
            if self._is_chapter(title, page) and title not in found:
                found[title] = anchor.get_text(" ", strip=True).replace("_", " ").strip()
        return list(found.items())

    def _subpages(self, page: str) -> List[Tuple[str, str]]:
        data = self._api({
            "action": "query",
            "list": "allpages",
            "apprefix": page + "/",
            "apnamespace": "0",
            "aplimit": "500",
        })
        return [
            (item["title"], item["title"].rsplit("/", 1)[-1])
            for item in data.get("query", {}).get("allpages", [])
        ]

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self._api({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": "10",
            "srnamespace": "0",
        })
        return [
            SearchResult(
                title=item["title"],
                url=self._page_url(item["title"]),
                info=_HTML_RE.sub("", item.get("snippet", "")).strip(),
            )
            for item in data.get("query", {}).get("search", [])
        ]

    def _is_browseable(self, title: str) -> bool:
        # Subpages ("Work/Chapter 1") are chapters, not works.
        return "/" not in title

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        cont: Optional[str] = None
        # ponytail: restarts pagination per call (offset not server-side); fine
        # for the small limits the harvest tooling uses.
        while len(results) < offset + limit:
            params = {
                "action": "query",
                "list": "allpages",
                "apnamespace": "0",
                "aplimit": "50",
            }
            if cont:
                params["apcontinue"] = cont
            data = self._api(params)
            for item in data.get("query", {}).get("allpages", []):
                if self._is_browseable(item["title"]):
                    results.append(SearchResult(
                        title=item["title"], url=self._page_url(item["title"]),
                    ))
            cont = data.get("continue", {}).get("apcontinue")
            if not cont:
                break
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        self.language = self._detect_language() or self.language

        page = self._title_from_url(self.novel_url)
        if not page:
            raise LNException(f"Cannot read a page title from {self.novel_url}")

        parsed = self._api({
            "action": "parse",
            "page": page,
            "prop": "text|wikitext|categories|displaytitle",
            "redirects": "1",
        }).get("parse")
        if not parsed:
            raise LNException(f"MediaWiki page not found: {page}")

        page = parsed.get("title") or page
        html = parsed.get("text", {}).get("*", "")
        wikitext = parsed.get("wikitext", {}).get("*", "")
        params = self._parse_params(wikitext)

        self.novel_title = self._field(params, "title") or page

        author = self._field(params, "author")
        if not author and " / " in page:
            author = page.split(" / ")[-1]  # "Work / Author" naming
        annotation = re.search(
            r"(?:अनुवाद|అనువాదం|translator)\s*[:：]\s*([^)）\n|}]+)", author + "\n" + wikitext
        )
        if annotation:
            translator = self._field(params, "translator")
            extra = annotation.group(1).strip()
            self.translators = [x.strip() for x in (translator + ", " + extra).split(",") if x.strip()]
            author = re.split(r"[（(]", author)[0].strip()
        else:
            translator = self._field(params, "translator")
            if translator:
                self.translators = [x.strip() for x in translator.split(",") if x.strip()]
        self.novel_author = author

        self.original_publisher = self._field(params, "publisher") or None
        self.novel_synopsis = self._field(params, "notes")
        self.status = NovelStatus.completed

        categories = [
            (c.get("*") or "").replace("_", " ")
            for c in parsed.get("categories", [])
        ]
        self.genres = [
            name for name in categories
            if name and "wikisource" not in name.lower() and "template" not in name.lower()
        ]
        self.novel_tags = list(self.genres)

        cover = self._field(params, "image")
        if cover:
            self.novel_cover = self._file_url(cover)

        try:
            self.alternative_titles = self._redirects(page)
        except Exception as error:  # redirects are a nicety, never fatal
            logger.debug("Could not read redirects for %s: %s", page, error)

        soup = self.make_soup(html) if html else self.make_soup("<div></div>")
        entries = self._chapter_entries(page, soup) or self._subpages(page)

        volume = Volume(id=1, title="Volume 1")
        self.volumes.append(volume)
        if entries:
            for title, label in entries:
                self.chapters.append(Chapter(
                    id=len(self.chapters) + 1,
                    title=label or title,
                    url=self._page_url(title),
                    volume=volume.id,
                    volume_title=volume.title,
                ))
        else:
            self.chapters.append(Chapter(
                id=1,
                title=self.novel_title,
                url=self._page_url(page),
                volume=volume.id,
                volume_title=volume.title,
            ))
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def _file_url(self, name: str) -> Optional[str]:
        data = self._api({
            "action": "query",
            "titles": "File:" + name,
            "prop": "imageinfo",
            "iiprop": "url",
        })
        for page in data.get("query", {}).get("pages", {}).values():
            info = page.get("imageinfo")
            if info:
                return info[0].get("url")
        return None

    def _redirects(self, page: str) -> List[str]:
        data = self._api({
            "action": "query",
            "titles": page,
            "prop": "redirects",
            "rdlimit": "20",
        })
        titles: List[str] = []
        for entry in data.get("query", {}).get("pages", {}).values():
            for redirect in entry.get("redirects", []):
                title = redirect.get("title")
                if title and title not in titles:
                    titles.append(title)
        return titles

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        title = self._title_from_url(chapter.url)
        parsed = self._api({
            "action": "parse",
            "page": title,
            "prop": "text",
            "redirects": "1",
        }).get("parse")
        if not parsed:
            logger.warning("MediaWiki page not found: %s", title)
            return ""

        soup = self.make_soup(parsed.get("text", {}).get("*", ""))
        body = soup.select_one(".mw-parser-output") or soup
        for selector in self.body_bad_css:
            for tag in body.select(selector):
                tag.decompose()
        return self.cleaner.extract_contents(body)


if __name__ == "__main__":
    # Run: python sources/multi/wikisource.py
    sample = "{{header\n| title = Test\n| author = [[Someone]] (अनुवाद: Other)\n| notes =}}\n"
    parsed = WikisourceCrawler._parse_params(sample)
    assert parsed["title"] == "Test", parsed
    assert parsed["author"] == "[[Someone]] (अनुवाद: Other)", parsed
    assert WikisourceCrawler._plain(parsed["author"]) == "Someone (अनुवाद: Other)"
    print("self-check OK")

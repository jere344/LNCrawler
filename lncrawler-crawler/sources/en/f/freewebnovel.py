# -*- coding: utf-8 -*-
import unicodedata
import re

from bs4 import BeautifulSoup, Tag

from lncrawl.models import Chapter, NovelStatus, SearchResult
from lncrawl.templates.soup.chapter_only import ChapterOnlySoupTemplate
from lncrawl.templates.soup.searchable import SearchableSoupTemplate

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}

# The novel page lists the first 40 chapters only; the site's own paged endpoint
# (behind its "C.41 - C.80" selector) serves up to 200 per request.
_CHAPTERS_PER_REQUEST = 200


class FreeWebNovelCrawler(SearchableSoupTemplate, ChapterOnlySoupTemplate):
    base_url = [
        "https://freewebnovel.com/",
        "https://bednovel.com/",
        "https://innread.com/",
        "https://innnovel.com/",
        "https://libread.com/",
        "https://libread.org/",
    ]

    def initialize(self) -> None:
        self.init_executor()
        self.cleaner.bad_tags.update(["h4", "sub"])
        self.cleaner.bad_tag_text_pairs.update(
            {
                "p": [
                    r"freewebnovel\.com",
                    r"innread\.com",
                    r"bednovel\.com",
                    r"Updates by Freewebnovel\. com",
                    r"” Search Freewebnovel\.com\. on google”\.",
                    r"\/ Please Keep reading on MYFreeWebNovel\.C0M",
                    r"please keep reading on Freewebnovel\(dot\)C0M",
                    r"Continue\_reading on Freewebnovel\.com",
                    r"Continue \-reading on Freewebnovel\.com",
                    r"\/ Please Keep reading 0n FreewebNOVEL\.C0M",
                    r"\[ Follow current novels on Freewebnovel\.com \]",
                    r"‘Freewebnovel\.com\*’",
                    r"‘Search Freewebnovel\.com\, on google’",
                    r"‘ Search Freewebnovel\.com\(\) ‘",
                    r"“Freewebnovel\.com \.”",
                    r"“Please reading on Freewebnovel\.com\.”",
                    r"“Search Freewebnovel\.com\. on google”",
                    r"“Read more on Freewebnovel\.com\. org”",
                    r"Thank you for reading on FreeWebNovel\.me",
                    r"Please reading \-on Freewebnovel\.com",
                    r"”Search \(Freewebnovel\.com\(\) on google\”\?",
                    r"“Please reading on Freewebnovel\.com \:”",
                    r"”Please reading on Freewebnovel\.com\.”\?",
                    r"“Please reading on Freewebnovel\.com\&gt\; ”"
                ],
                "i": [
                    r"\[ Follow current novels on Freewebnovel\.com \]"
                ]
            }
        )

    def select_search_items(self, query: str):
        data = {"keyword": query}
        soup = self.post_soup(f"{self.home_url}search/", data=data)
        yield from soup.select(".col-content .con .txt h3 a")

    def parse_search_item(self, tag: Tag) -> SearchResult:
        return SearchResult(
            title=tag.text.strip(),
            url=self.absolute_url(tag["href"]),
            cover=self.image_url(tag.find_parent(class_="con").select_one(".pic img")),
        )

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = f"{self.home_url}sort/most-popular"
            if page > 1:
                url += f"/{page}"
            soup = self.get_soup(url)
            items = soup.select(".col-content .con .txt h3 a[href]")
            if not items:
                break
            for a in items:
                results.append(
                    SearchResult(
                        title=a.text.strip(),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 200:
                break
        return results[offset : offset + limit]

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".m-desc h1.tit")
        assert isinstance(tag, Tag)
        return tag.text.strip()

    def parse_cover(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".m-imgtxt img")
        assert isinstance(tag, Tag)
        if tag.has_attr("data-src"):
            return self.absolute_url(tag["data-src"])
        if tag.has_attr("src"):
            return self.absolute_url(tag["src"])

    def parse_authors(self, soup: BeautifulSoup):
        for a in soup.select(".m-imgtxt .txt a[href*='/author/']"):
            yield a.text.strip()

    def parse_genres(self, soup: BeautifulSoup):
        for a in soup.select(".m-imgtxt .txt a[href*='/genre/']"):
            yield a.text.strip()

    def parse_summary(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".m-desc .inner")
        if not isinstance(tag, Tag):
            return ""
        lines = []
        for p in tag.select("p"):
            text = p.get_text(" ", strip=True)
            if not text:
                continue
            # A paragraph starting with a dash continues the sentence before it.
            if lines and text.startswith("–"):
                lines[-1] += " " + text
            else:
                lines.append(text)
        return "\n".join(lines)

    @staticmethod
    def _info_value(soup: BeautifulSoup, label: str) -> str:
        for item in soup.select(".m-imgtxt .txt .item"):
            icon = item.select_one(".glyphicon[title]")
            if icon and icon.get("title") == label:
                value = item.select_one(".right")
                return value.get_text(" ", strip=True) if isinstance(value, Tag) else ""
        return ""

    def read_novel_info(self) -> None:
        super().read_novel_info()
        soup = self.last_soup
        if not isinstance(soup, BeautifulSoup):
            return
        alt_titles = self._info_value(soup, "Alternative names")
        if alt_titles:
            self.alternative_titles = [
                t.strip() for t in re.split(r"\s*[,;]\s*", alt_titles) if t.strip()
            ]
        status = self._info_value(soup, "Status")
        self.status = _STATUSES.get(status.lower(), NovelStatus.unknown)

    @staticmethod
    def _parse_total_pages(value) -> int:
        try:
            return max(1, int(value or 1))
        except (TypeError, ValueError):
            return 1

    def _more_chapter_tags(self) -> list:
        tags = []
        seen = set()
        page, total_pages = 1, 1
        while page <= total_pages and page <= 100:
            try:
                data = self.get_json(
                    f"{self.novel_url}?ajax=chapters&page={page}&pageSize={_CHAPTERS_PER_REQUEST}",
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
            except Exception as e:
                # A partial chapter list must not be saved as the complete one.
                raise RuntimeError(f"Chapter list page {page} failed: {e}") from e
            total_pages = self._parse_total_pages(data.get("totalPage"))
            added = 0
            for a in self.make_soup(data.get("html") or "").select("li > a[href]"):
                if a["href"] in seen:
                    continue
                seen.add(a["href"])
                tags.append(a)
                added += 1
            if added == 0:
                break
            page += 1
        return tags

    def select_chapter_tags(self, soup: BeautifulSoup):
        listed = [a for chapter in soup.select("#idData") for a in chapter.select("li > a")]
        seen = set()
        for tag in listed + self._more_chapter_tags():
            if tag["href"] in seen:
                continue
            seen.add(tag["href"])
            yield tag

    def parse_chapter_item(self, tag: Tag, id: int) -> Chapter:
        return Chapter(
            id=id,
            url=self.absolute_url(tag["href"]),
            title=tag.text.strip(),
        )

    def normalize_text(self, text: str) -> str:
        return unicodedata.normalize("NFKC", text)

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        body_tag = soup.select_one(".m-read .txt")
        # style element on page that hides usually last paragraph which contains randomised self-promo text
        has_promo = soup.find("style", text=re.compile("p:nth-last-child\\(\\d\\)"))
        if body_tag:
            normalized_body = self.normalize_text(str(body_tag))
            normalized_soup = BeautifulSoup(normalized_body, "html.parser")
            if has_promo:
                # get index out of css selector and manually remove it via decompose
                idx = int(re.match(re.compile(".+p:nth-last-child\\((\\d)\\).+"), has_promo.text)[1])
                random_self_promo = normalized_soup.find_all("p")[-idx]
                if isinstance(random_self_promo, Tag):
                    random_self_promo.decompose()
            return normalized_soup
        return body_tag

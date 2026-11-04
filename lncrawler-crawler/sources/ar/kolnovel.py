import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume
from lncrawl.templates.mangastream import MangaStreamTemplate

logger = logging.getLogger(__name__)

# The chapter table is paginated, 24 rows per page, oldest first. Pages past the
# last one repeat the last page, so the walk stops on a page with no new rows.
CHAPTER_PAGE_LIMIT = 400

STATUSES = {
    "مستمرة": NovelStatus.ongoing,
    "مكتملة": NovelStatus.completed,
    "متوقفة": NovelStatus.hiatus,
    "معلقة": NovelStatus.hiatus,
}

# Volume label of the rows that are not inside a volume.
NO_VOLUME_LABELS = {"", "الفصول"}

# Title slot that only repeats the chapter number ("الفصل 6", "631").
NUMBER_LABEL = re.compile(r"(?:الفصل|فصل)?\s*\d+")

# Site and support lines the aggregator or translator adds after the story.
WATERMARK_TEXTS = (
    "تابع موقع ملوك الروايات",
    "هذا الفصل تم دعمه",
    "موقع الدعم",
    "لدعمنا على",
    "عن طريق رابط الدعم",
    "paypal.me",
    "getsurlpro.com",
)
WATERMARK_MAX_LENGTH = 300
# Empty paragraphs and separator lines ("****", "____").
SEPARATOR = re.compile(r"^[\s*_\-=~]*$")


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def _is_name(text: str) -> bool:
    """A real chapter name: has letters and is not just a chapter number."""
    return any(c.isalpha() for c in text) and not NUMBER_LABEL.fullmatch(text)


def _strip_watermarks(html: str, title: str) -> str:
    """Drop the support block at the end of a body and a heading repeating the title.

    Only a run of short support paragraphs at the very end is removed; the first
    paragraph is dropped only when it is the chapter number followed by its title.
    """
    soup = BeautifulSoup(html, "html.parser")
    paras = soup.find_all("p")
    texts = [_clean(p.get_text(" ", strip=True)) for p in paras]

    cut = None
    for i in range(len(paras) - 1, -1, -1):
        text = texts[i]
        if SEPARATOR.match(text):
            continue
        if len(text) < WATERMARK_MAX_LENGTH and any(w in text for w in WATERMARK_TEXTS):
            cut = i
            continue
        break
    if cut is not None:
        while cut > 0 and SEPARATOR.match(texts[cut - 1]):
            cut -= 1
    drop = set(range(cut, len(paras))) if cut is not None else set()

    if title:
        heading = re.compile(rf"\d+\s*[-–—:.]?\s*{re.escape(title)}")
        first = next((i for i, text in enumerate(texts) if text), None)
        if first is not None and heading.fullmatch(texts[first]):
            drop.add(first)

    return "".join(str(p) for i, p in enumerate(paras) if i not in drop)


def _unique(values) -> List[str]:
    return list(dict.fromkeys(v for v in values if v))


class Kolnovel(MangaStreamTemplate):
    version = 2  # v2: support/watermark lines and the chapter heading removed from bodies
    has_mtl = False
    has_manga = False
    base_url = ["https://kolnovel.com/"]

    def select_search_items(self, query: str):
        params = dict(s=query)
        soup = self.get_soup(f"{self.home_url}?{urlencode(params)}")
        yield from soup.select("article.kol-search__item")

    def select_search_items_in_browser(self, query: str):
        params = dict(s=query)
        self.visit(f"{self.home_url}?{urlencode(params)}")
        yield from self.browser.soup.select("article.kol-search__item")

    def parse_search_item(self, tag: Tag) -> SearchResult:
        a = tag.select_one("h3 a")
        meta = tag.select_one(".kol-search__meta")
        info = " · ".join(
            span.get_text(" ", strip=True) for span in meta.find_all("span")
        ) if meta else ""
        return SearchResult(
            title=a.get_text(strip=True),
            url=self.absolute_url(a["href"]),
            info=info,
            cover=self.image_url(tag.select_one("img")),
        )

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = "https://kolnovel.com/series/?order=popular"
            if page > 1:
                url = f"https://kolnovel.com/series/?order=popular&page={page}"
            soup = self.get_soup(url)
            items = soup.select("article.kol-series-archive__item")
            if not items:
                break
            for item in items:
                a = item.select_one("h3 a")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def initialize(self) -> None:
        super().initialize()
        # Listing pages and chapter bodies are spaced out: bursts get the IP flagged.
        self.init_executor(ratelimit=1)

    def read_novel_info(self) -> None:
        # Static HTML only: the series page carries the metadata, the chapter
        # table is walked through `chapter_page` listing URLs. No browser fallback.
        soup = self.get_novel_soup()

        self.is_rtl = True
        self.novel_title = self.parse_title(soup)
        self.novel_cover = self.parse_cover(soup)
        self.novel_author = ", ".join(self.parse_authors(soup))
        self.novel_tags = ", ".join(self.parse_genres(soup))
        self.novel_synopsis = self.parse_summary(soup)
        self.alternative_titles = self.parse_alternative_titles(soup)
        self.status = self.parse_status(soup)

        rows = self.fetch_chapter_rows()
        volumes, chapters = self.parse_chapter_rows(rows)
        self.volumes.extend(volumes)
        self.chapters.extend(chapters)
        if not chapters:
            logger.warning("No chapters found for %s", self.novel_url)

    def parse_title(self, soup: BeautifulSoup) -> str:
        title = soup.select_one("h1.kol-series-editorial__title")
        if not title:
            raise LNException("No novel title")
        return _clean(title.get_text(" ", strip=True))

    def parse_cover(self, soup: BeautifulSoup) -> Optional[str]:
        return self.image_url(soup.select_one(".kol-series-editorial__cover img"))

    def parse_authors(self, soup: BeautifulSoup) -> List[str]:
        return _unique(
            _clean(a.get_text(" ", strip=True))
            for a in soup.select(".kol-series-editorial__byline a[href*='/writer/']")
        )

    def parse_genres(self, soup: BeautifulSoup) -> List[str]:
        # The "النوع" facts (web novel, korean...) are type labels, not genres.
        return _unique(
            _clean(a.get_text(" ", strip=True))
            for a in soup.select(
                ".kol-series-editorial__genres a[href*='/genre/']"
            )
        )

    def parse_summary(self, soup: BeautifulSoup) -> str:
        # The synopsis preview is complete; the "read full" button is outside it.
        prose = soup.select_one(
            ".kol-series-editorial__synopsis .kol-series-editorial__prose"
        )
        return self.cleaner.extract_contents(prose) if prose else ""

    def parse_alternative_titles(self, soup: BeautifulSoup) -> List[str]:
        alt = soup.select_one(".kol-series-editorial__alt-title")
        if not alt:
            return []
        return _unique(
            _clean(part) for part in alt.get_text(" ", strip=True).split(",")
        )

    def parse_status(self, soup: BeautifulSoup) -> NovelStatus:
        value = soup.select_one(".kol-series-editorial__quick-fact--status dd")
        label = _clean(value.get_text(" ", strip=True)) if value else ""
        return STATUSES.get(label, NovelStatus.unknown)

    def fetch_chapter_rows(self) -> List[Tag]:
        """Every chapter row of the table, oldest first, without duplicates."""
        base = self.novel_url.split("?")[0].rstrip("/") + "/"
        rows: List[Tag] = []
        seen = set()
        for page in range(1, CHAPTER_PAGE_LIMIT + 1):
            soup = self.get_soup(
                f"{base}?chapter_order=oldest&chapter_page={page}"
            )
            new_rows = 0
            for li in soup.select("li.kol-series-chapter"):
                link = li.select_one("a[href]")
                if not link:
                    continue
                url = self.absolute_url(link["href"])
                if url in seen:
                    continue
                seen.add(url)
                rows.append(li)
                new_rows += 1
            if not new_rows:
                break
        else:
            logger.warning(
                "Chapter list stopped at page cap (%d) for %s",
                CHAPTER_PAGE_LIMIT,
                self.novel_url,
            )
        return rows

    def parse_chapter_rows(self, rows: List[Tag]) -> Tuple[List[Volume], List[Chapter]]:
        volumes: List[Volume] = []
        chapters: List[Chapter] = []
        current_label = None
        for li in rows:
            label = self.parse_volume_label(li)
            if label != current_label:
                current_label = label
                if label is not None:
                    volumes.append(Volume(id=len(volumes) + 1, title=label))
            link = li.select_one("a[href]")
            chapters.append(
                Chapter(
                    id=len(chapters) + 1,
                    url=self.absolute_url(link["href"]),
                    title=self.parse_chapter_title(li),
                    volume=volumes[-1].id if label is not None else None,
                )
            )
        return volumes, chapters

    def parse_volume_label(self, li: Tag) -> Optional[str]:
        tag = li.select_one(".kol-series-chapter__volume")
        label = _clean(tag.get_text(" ", strip=True)) if tag else ""
        return None if label in NO_VOLUME_LABELS else label

    def parse_chapter_title(self, li: Tag) -> str:
        copy = li.select_one("[data-kol-chapter-title]")
        title = _clean(copy.get_text(" ", strip=True)) if copy else ""
        if _is_name(title):
            return title
        # No name in the title slot ("—", "631"): a special chapter can carry its
        # name in the number slot instead ("الرحمة والموت").
        number = li.select_one(".kol-series-chapter__number")
        label = _clean(number.get("data-kol-chapter-number")) if number else ""
        return label if _is_name(label) else ""

    def download_chapter_body_in_soup(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = self.parse_chapter_body(self.select_chapter_body(soup))
        return _strip_watermarks(body, chapter.title)

    def download_chapter_body_in_browser(self, chapter: Chapter) -> str:
        body = super().download_chapter_body_in_browser(chapter)
        return _strip_watermarks(body, chapter.title)

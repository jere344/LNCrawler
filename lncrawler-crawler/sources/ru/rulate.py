# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

# A paragraph holding only the site's own chapter URL.
_SITE_URL_LINE_RE = re.compile(r"\s*(https?://)?(tl\.)?rulate\.ru/\S*\s*")


class RulateCrawler(Crawler):
    base_url = [
        "https://tl.rulate.ru/",
    ]

    language = "ru"
    # v2: the site's own URL line is no longer kept at the end of bodies.
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self):
        self.cleaner.bad_css.update([".thumbnail"])

    def login(self, email: str, password: str):
        login_url = "https://tl.rulate.ru/"
        login_data = {
            'login[login]': email,
            'login[pass]': password
        }
        self.post_response(
            login_url,
            data=login_data
        )

    def search_novel(self, query):
        soup = self.get_soup(f"{self.base_url[0]}/search?t={quote_plus(query)}")
        return [
            {
                "title": a.text.strip(),
                "url": self.absolute_url(a["href"]),
                "cover": self.image_url((a.find_parent("li") or a).select_one(".th img")),
            }
            for a in soup.select(".search-results p.book-tooltip a[href^='/book/']")
            if a.text.strip()
        ][:10]

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}site/top?Book_page={page}")
            items = soup.select(".search-results p.book-tooltip a[href^='/book/']")
            if not items:
                break
            for a in items:
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 100:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        chapters = soup.select_one("#Chapters")
        if not chapters:
            input_path = soup.find("input", {"name": "path", "type": "hidden"})
            if input_path:
                soup = self.submit_form_for_soup(
                    url="https://tl.rulate.ru/mature",
                    data={
                        "path": input_path["value"],
                        "ok": "Да",
                    },
                )
                chapters = soup.select_one("#Chapters")

        possible_title = soup.find("h1")
        if possible_title:
            self.novel_title = possible_title.text.split("/")[-1].strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_images = soup.find("div", {"class": "span2"})
        if possible_images:
            possible_image = possible_images.find("img")
            if possible_image:
                self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        possible_author = soup.find("strong", text="Автор:")
        if possible_author:
            possible_author = possible_author.parent.find("a")
            if possible_author:
                self.novel_author = possible_author.text
        logger.info("Novel author: %s", self.novel_author)

        # The full text sits in book-description-full; the summary above it is
        # a truncated copy with the "read more" toggle.
        possible_synopsis = soup.select_one("#Info div.book-description-full") or soup.select_one(
            "#Info > div:nth-child(3)"
        )
        if possible_synopsis:
            # The team's footer (other translations, fanfic source link) is not blurb.
            for marker in possible_synopsis.find_all("p"):
                if re.match(
                    r"(ДРУГИЕ НАШИ ПЕРЕВОДЫ|Фанфик по произведению)",
                    marker.get_text(" ", strip=True),
                    re.IGNORECASE,
                ):
                    previous = marker.find_previous_sibling()
                    if previous is not None and re.fullmatch(r"[_\s]+", previous.get_text()):
                        previous.decompose()
                    for sibling in list(marker.find_next_siblings()):
                        sibling.decompose()
                    marker.decompose()
                    break
            self.novel_synopsis = self.cleaner.extract_contents(possible_synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        release = soup.find("strong", text="Выпуск:")
        if release and release.parent:
            release_text = release.parent.get_text(" ", strip=True).lower()
            if "продолж" in release_text:
                self.status = NovelStatus.ongoing
            elif "заверш" in release_text or "закончен" in release_text:
                self.status = NovelStatus.completed
            elif "приостанов" in release_text or "заморож" in release_text:
                self.status = NovelStatus.hiatus

        team = soup.find("strong", text="Группа:")
        if team and team.parent:
            self.translators = [
                name.strip()
                for a in team.parent.find_all("a")
                for name in a.get_text(" ", strip=True).split("|")
                if name.strip()
            ]

        for tag in soup.find_all("a", {"class": "badge"}):
            self.novel_tags.append(tag.text)
        logger.info("Novel tags: %s", self.novel_tags)

        # The chapter table is paged (100 rows per ?Chapter_page=N).
        # Only classed rows are chapters or volume headings; the header is not.
        rows = list(chapters.find_all("tr")) if chapters else []
        previous_first = next(
            (r.get_text(" ", strip=True) for r in rows if r.has_attr("class")), None
        )
        page = 2
        while chapters and page <= 300:
            page_table = self.get_soup(
                f"{self.novel_url.split('?')[0]}?Chapter_page={page}"
            ).select_one("#Chapters")
            page_rows = [
                r
                for r in (page_table.find_all("tr") if page_table else [])
                if r.has_attr("class")
            ]
            # Stop past the last page, or when the site repeats an earlier one.
            if not page_rows:
                break
            first = page_rows[0].get_text(" ", strip=True)
            if first == previous_first:
                break
            previous_first = first
            rows.extend(page_rows)
            page += 1

        chap_id = 0
        vol_id = 1
        self.volumes.append({"id": vol_id})
        for row in rows:
            if not row.has_attr("class"):
                continue

            if row["class"][0] == "volume_helper":
                if chap_id:
                    vol_id = vol_id + 1
                else:
                    self.volumes.pop()

                self.volumes.append({"id": vol_id, "title": row.text})
                continue

            if row.find("span", {"class": "disabled"}):
                continue

            possible_chapter_ref = row.find("a", {"class": False, "href": True})
            if possible_chapter_ref:
                chap_id = chap_id + 1
                self.chapters.append(
                    {
                        "id": chap_id,
                        "volume": vol_id,
                        "url": self.absolute_url(possible_chapter_ref["href"]),
                        "title": possible_chapter_ref.text,
                    }
                )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".content-text")
        # The site appends a paragraph with the chapter's own URL.
        for p in contents.find_all("p"):
            if _SITE_URL_LINE_RE.fullmatch(p.get_text()):
                p.decompose()
        self.cleaner.clean_contents(contents)
        return str(contents)

    def _migrate_v2(self, body, chapter):
        soup = body_migrations.parse(body)
        for p in soup.find_all("p"):
            if _SITE_URL_LINE_RE.fullmatch(p.get_text()):
                p.decompose()
        return str(soup)

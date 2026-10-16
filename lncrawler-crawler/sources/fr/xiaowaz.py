# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException

logger = logging.getLogger(__name__)


class XiaowazCrawler(Crawler):
    base_url = ["https://xiaowaz.fr/"]

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            [".abh_box_business", ".footnote_container_prepare"]
        )

    def search_novel(self, query):
        data = self.get_json(
            f"{self.base_url[0]}/wp-json/wp/v2/pages"
            f"?search={quote_plus(query)}&per_page=20&_fields=title,link"
        )
        prefixes = ("/series-en-cours/", "/series-abandonnees/", "/oeuvres-originales/")
        return [
            {"title": item["title"]["rendered"], "url": item["link"]}
            for item in data
            if any(p in item["link"] for p in prefixes)
        ]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title_tag = soup.select_one("h1.card_title")
        if not isinstance(title_tag, Tag):
            raise LNException("No title found")

        self.novel_title = title_tag.text.strip()

        entry = soup.select_one(".entry-content")

        image_tag = soup.select_one(".entry-content img")
        if isinstance(image_tag, Tag):
            self.novel_cover = self.absolute_url(image_tag["src"])

        logger.info("Novel cover: %s", self.novel_cover)

        if isinstance(entry, Tag):
            for heading in entry.select("h4, h5"):
                label = heading.get_text(strip=True).rstrip(":").strip().lower()
                if label == "auteur":
                    value = heading.find_next_sibling()
                    if value:
                        self.novel_author = value.get_text(strip=True)
                elif label == "genres":
                    value = heading.find_next_sibling()
                    if value:
                        self.genres = [
                            g.strip()
                            for g in value.get_text(strip=True).split(",")
                            if g.strip()
                        ]
                elif label == "synopsis":
                    value = heading.find_next_sibling()
                    if value:
                        self.novel_synopsis = value.get_text(" ", strip=True)

            for strong in entry.select("strong"):
                text = strong.get_text(strip=True)
                parent = strong.parent
                if text.startswith("Auteur"):
                    author = parent.get_text(" ", strip=True).split(":", 1)[-1].strip()
                    if author:
                        self.novel_author = author
                elif text.startswith("Nom utilisé"):
                    nom = parent.get_text(" ", strip=True).split(":", 1)[-1].strip()
                    if nom:
                        self.alternative_titles = [re.sub(r"\s+", " ", nom)]

            first_p = entry.find("p")
            if first_p:
                self.alternative_titles = self.alternative_titles or []
                raw = first_p.get_text(" ", strip=True)
                for part in re.split(r"\s{2,}", raw):
                    part = re.sub(r"\s+", " ", part).strip()
                    if part and part not in self.alternative_titles:
                        self.alternative_titles.append(part)

        logger.info("Novel author: %s", self.novel_author)
        logger.info("Novel genres: %s", self.genres)

        for a in soup.select(".entry-content a[href*='/articles/']"):
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".entry-content")
        self.cleaner.clean_contents(contents)

        return str(contents)

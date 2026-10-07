# -*- coding: utf-8 -*-
import csv
import io
import logging
import re
import zipfile
from typing import List

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

INDEX_URL = "https://www.aozora.gr.jp/index_pages/list_person_all_extended_utf8.zip"

# Parsed work index, shared across crawler instances in the same process.
_WORK_INDEX = None


class AozoraCrawler(Crawler):
    """Aozora Bunko: public-domain Japanese literature.

    One work = one novel; each XHTML file of the work is a chapter (long works
    are split across a handful of files, short ones are a single file).
    """

    base_url = "https://www.aozora.gr.jp/"
    language = "ja"

    def search_novel(self, query):
        query = (query or "").strip().lower()
        if not query:
            return []
        results: List[SearchResult] = []
        seen = set()
        for row in self._load_index():
            if query not in row["title"].lower() and query not in row["reading"].lower():
                continue
            if row["id"] in seen or not row["card"]:
                continue
            seen.add(row["id"])
            results.append(
                SearchResult(
                    title=row["title"],
                    url=row["card"],
                    info=", ".join(row["authors"]),
                )
            )
            if len(results) >= 20:
                break
        return results

    def browse_novels(self, offset=0, limit=50):
        results: List[SearchResult] = []
        seen = set()
        for row in self._load_index():
            if row["id"] in seen or not row["card"]:
                continue
            seen.add(row["id"])
            results.append(
                SearchResult(
                    title=row["title"],
                    url=row["card"],
                    info=", ".join(row["authors"]),
                )
            )
        return results[offset : offset + limit]

    def _load_index(self):
        """Parsed official CSV index, downloaded once per process."""
        global _WORK_INDEX
        if _WORK_INDEX is not None:
            return _WORK_INDEX

        response = self.get_response(INDEX_URL)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            data = archive.read(archive.namelist()[0]).decode("utf-8-sig")

        works = {}
        for row in csv.DictReader(io.StringIO(data)):
            work_id = (row.get("作品ID") or "").strip()
            if not work_id:
                continue
            entry = works.get(work_id)
            if entry is None:
                works[work_id] = entry = {
                    "id": work_id,
                    "title": (row.get("作品名") or "").strip(),
                    "reading": (row.get("作品名読み") or "").strip(),
                    "card": (row.get("図書カードURL") or "").strip(),
                    "authors": [],
                }
            name = "{0} {1}".format(
                (row.get("姓") or "").strip(), (row.get("名") or "").strip()
            ).strip()
            if name and name not in entry["authors"]:
                entry["authors"].append(name)

        _WORK_INDEX = list(works.values())
        logger.info("Aozora index: %d works", len(_WORK_INDEX))
        return _WORK_INDEX

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title_table = soup.select_one('table[summary="タイトルデータ"]')
        self.novel_title = self._cell(title_table, "作品名")
        self.novel_author = self._cell(title_table, "著者名")
        reading = self._cell(title_table, "作品名読み")
        if reading:
            self.alternative_titles = [reading]

        work_table = soup.select_one('table[summary="作品データ"]')
        self.novel_synopsis = self._cell(work_table, "作品について")
        classification = self._cell(work_table, "分類")
        self.genres = [classification] if classification else []
        notation = self._cell(work_table, "文字遣い種別")
        self.tags = [notation] if notation else []
        self.status = NovelStatus.completed

        base_table = soup.select_one('table[summary="底本データ"]')
        self.original_publisher = self._cell(base_table, "出版社") or None

        editors = []
        for table in soup.select('table[summary="工作員データ"]'):
            for td in table.select("td.header"):
                if td.get_text(strip=True).rstrip("：:") not in ("入力", "校正"):
                    continue
                sibling = td.find_next_sibling("td")
                if isinstance(sibling, Tag):
                    value = sibling.get_text(" ", strip=True)
                    if value and value not in editors:
                        editors.append(value)
        self.editors = editors

        translators = []
        for table in soup.select('table[summary="作家データ"]'):
            role = self._cell(table, "分類")
            if role and "翻訳" in role:
                name = self._cell(table, "作家名")
                if name and name not in translators:
                    translators.append(name)
        self.translators = translators

        self.volumes.append({"id": 0})
        seen = set()
        for anchor in soup.select('table.download a[href$=".html"]'):
            href = anchor.get("href") or ""
            # Only local transcriptions; some cards also list external mirrors.
            if not href or href.startswith("http") or "/files/" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "volume": 0,
                    "title": self.novel_title,
                    "url": self.absolute_url(href),
                }
            )
        if len(self.chapters) > 1:
            for index, chapter in enumerate(self.chapters, 1):
                chapter["title"] = "{0} ({1})".format(self.novel_title, index)

    @staticmethod
    def _cell(table, label):
        if not isinstance(table, Tag):
            return ""
        for td in table.select("td.header"):
            if label in td.get_text(strip=True):
                sibling = td.find_next_sibling("td")
                if isinstance(sibling, Tag):
                    return sibling.get_text(" ", strip=True)
        return ""

    def download_chapter_body(self, chapter):
        response = self.get_response(chapter["url"])
        raw = response.content
        encoding = "shift_jis"
        match = re.search(rb"""charset=["']?([A-Za-z0-9_-]+)""", raw[:3000])
        if match:
            encoding = match.group(1).decode("ascii", "ignore").strip().lower()
            if encoding in ("shift-jis", "x-sjis", "sjis"):
                encoding = "shift_jis"

        soup = self.make_soup(raw, encoding)
        body = soup.select_one(".main_text")
        if not isinstance(body, Tag):
            logger.warning("No main_text in %s", chapter["url"])
            return ""

        # Drop ruby readings so the text keeps only the base characters.
        for tag in body.select("rp, rt"):
            tag.decompose()
        for tag in body.select("ruby, rb"):
            tag.unwrap()

        return self.cleaner.extract_contents(body)

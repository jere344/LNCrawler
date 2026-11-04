# -*- coding: utf-8 -*-
"""Gadya Kosh (https://www.gadyakosh.org/gk/), a Hindi public-domain prose wiki.

A MediaWiki installed under ``/gk/`` (API at ``/gk/api.php``, no bot challenge).
Works are named ``Title / Author`` and have no subpages, so each work is a
single chapter. All the MediaWiki logic lives in the generic crawler in
``sources/multi/wikisource.py``; this file only changes the site layout.

``sources/`` is not a package, so the base module is loaded by path.
"""

import importlib.util
import os

from lncrawl.models import Chapter

_BASE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "multi", "wikisource.py"
)
_spec = importlib.util.spec_from_file_location("lncrawl_wikisource_base", _BASE_PATH)
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)


class GadyaKoshCrawler(_base.WikisourceCrawler):
    base_url = ["https://www.gadyakosh.org/gk/"]
    language = "hi"
    version = 2

    api_path = "api.php"
    article_path = ""

    # Page chrome rendered inside the article: the language and author/collection
    # breadcrumb, and the heading that repeats the title with the publication date.
    body_bad_css = _base.WikisourceCrawler.body_bad_css + [
        "#gkrachna",
        "#gk-article-cust-heading-div",
    ]
    # Type label set by the {{GKCatLekh}} template ("article"), not a genre.
    type_tags = {"लेख"}

    def _site(self) -> str:
        # Fixed root: prepare_crawler() overwrites home_url with the bare host,
        # so the "/gk/" prefix cannot be taken from self.origin.
        return "https://www.gadyakosh.org/gk/"

    def _is_browseable(self, title: str) -> bool:
        # Every work is named "Title / Author", so the base "/" rule would
        # drop the whole catalogue.
        return True

    def read_novel_info(self) -> None:
        super().read_novel_info()
        # Keep only the title part of "Title / Author".
        self.novel_title = self.novel_title.split(" / ")[0].strip() or self.novel_title
        for chapter in self.chapters:
            chapter.title = chapter.title.split(" / ")[0].strip() or chapter.title
        self.genres = [g for g in self.genres if g not in self.type_tags]
        self.novel_tags = list(self.genres)

    def download_chapter_body(self, chapter: Chapter) -> str:
        body = super().download_chapter_body(chapter)
        # A stray "<metadesc>" element keeps its lead text in the cleaned body, and
        # the same text follows in the next paragraph. The cleaner keeps it as a
        # tag (not text), so it is decomposed here, and a paragraph left empty by
        # that is dropped.
        soup = self.make_soup(body)
        for meta in soup.select("metadesc"):
            para = meta.find_parent("p")
            meta.decompose()
            if para is not None and not para.get_text(strip=True):
                para.decompose()
        return "".join(str(p) for p in soup.find_all("p"))

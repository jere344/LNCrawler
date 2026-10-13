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

_BASE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "multi", "wikisource.py"
)
_spec = importlib.util.spec_from_file_location("lncrawl_wikisource_base", _BASE_PATH)
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)


class GadyaKoshCrawler(_base.WikisourceCrawler):
    base_url = ["https://www.gadyakosh.org/gk/"]
    language = "hi"

    api_path = "api.php"
    article_path = ""

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

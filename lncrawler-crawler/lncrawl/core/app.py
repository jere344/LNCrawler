"""Top-level orchestrator for search + download.

JSON-only: prepare search, fetch novel info, select chapters, download chapter
bodies/images and write meta.json.
"""

import logging
import os
from typing import List
from urllib.parse import urlparse

from slugify import slugify

from ..constants import DEFAULT_OUTPUT_PATH
from ..models import Chapter
from ..utils.novelupdates import find_novelupdates_url
from .crawler import Crawler
from .downloader import fetch_chapter_body, fetch_chapter_images
from .novel_info import format_novel, save_metadata
from .search import run_search
from .sources import get_search_crawlers, prepare_crawler

logger = logging.getLogger(__name__)


def _safe_folder_name(slug: str, limit: int = 180) -> str:
    """Bound a slug so long titles cannot exceed filesystem name limits."""
    if len(slug) <= limit:
        return slug
    cut = slug[:limit].rsplit("-", 1)[0].strip("-")
    return cut or slug[:limit]


class App:
    def __init__(self) -> None:
        self.initialize()

    def initialize(self) -> None:
        self.progress = 0
        self.user_input = ""
        self.crawler = None
        self.crawler_links: List = []
        self.search_results: List[dict] = []
        self.output_path = ""
        self.pack_by_volume = False
        self.chapters: List[Chapter] = []
        self.output_formats: dict = {}
        self.good_file_name = ""

    def destroy(self) -> None:
        if self.crawler is not None:
            try:
                self.crawler.close()
            except Exception:
                pass
            self.crawler = None

    # -- search -------------------------------------------------------- #

    def prepare_search(self) -> None:
        user_input = str(self.user_input or "").strip()
        if user_input.startswith("http"):
            self.crawler = prepare_crawler(user_input)
            return
        self.crawler_links = get_search_crawlers()

    def search_novel(self) -> None:
        def on_progress(current: int, total: int) -> None:
            self.progress = current

        self.search_results = run_search(self.user_input, on_progress=on_progress)

    # -- novel info ---------------------------------------------------- #

    def get_novel_info(self) -> None:
        assert self.crawler is not None, "No crawler selected"

        self.crawler.read_novel_info()
        format_novel(self.crawler)

        # Best-effort NovelUpdates link, once per novel, only when the source
        # did not already provide one. Never let a lookup break the download.
        if not getattr(self.crawler, "novelupdates_url", None):
            try:
                self.crawler.novelupdates_url = find_novelupdates_url(
                    self.crawler.novel_title
                )
            except Exception:
                pass

        self.chapters = self.crawler.chapters[:]
        self.good_file_name = _safe_folder_name(slugify(self.crawler.novel_title or "unknown"))

        if not self.output_path:
            host = urlparse(self.crawler.novel_url).netloc or "unknown"
            self.output_path = os.path.join(
                DEFAULT_OUTPUT_PATH, slugify(host), self.good_file_name
            )

    # -- download ------------------------------------------------------ #

    def start_download(self) -> None:
        assert self.crawler is not None, "No crawler selected"

        save_metadata(self)
        fetch_chapter_body(self)
        save_metadata(self)
        fetch_chapter_images(self)
        save_metadata(self, completed=True)

        try:
            self.crawler.logout()
        except Exception:
            pass

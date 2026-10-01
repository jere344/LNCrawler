import logging

from lncrawl.templates.mangastream import MangaStreamTemplate

logger = logging.getLogger(__name__)


class Kolnovel(MangaStreamTemplate):
    has_mtl = False
    has_manga = False
    base_url = ["https://kolnovel.com/"]

    def select_chapter_tags(self, tag):
        # kolnovel lists a `/pdf` download link next to every real chapter in
        # `.eplister`; those stubs have no body, so skip them.
        for a in super().select_chapter_tags(tag):
            if not a.get("href", "").rstrip("/").endswith("/pdf"):
                yield a

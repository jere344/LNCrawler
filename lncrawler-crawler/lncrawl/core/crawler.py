import hashlib
import logging
import os
import re
from typing import Generator, List, Optional, Union

from bs4 import Tag

from ..models import Chapter, SearchResult, Volume
from .arguments import get_args
from .cleaner import TextCleaner
from .exeptions import RetryErrorGroup
from .scraper import Scraper

logger = logging.getLogger(__name__)


class Crawler(Scraper):
    """Blueprint for creating new crawlers."""

    base_url: Union[str, List[str]]
    # Canonical source identity. Defaults (in sources._register) to the host of
    # the first base_url, so mirror domains handled by the same crawler collapse
    # into a single source. Override explicitly for less obvious cases.
    source_name: str = ""
    has_manga = False
    has_mtl = False
    # Set True on sources whose content is adult (R18/NSFW). Written to
    # meta.json and loaded by the DB importer.
    is_adult = False
    language = ""

    # Set True on sources that must authenticate before crawling. When set,
    # prepare_crawler() logs in automatically using get_credentials().
    login_required = False

    is_disabled = False
    disable_reason: Optional[str] = None

    def __init__(
        self,
        workers: Optional[int] = None,
        parser: Optional[str] = None,
    ) -> None:
        self.cleaner = TextCleaner()

        self.novel_url = ""
        self.novel_title: str = ""
        self.novel_author: str = ""
        self.novel_cover: Optional[str] = None
        self.is_rtl: bool = False
        self.novel_synopsis: str = ""
        self.novel_tags: List[str] = []
        # Alternative/alternate titles exposed by some sources. Written to
        # meta.json; not yet consumed by the DB importer.
        self.alternative_titles: List[str] = []
        self.volumes: List[Volume] = []
        self.chapters: List[Chapter] = []

        # Progress reported while building the table of contents, before the
        # chapter list is known (e.g. fetching EPUB volumes). The API monitor
        # reads these until chapters exist, then switches to app.progress.
        self.progress = 0
        self.progress_total = 0
        self.progress_unit = "chapters"

        # Previous chapter list and metadata for this novel, injected by the
        # caller (the API loads them from the DB). Sources whose table of
        # contents is expensive to rebuild (e.g. EPUB volumes) can reuse them
        # instead of re-fetching every archive on update.
        self.existing_chapters: list = []
        self.existing_meta: dict = {}

        base_url = self.base_url
        origin = base_url[0] if isinstance(base_url, (list, tuple)) else base_url
        super().__init__(origin=origin, workers=workers, parser=parser)

    # -- methods for sources to implement ------------------------------ #

    def initialize(self) -> None:
        pass

    def get_credentials(self) -> "tuple[str, str]":
        """Username/password for login-gated sources, read from the environment.

        Default variable names are ``LNCRAWL_<KEY>_USERNAME`` / ``LNCRAWL_<KEY>_PASSWORD``
        where ``<KEY>`` is the first label of the source's canonical name, uppercased
        (e.g. ``cyrisia.com`` -> ``LNCRAWL_CYRISIA_USERNAME``). Sources that need
        different names can override this method.
        """
        host = self.source_name or ""
        if host.startswith("www."):
            host = host[4:]
        key = re.sub(r"[^A-Za-z0-9]+", "_", host.split(".")[0]).upper()
        return (
            os.getenv(f"LNCRAWL_{key}_USERNAME", ""),
            os.getenv(f"LNCRAWL_{key}_PASSWORD", ""),
        )

    def login(self, email: str, password: str) -> None:
        pass

    def logout(self) -> None:
        pass

    def search_novel(self, query: str) -> List[SearchResult]:
        """Gets a list of results matching the given query."""
        raise NotImplementedError()

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        """Return up to ``limit`` novels starting at ``offset``.

        Results are in the source's own default order (usually popularity or
        ranking) taken from its browse/all-novels/ranking section. Sources
        without such a section leave this unimplemented and are skipped by the
        harvest tooling. Follow pagination internally until ``offset + limit``
        items are collected or the source runs out.
        """
        raise NotImplementedError()

    def read_novel_info(self) -> None:
        """Get novel title, author, cover, volumes and chapters."""
        raise NotImplementedError()

    def download_chapter_body(self, chapter: Chapter) -> str:
        """Download body of a single chapter and return clean html."""
        raise NotImplementedError()

    # -- utility ------------------------------------------------------- #

    def index_of_chapter(self, url: str) -> int:
        url = self.absolute_url(url)
        for chapter in self.chapters:
            if chapter.url.rstrip("/") == url:
                return chapter.id
        return 0

    def extract_chapter_images(self, chapter: Chapter) -> None:
        if get_args().ignore_images:
            return
        # Most chapters have no inline image; skip the extra parse.
        if not chapter.body or "<img" not in chapter.body:
            return

        has_changes = False
        chapter.setdefault("images", {})
        soup = self.make_soup(chapter.body)
        for img in soup.select("img[src]"):
            src_url = img.get("src")
            assert isinstance(src_url, str)
            full_url = self.absolute_url(src_url, page_url=chapter["url"])
            if not full_url.startswith("http"):
                continue
            filename = hashlib.md5(full_url.encode()).hexdigest() + ".jpg"
            img.attrs = {"src": "images/" + filename, "alt": filename}
            chapter.images[filename] = full_url
            has_changes = True

        if has_changes:
            body = soup.find("body")
            assert isinstance(body, Tag)
            chapter.body = body.decode_contents()

    def download_chapters(
        self,
        chapters: List[Chapter],
        fail_fast: bool = False,
    ) -> Generator[Chapter, None, None]:
        from collections import deque

        chapters = list(chapters)
        # Bounded sliding window: never hold more than `window` chapter bodies
        # in memory. The previous all-futures-upfront version could pin
        # 3000 x 100-500KB (~0.3-1.5GB) when an early chapter was slow.
        window = max(self.workers, 1) * 2
        queue = deque()
        next_index = 0

        def submit(index: int) -> None:
            chapter = chapters[index]
            queue.append((chapter, self.executor.submit(self.download_chapter_body, chapter)))

        while next_index < len(chapters) and len(queue) < window:
            submit(next_index)
            next_index += 1

        try:
            while queue:
                chapter, future = queue.popleft()
                try:
                    result = future.result()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    if fail_fast:
                        raise
                    if isinstance(e, RetryErrorGroup):
                        # Expected per-chapter network/IO failure. Tolerated
                        # (chapter marked failed, download continues), so it is
                        # noise for the issue reporter.
                        logger.warning("%s: %s", type(e).__name__, e)
                    else:
                        # Anything else is an unexpected parser/logic bug, so
                        # report it. Dedup per source+type so one report covers
                        # all chapters of a source.
                        logger.error(
                            "%s: %s",
                            type(e).__name__,
                            e,
                            exc_info=True,
                            extra={
                                "github_fingerprint": hashlib.sha1(
                                    f"{self.source_name}:{type(e).__name__}".encode()
                                ).hexdigest()[:12]
                            },
                        )
                    result = None

                chapter.body = result or ""
                chapter.images = {}
                if result:
                    self.extract_chapter_images(chapter)
                chapter.success = bool(result)
                yield chapter

                if next_index < len(chapters):
                    submit(next_index)
                    next_index += 1
        finally:
            self.cancel_futures([future for _, future in queue])

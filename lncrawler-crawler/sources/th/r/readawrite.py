# -*- coding: utf-8 -*-
"""readAWrite (readawrite.com) - Thai novel platform (MEB / Ookbee).

Metadata and the table of contents are plain server-rendered/embedded data, but
the chapter text itself is DRM-protected: the reader downloads an encrypted
``.raw`` blob and then renders it through a per-novel font substitution that
replaces every character with a Private Use Area codepoint.  The visible glyphs
are correct only when the site's custom webfont is loaded; the underlying text
is not recoverable without defeating that protection.  Kept disabled.
"""

import json
import logging
import re
from html import unescape

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter

logger = logging.getLogger(__name__)


class ReadAWriteCrawler(Crawler):
    base_url = "https://readawrite.com/"
    language = "th"

    is_disabled = True
    disable_reason = (
        "Chapter text is an encrypted .raw payload rendered through a per-novel "
        "font substitution (PUA codepoints); DRM, not crawler-readable."
    )

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        tag = soup.select_one('meta[property="og:title"]')
        if tag and tag.get("content"):
            self.novel_title = re.split(r"\s*:", tag["content"])[0].strip()

        tag = soup.select_one('meta[property="og:description"]')
        if tag and tag.get("content"):
            self.novel_synopsis = tag["content"].strip()

        tag = soup.select_one('meta[property="og:image"]')
        if tag and tag.get("content"):
            self.novel_cover = self.absolute_url(tag["content"])

        tag = soup.select_one("#chapter_list")
        raw = None
        if tag and tag.string:
            raw = tag.string
        if raw is None:
            match = re.search(r"var chapter_list = '(.*?)';", str(soup), re.S)
            raw = match.group(1) if match else ""
        try:
            items = json.loads(json.loads('"' + raw + '"'))
        except Exception:
            items = []

        for item in items:
            guid = item.get("chapter_guid")
            if not guid:
                continue
            title = " ".join(
                filter(
                    None,
                    [
                        unescape(item.get("chapter_title") or "").strip(),
                        unescape(item.get("chapter_subtitle") or "").strip(),
                    ],
                )
            )
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title or f"Chapter {item.get('chapter_order')}",
                    url=self.absolute_url(f"/c/{guid}"),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        raise LNException(
            "readAWrite chapter bodies are DRM-protected (encrypted .raw + "
            "font substitution); they cannot be downloaded."
        )

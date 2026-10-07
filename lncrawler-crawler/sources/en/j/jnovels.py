# -*- coding: utf-8 -*-
"""jnovels.com — official/fan light-novel EPUB packs (WordPress).

The book pages are reachable (WordPress behind Cloudflare, no challenge) and
expose title/cover/synopsis, but every volume's ``Download`` link points at an
external shortener (``charexempire.com`` / ``enagato.com`` / ``zshort.net``).
That shortener fronts the file with a Cloudflare Turnstile gate: it 307s to a
landing page whose only way forward is a POST carrying a solved
``cf-turnstile-response``.  The token is never issued to a non-interactive
client, so the EPUB URL cannot be resolved and the source is disabled.
"""

import logging

from bs4 import Tag

from lncrawl.core.exeptions import LNException
from lncrawl.templates.epub import EpubCrawler

logger = logging.getLogger(__name__)


class JNovelsCrawler(EpubCrawler):
    base_url = [
        "https://jnovels.com/",
        "https://www.jnovels.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Every volume download link goes through an external shortener "
        "(charexempire.com / enagato.com / zshort.net) gated by a Cloudflare "
        "Turnstile challenge; the EPUB URL is never issued to a "
        "non-interactive client."
    )

    def _parse_meta(self, soup) -> None:
        title = soup.select_one('meta[property="og:title"]')
        if isinstance(title, Tag) and title.get("content"):
            self.novel_title = title["content"].strip()
        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = self.absolute_url(cover["content"])
        desc = soup.select_one('meta[property="og:description"]')
        if isinstance(desc, Tag) and desc.get("content"):
            self.novel_synopsis = desc["content"].strip()

    def read_novel_info(self) -> None:
        self._parse_meta(self.get_soup(self.novel_url))
        raise LNException(self.disable_reason)

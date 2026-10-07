# -*- coding: utf-8 -*-
"""NextNovels (es) — download-only aggregator, disabled.

Every novel page is a Divi/WordPress article whose only download button points
at a 1024teraBox share link (verified across multiple titles). The actual
EPUB/PDF therefore lives behind TeraBox's login/JS-gated interface, not on a
direct URL this crawler could hand to :class:`EpubCrawler`, and there is no
on-site chapter reader to scrape. Many of the hosted editions are also
explicitly MTL, which this project does not index. Registered but hidden.
"""

from lncrawl.core.crawler import Crawler


class NextNovelsCrawler(Crawler):
    base_url = [
        "https://nextnovels.com/",
        "https://www.nextnovels.com/",
    ]
    language = "es"

    is_disabled = True
    disable_reason = (
        "Download-only aggregator: files are TeraBox share links (JS/login "
        "gated, often MTL); no readable chapters or direct EPUB/PDF URLs."
    )

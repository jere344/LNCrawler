# -*- coding: utf-8 -*-
"""WebNovelPub (webnovelpub.com). Disabled: Bot-protected: redirects to a JS challenge page (?ch=1&js=...)."""

from lncrawl.core.crawler import Crawler


class WebnovelPubCrawler(Crawler):
    base_url = [
        "https://webnovelpub.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Home and novel pages are a ~480-byte JS loading shell (no challenge redirect any more); the data API was not located. Retested through the crawler scraper 2026-10"
    )

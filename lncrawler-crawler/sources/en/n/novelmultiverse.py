# -*- coding: utf-8 -*-
"""NovelMultiverse (novelmultiverse.com). Disabled: JS 'Loading...' shell with no discoverable endpoints."""

from lncrawl.core.crawler import Crawler


class NovelMultiverseCrawler(Crawler):
    base_url = [
        "https://novelmultiverse.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "JS 'Loading...' shell with no discoverable endpoints"
    )

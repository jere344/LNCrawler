# -*- coding: utf-8 -*-
"""NovelUpdates (novelupdates.com) - series directory, not a chapter host. Disabled: Directory/aggregator, not a content host (HTTP 403 to plain HTTP)."""

from lncrawl.core.crawler import Crawler


class NovelUpdatesCrawler(Crawler):
    base_url = [
        "https://novelupdates.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Directory/aggregator, not a content host (HTTP 403 to plain HTTP)"
    )

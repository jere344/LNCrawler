# -*- coding: utf-8 -*-
"""Novelcat (novelcat.net). Disabled."""
from lncrawl.core.crawler import Crawler


class NovelcatCrawler(Crawler):
    base_url = ["https://novelcat.net/"]
    language = "th"
    is_disabled = True
    disable_reason = (
        "novelcat.net returns Cloudflare 403 to curl (browser not tested); "
        "novelcat.com is a placeholder page, so it is dead"
    )

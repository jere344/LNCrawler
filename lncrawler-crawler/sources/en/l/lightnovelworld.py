# -*- coding: utf-8 -*-
"""LightNovelWorld (lightnovelworld.com). Disabled: Cloudflare challenge (HTTP 403 'Just a moment')."""

from lncrawl.core.crawler import Crawler


class LightNovelWorldCrawler(Crawler):
    base_url = [
        "https://lightnovelworld.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Cloudflare challenge (HTTP 403 'Just a moment'); not reachable with plain HTTP"
    )

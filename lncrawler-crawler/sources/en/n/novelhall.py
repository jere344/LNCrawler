# -*- coding: utf-8 -*-
"""NovelHall (novelhall.com). Disabled: Cloudflare challenge (HTTP 403 'Just a moment')."""

from lncrawl.core.crawler import Crawler


class NovelHallCrawler(Crawler):
    base_url = [
        "https://novelhall.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Cloudflare challenge (HTTP 403 'Just a moment'); not reachable with plain HTTP"
    )

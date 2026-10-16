# -*- coding: utf-8 -*-
"""SkyDemonOrder (skydemonorder.com). Disabled: Cloudflare challenge (HTTP 403 'Just a moment')."""

from lncrawl.core.crawler import Crawler


class SkyDemonOrderCrawler(Crawler):
    base_url = [
        "https://skydemonorder.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Cloudflare challenge (HTTP 403 'Just a moment'); not reachable with plain HTTP"
    )

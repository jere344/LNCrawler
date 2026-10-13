# -*- coding: utf-8 -*-
"""Readwn (readwn.com). Disabled: Cloudflare challenge (HTTP 403 'Just a moment')."""

from lncrawl.core.crawler import Crawler


class ReadwnCrawler(Crawler):
    base_url = [
        "https://readwn.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Cloudflare challenge (HTTP 403 'Just a moment'); not reachable with plain HTTP"
    )

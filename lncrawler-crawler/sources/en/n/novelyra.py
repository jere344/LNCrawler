# -*- coding: utf-8 -*-
"""NovelYra (novelyra.com). Disabled: Cloudflare challenge (HTTP 403 'Just a moment')."""

from lncrawl.core.crawler import Crawler


class NovelYraCrawler(Crawler):
    base_url = [
        "https://novelyra.com/",
    ]
    language = "en"

    is_disabled = True
    disable_reason = (
        "Cloudflare challenge (HTTP 403 'Just a moment'); not reachable with plain HTTP; also blocked in headless chromium 25s"
    )

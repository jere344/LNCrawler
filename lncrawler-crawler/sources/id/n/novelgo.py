# -*- coding: utf-8 -*-
"""NovelGoId - disabled source.

Disabled: Cloudflare 'Just a moment...' 403 on the root and HTTP probe.
"""

from lncrawl.core.crawler import Crawler


class NovelGoIdCrawler(Crawler):
    base_url = "https://novelgo.id/"
    language = "id"
    has_mtl = False

    is_disabled = True
    disable_reason = "Cloudflare 'Just a moment...' 403 on the root and HTTP probe; also blocked in headless chromium 25s"

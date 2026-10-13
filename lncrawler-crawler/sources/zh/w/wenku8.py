# -*- coding: utf-8 -*-
"""wenku8.net - Chinese light novel library.

Disabled: the site answers HTTP 403 to non-browser requests (anti-bot
protection), so no catalog or chapter can be fetched without bypassing it.
"""

from lncrawl.core.crawler import Crawler


class Wenku8Crawler(Crawler):
    base_url = "https://www.wenku8.net"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Blocked (403) to non-browser requests; anti-bot protection, not workable without bypassing it."

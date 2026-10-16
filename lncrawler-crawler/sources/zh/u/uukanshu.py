# -*- coding: utf-8 -*-
"""uukanshu.com - Chinese web novel library.

Disabled: the host does not respond (connection timeout).
"""

from lncrawl.core.crawler import Crawler


class UukanshuCrawler(Crawler):
    base_url = "https://www.uukanshu.com"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Unreachable (no response from host)."

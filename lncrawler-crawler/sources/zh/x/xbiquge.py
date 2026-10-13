# -*- coding: utf-8 -*-
"""xbiquge.so - Chinese web novel library.

Disabled: the site answers HTTP 403 (anti-bot protection).
"""

from lncrawl.core.crawler import Crawler


class XbiqugeCrawler(Crawler):
    base_url = "https://www.xbiquge.so"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Blocked (403) by anti-bot protection; not workable."

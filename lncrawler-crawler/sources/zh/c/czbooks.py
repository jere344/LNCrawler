# -*- coding: utf-8 -*-
"""czbooks.net - Chinese web novel library.

Disabled: the site answers HTTP 403 (anti-bot protection).
"""

from lncrawl.core.crawler import Crawler


class CzbooksCrawler(Crawler):
    base_url = "https://czbooks.net"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Blocked (403) by anti-bot protection; not workable without bypassing it."

# -*- coding: utf-8 -*-
"""101kanshu.com - Chinese web novel library.

Disabled: the site answers HTTP 403 (anti-bot protection).
"""

from lncrawl.core.crawler import Crawler


class Kanshu101Crawler(Crawler):
    base_url = "https://www.101kanshu.com"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Blocked (403) by anti-bot protection; not workable without bypassing it."

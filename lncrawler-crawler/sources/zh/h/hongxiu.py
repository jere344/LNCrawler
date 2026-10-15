# -*- coding: utf-8 -*-
"""hongxiu.com - Yuewen-group web novel platform.

Disabled: the site is alive and serves Chinese text, but chapter access
is gated by login and VIP unlock flags. Free chapter coverage is too
limited to justify a source, and the reader is not reviewed further here.
"""

from lncrawl.core.crawler import Crawler


class HongxiuCrawler(Crawler):
    base_url = "https://www.hongxiu.com/"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Login and VIP-gated chapters; free chapter coverage insufficient. Not implemented."

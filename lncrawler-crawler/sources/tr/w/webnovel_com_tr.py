# -*- coding: utf-8 -*-
"""webnovel.com.tr — Turkish novel site.

Returns a 114-byte body with HTTP 200; nothing verified. Disabled.
"""

from lncrawl.core.crawler import Crawler


class WebnovelTrCrawler(Crawler):
    base_url = "https://webnovel.com.tr/"
    language = "tr"
    has_mtl = False

    is_disabled = True
    disable_reason = "Returns an empty 114-byte body; no content verified"

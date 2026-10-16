# -*- coding: utf-8 -*-
"""yousuu.com - book review and rating site.

Disabled: the host does not respond, and it is a review site rather than a
content host.
"""

from lncrawl.core.crawler import Crawler


class YousuuCrawler(Crawler):
    base_url = "https://www.yousuu.com"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Unreachable and not a content host (review site)."

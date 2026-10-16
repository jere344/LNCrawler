# -*- coding: utf-8 -*-
"""VyNovel - disabled source.

Disabled: Unreachable from the research host (DNS/connection failure, HTTP 000).
"""

from lncrawl.core.crawler import Crawler


class VyNovelCrawler(Crawler):
    base_url = "https://vynovel.com/"
    language = "id"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable from the research host (DNS/connection failure, HTTP 000)'

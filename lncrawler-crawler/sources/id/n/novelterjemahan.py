# -*- coding: utf-8 -*-
"""NovelTerjemahan - disabled source.

Disabled: Unreachable from the research host (DNS/connection failure, HTTP 000).
"""

from lncrawl.core.crawler import Crawler


class NovelTerjemahanCrawler(Crawler):
    base_url = "https://novelterjemahan.com/"
    language = "id"
    has_mtl = False

    is_disabled = True
    disable_reason = 'Unreachable from the research host (DNS/connection failure, HTTP 000)'
